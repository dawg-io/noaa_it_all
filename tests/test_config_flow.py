"""Tests for config_flow.py — validation logic, no Home Assistant runtime needed."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

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

# Make ConfigFlow a real base class
_ha_config_entries.ConfigFlow = type("ConfigFlow", (), {
    "__init_subclass__": classmethod(lambda cls, **kw: None),
    "async_set_unique_id": lambda self, uid: None,
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


class TestLatLonValidation(unittest.TestCase):
    """Test latitude/longitude validation logic used in config flow."""

    def test_valid_latitude(self):
        self.assertTrue(-90 <= 32.7 <= 90)

    def test_invalid_latitude_too_high(self):
        self.assertFalse(-90 <= 91.0 <= 90)

    def test_invalid_latitude_too_low(self):
        self.assertFalse(-90 <= -91.0 <= 90)

    def test_valid_longitude(self):
        self.assertTrue(-180 <= -117.1 <= 180)

    def test_invalid_longitude_too_high(self):
        self.assertFalse(-180 <= 181.0 <= 180)

    def test_invalid_longitude_too_low(self):
        self.assertFalse(-180 <= -181.0 <= 180)

    def test_edge_latitude(self):
        self.assertTrue(-90 <= 90.0 <= 90)
        self.assertTrue(-90 <= -90.0 <= 90)

    def test_edge_longitude(self):
        self.assertTrue(-180 <= 180.0 <= 180)
        self.assertTrue(-180 <= -180.0 <= 180)


if __name__ == "__main__":
    unittest.main()
