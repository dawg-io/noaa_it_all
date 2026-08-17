"""Tests for resolve_entry_config — the options-over-data merge.

Initial setup writes latitude / longitude / office_code to
``config_entry.data``; the options flow writes them to ``config_entry.options``.
Runtime reads must see the saved options and fall back to the setup values,
which is bug 2 of dawg-io/noaa_it_all#21.
"""

import os
import sys
import unittest


# ---------------------------------------------------------------------------
# Ensure the custom_components directory is on sys.path so that
# ``noaa_it_all`` resolves as a package.
# ---------------------------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = os.path.join(_REPO, "custom_components", "noaa_it_all")
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)


from entry_config import resolve_entry_config  # noqa: E402


class _FakeEntry:
    """Stand-in for a Home Assistant ConfigEntry."""

    def __init__(self, data, options=None):
        self.data = data
        self.options = {} if options is None else options


class TestResolveEntryConfig(unittest.TestCase):
    """Cover every combination of data and options."""

    def test_empty_options_returns_setup_data(self):
        entry = _FakeEntry({"office_code": "SGX", "latitude": 32.7, "longitude": -117.1})
        self.assertEqual(resolve_entry_config(entry), {
            "office_code": "SGX",
            "latitude": 32.7,
            "longitude": -117.1,
        })

    def test_options_override_every_key(self):
        entry = _FakeEntry(
            {"office_code": "SGX", "latitude": 32.7, "longitude": -117.1},
            {"office_code": "ILM", "latitude": 34.2257, "longitude": -77.9447},
        )
        self.assertEqual(resolve_entry_config(entry), {
            "office_code": "ILM",
            "latitude": 34.2257,
            "longitude": -77.9447,
        })

    def test_options_override_only_the_keys_they_carry(self):
        entry = _FakeEntry(
            {"office_code": "SGX", "latitude": 32.7, "longitude": -117.1},
            {"latitude": 34.2257},
        )
        self.assertEqual(resolve_entry_config(entry), {
            "office_code": "SGX",
            "latitude": 34.2257,
            "longitude": -117.1,
        })

    def test_none_options_is_tolerated(self):
        """A config entry with options set to None must not blow up."""
        entry = _FakeEntry({"office_code": "SGX"})
        entry.options = None
        self.assertEqual(resolve_entry_config(entry), {"office_code": "SGX"})

    def test_options_may_add_keys_absent_from_data(self):
        entry = _FakeEntry({"office_code": "SGX"}, {"latitude": 34.2257})
        self.assertEqual(resolve_entry_config(entry), {
            "office_code": "SGX",
            "latitude": 34.2257,
        })

    def test_falsy_option_values_still_win(self):
        """0.0 is a real coordinate, not a missing value."""
        entry = _FakeEntry({"latitude": 32.7, "longitude": -117.1}, {"latitude": 0.0})
        self.assertEqual(resolve_entry_config(entry)["latitude"], 0.0)

    def test_result_does_not_alias_the_entry_mappings(self):
        """The merged dict must be a copy — callers stash it in hass.data."""
        data = {"office_code": "SGX"}
        entry = _FakeEntry(data)
        resolved = resolve_entry_config(entry)
        resolved["office_code"] = "ILM"
        self.assertEqual(data["office_code"], "SGX")


if __name__ == "__main__":
    unittest.main()
