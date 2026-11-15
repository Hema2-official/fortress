"""Dataset curation retains spatial movement and rejects unusable records."""
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('mouse_import', ROOT / 'tools/import_mouse_traces.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def trace(**changes):
    return dict({'type': 0, 'trajectory': [[i * 10, i * 2] for i in range(24)],
                 'id': 'discard', 'screen': [1920, 1080], 'time': 123}, **changes)


def test_normalization_is_reproducible_and_discards_metadata():
    records = [trace() for _ in range(64)]
    result = module.curate(records)
    assert result == module.curate(records)
    assert len(result) == 64
    assert all(len(row) == 24 for row in result)
    assert result[0][0] == [0.0, 0.0]
    assert result[0][-1] == [1.0, 0.0]
    assert 'discard' not in module.header(result)


@pytest.mark.parametrize('bad', [trace(type=1), trace(trajectory=[[0, 0]]),
    trace(trajectory=[[float('nan'), 0]] * 24),
    trace(trajectory=[[0, 0]] * 24)])
def test_invalid_record_is_skipped(bad):
    good = [trace() for _ in range(64)]
    assert module.curate([bad, *good]) == module.curate(good)


def test_insufficient_data_fails_explicitly():
    with pytest.raises(ValueError, match='usable mouse trajectories'):
        module.curate([])


def test_committed_header_matches_provenance():
    import hashlib
    import json
    provenance = json.loads((ROOT / 'packaging/mouse-provenance.json').read_text())
    data = (ROOT / 'tools/native_tests/uxr_mouse_trajectories.h').read_bytes()
    assert hashlib.sha256(data).hexdigest() == provenance['generated_header_sha256']
