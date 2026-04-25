"""Tests for image.py entity properties using mocked HA modules."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_image = MagicMock()
_ha_entity = MagicMock()
_ha_coordinator = MagicMock()

# Make ImageEntity a proper base class that accepts hass in __init__
_ha_image.ImageEntity = type("ImageEntity", (), {
    "__init__": lambda self, hass: setattr(self, "hass", hass),
})

_ha_entity.DeviceInfo = dict
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.image": _ha_image,
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.weather": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
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


OFFICE = "SGX"
HASS = MagicMock()


class TestGeoelectricFieldImageEntity(unittest.TestCase):
    """Tests for GeoelectricFieldImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import GeoelectricFieldImageEntity
        return GeoelectricFieldImageEntity(HASS, OFFICE)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Geoelectric Field Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, f"noaa_{OFFICE}_geoelectric_image")

    def test_entity_picture_is_url(self):
        entity = self._make()
        self.assertTrue(entity.entity_picture.startswith("https://"))
        self.assertIn("geoelectric", entity.entity_picture)

    def test_cache_bust_contains_timestamp(self):
        entity = self._make()
        self.assertIn("?t=", entity.entity_picture)

    def test_device_info(self):
        entity = self._make()
        info = entity.device_info
        self.assertIn("identifiers", info)
        self.assertIn("manufacturer", info)


class TestAuroraForecastImageEntity(unittest.TestCase):
    """Tests for AuroraForecastImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import AuroraForecastImageEntity
        return AuroraForecastImageEntity(HASS, OFFICE)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Aurora Forecast Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, f"noaa_{OFFICE}_aurora_image")

    def test_entity_picture_is_url(self):
        entity = self._make()
        self.assertTrue(entity.entity_picture.startswith("https://"))
        self.assertIn("ovation", entity.entity_picture)

    def test_cache_bust_contains_timestamp(self):
        entity = self._make()
        self.assertIn("?t=", entity.entity_picture)

    def test_device_info(self):
        entity = self._make()
        info = entity.device_info
        self.assertIn("identifiers", info)
        self.assertIn("manufacturer", info)


class TestHurricaneOutlookImageEntity(unittest.TestCase):
    """Tests for HurricaneOutlookImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import HurricaneOutlookImageEntity
        return HurricaneOutlookImageEntity(HASS, OFFICE)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Hurricane Outlook Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, "noaa_hurricane_outlook_image")


class TestRadarBaseReflectivityImageEntity(unittest.TestCase):
    """Tests for RadarBaseReflectivityImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        return RadarBaseReflectivityImageEntity(HASS, OFFICE, "KNKX")

    def test_name(self):
        entity = self._make()
        self.assertIn(OFFICE, entity.name)

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, f"noaa_{OFFICE}_radar_base_reflectivity")

    def test_entity_picture_contains_radar_site(self):
        entity = self._make()
        self.assertIn("KNKX", entity.entity_picture)


class TestRadarLoopImageEntity(unittest.TestCase):
    """Tests for RadarLoopImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import RadarLoopImageEntity
        return RadarLoopImageEntity(HASS, OFFICE, "KNKX")

    def test_name(self):
        entity = self._make()
        self.assertIn(OFFICE, entity.name)

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, f"noaa_{OFFICE}_radar_loop")


class TestGOESImageEntities(unittest.TestCase):
    """Tests for GOES satellite image entity properties."""

    def test_goes_airmass_unique_id(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        entity = GOESAirMassImageEntity(HASS, OFFICE)
        self.assertEqual(entity.unique_id, "noaa_goes_airmass_image")

    def test_goes_airmass_name(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        entity = GOESAirMassImageEntity(HASS, OFFICE)
        self.assertEqual(entity.name, "NOAA Satellite - GOES Air Mass")

    def test_goes_geocolor_unique_id(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        entity = GOESGeoColorImageEntity(HASS, OFFICE)
        self.assertEqual(entity.unique_id, "noaa_goes_geocolor_image")

    def test_goes_geocolor_name(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        entity = GOESGeoColorImageEntity(HASS, OFFICE)
        self.assertEqual(entity.name, "NOAA Satellite - GOES GeoColor")


if __name__ == "__main__":
    unittest.main()
