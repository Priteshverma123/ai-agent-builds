from pathlib import Path

import pytest

from reviewer.diff import PatchError, apply_patch, parse_diff

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
DIFF = (EXAMPLES / "change.diff").read_text()


def test_parser_maps_added_lines_to_new_line_numbers():
    files = {f.path: f for f in parse_diff(DIFF)}
    assert set(files) == {"shop/api.py", "shop/db.py", "shop/pricing.py", "tests/test_pricing.py"}
    api = files["shop/api.py"]
    assert api.added()[10] == 'API_KEY = "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e"'
    assert api.stats() == (20, 0)
    assert files["shop/pricing.py"].is_new and not api.is_new


def test_apply_patch_rebuilds_the_new_file():
    api = next(f for f in parse_diff(DIFF) if f.path == "shop/api.py")
    new = apply_patch((EXAMPLES / "base" / "shop" / "api.py").read_text(), api).splitlines()
    assert new[0] == '"""HTTP handlers."""'
    assert new[9] == 'API_KEY = "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e"'
    assert new[-1] == "    return requests.get(url).json()"
    for line_no, text in api.added().items():  # every added line lands where the diff says
        assert new[line_no - 1] == text


def test_apply_patch_refuses_a_base_that_does_not_match():
    db = next(f for f in parse_diff(DIFF) if f.path == "shop/db.py")
    with pytest.raises(PatchError):
        apply_patch("something else entirely\n" * 20, db)
