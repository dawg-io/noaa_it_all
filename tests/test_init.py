"""Tests for async_setup_entry — merged config and the options update listener.

Covers the runtime half of dawg-io/noaa_it_all#21: coordinators must be built
from the saved options rather than the initial setup data, and changing an
option must reload the entry so those coordinators are rebuilt (they capture
office_code / latitude / longitude at construction and cannot be re-pointed).
"""

import asyncio
import contextlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

# ---------------------------------------------------------------------------
# Ensure the custom_components directory is on sys.path
# ---------------------------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_config_entries = MagicMock()
_ha_core = MagicMock()
_ha_coordinator = MagicMock()

# Coordinators subclass DataUpdateCoordinator at import time, so it has to be a
# real class rather than a MagicMock.
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})

_ha_homeassistant = MagicMock()
_ha_homeassistant.config_entries = _ha_config_entries
_ha_homeassistant.core = _ha_core

_MOCK_MODULES = {
    "homeassistant": _ha_homeassistant,
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.discovery": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.config_entries": _ha_config_entries,
    "homeassistant.core": _ha_core,
    "aiohttp": MagicMock(),
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


# Every coordinator class bound into the noaa_it_all package namespace by
# ``from .coordinator import (...)``.
_COORDINATOR_NAMES = (
    "SpaceWeatherCoordinator",
    "HurricaneCoordinator",
    "NWSAlertsCoordinator",
    "ObservationsCoordinator",
    "SurfCoordinator",
    "ForecastCoordinator",
    "CloudCoverCoordinator",
    "RadarTimestampCoordinator",
    "ForecastDiscussionCoordinator",
    "MeteorShowerCoordinator",
    "EclipseCoordinator",
)

# Wilmington, NC — the ILM forecast office.
_ILM = {"office_code": "ILM", "latitude": 34.2257, "longitude": -77.9447}
# San Diego, CA — the SGX forecast office.
_SGX = {"office_code": "SGX", "latitude": 32.7157, "longitude": -117.1611}


def _run(coro):
    """Run a coroutine synchronously for unittest."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@contextlib.contextmanager
def _patched_coordinators():
    """Replace every coordinator class with an awaitable-refresh stub."""
    with contextlib.ExitStack() as stack:
        patched = {}
        for name in _COORDINATOR_NAMES:
            cls = stack.enter_context(patch(f"noaa_it_all.{name}"))
            cls.return_value.async_refresh = AsyncMock(return_value=None)
            patched[name] = cls
        yield patched


def _make_hass():
    """Create a fake Home Assistant object with a real hass.data dict."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    hass.config_entries.async_reload = AsyncMock(return_value=None)
    return hass


def _make_entry(data, options=None):
    """Create a fake ConfigEntry with real data / options mappings."""
    entry = MagicMock()
    entry.entry_id = "entry_1"
    entry.data = dict(data)
    entry.options = {} if options is None else dict(options)
    entry.add_update_listener = MagicMock(return_value="unsubscribe")
    entry.async_on_unload = MagicMock()
    return entry


def _setup(entry):
    """Run async_setup_entry against a fresh hass with stubbed coordinators."""
    import noaa_it_all

    hass = _make_hass()
    with _patched_coordinators() as coordinators:
        result = _run(noaa_it_all.async_setup_entry(hass, entry))
    return hass, result, coordinators


class TestSetupEntryUsesSavedOptions(unittest.TestCase):
    """Coordinators and stored config must reflect config_entry.options."""

    def _entry_data(self, hass):
        from noaa_it_all.const import DOMAIN
        return hass.data[DOMAIN]["entry_1"]

    def test_setup_returns_true_and_stores_entry_data(self):
        from noaa_it_all.const import DOMAIN

        hass, result, _ = _setup(_make_entry(_SGX))
        self.assertTrue(result)
        self.assertIn("entry_1", hass.data[DOMAIN])

    def test_stored_config_is_the_merged_mapping(self):
        hass, _, _ = _setup(_make_entry(_SGX, _ILM))
        self.assertEqual(self._entry_data(hass)["config"], _ILM)

    def test_stored_config_falls_back_to_data(self):
        hass, _, _ = _setup(_make_entry(_SGX))
        self.assertEqual(self._entry_data(hass)["config"], _SGX)

    def test_location_coordinators_get_the_option_coordinates(self):
        _, _, coordinators = _setup(_make_entry(_SGX, _ILM))
        coordinators["ObservationsCoordinator"].assert_called_once()
        args = coordinators["ObservationsCoordinator"].call_args.args
        self.assertEqual(args[1], "ILM")
        self.assertAlmostEqual(args[2], 34.2257)
        self.assertAlmostEqual(args[3], -77.9447)

    def test_alerts_coordinator_gets_the_option_coordinates(self):
        _, _, coordinators = _setup(_make_entry(_SGX, _ILM))
        args = coordinators["NWSAlertsCoordinator"].call_args.args
        self.assertAlmostEqual(args[1], 34.2257)
        self.assertAlmostEqual(args[2], -77.9447)

    def test_office_coordinators_get_the_option_office(self):
        _, _, coordinators = _setup(_make_entry(_SGX, _ILM))
        self.assertEqual(
            coordinators["ForecastDiscussionCoordinator"].call_args.args[1], "ILM"
        )

    def test_partial_options_only_override_what_they_carry(self):
        """Changing only the coordinates keeps the office from setup data."""
        entry = _make_entry(_SGX, {"latitude": 34.2257, "longitude": -77.9447})
        hass, _, coordinators = _setup(entry)
        self.assertEqual(self._entry_data(hass)["config"]["office_code"], "SGX")
        args = coordinators["ForecastCoordinator"].call_args.args
        self.assertEqual(args[1], "SGX")
        self.assertAlmostEqual(args[2], 34.2257)

    def test_location_coordinators_skipped_without_coordinates(self):
        _, _, coordinators = _setup(_make_entry({"office_code": "ILM"}))
        coordinators["NWSAlertsCoordinator"].assert_not_called()
        coordinators["ObservationsCoordinator"].assert_not_called()
        coordinators["MeteorShowerCoordinator"].assert_not_called()
        coordinators["EclipseCoordinator"].assert_not_called()


class TestOptionsUpdateListener(unittest.TestCase):
    """An options change has to reload the entry to take effect."""

    def test_update_listener_registered_once(self):
        entry = _make_entry(_SGX)
        _setup(entry)
        entry.add_update_listener.assert_called_once()

    def test_update_listener_is_unregistered_on_unload(self):
        entry = _make_entry(_SGX)
        _setup(entry)
        entry.async_on_unload.assert_any_call("unsubscribe")

    def test_registered_listener_reloads_the_entry(self):
        import noaa_it_all

        entry = _make_entry(_SGX)
        _setup(entry)
        listener = entry.add_update_listener.call_args.args[0]
        self.assertIs(listener, noaa_it_all._async_update_listener)

        hass = _make_hass()
        _run(listener(hass, entry))
        hass.config_entries.async_reload.assert_awaited_once_with("entry_1")


if __name__ == "__main__":
    unittest.main()


class TestRemoveEntryCleansUpRadarFrames(unittest.TestCase):
    """Uninstalling should not leave a day of radar behind.

    The frames live in the configuration directory, so anything left there
    rides along in every backup from then on.
    """

    @staticmethod
    def _entry(entry_id, office):
        entry = MagicMock()
        entry.entry_id = entry_id
        entry.data = {"office_code": office}
        entry.options = {}
        return entry

    @staticmethod
    def _hass(entries):
        hass = MagicMock()
        hass.config.path = MagicMock(return_value="/config/noaa_it_all/radar_frames")
        hass.config_entries.async_entries = MagicMock(return_value=entries)
        return hass

    def _remove(self, hass, entry):
        import noaa_it_all

        removed = []

        class _Store:
            def __init__(self, _hass, _base, site):
                self.site = site

            async def async_remove_all(self):
                removed.append(self.site)

        with patch.object(noaa_it_all, "RadarFrameStore", _Store):
            _run(noaa_it_all.async_remove_entry(hass, entry))
        return removed

    def test_the_sites_frames_are_deleted(self):
        entry = self._entry("entry_1", "ILM")
        removed = self._remove(self._hass([entry]), entry)
        self.assertEqual(["KLTX"], removed)

    def test_frames_shared_with_another_entry_are_kept(self):
        entry = self._entry("entry_1", "ILM")
        other = self._entry("entry_2", "ILM")
        removed = self._remove(self._hass([entry, other]), entry)
        self.assertEqual([], removed)

    def test_an_office_without_a_radar_site_is_a_no_op(self):
        entry = self._entry("entry_1", "ZZZ")
        removed = self._remove(self._hass([entry]), entry)
        self.assertEqual([], removed)
