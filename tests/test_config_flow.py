"""Tests for config_flow.py — exercises actual async config flow logic."""

import asyncio
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
_ha_entity = MagicMock()

# Make ConfigFlow a real base class with async_set_unique_id as a coroutine
_ha_config_entries.ConfigFlow = type("ConfigFlow", (), {
    "__init_subclass__": classmethod(lambda cls, **kw: None),
    "async_set_unique_id": AsyncMock(return_value=None),
    "_abort_if_unique_id_configured": lambda self: None,
    "async_create_entry": lambda self, **kw: {"type": "create_entry", **kw},
    "async_show_form": lambda self, **kw: {"type": "form", **kw},
})
_ha_config_entries.OptionsFlow = type("OptionsFlow", (), {
    "async_create_entry": lambda self, **kw: {"type": "create_entry", **kw},
    "async_show_form": lambda self, **kw: {"type": "form", **kw},
})

_ha_core.callback = lambda f: f
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_entity.DeviceInfo = dict

_ha_homeassistant = MagicMock()
_ha_homeassistant.config_entries = _ha_config_entries
_ha_homeassistant.core = _ha_core

_MOCK_MODULES = {
    "homeassistant": _ha_homeassistant,
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.weather": MagicMock(),
    "homeassistant.components.image": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.config_entries": _ha_config_entries,
    "homeassistant.core": _ha_core,
    "voluptuous": MagicMock(),
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


class TestConfigFlowImport(unittest.TestCase):
    """Verify config_flow module can be imported and classes exist."""

    def test_import_config_flow(self):
        from noaa_it_all.config_flow import NOAAConfigFlow
        self.assertTrue(hasattr(NOAAConfigFlow, "async_step_user"))

    def test_import_options_flow(self):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        self.assertTrue(hasattr(NOAAOptionsFlow, "async_step_init"))


class TestNWSOffices(unittest.TestCase):
    """Validate the NWS_OFFICES dictionary."""

    def test_nws_offices_not_empty(self):
        from noaa_it_all.config_flow import NWS_OFFICES
        self.assertGreater(len(NWS_OFFICES), 0)

    def test_all_offices_are_three_letter_codes(self):
        from noaa_it_all.config_flow import NWS_OFFICES
        for code in NWS_OFFICES:
            self.assertEqual(len(code), 3, f"Office code '{code}' is not 3 letters")
            self.assertTrue(code.isalpha(), f"Office code '{code}' is not alphabetic")

    def test_sgx_present(self):
        from noaa_it_all.config_flow import NWS_OFFICES
        self.assertIn("SGX", NWS_OFFICES)
        self.assertEqual(NWS_OFFICES["SGX"], "San Diego, CA")


class TestUniqueIdFormatting(unittest.TestCase):
    """Test the unique ID formatting logic from config flow."""

    def test_positive_coords(self):
        lat, lon = 32.7157, -117.1611
        lat_str = f"{lat:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{lon:.4f}".replace('.', '_').replace('-', 'n')
        uid = f"noaa_SGX_{lat_str}_{lon_str}"
        self.assertEqual(uid, "noaa_SGX_32_7157_n117_1611")

    def test_negative_lat(self):
        lat = -33.8688
        lat_str = f"{lat:.4f}".replace('.', '_').replace('-', 'n')
        self.assertEqual(lat_str, "n33_8688")

    def test_zero_coords(self):
        lat, lon = 0.0, 0.0
        lat_str = f"{lat:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{lon:.4f}".replace('.', '_').replace('-', 'n')
        uid = f"noaa_GUM_{lat_str}_{lon_str}"
        self.assertEqual(uid, "noaa_GUM_0_0000_0_0000")


# ---------------------------------------------------------------------------
# Async tests exercising the actual config flow methods
# ---------------------------------------------------------------------------

def _run(coro):
    """Run a coroutine synchronously for unittest."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestAsyncStepUser(unittest.TestCase):
    """Exercise NOAAConfigFlow.async_step_user with valid/invalid inputs."""

    def _make_flow(self):
        from noaa_it_all.config_flow import NOAAConfigFlow
        flow = NOAAConfigFlow()
        flow.async_set_unique_id = AsyncMock(return_value=None)
        flow._abort_if_unique_id_configured = MagicMock()
        return flow

    def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    def test_valid_input_creates_entry(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 32.7157,
            "longitude": -117.1611,
        }))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA - San Diego, CA")

    def test_valid_input_calls_async_set_unique_id(self):
        flow = self._make_flow()
        _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 32.7157,
            "longitude": -117.1611,
        }))
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_SGX_32_7157_n117_1611"
        )

    def test_valid_input_calls_abort_if_configured(self):
        flow = self._make_flow()
        _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 32.7157,
            "longitude": -117.1611,
        }))
        flow._abort_if_unique_id_configured.assert_called_once()

    def test_invalid_latitude_too_high_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_latitude_too_low_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": -91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_longitude_too_high_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 32.0,
            "longitude": 181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_longitude_too_low_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 32.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_lat_and_lon_returns_both_errors(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 91.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertIn("longitude", result["errors"])

    def test_invalid_input_does_not_set_unique_id(self):
        flow = self._make_flow()
        _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        flow.async_set_unique_id.assert_not_awaited()

    def test_edge_latitude_90(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 90.0,
            "longitude": 0.0,
        }))
        self.assertEqual(result["type"], "create_entry")

    def test_edge_latitude_neg90(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": -90.0,
            "longitude": 0.0,
        }))
        self.assertEqual(result["type"], "create_entry")

    def test_edge_longitude_180(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 0.0,
            "longitude": 180.0,
        }))
        self.assertEqual(result["type"], "create_entry")

    def test_edge_longitude_neg180(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "office_code": "SGX",
            "latitude": 0.0,
            "longitude": -180.0,
        }))
        self.assertEqual(result["type"], "create_entry")

    def test_unique_id_with_negative_coords(self):
        flow = self._make_flow()
        _run(flow.async_step_user(user_input={
            "office_code": "ILM",
            "latitude": -33.8688,
            "longitude": -117.1611,
        }))
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_ILM_n33_8688_n117_1611"
        )


class TestAsyncStepInit(unittest.TestCase):
    """Exercise NOAAOptionsFlow.async_step_init with valid/invalid inputs."""

    def _make_flow(self):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        entry = MagicMock()
        entry.data = {"office_code": "SGX", "latitude": 32.0, "longitude": -117.0}
        return NOAAOptionsFlow(entry)

    def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    def test_valid_input_creates_entry(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "office_code": "ILM",
            "latitude": 34.0,
            "longitude": -78.0,
        }))
        self.assertEqual(result["type"], "create_entry")

    def test_invalid_latitude_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "office_code": "SGX",
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_longitude_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "office_code": "SGX",
            "latitude": 32.0,
            "longitude": 181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_lat_and_lon_returns_both_errors(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "office_code": "SGX",
            "latitude": -91.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertIn("longitude", result["errors"])

    def test_edge_values_accepted(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "office_code": "SGX",
            "latitude": 90.0,
            "longitude": -180.0,
        }))
        self.assertEqual(result["type"], "create_entry")


if __name__ == "__main__":
    unittest.main()
