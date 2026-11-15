"""Run the real shell entrypoint with a socket stub, never a browser or Docker."""
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_entrypoint(tmp_path, args=(), mode="ready", bridge_exit="0"):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    launcher = tmp_path / "launcher"
    launcher.write_text(f'''#!{sys.executable}
import json, os, socket, sys, time
from pathlib import Path
Path(os.environ["RECORD"]).write_text(json.dumps(sys.argv[1:]))
if os.environ["MODE"] == "exit": sys.exit(7)
if os.environ["MODE"] == "ready":
    s = socket.socket()
    s.bind(("127.0.0.1", {port}))
    s.listen()
time.sleep(30)
''')
    launcher.chmod(0o755)
    bridge = tmp_path / "socat"
    bridge.write_text('#!/bin/sh\necho bridge-started\nexit "${BRIDGE_EXIT:-0}"\n')
    bridge.chmod(0o755)
    script = tmp_path / "entrypoint.sh"
    script.write_text((ROOT / "packaging/docker-entrypoint.sh").read_text()
                      .replace("/opt/tilion/tilion", shlex.quote(str(launcher)))
                      .replace("INTERNAL=9223", f"INTERNAL={port}")
                      .replace("seq 1 80", "seq 1 15")
                      .replace("sleep 0.5", "sleep 0.05"))
    record = tmp_path / "args.json"
    env = dict(os.environ, PATH=f"{tmp_path}:{os.environ['PATH']}",
               RECORD=str(record), MODE=mode, BRIDGE_EXIT=bridge_exit)
    result = subprocess.run(["bash", str(script), *args], env=env,
                            capture_output=True, text=True, timeout=5)
    return result, json.loads(record.read_text()), port


@pytest.mark.parametrize("args", [
    ["--remote-debugging-port=9222", "https://example.com"],
    ["--remote-debugging-port", "9222", "https://example.com"],
    ["--remote-debugging-port=0", "--remote-debugging-port", "9222", "https://example.com"],
    ["--remote-debugging-port", "--uxr-timezone=Asia/Jakarta", "https://example.com"],
    [],
])
def test_bridge_port_cannot_be_overridden(tmp_path, args):
    result, actual, port = run_entrypoint(tmp_path, args)
    assert result.returncode == 0, result.stderr
    assert [arg for arg in actual if arg.startswith("--remote-debugging-port")] == [
        f"--remote-debugging-port={port}"]
    assert "9222" not in actual
    if "https://example.com" in args:
        assert actual[-1] == "https://example.com"
    if "--uxr-timezone=Asia/Jakarta" in args:
        assert "--uxr-timezone=Asia/Jakarta" in actual
    assert "bridge-started" in result.stdout


def test_failed_browser_does_not_start_bridge(tmp_path):
    result, _, _ = run_entrypoint(tmp_path, mode="exit")
    assert result.returncode == 7
    assert "browser exited before CDP became ready" in result.stderr
    assert "bridge-started" not in result.stdout


def test_unready_browser_fails_with_diagnostic(tmp_path):
    result, _, _ = run_entrypoint(tmp_path, mode="unready")
    assert result.returncode == 1
    assert "timed out waiting for browser CDP" in result.stderr
    assert "bridge-started" not in result.stdout


def test_bridge_failure_preserves_exit_status(tmp_path):
    result, _, _ = run_entrypoint(tmp_path, bridge_exit="9")
    assert result.returncode == 9
    assert "browser or CDP bridge exited with status 9" in result.stderr
