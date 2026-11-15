"""Exercise the source gate against actual git patches without network or a browser."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import check_chromium_source as cs


@pytest.fixture
def source_pair(tmp_path):
    repo = tmp_path / "repo"
    source = tmp_path / "source"
    (repo / "patches").mkdir(parents=True)
    (repo / "build").mkdir()
    source.mkdir()
    (source / "example.cc").write_text("old\n")
    (repo / "CHROMIUM_VERSION").write_text("156.0.8078.47\n")
    manifest = {"version": "156.0.8078.47", "revision": "a" * 40,
                "source_files": {"example.cc": hashlib.sha256(b"old\n").hexdigest()}}
    (repo / "build/chromium-source.json").write_text(json.dumps(manifest))
    (repo / "patches/series").write_text("patches/change.patch\npatches/add.patch\n")
    (repo / "patches/change.patch").write_text(
        "diff --git a/example.cc b/example.cc\n--- a/example.cc\n+++ b/example.cc\n"
        "@@ -1 +1 @@\n-old\n+new\n")
    (repo / "patches/add.patch").write_text(
        "diff --git a/extra.cc b/extra.cc\nnew file mode 100644\n"
        "--- /dev/null\n+++ b/extra.cc\n@@ -0,0 +1 @@\n+added\n")
    return repo, source


def test_series_applies_in_isolation(source_pair):
    repo, source = source_pair
    assert cs.verify(repo, source) == 2
    assert (source / "example.cc").read_text() == "old\n"
    assert not (source / "extra.cc").exists()


def test_altered_source_bytes_are_rejected(source_pair):
    repo, source = source_pair
    (source / "example.cc").write_text("changed\n")
    with pytest.raises(ValueError, match="source hash mismatch"):
        cs.verify(repo, source)


def test_version_mismatch_is_rejected(source_pair):
    repo, source = source_pair
    (repo / "CHROMIUM_VERSION").write_text("151.0.7908.0\n")
    with pytest.raises(ValueError, match="disagrees"):
        cs.verify(repo, source)


def test_missing_source_pin_is_rejected(source_pair):
    repo, source = source_pair
    path = repo / "build/chromium-source.json"
    manifest = json.loads(path.read_text())
    manifest["source_files"] = {}
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="cover exactly"):
        cs.verify(repo, source)
