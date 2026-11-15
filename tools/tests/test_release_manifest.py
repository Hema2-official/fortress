"""Validate archive identity and malicious member paths without extraction."""
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
import zipfile

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import release_manifest as rm


ENGINE = b"test engine bytes, not a browser"


@pytest.fixture
def release_record(tmp_path):
    archive = tmp_path / "tilion-fortress-linux-x64.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        item = tarfile.TarInfo("tilion-fortress/chrome")
        item.size = len(ENGINE)
        tar.addfile(item, io.BytesIO(ENGINE))
    value = hashlib.sha256(archive.read_bytes()).hexdigest()
    manifest = {
        "tag": "fural-public-156.0.8078.47", "chromium_version": "156.0.8078.47",
        "source_revision": "a" * 40, "repository_revision": "b" * 40,
        "required_platforms": ["linux-x64"],
        "assets": [{"platform": "linux-x64", "name": archive.name,
                    "bytes": archive.stat().st_size, "sha256": value,
                    "engine_file": "tilion-fortress/chrome",
                    "engine_sha256": hashlib.sha256(ENGINE).hexdigest()}],
    }
    return manifest, f"{value}  {archive.name}\n", archive


def test_manifest_checks_actual_archive_and_engine(release_record):
    manifest, sums, archive = release_record
    assert rm.evaluate_manifest(manifest, sums, archive.parent) == []
    assert not (archive.parent / "tilion-fortress").exists()


def test_archive_corruption_is_rejected(release_record):
    manifest, sums, archive = release_record
    archive.write_bytes(archive.read_bytes() + b"corruption")
    assert any("archive bytes mismatch" in e for e in rm.evaluate_manifest(manifest, sums, archive.parent))


def test_wrong_native_engine_hash_is_rejected(release_record):
    manifest, sums, archive = release_record
    manifest["assets"][0]["engine_sha256"] = "0" * 64
    assert any("engine bytes mismatch" in e for e in rm.evaluate_manifest(manifest, sums, archive.parent))


def test_checksum_and_platform_duplicates_are_rejected(release_record):
    manifest, sums, _ = release_record
    manifest["assets"] *= 2
    errors = rm.evaluate_manifest(manifest, sums + sums)
    assert any("duplicate checksum" in e for e in errors)
    assert "duplicate or empty artifact identity" in errors


def test_required_platform_cannot_be_silently_skipped(release_record):
    manifest, sums, _ = release_record
    manifest["required_platforms"].append("linux-arm64")
    assert "required platforms missing" in rm.evaluate_manifest(manifest, sums)


@pytest.mark.parametrize("member", ["../outside", "/tmp/outside", "C:/outside", "bundle/../../outside", "bundle/license.jwt"])
def test_unsafe_or_credential_tar_members_rejected(tmp_path, member):
    path = tmp_path / "test.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo(member)
        item.size = 1
        archive.addfile(item, io.BytesIO(b"x"))
    _, errors = rm.inspect_archive(path, "bundle/chrome")
    assert errors


@pytest.mark.parametrize("kind", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_escaping_tar_links_rejected(tmp_path, kind):
    path = tmp_path / "test.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo("bundle/link")
        item.type = kind
        item.linkname = "../../outside"
        archive.addfile(item)
    _, errors = rm.inspect_archive(path, "bundle/chrome")
    assert any("unsafe link" in e for e in errors)


def test_safe_relative_library_symlink_is_allowed(tmp_path):
    path = tmp_path / "test.tar.gz"
    with tarfile.open(path, "w:gz") as archive:
        item = tarfile.TarInfo("bundle/libfoo.so")
        item.type = tarfile.SYMTYPE
        item.linkname = "libfoo.so.1"
        archive.addfile(item)
    _, errors = rm.inspect_archive(path, "bundle/chrome")
    assert errors == []


def test_zip_case_collisions_rejected(tmp_path):
    path = tmp_path / "test.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("bundle/Chrome.exe", ENGINE)
        archive.writestr("bundle/chrome.exe", ENGINE)
    _, errors = rm.inspect_archive(path, "bundle/Chrome.exe")
    assert any("duplicate member" in e for e in errors)


def test_offline_verifier_cli_checks_manifest(release_record, tmp_path):
    import subprocess
    manifest, sums, archive = release_record
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(manifest))
    (tmp_path / "SHA256SUMS").write_text(sums)
    result = subprocess.run([
        sys.executable, str(Path(__file__).resolve().parents[1] / "verify_release.py"),
        manifest["tag"], "--manifest", str(path), "--artifacts-dir", str(archive.parent),
    ], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert "archive bytes" in result.stdout
