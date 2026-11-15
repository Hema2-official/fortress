#!/usr/bin/env python3
"""Verify pinned source bytes and apply the public patch series in an isolated tree."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def verify(repo: Path, source: Path | None = None) -> int:
    manifest = json.loads((repo / "build/chromium-source.json").read_text())
    if (repo / "CHROMIUM_VERSION").read_text().strip() != manifest["version"]:
        raise ValueError("CHROMIUM_VERSION disagrees with pinned source manifest")
    revision = manifest["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("source revision must be an immutable Git SHA")
    patches = []
    originals = set()
    for entry in (repo / "patches/series").read_text().splitlines():
        entry = entry.strip()
        if not entry:
            continue
        path = PurePosixPath(entry)
        if path.is_absolute() or ".." in path.parts or not entry.startswith("patches/"):
            raise ValueError(f"unsafe patch path: {entry}")
        patch = repo / entry
        patches.append(patch)
        originals.update(re.findall(r"^--- a/(.+)$", patch.read_text(), re.MULTILINE))
    if originals != set(manifest["source_files"]):
        raise ValueError("source manifest must cover exactly the existing files touched by patches")
    with tempfile.TemporaryDirectory(prefix="fortress-source-check-") as directory:
        work = Path(directory)
        for name, digest in manifest["source_files"].items():
            path = PurePosixPath(name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"unsafe source path: {name}")
            if source is None:
                content = subprocess.check_output([
                    "gh", "api", f"repos/chromium/chromium/contents/{name}?ref={revision}",
                    "-H", "Accept: application/vnd.github.raw+json",
                ])
            else:
                content = (source / name).read_bytes()
            if hashlib.sha256(content).hexdigest() != digest:
                raise ValueError(f"source hash mismatch: {name}")
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            print(f"Verified source: {name}", flush=True)
        subprocess.run(["git", "init", "-q", str(work)], check=True)
        for patch in patches:
            subprocess.run(["git", "apply", "--check", "--recount", str(patch)],
                           cwd=work, check=True)
            subprocess.run(["git", "apply", "--recount", str(patch)], cwd=work, check=True)
            print(f"PASS {patch.name}")
    print(f"Verified {len(patches)} public patches against Chromium {manifest['version']} ({revision})")
    print("This checks source compatibility, not compilation or runtime behavior.")
    return len(patches)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, help="pristine local Chromium source; otherwise fetch via gh")
    args = parser.parse_args()
    verify(ROOT, args.source)


if __name__ == "__main__":
    main()
