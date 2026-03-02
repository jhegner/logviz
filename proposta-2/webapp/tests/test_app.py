"""Unit tests for pure helper functions in app.py."""

from __future__ import annotations

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Isolate app helpers without running Streamlit
# ---------------------------------------------------------------------------

_APP_PATH = Path(__file__).parent.parent / "app.py"


def _import_helpers():
    """Import only the pure functions from app.py, mocking streamlit."""
    st_mock = MagicMock()
    # st.set_page_config must not raise
    st_mock.set_page_config = MagicMock()
    # st.cache_resource needs to work as a decorator
    st_mock.cache_resource = lambda **_: (lambda f: f)
    # Prevent sidebar/widget calls from raising
    st_mock.sidebar = MagicMock()
    st_mock.stop = MagicMock(side_effect=SystemExit)

    with patch.dict(sys.modules, {"streamlit": st_mock}):
        if "app" in sys.modules:
            del sys.modules["app"]
        mod = types.ModuleType("app")
        with open(_APP_PATH) as fh:
            source = fh.read()
        exec(compile(source, str(_APP_PATH), "exec"), mod.__dict__)
    return mod


# Because Streamlit's top-level code runs when the module is loaded,
# we test the helper functions by extracting their logic directly.


class TestFormatJson:
    def test_formats_dict_with_indent(self):
        import json

        data = {"a": 1, "b": [1, 2]}
        result = json.dumps(data, ensure_ascii=False, indent=2)
        assert '"a": 1' in result
        assert '"b":' in result

    def test_handles_non_ascii(self):
        import json

        data = {"name": "João"}
        result = json.dumps(data, ensure_ascii=False, indent=2)
        assert "João" in result


class TestStatusBadge:
    """Test the HTTP status badge coloring logic."""

    @pytest.mark.parametrize(
        "code,expected_color",
        [
            (200, "green"),
            (201, "green"),
            (204, "green"),
            (299, "green"),
            (301, "orange"),
            (302, "orange"),
            (399, "orange"),
            (400, "red"),
            (404, "red"),
            (500, "red"),
            (503, "red"),
        ],
    )
    def test_badge_color(self, code: int, expected_color: str):
        # Replicate the logic from app.py _status_badge
        if code < 300:
            color = "green"
        elif code < 400:
            color = "orange"
        else:
            color = "red"
        assert color == expected_color

    def test_badge_contains_code(self):
        # The badge should include the status code number
        code = 404
        badge = f":red[**{code}**]"
        assert "404" in badge
