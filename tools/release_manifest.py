"""Offline artifact identity validation without extracting archives or license gates."""
from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile


def digest(stream):
    h = hashlib.sha256()
    for data in iter(lambda: stream.read(1024 * 1024), b""):
        h.update(data)
    return h.hexdigest()


def safe_name(name):
    path = PurePosixPath(name.replace("\\", "/"))
    return bool(name) and not path.is_absolute() and ".." not in path.parts and ":" not in name


def safe_link(name, target, hardlink=False):
    if not target or target.startswith(("/", "\\")) or ":" in target:
        return False
    parts = [] if hardlink else list(PurePosixPath(name).parent.parts)
    for part in target.replace("\\", "/").split("/"):
        if part == "..":
            if not parts:
                return False
            parts.pop()
        elif part not in ("", "."):
            parts.append(part)
    return bool(parts)


def inspect_archive(path: Path, engine_file: str):
    """Check paths, duplicates, links and credential exclusion before any extraction."""
    engine_hash = None
    problems = []
    seen = set()

    def inspect(name, stream=None, link=None, hardlink=False):
        nonlocal engine_hash
        canonical = PurePosixPath(name.replace("\\", "/")).as_posix()
        key = canonical.casefold() if path.suffix.lower() == ".zip" else canonical
        if not safe_name(name):
            problems.append(f"unsafe member: {name}")
        if key in seen:
            problems.append(f"duplicate member: {name}")
        seen.add(key)
        if PurePosixPath(canonical).suffix.lower() == ".jwt":
            problems.append(f"credential member: {name}")
        if link is not None and not safe_link(canonical, link, hardlink):
            problems.append(f"unsafe link: {name}")
        if canonical == engine_file and stream is not None:
            engine_hash = digest(stream)

    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            for member in archive.infolist():
                # Unix symlinks in ZIP store their target as the member data.
                if (member.external_attr >> 16) & 0o170000 == 0o120000:
                    inspect(member.filename, link=archive.read(member).decode("utf-8"))
                else:
                    with archive.open(member) as stream:
                        inspect(member.filename, stream)
    else:
        with tarfile.open(path, "r:gz") as archive:
            for member in archive:
                if member.isfile():
                    with archive.extractfile(member) as stream:
                        inspect(member.name, stream)
                elif member.issym() or member.islnk():
                    inspect(member.name, link=member.linkname, hardlink=member.islnk())
                elif member.isdir():
                    inspect(member.name)
                else:
                    problems.append(f"unsupported member type: {member.name}")
    return engine_hash, problems


def evaluate_manifest(manifest, sums_text, artifacts_dir=None):
    """Return errors for a release record; optionally verify the retained archive bytes."""
    errors = []
    version = manifest.get("chromium_version", "")
    if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", version):
        errors.append("invalid Chromium version")
    for field in ("source_revision", "repository_revision"):
        if not re.fullmatch(r"[0-9a-f]{40}", manifest.get(field, "")):
            errors.append(f"invalid {field}")
    if manifest.get("tag") not in (f"v{version}", f"fural-public-{version}"):
        errors.append("tag does not match Chromium version")
    sums = {}
    for line in sums_text.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            errors.append("malformed checksum entry")
            continue
        name = parts[1].lstrip("*")
        if name in sums:
            errors.append(f"duplicate checksum: {name}")
        sums[name] = parts[0].lower()
    assets = manifest.get("assets", [])
    names, platforms = set(), set()
    for asset in assets:
        name, platform = asset.get("name", ""), asset.get("platform", "")
        if not safe_name(name) or PurePosixPath(name).name != name or "\\" in name:
            errors.append("unsafe artifact name")
            continue
        if name in names or platform in platforms or not platform:
            errors.append("duplicate or empty artifact identity")
        names.add(name)
        platforms.add(platform)
        if not re.fullmatch(r"[0-9a-f]{64}", asset.get("sha256", "")) or sums.get(name) != asset.get("sha256"):
            errors.append(f"artifact checksum mismatch: {name}")
        if type(asset.get("bytes")) is not int or asset["bytes"] <= 0:
            errors.append(f"invalid artifact size: {name}")
        member = asset.get("engine_file", "")
        if not safe_name(member) or not re.fullmatch(r"[0-9a-f]{64}", asset.get("engine_sha256", "")):
            errors.append(f"invalid engine identity: {name}")
            continue
        if artifacts_dir is None:
            continue
        path = Path(artifacts_dir) / name
        if not path.is_file():
            errors.append(f"archive missing: {name}")
            continue
        with path.open("rb") as stream:
            actual = digest(stream)
        if actual != asset.get("sha256") or path.stat().st_size != asset.get("bytes"):
            errors.append(f"archive bytes mismatch: {name}")
            continue
        engine, problems = inspect_archive(path, member)
        errors.extend(problems)
        if engine != asset.get("engine_sha256"):
            errors.append(f"engine bytes mismatch: {name}")
    required = set(manifest.get("required_platforms", []))
    if not required or not required <= platforms:
        errors.append("required platforms missing")
    if set(sums) != names:
        errors.append("checksums do not cover exactly the manifest")
    return errors
