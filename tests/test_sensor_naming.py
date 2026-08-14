"""Tests for sensor entity naming convention: sensor.noaa_{office}_{metric}.

Verifies that all location-specific sensors include the office code in
their name and unique_id, matching the README documented format.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Ensure the custom_components directory is on sys.path so that
# ``noaa_it_all`` resolves as a package and relative imports work.
# ---------------------------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules — scoped so they don't leak into other tests
# ---------------------------------------------------------------------------

_ha_entity = MagicMock()
_ha_coordinator = MagicMock()
_ha_binary = MagicMock()
_ha_weather_mod = MagicMock()
_ha_const = MagicMock()
_ha_config_entries = MagicMock()
_ha_core = MagicMock()
_ha_platform = MagicMock()

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.entity_platform": _ha_platform,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.binary_sensor": _ha_binary,
    "homeassistant.components.weather": _ha_weather_mod,
    "homeassistant.const": _ha_const,
    "homeassistant.config_entries": _ha_config_entries,
    "homeassistant.core": _ha_core,
    "aiohttp": MagicMock(),
}

# Make CoordinatorEntity a plain base class for testing
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})

# Make DeviceInfo a simple dict-like for testing
_ha_entity.DeviceInfo = dict

# BinarySensorEntity stub
_ha_binary.BinarySensorEntity = type("BinarySensorEntity", (), {})

_patcher = None


def setUpModule():
    """Install HA mocks into sys.modules for this test module only."""
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    """Remove HA mocks from sys.modules."""
    if _patcher is not None:
        _patcher.stop()


OFFICE = "SGX"
COORD = MagicMock()
COORD.data = None
LAT = 32.7157
LON = -117.1611


def _slugify(value):
    """Lowercase and underscore a name the way Home Assistant's slugify does.

    Every run of non-alphanumeric characters collapses to a single underscore, so "Flood/Winter
    Alert" becomes "flood_winter_alert" — the slash becomes a separator rather than being
    dropped. Confirmed against a live Home Assistant instance, which registered
    ``binary_sensor.noaa_ilm_weather_flood_winter_alert``.
    """
    import re
    return re.sub(r'[^a-z0-9]+', '_', value.lower()).strip('_')


def _entity_id_slug(sensor):
    """Derive the entity ID slug as HA does for _attr_has_entity_name=True entities.

    HA combines slugify(device_name) + "_" + slugify(local_name).
    """
    dev_name = sensor.device_info.get('name', '') if isinstance(sensor.device_info, dict) else ''
    return _slugify(dev_name) + '_' + _slugify(sensor.name)


# ---------------------------------------------------------------------------
# Weather observation sensors
# ---------------------------------------------------------------------------

class TestWeatherObservationNaming(unittest.TestCase):
    """Verify weather observation sensor names include the office code."""

    def _make(self, cls, **kwargs):
        return cls(COORD, OFFICE, latitude=LAT, longitude=LON, **kwargs)

    def test_temperature_name(self):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        s = self._make(TemperatureSensor)
        self.assertEqual(s.name, "Temperature")

    def test_humidity_name(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        s = self._make(HumiditySensor)
        self.assertEqual(s.name, "Humidity")

    def test_wind_speed_name(self):
        from noaa_it_all.sensors.weather_observations import WindSpeedSensor
        s = self._make(WindSpeedSensor)
        self.assertEqual(s.name, "Wind Speed")

    def test_wind_direction_name(self):
        from noaa_it_all.sensors.weather_observations import WindDirectionSensor
        s = self._make(WindDirectionSensor)
        self.assertEqual(s.name, "Wind Direction")

    def test_barometric_pressure_name(self):
        from noaa_it_all.sensors.weather_observations import BarometricPressureSensor
        s = self._make(BarometricPressureSensor)
        self.assertEqual(s.name, "Barometric Pressure")

    def test_dewpoint_name(self):
        from noaa_it_all.sensors.weather_observations import DewpointSensor
        s = self._make(DewpointSensor)
        self.assertEqual(s.name, "Dewpoint")

    def test_visibility_name(self):
        from noaa_it_all.sensors.weather_observations import VisibilitySensor
        s = self._make(VisibilitySensor)
        self.assertEqual(s.name, "Visibility")

    def test_sky_conditions_name(self):
        from noaa_it_all.sensors.weather_observations import SkyConditionsSensor
        s = self._make(SkyConditionsSensor)
        self.assertEqual(s.name, "Sky Conditions")

    def test_feels_like_name(self):
        from noaa_it_all.sensors.weather_observations import FeelsLikeSensor
        s = self._make(FeelsLikeSensor)
        self.assertEqual(s.name, "Feels Like")

    def test_unique_id_contains_office(self):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        s = self._make(TemperatureSensor)
        uid = s.unique_id
        self.assertIn(OFFICE.lower(), uid.lower())
        self.assertTrue(uid.startswith("noaa_"))


# ---------------------------------------------------------------------------
# Space weather sensors (location-specific aurora & solar)
# ---------------------------------------------------------------------------

class TestSpaceWeatherNaming(unittest.TestCase):
    """Verify space-weather sensor names include the office code."""

    def test_aurora_next_time_name(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        s = AuroraNextTimeSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Aurora Next Time")

    def test_aurora_next_time_unique_id(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        s = AuroraNextTimeSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_aurora_next_time")

    def test_aurora_duration_name(self):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        s = AuroraDurationSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Aurora Duration")

    def test_aurora_duration_unique_id(self):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        s = AuroraDurationSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_aurora_duration")

    def test_aurora_visibility_probability_name(self):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        s = AuroraVisibilityProbabilitySensor(COORD, OFFICE)
        self.assertEqual(s.name, "Aurora Visibility Probability")

    def test_aurora_visibility_probability_unique_id(self):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        s = AuroraVisibilityProbabilitySensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_aurora_visibility_probability")

    def test_solar_radiation_name(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        s = SolarRadiationStormAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Solar Radiation Storm Alerts")

    def test_solar_radiation_unique_id(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        s = SolarRadiationStormAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_solar_radiation_storm_alerts")


# ---------------------------------------------------------------------------
# Surf sensors
# ---------------------------------------------------------------------------

class TestSurfNaming(unittest.TestCase):
    """Verify surf sensor names include the office code."""

    def test_rip_current_name(self):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        s = RipCurrentRiskSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Rip Current Risk")

    def test_rip_current_unique_id(self):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        s = RipCurrentRiskSensor(COORD, OFFICE)
        self.assertEqual(s._attr_unique_id, f"noaa_{OFFICE}_rip_current_risk")

    def test_surf_height_name(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Surf Height")

    def test_surf_height_unique_id(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertEqual(s._attr_unique_id, f"noaa_{OFFICE}_surf_height")

    def test_water_temperature_name(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        s = WaterTemperatureSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Water Temperature")

    def test_water_temperature_unique_id(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        s = WaterTemperatureSensor(COORD, OFFICE)
        self.assertEqual(s._attr_unique_id, f"noaa_{OFFICE}_water_temperature")


# ---------------------------------------------------------------------------
# Forecast sensors
# ---------------------------------------------------------------------------

class TestForecastNaming(unittest.TestCase):
    """Verify forecast sensor names include the office code."""

    def test_extended_forecast_name(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.name, "Extended Forecast")

    def test_extended_forecast_unique_id(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        uid = s.unique_id
        self.assertIn(OFFICE.lower(), uid.lower())
        self.assertTrue(uid.startswith("noaa_"))

    def test_hourly_forecast_name(self):
        from noaa_it_all.sensors.forecasts import HourlyForecastSensor
        s = HourlyForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.name, "Hourly Forecast")

    def test_extended_forecast_suggested_object_id(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertTrue(s._attr_has_entity_name)
        expected = f"noaa_{OFFICE.lower()}_weather_extended_forecast"
        self.assertEqual(_entity_id_slug(s), expected)

    def test_hourly_forecast_suggested_object_id(self):
        from noaa_it_all.sensors.forecasts import HourlyForecastSensor
        s = HourlyForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertTrue(s._attr_has_entity_name)
        expected = f"noaa_{OFFICE.lower()}_weather_hourly_forecast"
        self.assertEqual(_entity_id_slug(s), expected)


# ---------------------------------------------------------------------------
# Alerts sensor
# ---------------------------------------------------------------------------

class TestAlertsNaming(unittest.TestCase):
    """Verify NWS alerts sensor name includes the office code."""

    def test_nws_alerts_name(self):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        s = NWSAlertsSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.name, "Active NWS Alerts")

    def test_nws_alerts_unique_id(self):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        s = NWSAlertsSensor(COORD, OFFICE, LAT, LON)
        uid = s.unique_id
        self.assertIn(OFFICE.lower(), uid.lower())
        self.assertTrue(uid.startswith("noaa_"))


# ---------------------------------------------------------------------------
# Weather extra sensors
# ---------------------------------------------------------------------------

class TestWeatherExtraNaming(unittest.TestCase):
    """Verify extra weather sensor names include the office code."""

    def test_cloud_cover_name(self):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        s = CloudCoverSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.name, "Cloud Cover")

    def test_cloud_cover_unique_id(self):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        s = CloudCoverSensor(COORD, OFFICE, LAT, LON)
        uid = s.unique_id
        self.assertIn(OFFICE.lower(), uid.lower())
        self.assertTrue(uid.startswith("noaa_"))

    def test_radar_timestamp_name(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Radar Timestamp")

    def test_radar_timestamp_unique_id(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_radar_timestamp")

    def test_forecast_discussion_name(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertEqual(s.name, "Forecast Discussion")

    def test_forecast_discussion_unique_id(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_forecast_discussion")


# ---------------------------------------------------------------------------
# Cross-cutting: all names should slug to noaa_{office}_*
# ---------------------------------------------------------------------------

class TestNamingConventionFormat(unittest.TestCase):
    """Verify all office-grouped sensors produce entity IDs prefixed noaa_{office}_."""

    def test_all_names_produce_correct_entity_prefix(self):
        """Every location sensor's device+name combination must produce an entity ID
        starting with 'noaa_{office}_' when combined using HA's has_entity_name logic."""
        from noaa_it_all.sensors.weather_observations import (
            TemperatureSensor, HumiditySensor, WindSpeedSensor,
            WindDirectionSensor, BarometricPressureSensor, DewpointSensor,
            VisibilitySensor, SkyConditionsSensor, FeelsLikeSensor,
        )
        from noaa_it_all.sensors.space_weather import (
            AuroraNextTimeSensor, AuroraDurationSensor,
            AuroraVisibilityProbabilitySensor, SolarRadiationStormAlertsSensor,
        )
        from noaa_it_all.sensors.surf import (
            RipCurrentRiskSensor, SurfHeightSensor, WaterTemperatureSensor,
        )
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor, HourlyForecastSensor
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        from noaa_it_all.sensors.weather_extra import (
            CloudCoverSensor, RadarTimestampSensor, ForecastDiscussionSensor,
        )

        obs = [cls(COORD, OFFICE, latitude=LAT, longitude=LON)
               for cls in (TemperatureSensor, HumiditySensor, WindSpeedSensor,
                           WindDirectionSensor, BarometricPressureSensor,
                           DewpointSensor, VisibilitySensor,
                           SkyConditionsSensor, FeelsLikeSensor)]
        space = [cls(COORD, OFFICE)
                 for cls in (AuroraNextTimeSensor, AuroraDurationSensor,
                             AuroraVisibilityProbabilitySensor,
                             SolarRadiationStormAlertsSensor)]
        surf = [cls(COORD, OFFICE)
                for cls in (RipCurrentRiskSensor, SurfHeightSensor,
                            WaterTemperatureSensor)]
        forecasts = [cls(COORD, OFFICE, LAT, LON)
                     for cls in (ExtendedForecastSensor, HourlyForecastSensor)]
        alerts = [NWSAlertsSensor(COORD, OFFICE, LAT, LON)]
        extras_with_location = [CloudCoverSensor(COORD, OFFICE, LAT, LON)]
        extras_office_only = [cls(COORD, OFFICE)
                              for cls in (RadarTimestampSensor, ForecastDiscussionSensor)]

        all_sensors = obs + space + surf + forecasts + alerts + extras_with_location + extras_office_only

        expected_prefix = f"noaa_{OFFICE.lower()}_"
        for sensor in all_sensors:
            slug = _entity_id_slug(sensor)
            self.assertTrue(
                slug.startswith(expected_prefix),
                f"{type(sensor).__name__}: entity slug '{slug}' does not start with '{expected_prefix}'"
            )


# ---------------------------------------------------------------------------
# Device grouping: all entities use the same device per office
# ---------------------------------------------------------------------------


class TestDeviceInfoGrouping(unittest.TestCase):
    """Verify entities are grouped into per-office + per-domain devices."""

    def _expected_weather(self):
        from noaa_it_all.const import DOMAIN
        return {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}_weather")},
            "name": f"NOAA {OFFICE} Weather",
            "manufacturer": "NOAA",
        }

    def _expected_surf(self):
        from noaa_it_all.const import DOMAIN
        return {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}_surf")},
            "name": f"NOAA {OFFICE} Surf",
            "manufacturer": "NOAA",
        }

    def _expected_space(self):
        from noaa_it_all.const import DOMAIN
        return {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}_space")},
            "name": f"NOAA {OFFICE} Space",
            "manufacturer": "NOAA",
        }

    def _expected_hurricane(self):
        from noaa_it_all.const import (
            DOMAIN, HURRICANE_DEVICE_ID, HURRICANE_DEVICE_NAME,
        )
        return {
            "identifiers": {(DOMAIN, HURRICANE_DEVICE_ID)},
            "name": HURRICANE_DEVICE_NAME,
            "manufacturer": "NOAA",
        }

    # -- weather device -------------------------------------------------------

    def test_temperature_device_info(self):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        s = TemperatureSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertEqual(s.device_info, self._expected_weather())

    def test_humidity_device_info(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        s = HumiditySensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertEqual(s.device_info, self._expected_weather())

    def test_hurricane_alerts_device_info(self):
        from noaa_it_all.sensors.hurricanes import HurricaneAlertsSensor
        s = HurricaneAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_hurricane())

    def test_hurricane_activity_device_info(self):
        from noaa_it_all.sensors.hurricanes import HurricaneActivitySensor
        s = HurricaneActivitySensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_hurricane())

    def test_extended_forecast_device_info(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.device_info, self._expected_weather())

    def test_nws_alerts_device_info(self):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        s = NWSAlertsSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.device_info, self._expected_weather())

    def test_cloud_cover_device_info(self):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        s = CloudCoverSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.device_info, self._expected_weather())

    def test_radar_timestamp_device_info(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_weather())

    def test_forecast_discussion_device_info(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_weather())

    # -- surf device ----------------------------------------------------------

    def test_rip_current_device_info(self):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        s = RipCurrentRiskSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_surf())

    def test_surf_height_device_info(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_surf())

    def test_water_temperature_device_info(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        s = WaterTemperatureSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_surf())

    # -- space device ---------------------------------------------------------

    def test_geomagnetic_device_info(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensor
        s = GeomagneticSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_space())

    def test_kp_index_device_info(self):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensor
        s = PlanetaryKIndexSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_space())

    def test_aurora_next_time_device_info(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        s = AuroraNextTimeSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_space())

    def test_solar_radiation_device_info(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        s = SolarRadiationStormAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_space())

    # -- cross-cutting: same-domain sensors share their device ----------------

    def test_weather_sensors_share_device(self):
        """All weather-domain sensors share 'NOAA {OFFICE} Weather'."""
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor

        sensors = [
            TemperatureSensor(COORD, OFFICE, latitude=LAT, longitude=LON),
            ExtendedForecastSensor(COORD, OFFICE, LAT, LON),
            NWSAlertsSensor(COORD, OFFICE, LAT, LON),
            CloudCoverSensor(COORD, OFFICE, LAT, LON),
        ]
        expected = self._expected_weather()
        for sensor in sensors:
            self.assertEqual(
                sensor.device_info, expected,
                f"{type(sensor).__name__}.device_info should be Weather device"
            )

    def test_hurricane_sensors_share_device(self):
        """All hurricane-domain sensors share the global 'NOAA Hurricane' device."""
        from noaa_it_all.sensors.hurricanes import (
            HurricaneAlertsSensor, HurricaneActivitySensor,
        )
        sensors = [
            HurricaneAlertsSensor(COORD, OFFICE),
            HurricaneActivitySensor(COORD, OFFICE),
        ]
        expected = self._expected_hurricane()
        for sensor in sensors:
            self.assertEqual(
                sensor.device_info, expected,
                f"{type(sensor).__name__}.device_info should be Hurricane device"
            )

    def test_surf_sensors_share_device(self):
        """All surf-domain sensors share 'NOAA {OFFICE} Surf'."""
        from noaa_it_all.sensors.surf import (
            RipCurrentRiskSensor, SurfHeightSensor, WaterTemperatureSensor,
        )
        sensors = [
            RipCurrentRiskSensor(COORD, OFFICE),
            SurfHeightSensor(COORD, OFFICE),
            WaterTemperatureSensor(COORD, OFFICE),
        ]
        expected = self._expected_surf()
        for sensor in sensors:
            self.assertEqual(
                sensor.device_info, expected,
                f"{type(sensor).__name__}.device_info should be Surf device"
            )

    def test_space_sensors_share_device(self):
        """All space-domain sensors share 'NOAA {OFFICE} Space'."""
        from noaa_it_all.sensors.space_weather import (
            GeomagneticSensor, AuroraNextTimeSensor,
        )
        from noaa_it_all.sensors.meteor_showers import (
            MeteorShowerActivitySensor, NextMeteorShowerSensor, MeteorViewingScoreSensor,
        )
        sensors = [
            GeomagneticSensor(COORD, OFFICE),
            AuroraNextTimeSensor(COORD, OFFICE),
            MeteorShowerActivitySensor(COORD, OFFICE),
            NextMeteorShowerSensor(COORD, OFFICE),
            MeteorViewingScoreSensor(COORD, OFFICE),
        ]
        expected = self._expected_space()
        for sensor in sensors:
            self.assertEqual(
                sensor.device_info, expected,
                f"{type(sensor).__name__}.device_info should be Space device"
            )


# ---------------------------------------------------------------------------
# Comprehensive suggested_object_id tests (format verification)
# ---------------------------------------------------------------------------

class TestSuggestedObjectIdFormat(unittest.TestCase):
    """Verify all office-grouped sensors produce the correct entity ID via has_entity_name.

    With _attr_has_entity_name=True, HA derives the entity ID as:
        slugify(device_name) + "_" + slugify(local_name)

    These tests verify that combination matches the expected noaa_[office]_[domain]_[metric]
    pattern for every sensor type.
    """

    # Weather observation sensors
    def test_temperature_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        s = TemperatureSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_temperature")

    def test_humidity_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        s = HumiditySensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_humidity")

    def test_wind_speed_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import WindSpeedSensor
        s = WindSpeedSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_wind_speed")

    def test_wind_direction_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import WindDirectionSensor
        s = WindDirectionSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_wind_direction")

    def test_barometric_pressure_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import BarometricPressureSensor
        s = BarometricPressureSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_barometric_pressure")

    def test_dewpoint_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import DewpointSensor
        s = DewpointSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_dewpoint")

    def test_visibility_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import VisibilitySensor
        s = VisibilitySensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_visibility")

    def test_sky_conditions_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import SkyConditionsSensor
        s = SkyConditionsSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_sky_conditions")

    def test_feels_like_suggested_object_id(self):
        from noaa_it_all.sensors.weather_observations import FeelsLikeSensor
        s = FeelsLikeSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_feels_like")

    # Forecast sensors
    def test_extended_forecast_suggested_object_id_complete(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_extended_forecast")

    def test_hourly_forecast_suggested_object_id_complete(self):
        from noaa_it_all.sensors.forecasts import HourlyForecastSensor
        s = HourlyForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_hourly_forecast")

    # Surf sensors
    def test_rip_current_risk_suggested_object_id(self):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        s = RipCurrentRiskSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_surf_rip_current_risk")

    def test_surf_height_suggested_object_id(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_surf_surf_height")

    def test_water_temperature_suggested_object_id(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        s = WaterTemperatureSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_surf_water_temperature")

    # Space weather sensors
    def test_geomagnetic_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensor
        s = GeomagneticSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_geomagnetic_storm")

    def test_geomagnetic_interpretation_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensorInterpretation
        s = GeomagneticSensorInterpretation(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_geomagnetic_storm_interpretation")

    def test_planetary_k_index_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensor
        s = PlanetaryKIndexSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_planetary_k_index")

    def test_planetary_k_index_rating_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensorRating
        s = PlanetaryKIndexSensorRating(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_planetary_k_index_rating")

    def test_aurora_next_time_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        s = AuroraNextTimeSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_aurora_next_time")

    def test_aurora_duration_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        s = AuroraDurationSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_aurora_duration")

    def test_aurora_visibility_probability_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        s = AuroraVisibilityProbabilitySensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_aurora_visibility_probability")

    def test_solar_radiation_storm_alerts_suggested_object_id(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        s = SolarRadiationStormAlertsSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_solar_radiation_storm_alerts")

    # Meteor shower sensors
    def test_meteor_shower_activity_suggested_object_id(self):
        from noaa_it_all.sensors.meteor_showers import MeteorShowerActivitySensor
        s = MeteorShowerActivitySensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_meteor_shower_activity")

    def test_next_meteor_shower_suggested_object_id(self):
        from noaa_it_all.sensors.meteor_showers import NextMeteorShowerSensor
        s = NextMeteorShowerSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_next_meteor_shower")

    def test_meteor_viewing_score_suggested_object_id(self):
        from noaa_it_all.sensors.meteor_showers import MeteorViewingScoreSensor
        s = MeteorViewingScoreSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_meteor_viewing_score")

    def test_meteor_unique_ids_keep_uppercase_office_and_omit_group(self):
        """unique_id keeps the office uppercase and drops the 'space' segment.

        This asymmetry with the entity ID is long-standing in this integration; new entities
        must match it or existing installs would see duplicate entities on upgrade.
        """
        from noaa_it_all.sensors.meteor_showers import (
            MeteorShowerActivitySensor, NextMeteorShowerSensor, MeteorViewingScoreSensor,
        )
        cases = [
            (MeteorShowerActivitySensor, f"noaa_{OFFICE}_meteor_shower_activity"),
            (NextMeteorShowerSensor, f"noaa_{OFFICE}_next_meteor_shower"),
            (MeteorViewingScoreSensor, f"noaa_{OFFICE}_meteor_viewing_score"),
        ]
        for cls, expected in cases:
            self.assertEqual(cls(COORD, OFFICE).unique_id, expected)

    def test_meteor_binary_sensor_object_id(self):
        """The meteor binary sensor opts into has_entity_name so it lands on the Space device."""
        from noaa_it_all.binary_sensor import MeteorShowerActiveBinarySensor
        s = MeteorShowerActiveBinarySensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_space_meteor_shower_active")
        self.assertEqual(s._attr_unique_id, f"noaa_{OFFICE}_meteor_shower_active")

    # Weather extra sensors
    def test_cloud_cover_suggested_object_id(self):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        s = CloudCoverSensor(COORD, OFFICE, LAT, LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_cloud_cover")

    def test_radar_timestamp_suggested_object_id(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_radar_timestamp")

    def test_forecast_discussion_suggested_object_id(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_forecast_discussion")

    # Alerts sensor
    def test_nws_alerts_suggested_object_id(self):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        s = NWSAlertsSensor(COORD, OFFICE, LAT, LON)
        self.assertTrue(s._attr_has_entity_name)
        self.assertEqual(_entity_id_slug(s), f"noaa_{OFFICE.lower()}_weather_active_nws_alerts")


# ---------------------------------------------------------------------------
# Binary sensors must not repeat the device prefix
# ---------------------------------------------------------------------------

class TestBinarySensorNaming(unittest.TestCase):
    """Binary sensor names must be local-only, so the device prefix is not duplicated.

    A binary sensor that sets a full ``_attr_name`` such as ``NOAA ILM Unsafe to Swim`` *and*
    carries a device gets that device's name prepended again, producing
    ``binary_sensor.noaa_ilm_surf_noaa_ilm_unsafe_to_swim`` and the friendly name
    "NOAA ILM Surf NOAA ILM Unsafe to Swim". This was observed on a live Home Assistant
    instance. The fix is ``_attr_has_entity_name = True`` plus a local-only name, which is
    also what every sensor in this integration does.
    """

    @staticmethod
    def _local_name(sensor):
        """Return the entity's local name the way Home Assistant resolves it.

        Real ``Entity.name`` falls back to ``_attr_name``; the stubbed CoordinatorEntity used by
        these tests has no such property, so classes that set ``_attr_name`` in ``__init__``
        instead of defining a ``name`` property need that fallback applied here.
        """
        name = getattr(sensor, "name", None)
        return name if isinstance(name, str) else sensor._attr_name

    def _all_binary_sensors(self):
        from noaa_it_all.binary_sensor import (
            ActiveAlertsGeneralBinarySensor,
            FloodWinterAlertBinarySensor,
            HeatAirQualityAlertBinarySensor,
            MeteorShowerActiveBinarySensor,
            SevereWeatherAlertBinarySensor,
            UnsafeToSwimBinarySensor,
        )
        return [
            UnsafeToSwimBinarySensor(COORD, OFFICE),
            SevereWeatherAlertBinarySensor(COORD, OFFICE, LAT, LON),
            FloodWinterAlertBinarySensor(COORD, OFFICE, LAT, LON),
            HeatAirQualityAlertBinarySensor(COORD, OFFICE, LAT, LON),
            ActiveAlertsGeneralBinarySensor(COORD, OFFICE, LAT, LON),
            MeteorShowerActiveBinarySensor(COORD, OFFICE),
        ]

    def test_all_binary_sensors_use_has_entity_name(self):
        for sensor in self._all_binary_sensors():
            self.assertTrue(
                sensor._attr_has_entity_name,
                f"{type(sensor).__name__} must set _attr_has_entity_name",
            )

    def test_names_do_not_embed_the_office_code(self):
        """A name containing 'NOAA {office}' is what causes the duplicated prefix."""
        for sensor in self._all_binary_sensors():
            local = self._local_name(sensor)
            self.assertNotIn(
                OFFICE, local,
                f"{type(sensor).__name__}.name should be local-only, got {local!r}",
            )
            self.assertNotIn(
                "NOAA", local,
                f"{type(sensor).__name__}.name should be local-only, got {local!r}",
            )

    def _slug(self, sensor):
        dev = sensor.device_info.get("name", "")
        return (_slugify(dev) + "_" + _slugify(self._local_name(sensor)))

    def test_entity_ids_have_no_duplicated_prefix(self):
        import re
        for sensor in self._all_binary_sensors():
            slug = self._slug(sensor)
            self.assertIsNone(
                re.search(rf"noaa_{OFFICE.lower()}_[a-z]+_noaa_{OFFICE.lower()}_", slug),
                f"{type(sensor).__name__} produces a duplicated prefix: {slug}",
            )

    def test_expected_entity_ids(self):
        expected = {
            "UnsafeToSwimBinarySensor": f"noaa_{OFFICE.lower()}_surf_unsafe_to_swim",
            "SevereWeatherAlertBinarySensor": f"noaa_{OFFICE.lower()}_weather_severe_weather_alert",
            "FloodWinterAlertBinarySensor": f"noaa_{OFFICE.lower()}_weather_flood_winter_alert",
            "HeatAirQualityAlertBinarySensor":
                f"noaa_{OFFICE.lower()}_weather_heat_air_quality_alert",
            "ActiveAlertsGeneralBinarySensor": f"noaa_{OFFICE.lower()}_weather_active_alerts",
            "MeteorShowerActiveBinarySensor": f"noaa_{OFFICE.lower()}_space_meteor_shower_active",
        }
        for sensor in self._all_binary_sensors():
            name = type(sensor).__name__
            self.assertEqual(self._slug(sensor), expected[name], f"{name} entity_id")

    def test_unique_ids_are_unchanged(self):
        """unique_id must stay put so existing installs keep their registered entity IDs."""
        expected = {
            "UnsafeToSwimBinarySensor": f"noaa_{OFFICE}_unsafe_to_swim",
            "SevereWeatherAlertBinarySensor": f"noaa_{OFFICE}_severe_weather_alert",
            "FloodWinterAlertBinarySensor": f"noaa_{OFFICE}_flood_winter_alert",
            "HeatAirQualityAlertBinarySensor": f"noaa_{OFFICE}_heat_air_quality_alert",
            "ActiveAlertsGeneralBinarySensor": f"noaa_{OFFICE}_active_alerts",
            "MeteorShowerActiveBinarySensor": f"noaa_{OFFICE}_meteor_shower_active",
        }
        for sensor in self._all_binary_sensors():
            name = type(sensor).__name__
            self.assertEqual(sensor._attr_unique_id, expected[name], f"{name} unique_id")


if __name__ == "__main__":
    unittest.main()
