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
    # Home Assistant modules
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
    # Block noaa_it_all internal modules that have Python 3.10+ type syntax
    # (|  union annotations in parsers.py) or heavy HA runtime dependencies,
    # so importing noaa_it_all.image doesn't pull in the full coordinator stack.
    "noaa_it_all.coordinator": MagicMock(),
    "noaa_it_all.parsers": MagicMock(),
    "noaa_it_all.sensors": MagicMock(),
    "noaa_it_all.sensors.hurricanes": MagicMock(),
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
        return HurricaneOutlookImageEntity(HASS)

    def test_name(self):
        # Local name only; HA prepends "NOAA Hurricane" to form the full name.
        entity = self._make()
        self.assertEqual(entity.name, "Outlook Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, "noaa_hurricane_outlook_image")

    def test_has_entity_name(self):
        from noaa_it_all.image import HurricaneOutlookImageEntity
        self.assertTrue(HurricaneOutlookImageEntity._attr_has_entity_name)

    def test_device_info_uses_hurricane_device(self):
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        entity = self._make()
        info = entity.device_info
        self.assertIn((DOMAIN, HURRICANE_DEVICE_ID), info["identifiers"])


class TestRadarBaseReflectivityImageEntity(unittest.TestCase):
    """Tests for RadarBaseReflectivityImageEntity properties."""

    def _make(self, office="SGX", radar_site="KNKX"):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        return RadarBaseReflectivityImageEntity(HASS, office, radar_site)

    def test_name(self):
        # Local name only; HA prepends the office weather device name.
        entity = self._make()
        self.assertEqual(entity.name, "Radar Base Reflectivity")

    def test_unique_id_sgx(self):
        entity = self._make(office="SGX")
        self.assertEqual(entity.unique_id, "noaa_sgx_weather_radar_base_reflectivity")

    def test_unique_id_ilm(self):
        entity = self._make(office="ILM", radar_site="KLTX")
        self.assertEqual(entity.unique_id, "noaa_ilm_weather_radar_base_reflectivity")

    def test_unique_id_lowercase(self):
        # Office code must be lowercased in the unique_id regardless of input case.
        entity = self._make(office="SGX")
        self.assertNotIn("SGX", entity.unique_id)
        self.assertIn("sgx", entity.unique_id)

    def test_has_entity_name(self):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        self.assertTrue(RadarBaseReflectivityImageEntity._attr_has_entity_name)

    def test_entity_picture_contains_radar_site(self):
        entity = self._make(radar_site="KNKX")
        self.assertIn("KNKX", entity.entity_picture)

    def test_device_info_uses_office_weather_device(self):
        from noaa_it_all.const import DOMAIN
        entity = self._make(office="SGX")
        info = entity.device_info
        self.assertIn((DOMAIN, "noaa_SGX_weather"), info["identifiers"])

    def test_device_name(self):
        entity = self._make(office="ILM", radar_site="KLTX")
        self.assertEqual(entity.device_info["name"], "NOAA ILM Weather")


class TestRadarLoopImageEntity(unittest.TestCase):
    """Tests for RadarLoopImageEntity properties."""

    def _make(self, office="SGX", radar_site="KNKX"):
        from noaa_it_all.image import RadarLoopImageEntity
        return RadarLoopImageEntity(HASS, office, radar_site)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Radar Loop")

    def test_unique_id_sgx(self):
        entity = self._make(office="SGX")
        self.assertEqual(entity.unique_id, "noaa_sgx_weather_radar_loop")

    def test_unique_id_ilm(self):
        entity = self._make(office="ILM", radar_site="KLTX")
        self.assertEqual(entity.unique_id, "noaa_ilm_weather_radar_loop")

    def test_has_entity_name(self):
        from noaa_it_all.image import RadarLoopImageEntity
        self.assertTrue(RadarLoopImageEntity._attr_has_entity_name)


class TestGOESImageEntities(unittest.TestCase):
    """Tests for GOES satellite image entity properties."""

    def test_goes_airmass_unique_id(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        entity = GOESAirMassImageEntity(HASS)
        self.assertEqual(entity.unique_id, "noaa_hurricane_goes_air_mass")

    def test_goes_airmass_name(self):
        # Local name only; HA prepends "NOAA Hurricane".
        from noaa_it_all.image import GOESAirMassImageEntity
        entity = GOESAirMassImageEntity(HASS)
        self.assertEqual(entity.name, "GOES Air Mass")

    def test_goes_airmass_has_entity_name(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        self.assertTrue(GOESAirMassImageEntity._attr_has_entity_name)

    def test_goes_airmass_device_info_uses_hurricane_device(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        entity = GOESAirMassImageEntity(HASS)
        self.assertIn((DOMAIN, HURRICANE_DEVICE_ID), entity.device_info["identifiers"])

    def test_goes_geocolor_unique_id(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        entity = GOESGeoColorImageEntity(HASS)
        self.assertEqual(entity.unique_id, "noaa_hurricane_goes_geocolor")

    def test_goes_geocolor_name(self):
        # Local name only; HA prepends "NOAA Hurricane".
        from noaa_it_all.image import GOESGeoColorImageEntity
        entity = GOESGeoColorImageEntity(HASS)
        self.assertEqual(entity.name, "GOES Geocolor")

    def test_goes_geocolor_has_entity_name(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        self.assertTrue(GOESGeoColorImageEntity._attr_has_entity_name)

    def test_goes_geocolor_device_info_uses_hurricane_device(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        entity = GOESGeoColorImageEntity(HASS)
        self.assertIn((DOMAIN, HURRICANE_DEVICE_ID), entity.device_info["identifiers"])


class TestTwoOfficeSetup(unittest.TestCase):
    """Verify entity structure when two NWS offices (ILM and SGX) are configured.

    These tests exercise entity properties directly — the async_setup_entry
    deduplication logic is tested separately in integration tests.  Here we
    confirm that:
      - Hurricane entities always attach to the shared NOAA Hurricane device.
      - Radar entities attach to their respective office weather device.
      - Unique-IDs are distinct across offices and do not collide with the
        global hurricane entity IDs.
    """

    def _make_hurricane_entities(self):
        from noaa_it_all.image import (
            HurricaneOutlookImageEntity,
            GOESAirMassImageEntity,
            GOESGeoColorImageEntity,
        )
        return [
            HurricaneOutlookImageEntity(HASS),
            GOESAirMassImageEntity(HASS),
            GOESGeoColorImageEntity(HASS),
        ]

    def _make_radar_entity(self, office, radar_site):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        return RadarBaseReflectivityImageEntity(HASS, office, radar_site)

    # ------------------------------------------------------------------
    # Hurricane entities are global — created once regardless of offices
    # ------------------------------------------------------------------

    def test_hurricane_entities_unique_ids_are_global(self):
        """Hurricane entity unique_ids must not contain an office code."""
        entities = self._make_hurricane_entities()
        for entity in entities:
            self.assertNotIn("ilm", entity.unique_id)
            self.assertNotIn("sgx", entity.unique_id)

    def test_hurricane_entities_attach_to_hurricane_device(self):
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        for entity in self._make_hurricane_entities():
            self.assertIn(
                (DOMAIN, HURRICANE_DEVICE_ID),
                entity.device_info["identifiers"],
                msg=f"{entity.__class__.__name__} must use the NOAA Hurricane device",
            )

    def test_hurricane_entity_ids_are_stable(self):
        """Hurricane unique_ids are constant — not per-office."""
        entities = self._make_hurricane_entities()
        self.assertEqual(entities[0].unique_id, "noaa_hurricane_outlook_image")
        self.assertEqual(entities[1].unique_id, "noaa_hurricane_goes_air_mass")
        self.assertEqual(entities[2].unique_id, "noaa_hurricane_goes_geocolor")

    # ------------------------------------------------------------------
    # Radar entities are per-office
    # ------------------------------------------------------------------

    def test_radar_unique_ids_differ_per_office(self):
        ilm_radar = self._make_radar_entity("ILM", "KLTX")
        sgx_radar = self._make_radar_entity("SGX", "KNKX")
        self.assertNotEqual(ilm_radar.unique_id, sgx_radar.unique_id)

    def test_ilm_radar_unique_id(self):
        entity = self._make_radar_entity("ILM", "KLTX")
        self.assertEqual(entity.unique_id, "noaa_ilm_weather_radar_base_reflectivity")

    def test_sgx_radar_unique_id(self):
        entity = self._make_radar_entity("SGX", "KNKX")
        self.assertEqual(entity.unique_id, "noaa_sgx_weather_radar_base_reflectivity")

    def test_ilm_radar_attaches_to_ilm_weather_device(self):
        from noaa_it_all.const import DOMAIN
        entity = self._make_radar_entity("ILM", "KLTX")
        self.assertIn((DOMAIN, "noaa_ILM_weather"), entity.device_info["identifiers"])
        self.assertEqual(entity.device_info["name"], "NOAA ILM Weather")

    def test_sgx_radar_attaches_to_sgx_weather_device(self):
        from noaa_it_all.const import DOMAIN
        entity = self._make_radar_entity("SGX", "KNKX")
        self.assertIn((DOMAIN, "noaa_SGX_weather"), entity.device_info["identifiers"])
        self.assertEqual(entity.device_info["name"], "NOAA SGX Weather")

    def test_radar_entities_do_not_use_hurricane_device(self):
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        for office, site in [("ILM", "KLTX"), ("SGX", "KNKX")]:
            entity = self._make_radar_entity(office, site)
            self.assertNotIn(
                (DOMAIN, HURRICANE_DEVICE_ID),
                entity.device_info["identifiers"],
                msg=f"Radar entity for {office} must NOT use the hurricane device",
            )

    # ------------------------------------------------------------------
    # No forbidden entity ID patterns
    # ------------------------------------------------------------------

    def test_no_noaa_weather_prefix_in_hurricane_unique_ids(self):
        for entity in self._make_hurricane_entities():
            self.assertFalse(
                entity.unique_id.startswith("noaa_weather_"),
                msg=f"{entity.unique_id} must not start with noaa_weather_",
            )

    def test_no_office_suffix_in_radar_unique_id(self):
        """Old pattern was noaa_{office}_radar_base_reflectivity (no 'weather')."""
        for office, site in [("ILM", "KLTX"), ("SGX", "KNKX")]:
            entity = self._make_radar_entity(office, site)
            # New pattern must contain 'weather' between office and radar name
            self.assertIn("weather", entity.unique_id)
            # Old pattern ended with the office code — ensure it now ends with
            # the entity slug, not the office code
            self.assertFalse(
                entity.unique_id.endswith(f"_{office.lower()}"),
                msg=f"{entity.unique_id} must not end with the office code",
            )

    def test_all_hurricane_entity_names_are_local_only(self):
        """With has_entity_name=True the name must be the local part only."""
        entities = self._make_hurricane_entities()
        local_names = {e.name for e in entities}
        for name in local_names:
            self.assertNotIn("NOAA Hurricane", name,
                             msg=f"Name '{name}' must be local-only, not include device name")
            self.assertNotIn("NOAA Satellite", name,
                             msg=f"Name '{name}' must not include legacy 'NOAA Satellite' prefix")

    def test_radar_entity_name_is_local_only(self):
        """Radar entity name must not embed the office code or device prefix."""
        entity = self._make_radar_entity("ILM", "KLTX")
        self.assertEqual(entity.name, "Radar Base Reflectivity")
        self.assertNotIn("ILM", entity.name)
        self.assertNotIn("NOAA Weather", entity.name)


if __name__ == "__main__":
    unittest.main()
