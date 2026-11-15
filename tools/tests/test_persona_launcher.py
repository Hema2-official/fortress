"""Verify portable launcher behavior using a fake executable, never a browser."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def launcher(tmp_path):
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    for name in ("tilion", "persona.sh"):
        shutil.copyfile(ROOT / "packaging" / name, bundle / name)
    (bundle / "fonts").mkdir()
    (bundle / "fonts/fonts.conf.template").write_text("@FONTDIR@ @CACHEDIR@")
    (bundle / "chrome").write_text(
        f"#!{sys.executable}\nimport json,os,sys\n"
        "print(json.dumps({'args':sys.argv[1:],'tz':os.environ.get('TZ')}))\n")
    (bundle / "chrome").chmod(0o755)

    def run(args=(), **extra_env):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("TILION_") and k not in ("XDG_CACHE_HOME", "TZ")}
        env.update(HOME=str(tmp_path), **extra_env)
        return subprocess.run(["bash", str(bundle / "tilion"), *args],
                              env=env, capture_output=True, text=True, timeout=10)
    return run


def flags(result):
    assert result.returncode == 0, result.stderr
    output = json.loads(result.stdout)
    values = {}
    for arg in output["args"]:
        if arg.startswith("--"):
            key, _, value = arg.partition("=")
            values[key] = value
    return output, values


def test_structural_seed_is_repeatable_but_rendering_noise_is_fresh(launcher):
    _, first = flags(launcher(["--uxr-seed=42"]))
    _, second = flags(launcher(["--uxr-seed", "42"]))
    for key in ("--uxr-canvas-seed", "--uxr-audio-seed"):
        assert 0 < int(first.pop(key)) <= 2**32 - 1
        assert 0 < int(second.pop(key)) <= 2**32 - 1
    assert first == second
    _, third = flags(launcher(["--uxr-seed=42"]))
    _, fourth = flags(launcher(["--uxr-seed=42"]))
    assert third["--uxr-canvas-seed"] != fourth["--uxr-canvas-seed"]
    assert third["--uxr-audio-seed"] != fourth["--uxr-audio-seed"]


def test_country_drives_language_and_first_tick_timezone(launcher):
    output, values = flags(launcher(["--uxr-country=ID"]))
    assert output["tz"] == values["--uxr-timezone"] == "Asia/Jakarta"
    assert values["--uxr-languages"] == values["--accept-lang"] == "id-ID,id,en"


def test_explicit_timezone_and_hardware_override_generated_defaults(launcher):
    output, values = flags(launcher(
        ["--uxr-country=JP", "--uxr-timezone", "Asia/Tokyo", "--uxr-hw-concurrency=12"],
        TILION_TZ="Europe/Berlin"))
    assert output["tz"] == values["--uxr-timezone"] == "Asia/Tokyo"
    assert values["--uxr-hw-concurrency"] == "12"


def test_unsafe_split_user_agent_does_not_consume_the_url(launcher):
    output, values = flags(launcher(
        ["--user-agent", "bad-agent", "--enable-automation", "https://example.com"]))
    assert "bad-agent" not in output["args"]
    assert "--user-agent" not in values
    assert "--enable-automation" not in values
    assert output["args"][-1] == "https://example.com"
    assert "ignoring" in launcher(["--user-agent=bad"]).stderr


def test_bare_launch_has_no_automatic_identity_or_noise(launcher):
    _, values = flags(launcher(TILION_NO_DEFAULTS="1"))
    assert not any(key.startswith("--uxr-") for key in values)


def test_environment_seed_matches_command_line_seed(launcher):
    _, a = flags(launcher(TILION_SEED="123", TILION_COUNTRY="DE"))
    _, b = flags(launcher(["--uxr-seed=123", "--uxr-country=DE"]))
    for key in ("--uxr-hw-concurrency", "--uxr-screen-width", "--uxr-screen-height"):
        assert a[key] == b[key]
    assert a["--uxr-languages"] == "de-DE,de,en"


def test_language_header_mismatch_is_rejected(launcher):
    result = launcher(["--uxr-languages=de-DE,de", "--accept-lang=en-US,en"])
    assert result.returncode == 2
    assert "must agree" in result.stderr


def test_unknown_country_requires_explicit_locale(launcher):
    assert launcher(["--uxr-country=ZZ"]).returncode == 2
    output, values = flags(launcher(
        ["--uxr-country=ZZ", "--uxr-timezone=UTC", "--uxr-languages=en-US,en"]))
    assert output["tz"] == "UTC"
    assert values["--uxr-languages"] == "en-US,en"


def test_explicit_render_seeds_cannot_link_default_launches(launcher):
    result = launcher(["--uxr-canvas-seed=0", "--uxr-audio-seed=0"])
    _, values = flags(result)
    assert int(values["--uxr-canvas-seed"]) > 0
    assert int(values["--uxr-audio-seed"]) > 0
    assert "fresh per launch" in result.stderr
