"""Bundle validation with inert fixtures; never execute a browser."""
import os
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ('chrome resources.pak icudtl.dat libEGL.so libGLESv2.so '
            'libvk_swiftshader.so libvulkan.so.1 vk_swiftshader_icd.json '
            'locales/en-US.pak').split()


def setup_bundle(tmp_path):
    source, fonts, dest, tools = [tmp_path / name for name in
                                 ('source', 'fonts', 'dest', 'tools')]
    for path in (source, fonts, dest, tools):
        path.mkdir()
    for name in REQUIRED:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('fixture')
    (fonts / 'font.ttf').write_text('fixture')
    strip = tools / 'strip'
    strip.write_text('#!/bin/sh\nexit "${TEST_STRIP_EXIT:-0}"\n')
    strip.chmod(0o755)
    env = dict(os.environ, PATH=f'{tools}:{os.environ["PATH"]}')
    def run(**changes):
        return subprocess.run(['bash', str(ROOT / 'packaging/build-bundle.sh'),
                               str(source), str(fonts), str(dest)],
                              env=dict(env, **changes), capture_output=True,
                              text=True, timeout=10)
    return source, dest, run


def test_missing_runtime_preserves_previous_bundle(tmp_path):
    source, dest, run = setup_bundle(tmp_path)
    previous = dest / 'tilion-fortress'
    previous.mkdir()
    (previous / 'marker').write_text('previous')
    (source / 'libvulkan.so.1').unlink()
    result = run()
    assert result.returncode != 0
    assert 'Missing required runtime file' in result.stderr
    assert (previous / 'marker').read_text() == 'previous'
    assert not list(dest.glob('*.tar.gz'))


def test_strip_failure_does_not_publish_archive(tmp_path):
    _, dest, run = setup_bundle(tmp_path)
    result = run(TEST_STRIP_EXIT='23')
    assert result.returncode == 23
    assert not list(dest.glob('*.tar.gz'))
    assert not (dest / 'SHA256SUMS').exists()


def test_success_includes_persona_and_checksum(tmp_path):
    _, dest, run = setup_bundle(tmp_path)
    result = run()
    assert result.returncode == 0, result.stderr
    assert (dest / 'tilion-fortress/persona.sh').is_file()
    checksum = subprocess.run(['sha256sum', '--check', 'SHA256SUMS'],
                              cwd=dest, capture_output=True, text=True)
    assert checksum.returncode == 0, checksum.stderr
