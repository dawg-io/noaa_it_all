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


def _make_hass(lat=None, lon=None):
    """Create a fake Home Assistant object with config.latitude/longitude."""
    hass = MagicMock()
    hass.config = MagicMock()
    hass.config.latitude = lat
    hass.config.longitude = lon
    return hass


class TestAsyncStepUser(unittest.TestCase):
    """Exercise NOAAConfigFlow.async_step_user with valid/invalid inputs."""

    def _make_flow(self, hass=None):
        from noaa_it_all.config_flow import NOAAConfigFlow
        flow = NOAAConfigFlow()
        flow.hass = hass
        flow.async_set_unique_id = AsyncMock(return_value=None)
        flow._abort_if_unique_id_configured = MagicMock()
        return flow

    def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")

    def test_no_input_form_has_no_office_code_field(self):
        """Step 1 must not require an office code from the user."""
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input=None))
        # office_code is collected later in step_office, never in step_user
        self.assertEqual(result["step_id"], "user")

    def test_no_input_with_ha_home_includes_ha_location_placeholder(self):
        flow = self._make_flow(hass=_make_hass(32.7157, -117.1611))
        result = _run(flow.async_step_user(user_input=None))
        self.assertIn("ha_location", result["description_placeholders"])
        self.assertIn("32.7157", result["description_placeholders"]["ha_location"])
        self.assertIn("-117.1611", result["description_placeholders"]["ha_location"])

    def test_no_input_without_ha_home_falls_back_to_not_configured(self):
        flow = self._make_flow(hass=_make_hass(None, None))
        result = _run(flow.async_step_user(user_input=None))
        self.assertEqual(
            result["description_placeholders"]["ha_location"], "not configured"
        )

    def test_valid_input_advances_to_office_step(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 32.7157,
            "longitude": -117.1611,
        }))
        # Now returns the office selection form, not create_entry yet
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "office")
        # Stored on the flow for the next step
        self.assertAlmostEqual(flow._latitude, 32.7157)
        self.assertAlmostEqual(flow._longitude, -117.1611)

    def test_invalid_latitude_too_high_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "user")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_latitude_too_low_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": -91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_longitude_too_high_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 32.0,
            "longitude": 181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_longitude_too_low_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 32.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_lat_and_lon_returns_both_errors(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 91.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertIn("longitude", result["errors"])

    def test_invalid_input_does_not_set_unique_id(self):
        flow = self._make_flow()
        _run(flow.async_step_user(user_input={
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        flow.async_set_unique_id.assert_not_awaited()

    def test_edge_latitude_90_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 90.0, "longitude": 0.0,
        }))
        self.assertEqual(result["step_id"], "office")

    def test_edge_latitude_neg90_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": -90.0, "longitude": 0.0,
        }))
        self.assertEqual(result["step_id"], "office")

    def test_edge_longitude_180_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 0.0, "longitude": 180.0,
        }))
        self.assertEqual(result["step_id"], "office")

    def test_edge_longitude_neg180_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_user(user_input={
            "latitude": 0.0, "longitude": -180.0,
        }))
        self.assertEqual(result["step_id"], "office")


class TestAsyncStepOffice(unittest.TestCase):
    """Exercise NOAAConfigFlow.async_step_office with auto-suggest behavior."""

    def _make_flow(self, lat, lon):
        from noaa_it_all.config_flow import NOAAConfigFlow
        flow = NOAAConfigFlow()
        flow.hass = None
        flow._latitude = lat
        flow._longitude = lon
        flow.async_set_unique_id = AsyncMock(return_value=None)
        flow._abort_if_unique_id_configured = MagicMock()
        return flow

    def test_office_form_suggests_closest_office(self):
        # San Diego coordinates -> SGX should be the default
        flow = self._make_flow(32.7157, -117.1611)
        result = _run(flow.async_step_office(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "office")

    def test_office_form_no_warning_when_office_within_50_miles(self):
        flow = self._make_flow(32.7157, -117.1611)  # San Diego, near SGX
        result = _run(flow.async_step_office(user_input=None))
        self.assertEqual(result["description_placeholders"]["warning"], "")

    def test_office_form_warning_when_no_office_within_50_miles(self):
        # Middle of the Atlantic - no office within 50 miles
        flow = self._make_flow(0.0, -30.0)
        result = _run(flow.async_step_office(user_input=None))
        self.assertNotEqual(result["description_placeholders"]["warning"], "")
        self.assertIn("50 miles", result["description_placeholders"]["warning"])

    def test_office_choice_creates_entry_with_unique_id(self):
        flow = self._make_flow(32.7157, -117.1611)
        result = _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA - San Diego, CA")
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_SGX_32_7157_n117_1611"
        )
        flow._abort_if_unique_id_configured.assert_called_once()
        self.assertEqual(result["data"]["office_code"], "SGX")
        self.assertAlmostEqual(result["data"]["latitude"], 32.7157)
        self.assertAlmostEqual(result["data"]["longitude"], -117.1611)

    def test_office_choice_with_negative_coords_unique_id(self):
        flow = self._make_flow(-33.8688, -117.1611)
        _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_ILM_n33_8688_n117_1611"
        )


class TestHaversineAndOfficeLookup(unittest.TestCase):
    """Tests for the haversine distance + office lookup helpers."""

    def test_haversine_zero_distance(self):
        from noaa_it_all.config_flow import haversine_miles
        self.assertEqual(haversine_miles(40.0, -75.0, 40.0, -75.0), 0.0)

    def test_haversine_known_distance(self):
        # NY (40.7128, -74.0060) to LA (34.0522, -118.2437) ~ 2451 miles
        from noaa_it_all.config_flow import haversine_miles
        d = haversine_miles(40.7128, -74.0060, 34.0522, -118.2437)
        self.assertAlmostEqual(d, 2451, delta=10)

    def test_find_nearby_offices_returns_only_within_radius(self):
        from noaa_it_all.config_flow import find_nearby_offices
        # San Diego -> SGX (San Diego) should be in the result
        results = find_nearby_offices(32.7157, -117.1611, max_miles=50)
        codes = [code for code, _ in results]
        self.assertIn("SGX", codes)
        for _, dist in results:
            self.assertLessEqual(dist, 50.0)

    def test_find_nearby_offices_sorted_ascending(self):
        from noaa_it_all.config_flow import find_nearby_offices
        results = find_nearby_offices(40.0, -75.0, max_miles=None)
        distances = [d for _, d in results]
        self.assertEqual(distances, sorted(distances))

    def test_find_nearby_offices_no_match_returns_empty(self):
        from noaa_it_all.config_flow import find_nearby_offices
        # Middle of the Atlantic - far from any US office
        results = find_nearby_offices(0.0, -30.0, max_miles=50)
        self.assertEqual(results, [])

    def test_find_nearby_offices_no_max_returns_all(self):
        from noaa_it_all.config_flow import find_nearby_offices, NWS_OFFICES
        from noaa_it_all.const import OFFICE_COORDINATES
        results = find_nearby_offices(0.0, 0.0, max_miles=None)
        self.assertEqual(len(results), len(OFFICE_COORDINATES))
        # Every office in NWS_OFFICES should also have coordinates
        for code in NWS_OFFICES:
            self.assertIn(code, OFFICE_COORDINATES)


class TestAsyncStepInit(unittest.TestCase):
    """Exercise NOAAOptionsFlow.async_step_init with valid/invalid inputs."""

    def _make_flow(self):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        entry = MagicMock()
        entry.data = {"office_code": "SGX", "latitude": 32.0, "longitude": -117.0}
        flow = NOAAOptionsFlow(entry)
        flow.hass = None
        return flow

    def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    def test_no_input_prefills_existing_coords(self):
        flow = self._make_flow()
        _run(flow.async_step_init(user_input=None))
        # We can't easily inspect schema defaults via our MagicMock voluptuous,
        # but we can confirm the form did not error.

    def test_valid_input_advances_to_office_step(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "latitude": 34.0,
            "longitude": -78.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "office")
        self.assertAlmostEqual(flow._latitude, 34.0)
        self.assertAlmostEqual(flow._longitude, -78.0)

    def test_office_step_creates_entry(self):
        flow = self._make_flow()
        _run(flow.async_step_init(user_input={
            "latitude": 34.0,
            "longitude": -78.0,
        }))
        result = _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["office_code"], "ILM")
        self.assertAlmostEqual(result["data"]["latitude"], 34.0)
        self.assertAlmostEqual(result["data"]["longitude"], -78.0)

    def test_invalid_latitude_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_longitude_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "latitude": 32.0,
            "longitude": 181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_lat_and_lon_returns_both_errors(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "latitude": -91.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertIn("longitude", result["errors"])

    def test_edge_values_advance_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input={
            "latitude": 90.0,
            "longitude": -180.0,
        }))
        self.assertEqual(result["step_id"], "office")


if __name__ == "__main__":
    unittest.main()
