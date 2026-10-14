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
    "_abort_if_unique_id_configured": lambda self, **kw: None,
    "async_create_entry": lambda self, **kw: {"type": "create_entry", **kw},
    "async_show_form": lambda self, **kw: {"type": "form", **kw},
    "async_show_menu": lambda self, **kw: {"type": "menu", **kw},
    "async_abort": lambda self, **kw: {"type": "abort", **kw},
    # Tests set ``_test_entries`` to the entries that already exist.
    "_async_current_entries": lambda self, include_ignore=None: list(
        getattr(self, "_test_entries", [])
    ),
})
# Mirror real Home Assistant: OptionsFlow.config_entry is a read-only property
# that the framework populates itself, so assigning to it must raise
# AttributeError. A permissive stub here is what let the crash in issue #21
# ship — keep this getter-only.
_ha_config_entries.OptionsFlow = type("OptionsFlow", (), {
    "config_entry": property(lambda self: self._config_entry),
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


def _reset_recorded_defaults():
    """Forget vol.Required(...) calls recorded by earlier tests."""
    _MOCK_MODULES["voluptuous"].Required.reset_mock()


def _recorded_defaults():
    """Return {field: default} from the vol.Required(...) calls since the reset.

    voluptuous is a MagicMock here, so schema defaults cannot be read back off
    the schema object — but the calls that built it are recorded.
    """
    vol = _MOCK_MODULES["voluptuous"]
    return {
        call.args[0]: call.kwargs.get("default")
        for call in vol.Required.call_args_list
        if call.args
    }


def _entry(data):
    """A stand-in for an existing config entry."""
    entry = MagicMock()
    entry.data = data
    return entry


def _flow(entries=(), issuing=None):
    """A config flow with the HA plumbing stubbed.

    ``entries`` are the entries that already exist. The issuing-offices lookup
    is skipped and reads as ``issuing``.
    """
    from noaa_it_all.config_flow import NOAAConfigFlow
    flow = NOAAConfigFlow()
    flow.hass = MagicMock()
    flow.hass.config.latitude = None
    flow.hass.config.longitude = None
    flow._test_entries = list(entries)
    flow._issuing = issuing
    flow._issuing_checked = True
    flow.async_set_unique_id = AsyncMock(return_value=None)
    flow._abort_if_unique_id_configured = MagicMock()
    return flow


def _added_entries(flow):
    """The data of every surf or hurricane entry the flow started adding."""
    return [
        call.kwargs["data"]
        for call in flow.hass.config_entries.flow.async_init.call_args_list
    ]


class TestAsyncStepLocation(unittest.TestCase):
    """Exercise NOAAConfigFlow.async_step_location with valid/invalid inputs."""

    def _make_flow(self, hass=None):
        from noaa_it_all.config_flow import NOAAConfigFlow
        flow = NOAAConfigFlow()
        flow.hass = hass
        flow.async_set_unique_id = AsyncMock(return_value=None)
        flow._abort_if_unique_id_configured = MagicMock()
        return flow

    def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "location")

    def test_no_input_form_has_no_office_code_field(self):
        """Step 1 must not require an office code from the user."""
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input=None))
        # office_code is collected later in step_office, never in step_location
        self.assertEqual(result["step_id"], "location")

    def test_no_input_with_ha_home_includes_ha_location_placeholder(self):
        flow = self._make_flow(hass=_make_hass(32.7157, -117.1611))
        result = _run(flow.async_step_location(user_input=None))
        self.assertIn("ha_location", result["description_placeholders"])
        self.assertIn("32.7157", result["description_placeholders"]["ha_location"])
        self.assertIn("-117.1611", result["description_placeholders"]["ha_location"])

    def test_no_input_without_ha_home_falls_back_to_not_configured(self):
        flow = self._make_flow(hass=_make_hass(None, None))
        result = _run(flow.async_step_location(user_input=None))
        self.assertEqual(
            result["description_placeholders"]["ha_location"], "not configured"
        )

    def test_valid_input_advances_to_office_step(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
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
        result = _run(flow.async_step_location(user_input={
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "location")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_latitude_too_low_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": -91.0,
            "longitude": -117.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertEqual(result["errors"]["latitude"], "invalid_latitude")

    def test_invalid_longitude_too_high_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": 32.0,
            "longitude": 181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_longitude_too_low_returns_error(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": 32.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("longitude", result["errors"])
        self.assertEqual(result["errors"]["longitude"], "invalid_longitude")

    def test_invalid_lat_and_lon_returns_both_errors(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": 91.0,
            "longitude": -181.0,
        }))
        self.assertEqual(result["type"], "form")
        self.assertIn("latitude", result["errors"])
        self.assertIn("longitude", result["errors"])

    def test_invalid_input_does_not_set_unique_id(self):
        flow = self._make_flow()
        _run(flow.async_step_location(user_input={
            "latitude": 91.0,
            "longitude": -117.0,
        }))
        flow.async_set_unique_id.assert_not_awaited()

    def test_edge_latitude_90_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": 90.0, "longitude": 0.0,
        }))
        self.assertEqual(result["step_id"], "office")

    def test_edge_latitude_neg90_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": -90.0, "longitude": 0.0,
        }))
        self.assertEqual(result["step_id"], "office")

    def test_edge_longitude_180_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": 0.0, "longitude": 180.0,
        }))
        self.assertEqual(result["step_id"], "office")

    def test_edge_longitude_neg180_advances_to_office(self):
        flow = self._make_flow()
        result = _run(flow.async_step_location(user_input={
            "latitude": 0.0, "longitude": -180.0,
        }))
        self.assertEqual(result["step_id"], "office")


class TestAsyncStepOffice(unittest.TestCase):
    """Exercise NOAAConfigFlow.async_step_office with auto-suggest behavior."""

    def _make_flow(self, lat, lon):
        flow = _flow()
        flow._latitude = lat
        flow._longitude = lon
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

    def test_office_choice_asks_for_a_surf_office(self):
        flow = self._make_flow(32.7157, -117.1611)
        result = _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "surf")

    def test_surf_choice_asks_about_space(self):
        flow = self._make_flow(32.7157, -117.1611)
        _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        _reset_recorded_defaults()
        result = _run(flow.async_step_surf(user_input={"surf_office_code": "SGX"}))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "space")
        self.assertEqual(result["description_placeholders"], {"office": "SGX"})
        self.assertEqual(_recorded_defaults()["space_office_code"], "SGX")

    def test_space_choice_creates_the_weather_entry(self):
        flow = self._make_flow(32.7157, -117.1611)
        _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        _run(flow.async_step_surf(user_input={"surf_office_code": "SGX"}))
        result = _run(flow.async_step_space(user_input={"space_office_code": "SGX"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA Weather - San Diego, CA")
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_SGX_32_7157_n117_1611"
        )
        flow._abort_if_unique_id_configured.assert_called_once()
        # SGX is in the radar table, so no site is saved: a later fix to the
        # table reaches the entry.
        self.assertEqual(result["data"], {
            "entry_type": "weather", "office_code": "SGX", "radar_site": None,
            "latitude": 32.7157, "longitude": -117.1611,
        })

    def test_office_choice_with_negative_coords_unique_id(self):
        flow = self._make_flow(-33.8688, -117.1611)
        flow._point = {"office": "ILM", "name": "Wilmington, NC", "radar": "KLTX"}
        _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        _run(flow.async_step_surf(user_input={"surf_office_code": "none"}))
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_ILM_n33_8688_n117_1611"
        )

    def test_office_not_offered_is_rejected(self):
        """Only an office on the list can be saved, as the dropdown enforces."""
        flow = self._make_flow(32.7157, -117.1611)
        result = _run(flow.async_step_office(user_input={"office_code": "GUM"}))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"office_code": "invalid_office"})

    def test_a_coastal_location_preselects_its_own_surf_office(self):
        flow = self._make_flow(32.7157, -117.1611)
        _reset_recorded_defaults()
        _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        self.assertEqual(_recorded_defaults()["surf_office_code"], "SGX")


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

    def _make_flow(self, options=None):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        entry = MagicMock()
        entry.data = {"office_code": "SGX", "latitude": 32.0, "longitude": -117.0}
        # Must be a real mapping — resolve_entry_config() unpacks it, and a bare
        # MagicMock attribute is truthy but not mappable.
        entry.options = {} if options is None else options
        flow = NOAAOptionsFlow()
        # Real Home Assistant populates the read-only config_entry property.
        flow._config_entry = entry
        flow.hass = None
        return flow

    def test_no_input_shows_form(self):
        flow = self._make_flow()
        result = _run(flow.async_step_init(user_input=None))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "init")

    def test_no_input_prefills_existing_coords(self):
        flow = self._make_flow()
        _reset_recorded_defaults()
        _run(flow.async_step_init(user_input=None))
        defaults = _recorded_defaults()
        self.assertAlmostEqual(defaults["latitude"], 32.0)
        self.assertAlmostEqual(defaults["longitude"], -117.0)

    def test_prefill_prefers_saved_options_over_setup_data(self):
        flow = self._make_flow(options={"latitude": 34.2257, "longitude": -77.9447})
        _reset_recorded_defaults()
        _run(flow.async_step_init(user_input=None))
        defaults = _recorded_defaults()
        self.assertAlmostEqual(defaults["latitude"], 34.2257)
        self.assertAlmostEqual(defaults["longitude"], -77.9447)

    def test_prefill_falls_back_to_data_for_keys_absent_from_options(self):
        flow = self._make_flow(options={"latitude": 34.2257})
        _reset_recorded_defaults()
        _run(flow.async_step_init(user_input=None))
        defaults = _recorded_defaults()
        self.assertAlmostEqual(defaults["latitude"], 34.2257)
        self.assertAlmostEqual(defaults["longitude"], -117.0)

    def test_office_default_prefers_saved_option(self):
        # ILM (Wilmington, NC) sits within the nearby radius of these coords, so
        # a saved office_code option should survive as the dropdown default.
        flow = self._make_flow(options={"office_code": "ILM"})
        _reset_recorded_defaults()
        _run(flow.async_step_init(user_input={
            "latitude": 34.2257,
            "longitude": -77.9447,
        }))
        self.assertEqual(_recorded_defaults()["office_code"], "ILM")

    def test_office_default_ignores_saved_option_that_is_not_nearby(self):
        flow = self._make_flow(options={"office_code": "GUM"})
        _reset_recorded_defaults()
        _run(flow.async_step_init(user_input={
            "latitude": 34.2257,
            "longitude": -77.9447,
        }))
        self.assertNotEqual(_recorded_defaults()["office_code"], "GUM")

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

    def test_office_step_advances_to_the_radar_step(self):
        flow = self._make_flow()
        _run(flow.async_step_init(user_input={
            "latitude": 34.0,
            "longitude": -78.0,
        }))
        result = _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["step_id"], "radar")
        self.assertEqual(flow._office_code, "ILM")

    def _through_to_radar(self, flow=None, office="ILM"):
        """Walk the options flow as far as the radar step."""
        flow = flow or self._make_flow()
        _run(flow.async_step_init(user_input={
            "latitude": 34.0,
            "longitude": -78.0,
        }))
        _run(flow.async_step_office(user_input={"office_code": office}))
        return flow

    def test_the_radar_step_creates_the_entry(self):
        flow = self._through_to_radar()
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 24}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["office_code"], "ILM")
        self.assertAlmostEqual(result["data"]["latitude"], 34.0)
        self.assertAlmostEqual(result["data"]["longitude"], -78.0)
        self.assertEqual(result["data"]["radar_loop_hours"], 24)

    def test_saved_options_survive_a_second_trip_through_the_flow(self):
        """Options replace the stored mapping rather than merging into it.

        A key the last step forgets to write is a key silently lost the next
        time anyone opens Configure, which is a slow enough failure to be worth
        pinning down.
        """
        flow = self._make_flow(options={
            "latitude": 34.0,
            "longitude": -78.0,
            "office_code": "ILM",
            "radar_loop_hours": 12,
        })
        self._through_to_radar(flow)
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 12}))
        self.assertEqual(
            {
                "latitude", "longitude", "office_code", "radar_loop_hours",
                "radar_site",
            },
            set(result["data"]),
        )
        self.assertEqual(result["data"]["radar_loop_hours"], 12)

    def test_the_radar_step_prefills_the_saved_value(self):
        flow = self._make_flow(options={"radar_loop_hours": 6})
        self._through_to_radar(flow)
        _reset_recorded_defaults()
        _run(flow.async_step_radar(user_input=None))
        self.assertEqual(_recorded_defaults()["radar_loop_hours"], 6)

    def test_the_radar_step_defaults_to_a_full_day(self):
        flow = self._through_to_radar()
        _reset_recorded_defaults()
        _run(flow.async_step_radar(user_input=None))
        self.assertEqual(_recorded_defaults()["radar_loop_hours"], 24)

    def test_zero_hours_is_accepted_as_the_opt_out(self):
        flow = self._through_to_radar()
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 0}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["radar_loop_hours"], 0)

    def test_out_of_range_or_unparseable_hours_are_rejected(self):
        for value in (-1, 25, 100, "abc", None):
            with self.subTest(value=value):
                flow = self._through_to_radar()
                result = _run(flow.async_step_radar(
                    user_input={"radar_loop_hours": value}
                ))
                self.assertEqual(result["type"], "form")
                self.assertEqual(
                    result["errors"]["radar_loop_hours"], "invalid_radar_hours"
                )

    def test_hours_given_as_a_numeric_string_are_accepted(self):
        flow = self._through_to_radar()
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": "8"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["data"]["radar_loop_hours"], 8)

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


class TestOptionsFlowConfigEntry(unittest.TestCase):
    """Guard the crash from issue #21 (dawg-io/noaa_it_all).

    Home Assistant made OptionsFlow.config_entry a read-only property, so the
    old-style `self.config_entry = config_entry` in __init__ raised
    AttributeError and the Configure screen failed with a 500.
    """

    def test_config_entry_cannot_be_assigned(self):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        flow = NOAAOptionsFlow()
        with self.assertRaises(AttributeError):
            flow.config_entry = MagicMock()

    def test_init_takes_no_config_entry(self):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        with self.assertRaises(TypeError):
            NOAAOptionsFlow(MagicMock())

    def test_config_entry_reads_through_base_class_property(self):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        entry = MagicMock()
        flow = NOAAOptionsFlow()
        flow._config_entry = entry
        self.assertIs(flow.config_entry, entry)

    def test_async_get_options_flow_returns_options_flow(self):
        from noaa_it_all.config_flow import NOAAConfigFlow, NOAAOptionsFlow
        flow = NOAAConfigFlow.async_get_options_flow(MagicMock())
        self.assertIsInstance(flow, NOAAOptionsFlow)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Inland offices: the office comes from NWS, surf from a second office
# ---------------------------------------------------------------------------

# Downtown Las Vegas: inside VEF, which issues no Surf Zone Forecast.
_VEGAS = (36.1699, -115.1398)
_VEF_POINT = {"office": "VEF", "name": "Las Vegas, NV", "radar": "KESX"}


class _FakeResponse:
    """Async context manager standing in for an aiohttp response."""

    def __init__(self, payload=None, error=None, status=200):
        self._payload = payload
        self._error = error
        self.status = status

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self._error:
            raise self._error
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    async def json(self, **kwargs):
        return self._payload


def _session(responses):
    """A session whose get() answers each URL from ``responses``."""
    session = MagicMock()
    session.get = MagicMock(side_effect=lambda url, **kw: responses[url])
    return session


class TestLookupPoint(unittest.TestCase):
    """async_lookup_point reads the office and radar NWS gives for a point."""

    _POINTS = "https://api.weather.gov/points/36.1699,-115.1398"
    _OFFICE = "https://api.weather.gov/offices/VEF"

    def _lookup(self, responses, hass=None):
        from noaa_it_all import config_flow
        with patch.object(
            config_flow, "async_get_clientsession", return_value=_session(responses)
        ):
            return _run(config_flow.async_lookup_point(hass or MagicMock(), *_VEGAS))

    def test_inland_office_and_its_name(self):
        result = self._lookup({
            self._POINTS: _FakeResponse(
                {"properties": {"cwa": "VEF", "radarStation": "KESX"}}
            ),
            self._OFFICE: _FakeResponse({"name": "Las Vegas, NV"}),
        })
        self.assertEqual(result, _VEF_POINT)

    def test_office_name_unavailable_falls_back_to_the_code(self):
        result = self._lookup({
            self._POINTS: _FakeResponse({"properties": {"cwa": "VEF"}}),
            self._OFFICE: _FakeResponse(error=RuntimeError("503")),
        })
        self.assertEqual(result, {"office": "VEF", "name": "VEF", "radar": None})

    def test_known_office_needs_no_second_request(self):
        result = self._lookup({
            self._POINTS: _FakeResponse(
                {"properties": {"cwa": "SGX", "radarStation": "KNKX"}}
            ),
        })
        self.assertEqual(result["name"], "San Diego, CA")

    def test_a_malformed_radar_site_is_dropped(self):
        for radar in ("../..", "/config", "KESX/../..", "kesx", "", 42):
            with self.subTest(radar=radar):
                result = self._lookup({
                    self._POINTS: _FakeResponse(
                        {"properties": {"cwa": "SGX", "radarStation": radar}}
                    ),
                })
                self.assertEqual(result["office"], "SGX")
                self.assertIsNone(result["radar"])

    def test_nws_unreachable_returns_none(self):
        result = self._lookup({self._POINTS: _FakeResponse(error=RuntimeError("404"))})
        self.assertIsNone(result)

    def test_malformed_office_returns_none(self):
        for cwa in (None, "", "VE", "VEFX", "../", "VÉF", 42):
            with self.subTest(cwa=cwa):
                result = self._lookup(
                    {self._POINTS: _FakeResponse({"properties": {"cwa": cwa}})}
                )
                self.assertIsNone(result)

    def test_no_hass_skips_the_request(self):
        from noaa_it_all.config_flow import async_lookup_point
        self.assertIsNone(_run(async_lookup_point(None, *_VEGAS)))


class TestInlandConfigFlow(unittest.TestCase):
    """A Las Vegas setup: VEF for the forecast, a coastal office for surf."""

    def _make_flow(self, point=_VEF_POINT):
        flow = _flow()
        with patch(
            "noaa_it_all.config_flow.async_lookup_point",
            AsyncMock(return_value=point),
        ):
            _reset_recorded_defaults()
            self.office_form = _run(flow.async_step_location(user_input={
                "latitude": _VEGAS[0], "longitude": _VEGAS[1],
            }))
        return flow

    def test_the_nws_office_is_offered_and_preselected(self):
        self._make_flow()
        self.assertEqual(self.office_form["step_id"], "office")
        self.assertEqual(_recorded_defaults()["office_code"], "VEF")
        self.assertEqual(self.office_form["description_placeholders"]["warning"], "")

    def test_without_nws_the_coastal_offices_are_offered_with_the_warning(self):
        self._make_flow(point=None)
        self.assertIn("50 miles", self.office_form["description_placeholders"]["warning"])
        self.assertNotEqual(_recorded_defaults()["office_code"], "VEF")

    def test_an_inland_office_asks_for_a_surf_office(self):
        flow = self._make_flow()
        _reset_recorded_defaults()
        result = _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        self.assertEqual(result["step_id"], "surf")
        # The nearest coast is pre-selected.
        self.assertIn(_recorded_defaults()["surf_office_code"], ("LOX", "SGX"))

    def test_surf_office_choice_creates_the_entry_and_adds_the_surf_entry(self):
        flow = self._make_flow()
        _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        _run(flow.async_step_surf(user_input={"surf_office_code": "MLB"}))
        result = _run(flow.async_step_space(user_input={"space_office_code": "VEF"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA Weather - Las Vegas, NV")
        self.assertEqual(result["data"], {
            "entry_type": "weather", "office_code": "VEF", "radar_site": "KESX",
            "latitude": _VEGAS[0], "longitude": _VEGAS[1],
        })
        flow.async_set_unique_id.assert_awaited_once_with(
            "noaa_VEF_36_1699_n115_1398"
        )
        self.assertIn({"entry_type": "surf", "office_code": "MLB"}, _added_entries(flow))
        # Space is named after the forecast office, and its title after the
        # name NWS gave it.
        self.assertIn({
            "entry_type": "space", "office_code": "VEF",
            "latitude": _VEGAS[0], "longitude": _VEGAS[1], "place": "Las Vegas, NV",
        }, _added_entries(flow))

    def test_no_surf_adds_no_surf_entry(self):
        flow = self._make_flow()
        _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        _run(flow.async_step_surf(user_input={"surf_office_code": "none"}))
        result = _run(flow.async_step_space(user_input={"space_office_code": "VEF"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertNotIn("surf", [d.get("entry_type") for d in _added_entries(flow)])

    def test_unknown_surf_office_is_rejected(self):
        flow = self._make_flow()
        _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        result = _run(flow.async_step_surf(user_input={"surf_office_code": "VEF"}))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"surf_office_code": "invalid_office"})


class TestSurfLabels(unittest.TestCase):
    """The surf dropdown says which surf data each office can provide."""

    def _labels(self):
        from noaa_it_all.config_flow import _build_surf_options
        options, _ = _build_surf_options(*_VEGAS)
        return options

    def test_tide_station_and_buoy(self):
        self.assertTrue(
            self._labels()["SGX"].endswith(" - rip current, water temp, surf height")
        )

    def test_tide_station_only(self):
        self.assertTrue(self._labels()["DLH"].endswith(" - rip current, water temp"))

    def test_neither(self):
        self.assertTrue(self._labels()["APX"].endswith(" - rip current only"))

    def test_label_keeps_the_office_and_distance(self):
        self.assertRegex(self._labels()["SGX"], r"^SGX - San Diego, CA \(\d+\.\d mi\) - ")

    def test_buoy_only(self):
        from noaa_it_all import config_flow, offices
        with patch.dict(offices.OFFICE_TIDE_STATIONS, clear=False) as tide:
            tide.pop("SGX")
            self.assertTrue(
                config_flow._format_surf_label("SGX", 1.0).endswith(" - rip current, surf height")
            )

    def test_no_surf_label_is_unchanged(self):
        self.assertEqual(self._labels()["none"], "No surf data")


class TestInlandOptionsFlow(unittest.TestCase):
    """Reconfiguring an inland entry: office and radar, no surf step."""

    _SAVED = {
        "entry_type": "weather", "office_code": "VEF", "radar_site": "KESX",
        "latitude": _VEGAS[0], "longitude": _VEGAS[1],
    }

    def _walk_to_office(self, point=_VEF_POINT, data=None):
        from noaa_it_all.config_flow import NOAAOptionsFlow
        entry = MagicMock()
        entry.data = dict(self._SAVED if data is None else data)
        entry.options = {}
        flow = NOAAOptionsFlow()
        flow._config_entry = entry
        flow.hass = MagicMock()
        with patch(
            "noaa_it_all.config_flow.async_lookup_point",
            AsyncMock(return_value=point),
        ):
            _reset_recorded_defaults()
            _run(flow.async_step_init(user_input={
                "latitude": _VEGAS[0], "longitude": _VEGAS[1],
            }))
        return flow

    def test_an_inland_office_goes_straight_to_the_radar_step(self):
        flow = self._walk_to_office()
        result = _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        self.assertEqual(result["step_id"], "radar")

    def test_inland_path_saves_every_key(self):
        flow = self._walk_to_office()
        _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 6}))
        self.assertEqual(result["data"], {
            "office_code": "VEF", "radar_site": "KESX",
            "latitude": _VEGAS[0], "longitude": _VEGAS[1], "radar_loop_hours": 6,
        })

    def test_with_nws_down_the_saved_inland_office_and_radar_are_kept(self):
        flow = self._walk_to_office(point=None)
        self.assertEqual(_recorded_defaults()["office_code"], "VEF")
        _run(flow.async_step_office(user_input={"office_code": "VEF"}))
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 6}))
        self.assertEqual(result["data"]["office_code"], "VEF")
        self.assertEqual(result["data"]["radar_site"], "KESX")

    def test_switching_to_a_coastal_office_takes_its_radar_from_the_table(self):
        from noaa_it_all.offices import radar_site
        flow = self._walk_to_office()
        _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 6}))
        self.assertEqual(result["data"]["office_code"], "SGX")
        self.assertIsNone(result["data"]["radar_site"])
        self.assertEqual(radar_site({**self._SAVED, **result["data"]}), "KNKX")

    def test_a_coastal_office_drops_a_radar_site_saved_before(self):
        """An entry saved with the table's site lets go of it on the next save."""
        flow = self._walk_to_office(data={
            **self._SAVED, "office_code": "SGX", "radar_site": "KNKX",
        })
        _run(flow.async_step_office(user_input={"office_code": "SGX"}))
        result = _run(flow.async_step_radar(user_input={"radar_loop_hours": 6}))
        self.assertIsNone(result["data"]["radar_site"])


# ---------------------------------------------------------------------------
# Entry types: weather, surf and hurricane entries
# ---------------------------------------------------------------------------

_WILMINGTON = (34.2257, -77.9447)
# The Space entry a Wilmington location flow adds.
_ILM_SPACE = {
    "entry_type": "space", "office_code": "ILM",
    "latitude": _WILMINGTON[0], "longitude": _WILMINGTON[1], "place": "Wilmington, NC",
}


class TestMenu(unittest.TestCase):
    """Add entry starts with what to add."""

    def test_offers_location_surf_marine_space_and_hurricanes(self):
        result = _run(_flow().async_step_user())
        self.assertEqual(result["type"], "menu")
        self.assertEqual(
            result["menu_options"], ["location", "surf", "marine", "space", "hurricane"]
        )

    def test_leaves_out_hurricanes_once_added(self):
        flow = _flow(entries=[_entry({"entry_type": "hurricane"})])
        self.assertEqual(
            _run(flow.async_step_user())["menu_options"], ["location", "surf", "marine", "space"]
        )


class TestLocationFlowAddsOtherEntries(unittest.TestCase):
    """A location flow adds the surf and Space entries it chose, and hurricanes the first time."""

    def _finish(self, surf="ILM", space="ILM", entries=()):
        flow = _flow(entries=entries)
        flow._latitude, flow._longitude = _WILMINGTON
        _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        _run(flow.async_step_surf(user_input={"surf_office_code": surf}))
        result = _run(flow.async_step_space(user_input={"space_office_code": space}))
        self.assertEqual(result["type"], "create_entry")
        return _added_entries(flow)

    def test_the_first_entry_adds_surf_space_and_hurricanes(self):
        self.assertEqual(self._finish(), [
            {"entry_type": "surf", "office_code": "ILM"},
            _ILM_SPACE,
            {"entry_type": "hurricane"},
        ])

    def test_a_later_location_does_not_add_hurricanes_back(self):
        """Deleting the hurricane entry is not undone by the next location."""
        added = self._finish(entries=[_entry({"entry_type": "weather", "office_code": "VEF"})])
        self.assertEqual(added, [{"entry_type": "surf", "office_code": "ILM"}, _ILM_SPACE])

    def test_nor_does_the_first_location_after_a_surf_entry(self):
        """A surf entry on its own, with hurricanes deleted, is not a fresh install."""
        added = self._finish(
            surf="none", space="none",
            entries=[_entry({"entry_type": "surf", "office_code": "SGX"})],
        )
        self.assertEqual(added, [])

    def test_an_entry_from_before_0_8_0_counts_as_weather(self):
        added = self._finish(entries=[_entry({"office_code": "SGX"})])
        self.assertNotIn({"entry_type": "hurricane"}, added)

    def test_a_surf_office_already_added_is_shared_not_added_again(self):
        added = self._finish(entries=[_entry({"entry_type": "surf", "office_code": "ILM"})])
        self.assertNotIn({"entry_type": "surf", "office_code": "ILM"}, added)

    def test_an_already_configured_location_is_refused_at_the_office_step(self):
        """Before the surf step, its NWS request, or any entry being added."""
        flow = _flow()
        flow._issuing_checked = False
        flow._latitude, flow._longitude = _WILMINGTON
        flow._abort_if_unique_id_configured = MagicMock(side_effect=RuntimeError("abort"))
        with patch("noaa_it_all.config_flow.async_issuing_surf_offices") as issuing:
            with self.assertRaises(RuntimeError):
                _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        issuing.assert_not_called()
        self.assertEqual(_added_entries(flow), [])

    def test_already_added_offices_are_labelled(self):
        from noaa_it_all.config_flow import _build_surf_options
        options, _ = _build_surf_options(*_WILMINGTON, configured={"ILM"})
        self.assertTrue(options["ILM"].endswith(" - already added"))


class TestSurfOnlyFlow(unittest.TestCase):
    """Add entry > Surf forecast: one coastal office, as its own entry."""

    def test_lists_offices_by_name_without_a_home_location(self):
        flow = _flow()
        _reset_recorded_defaults()
        result = _run(flow.async_step_surf())
        self.assertEqual(result["step_id"], "surf")
        self.assertEqual(result["description_placeholders"]["none_note"], "")
        # Alphabetical by name without a location: Boston, MA comes first.
        self.assertEqual(_recorded_defaults()["surf_office_code"], "BOX")

    def test_lists_offices_nearest_the_home_location_first(self):
        flow = _flow()
        flow.hass.config.latitude, flow.hass.config.longitude = _WILMINGTON
        _reset_recorded_defaults()
        _run(flow.async_step_surf())
        self.assertEqual(_recorded_defaults()["surf_office_code"], "ILM")

    def test_creates_the_surf_entry(self):
        flow = _flow()
        result = _run(flow.async_step_surf(user_input={"surf_office_code": "ILM"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA Surf - Wilmington, NC")
        self.assertEqual(result["data"], {"entry_type": "surf", "office_code": "ILM"})
        flow.async_set_unique_id.assert_awaited_once_with("noaa_surf_ILM")
        flow._abort_if_unique_id_configured.assert_called_once_with(
            error="surf_already_configured"
        )

    def test_offers_no_none_and_leaves_out_offices_already_added(self):
        from noaa_it_all.config_flow import _build_surf_options
        options, _ = _build_surf_options(None, None, configured={"ILM"}, offer_none=False)
        self.assertNotIn("ILM", options)
        self.assertNotIn("none", options)

    def test_none_is_not_accepted(self):
        result = _run(_flow().async_step_surf(user_input={"surf_office_code": "none"}))
        self.assertEqual(result["errors"], {"surf_office_code": "invalid_office"})

    def test_aborts_when_every_office_is_added(self):
        from noaa_it_all.config_flow import NWS_OFFICES
        flow = _flow(entries=[
            _entry({"entry_type": "surf", "office_code": code}) for code in NWS_OFFICES
        ])
        result = _run(flow.async_step_surf())
        self.assertEqual(result, {"type": "abort", "reason": "all_surf_configured"})


class TestImportAndHurricaneSteps(unittest.TestCase):
    """Surf and hurricane entries added by a location flow or an upgrade."""

    def test_import_creates_a_surf_entry(self):
        result = _run(_flow().async_step_import({"entry_type": "surf", "office_code": "SGX"}))
        self.assertEqual(result["title"], "NOAA Surf - San Diego, CA")

    def test_import_creates_the_hurricane_entry(self):
        flow = _flow()
        result = _run(flow.async_step_import({"entry_type": "hurricane"}))
        self.assertEqual(result["title"], "NOAA Hurricane")
        self.assertEqual(result["data"], {"entry_type": "hurricane"})
        flow.async_set_unique_id.assert_awaited_once_with("noaa_hurricane")
        flow._abort_if_unique_id_configured.assert_called_once_with(
            error="hurricane_already_configured"
        )

    def test_import_refuses_an_office_without_surf(self):
        for data in (
            {"entry_type": "surf", "office_code": "VEF"},
            {"entry_type": "weather", "office_code": "SGX"},
        ):
            with self.subTest(data=data):
                result = _run(_flow().async_step_import(data))
                self.assertEqual(result, {"type": "abort", "reason": "unknown_surf_office"})

    def test_the_hurricane_menu_choice_creates_the_entry(self):
        result = _run(_flow().async_step_hurricane())
        self.assertEqual(result["title"], "NOAA Hurricane")


class TestIssuingSurfOffices(unittest.TestCase):
    """Which offices have issued a Surf Zone Forecast this week."""

    _URL = "https://api.weather.gov/products/types/SRF"

    def _issuing(self, response):
        from noaa_it_all import config_flow
        with patch.object(
            config_flow, "async_get_clientsession",
            return_value=_session({self._URL: response}),
        ):
            return _run(config_flow.async_issuing_surf_offices(MagicMock()))

    def test_maps_issuing_offices_to_office_codes(self):
        result = self._issuing(_FakeResponse({"@graph": [
            {"issuingOffice": "KILM"}, {"issuingOffice": "KILM"},
            {"issuingOffice": "TJSJ"}, {"issuingOffice": "PGUM"},
            {"issuingOffice": "KVEF"}, "junk",
        ]}))
        self.assertEqual(result, {"ILM", "SJU", "GUM"})

    def test_unknown_when_nws_cannot_say(self):
        self.assertIsNone(self._issuing(_FakeResponse(error=RuntimeError("503"))))
        self.assertIsNone(self._issuing(_FakeResponse({"@graph": None})))

    def test_labels_offices_without_a_forecast_this_week(self):
        from noaa_it_all.config_flow import _build_surf_options
        options, _ = _build_surf_options(*_WILMINGTON, issuing={"ILM"})
        self.assertFalse(options["ILM"].endswith("no forecast this week"))
        self.assertTrue(options["DLH"].endswith(" - no forecast this week"))
        # Nothing is claimed when NWS could not say.
        options, _ = _build_surf_options(*_WILMINGTON, issuing=None)
        self.assertNotIn("no forecast", options["DLH"])


class TestOptionsOnlyForWeather(unittest.TestCase):
    """Configure is offered on weather entries only."""

    def test_supports_options_flow(self):
        from noaa_it_all.config_flow import NOAAConfigFlow
        for data, expected in (
            ({"entry_type": "weather", "office_code": "ILM"}, True),
            ({"office_code": "ILM"}, True),
            ({"entry_type": "surf", "office_code": "ILM"}, False),
            ({"entry_type": "space", "office_code": "ILM"}, False),
            ({"entry_type": "hurricane"}, False),
        ):
            with self.subTest(data=data):
                self.assertIs(
                    NOAAConfigFlow.async_supports_options_flow(_entry(data)), expected
                )


class TestSpaceStep(unittest.TestCase):
    """The location flow's last step: Space for the location's office."""

    def _space_form(self, entries=()):
        flow = _flow(entries=entries)
        flow._latitude, flow._longitude = _WILMINGTON
        _run(flow.async_step_office(user_input={"office_code": "ILM"}))
        _reset_recorded_defaults()
        form = _run(flow.async_step_surf(user_input={"surf_office_code": "none"}))
        return flow, form

    def _space_added(self, flow):
        return [d for d in _added_entries(flow) if d.get("entry_type") == "space"]

    def test_this_office_is_offered_and_preselected(self):
        _, form = self._space_form()
        self.assertEqual(form["step_id"], "space")
        self.assertEqual(_recorded_defaults()["space_office_code"], "ILM")

    def test_options_list_this_office_then_the_ones_already_added(self):
        from noaa_it_all.config_flow import _build_space_options
        options, default = _build_space_options("ILM", {"MQT", "BOX"})
        self.assertEqual(default, "ILM")
        self.assertEqual(options, {
            "ILM": "NOAA ILM Space - this location",
            "BOX": "NOAA BOX Space - already added",
            "MQT": "NOAA MQT Space - already added",
            "none": "No space data",
        })

    def test_an_office_with_a_space_entry_is_preselected_as_already_added(self):
        from noaa_it_all.config_flow import _build_space_options
        options, default = _build_space_options("ILM", {"ILM"})
        self.assertEqual(default, "ILM")
        self.assertEqual(options["ILM"], "NOAA ILM Space - already added")

    def test_this_office_adds_its_space_entry(self):
        flow, _ = self._space_form()
        _run(flow.async_step_space(user_input={"space_office_code": "ILM"}))
        self.assertEqual(self._space_added(flow), [_ILM_SPACE])

    def test_an_office_that_has_space_is_shared_not_added_again(self):
        flow, _ = self._space_form(entries=[_entry({"entry_type": "space", "office_code": "ILM"})])
        result = _run(flow.async_step_space(user_input={"space_office_code": "ILM"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(self._space_added(flow), [])

    def test_another_office_already_added_adds_nothing(self):
        flow, _ = self._space_form(entries=[_entry({"entry_type": "space", "office_code": "MQT"})])
        result = _run(flow.async_step_space(user_input={"space_office_code": "MQT"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(self._space_added(flow), [])

    def test_no_space_adds_nothing(self):
        flow, _ = self._space_form()
        result = _run(flow.async_step_space(user_input={"space_office_code": "none"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(self._space_added(flow), [])

    def test_an_office_not_offered_is_rejected(self):
        flow, _ = self._space_form()
        result = _run(flow.async_step_space(user_input={"space_office_code": "MQT"}))
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"space_office_code": "invalid_office"})
        self.assertEqual(_added_entries(flow), [])


class TestSpaceOnlyFlow(unittest.TestCase):
    """Add entry > Space: a location, then the office it is named after."""

    def _office_form(self, point=_VEF_POINT):
        flow = _flow()
        flow.hass.config.latitude, flow.hass.config.longitude = _VEGAS
        location_form = _run(flow.async_step_space())
        self.assertEqual(location_form["step_id"], "space_location")
        self.assertEqual(
            location_form["description_placeholders"], {"ha_location": "36.1699, -115.1398"}
        )
        with patch(
            "noaa_it_all.config_flow.async_lookup_point", AsyncMock(return_value=point),
        ):
            _reset_recorded_defaults()
            form = _run(flow.async_step_space_location(user_input={
                "latitude": _VEGAS[0], "longitude": _VEGAS[1],
            }))
        return flow, form

    def test_the_location_asks_for_the_office_nws_names(self):
        _, form = self._office_form()
        self.assertEqual(form["step_id"], "space_office")
        self.assertEqual(_recorded_defaults()["office_code"], "VEF")
        self.assertEqual(form["description_placeholders"]["warning"], "")

    def test_an_invalid_location_is_refused(self):
        result = _run(_flow().async_step_space_location(user_input={
            "latitude": 91.0, "longitude": 0.0,
        }))
        self.assertEqual(result["step_id"], "space_location")
        self.assertEqual(result["errors"], {"latitude": "invalid_latitude"})

    def test_creates_the_space_entry_named_after_the_office(self):
        flow, _ = self._office_form()
        result = _run(flow.async_step_space_office(user_input={"office_code": "VEF"}))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA Space - Las Vegas, NV")
        self.assertEqual(result["data"], {
            "entry_type": "space", "office_code": "VEF",
            "latitude": _VEGAS[0], "longitude": _VEGAS[1],
        })
        flow.async_set_unique_id.assert_awaited_with("noaa_space_VEF")
        flow._abort_if_unique_id_configured.assert_called_with(error="space_already_configured")
        # A Space entry on its own adds no other entries.
        self.assertEqual(_added_entries(flow), [])

    def test_without_an_office_for_the_location_it_is_refused(self):
        """A distant coastal office chosen here would take that office's only Space entry."""
        flow, result = self._office_form(point=None)
        self.assertEqual(result, {"type": "abort", "reason": "space_no_office"})

    def test_without_nws_a_coastal_office_nearby_is_offered(self):
        flow = _flow()
        with patch(
            "noaa_it_all.config_flow.async_lookup_point", AsyncMock(return_value=None),
        ):
            form = _run(flow.async_step_space_location(user_input={
                "latitude": _WILMINGTON[0], "longitude": _WILMINGTON[1],
            }))
        self.assertEqual(form["step_id"], "space_office")
        result = _run(flow.async_step_space_office(user_input={"office_code": "ILM"}))
        self.assertEqual(result["title"], "NOAA Space - Wilmington, NC")

    def test_an_office_not_offered_is_rejected(self):
        flow, _ = self._office_form()
        result = _run(flow.async_step_space_office(user_input={"office_code": "ILM"}))
        self.assertEqual(result["step_id"], "space_office")
        self.assertEqual(result["errors"], {"office_code": "invalid_office"})


class TestImportSpace(unittest.TestCase):
    """Space entries added by a location flow or an upgrade."""

    def test_creates_the_space_entry(self):
        flow = _flow()
        result = _run(flow.async_step_import(dict(_ILM_SPACE)))
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA Space - Wilmington, NC")
        # The place only names the entry.
        self.assertEqual(result["data"], {
            "entry_type": "space", "office_code": "ILM",
            "latitude": _WILMINGTON[0], "longitude": _WILMINGTON[1],
        })
        flow.async_set_unique_id.assert_awaited_once_with("noaa_space_ILM")
        flow._abort_if_unique_id_configured.assert_called_once_with(
            error="space_already_configured"
        )

    def test_without_a_place_the_office_names_it(self):
        for office, title in (("SGX", "NOAA Space - San Diego, CA"), ("VEF", "NOAA Space - VEF")):
            with self.subTest(office=office):
                result = _run(_flow().async_step_import({
                    "entry_type": "space", "office_code": office,
                    "latitude": 36.0, "longitude": -115.0,
                }))
                self.assertEqual(result["title"], title)

    def test_refuses_data_that_is_not_an_office_and_a_location(self):
        good = {k: v for k, v in _ILM_SPACE.items() if k != "place"}
        for change in (
            {"office_code": None}, {"office_code": "ilm"}, {"office_code": "ILMX"},
            {"latitude": None}, {"latitude": 91}, {"latitude": True},
            {"longitude": "-77.9"}, {"longitude": -181},
        ):
            with self.subTest(change=change):
                result = _run(_flow().async_step_import({**good, **change}))
                self.assertEqual(result, {"type": "abort", "reason": "invalid_space"})


# ---------------------------------------------------------------------------
# Marine entries: one zone's nearshore marine forecast
# ---------------------------------------------------------------------------

def _nsh_lot():
    with open(os.path.join(_REPO, "tests", "fixtures", "nsh_lot.txt"), encoding="utf-8") as f:
        return f.read()


class TestLookupMarineZone(unittest.TestCase):
    """async_lookup_marine_zone checks a zone with NWS before it is added."""

    _ZONE = "https://api.weather.gov/zones/marine/LMZ741"
    _LIST = "https://api.weather.gov/products/types/NSH/locations/LOT"
    _NSH = "https://api.weather.gov/products/types/NSH/locations/LOT/latest"
    _ISSUED = _FakeResponse({"@graph": [{"id": "abc"}]})

    def _lookup(self, responses, zone="LMZ741"):
        from noaa_it_all import config_flow
        with patch.object(
            config_flow, "async_get_clientsession", return_value=_session(responses)
        ):
            return _run(config_flow.async_lookup_marine_zone(MagicMock(), zone))

    def _zone(self, cwa="LOT"):
        return _FakeResponse({"properties": {
            "cwa": [cwa], "name": "Wilmette Harbor to Northerly Island IL",
        }})

    def test_a_zone_in_its_office_nearshore_forecast(self):
        result = self._lookup({
            self._ZONE: self._zone(),
            self._LIST: self._ISSUED,
            self._NSH: _FakeResponse({"productText": _nsh_lot()}),
        })
        self.assertEqual(
            result, ({"office": "LOT", "name": "Wilmette Harbor to Northerly Island IL"}, None)
        )

    def test_an_office_that_has_not_issued_for_a_day(self):
        """Its last forecast is still served, but it would show as unavailable."""
        result = self._lookup({
            self._ZONE: self._zone(),
            self._LIST: self._ISSUED,
            self._NSH: _FakeResponse({
                "issuanceTime": "2020-04-01T14:00:00+00:00", "productText": _nsh_lot(),
            }),
        })
        self.assertEqual(result, (None, "marine_forecast_stale"))

    def test_an_unknown_zone(self):
        self.assertEqual(
            self._lookup({self._ZONE: _FakeResponse(status=404)}),
            (None, "unknown_marine_zone"),
        )

    def test_a_zone_missing_from_the_nearshore_forecast(self):
        """Open-lake waters are a marine zone but not in the nearshore product."""
        result = self._lookup({
            self._ZONE: self._zone(),
            self._LIST: self._ISSUED,
            self._NSH: _FakeResponse({"productText": "nothing for this zone"}),
        })
        self.assertEqual(result, (None, "marine_zone_not_covered"))

    def test_an_office_without_a_nearshore_forecast(self):
        """It lists no products; its latest URL would answer 500, not 404."""
        result = self._lookup({
            self._ZONE: self._zone(cwa="ILM"),
            "https://api.weather.gov/products/types/NSH/locations/ILM":
                _FakeResponse({"@graph": []}),
        })
        self.assertEqual(result, (None, "marine_zone_not_covered"))

    def test_nws_unreachable(self):
        self.assertEqual(
            self._lookup({self._ZONE: _FakeResponse(error=RuntimeError("timeout"))}),
            (None, "cannot_connect"),
        )
        self.assertEqual(
            self._lookup({
                self._ZONE: self._zone(),
                self._LIST: self._ISSUED,
                self._NSH: _FakeResponse(error=RuntimeError("timeout")),
            }),
            (None, "cannot_connect"),
        )
        self.assertEqual(
            self._lookup({
                self._ZONE: self._zone(),
                self._LIST: _FakeResponse(status=500),
            }),
            (None, "cannot_connect"),
        )


class TestMarineFlow(unittest.TestCase):
    """Add entry > Nearshore marine forecast."""

    def _submit(self, zone, found=({"office": "LOT", "name": "Wilmette Harbor IL"}, None)):
        flow = _flow()
        with patch(
            "noaa_it_all.config_flow.async_lookup_marine_zone", AsyncMock(return_value=found)
        ) as lookup:
            result = _run(flow.async_step_marine(user_input={"marine_zone": zone}))
        return flow, result, lookup

    def test_shows_the_form(self):
        result = _run(_flow().async_step_marine())
        self.assertEqual(result["step_id"], "marine")
        self.assertEqual(result["errors"], {})

    def test_creates_the_marine_entry(self):
        flow, result, lookup = self._submit(" lmz741 ")
        self.assertEqual(result["type"], "create_entry")
        self.assertEqual(result["title"], "NOAA Marine - Wilmette Harbor IL")
        self.assertEqual(result["data"], {
            "entry_type": "marine", "marine_zone": "LMZ741", "office_code": "LOT",
        })
        lookup.assert_awaited_once_with(flow.hass, "LMZ741")
        flow.async_set_unique_id.assert_awaited_once_with("noaa_marine_LMZ741")
        flow._abort_if_unique_id_configured.assert_called_once_with(
            error="marine_already_configured"
        )

    def test_a_malformed_zone_is_refused_without_asking_nws(self):
        _, result, lookup = self._submit("Lake Michigan")
        self.assertEqual(result["errors"], {"marine_zone": "invalid_marine_zone"})
        lookup.assert_not_called()

    def test_nws_errors_are_shown_on_the_form(self):
        for error in ("unknown_marine_zone", "marine_zone_not_covered", "cannot_connect"):
            with self.subTest(error=error):
                _, result, _ = self._submit("LMZ741", found=(None, error))
                self.assertEqual(result["type"], "form")
                self.assertEqual(result["errors"], {"marine_zone": error})
                self.assertEqual(result["description_placeholders"], {"zone": "LMZ741"})

    def test_marine_entries_have_no_configure(self):
        from noaa_it_all.config_flow import NOAAConfigFlow
        self.assertFalse(NOAAConfigFlow.async_supports_options_flow(
            _entry({"entry_type": "marine", "marine_zone": "LMZ741", "office_code": "LOT"})
        ))
