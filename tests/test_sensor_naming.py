"""Tests for sensor entity naming convention: sensor.noaa_{office}_{metric}.

Verifies that all location-specific sensors include the office code in
their name and unique_id, matching the README documented format.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Ensure the custom_components directory is on sys.path so that
# ``noaa_it_all`` resolves as a package and relative imports work.
# ---------------------------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules before importing any sensor code
# ---------------------------------------------------------------------------

_ha_entity = MagicMock()
_ha_coordinator = MagicMock()
_ha_binary = MagicMock()
_ha_weather_mod = MagicMock()
_ha_const = MagicMock()
_ha_config_entries = MagicMock()
_ha_core = MagicMock()
_ha_platform = MagicMock()

sys.modules.setdefault("homeassistant", MagicMock())
sys.modules.setdefault("homeassistant.helpers", MagicMock())
sys.modules.setdefault("homeassistant.helpers.entity", _ha_entity)
sys.modules.setdefault("homeassistant.helpers.update_coordinator", _ha_coordinator)
sys.modules.setdefault("homeassistant.helpers.entity_platform", _ha_platform)
sys.modules.setdefault("homeassistant.helpers.aiohttp_client", MagicMock())
sys.modules.setdefault("homeassistant.components", MagicMock())
sys.modules.setdefault("homeassistant.components.binary_sensor", _ha_binary)
sys.modules.setdefault("homeassistant.components.weather", _ha_weather_mod)
sys.modules.setdefault("homeassistant.const", _ha_const)
sys.modules.setdefault("homeassistant.config_entries", _ha_config_entries)
sys.modules.setdefault("homeassistant.core", _ha_core)
sys.modules.setdefault("aiohttp", MagicMock())

# Make CoordinatorEntity a plain base class for testing
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})

# Make DeviceInfo a simple dict-like for testing
_ha_entity.DeviceInfo = dict

# BinarySensorEntity stub
_ha_binary.BinarySensorEntity = type("BinarySensorEntity", (), {})

OFFICE = "SGX"
COORD = MagicMock()
COORD.data = None
LAT = 32.7157
LON = -117.1611


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
        self.assertEqual(s.name, f"NOAA {OFFICE} Temperature")

    def test_humidity_name(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        s = self._make(HumiditySensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Humidity")

    def test_wind_speed_name(self):
        from noaa_it_all.sensors.weather_observations import WindSpeedSensor
        s = self._make(WindSpeedSensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Wind Speed")

    def test_wind_direction_name(self):
        from noaa_it_all.sensors.weather_observations import WindDirectionSensor
        s = self._make(WindDirectionSensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Wind Direction")

    def test_barometric_pressure_name(self):
        from noaa_it_all.sensors.weather_observations import BarometricPressureSensor
        s = self._make(BarometricPressureSensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Barometric Pressure")

    def test_dewpoint_name(self):
        from noaa_it_all.sensors.weather_observations import DewpointSensor
        s = self._make(DewpointSensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Dewpoint")

    def test_visibility_name(self):
        from noaa_it_all.sensors.weather_observations import VisibilitySensor
        s = self._make(VisibilitySensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Visibility")

    def test_sky_conditions_name(self):
        from noaa_it_all.sensors.weather_observations import SkyConditionsSensor
        s = self._make(SkyConditionsSensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Sky Conditions")

    def test_feels_like_name(self):
        from noaa_it_all.sensors.weather_observations import FeelsLikeSensor
        s = self._make(FeelsLikeSensor)
        self.assertEqual(s.name, f"NOAA {OFFICE} Feels Like")

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
        self.assertEqual(s.name, f"NOAA {OFFICE} Aurora Next Time")

    def test_aurora_next_time_unique_id(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        s = AuroraNextTimeSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_aurora_next_time")

    def test_aurora_duration_name(self):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        s = AuroraDurationSensor(COORD, OFFICE)
        self.assertEqual(s.name, f"NOAA {OFFICE} Aurora Duration")

    def test_aurora_duration_unique_id(self):
        from noaa_it_all.sensors.space_weather import AuroraDurationSensor
        s = AuroraDurationSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_aurora_duration")

    def test_aurora_visibility_probability_name(self):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        s = AuroraVisibilityProbabilitySensor(COORD, OFFICE)
        self.assertEqual(s.name, f"NOAA {OFFICE} Aurora Visibility Probability")

    def test_aurora_visibility_probability_unique_id(self):
        from noaa_it_all.sensors.space_weather import AuroraVisibilityProbabilitySensor
        s = AuroraVisibilityProbabilitySensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_aurora_visibility_probability")

    def test_solar_radiation_name(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        s = SolarRadiationStormAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.name, f"NOAA {OFFICE} Solar Radiation Storm Alerts")

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
        self.assertEqual(s._attr_name, f"NOAA {OFFICE} Rip Current Risk")

    def test_rip_current_unique_id(self):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        s = RipCurrentRiskSensor(COORD, OFFICE)
        self.assertEqual(s._attr_unique_id, f"noaa_{OFFICE}_rip_current_risk")

    def test_surf_height_name(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertEqual(s._attr_name, f"NOAA {OFFICE} Surf Height")

    def test_surf_height_unique_id(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertEqual(s._attr_unique_id, f"noaa_{OFFICE}_surf_height")

    def test_water_temperature_name(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        s = WaterTemperatureSensor(COORD, OFFICE)
        self.assertEqual(s._attr_name, f"NOAA {OFFICE} Water Temperature")

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
        self.assertEqual(s.name, f"NOAA {OFFICE} Extended Forecast")

    def test_extended_forecast_unique_id(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        uid = s.unique_id
        self.assertIn(OFFICE.lower(), uid.lower())
        self.assertTrue(uid.startswith("noaa_"))

    def test_hourly_forecast_name(self):
        from noaa_it_all.sensors.forecasts import HourlyForecastSensor
        s = HourlyForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.name, f"NOAA {OFFICE} Hourly Forecast")


# ---------------------------------------------------------------------------
# Alerts sensor
# ---------------------------------------------------------------------------

class TestAlertsNaming(unittest.TestCase):
    """Verify NWS alerts sensor name includes the office code."""

    def test_nws_alerts_name(self):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        s = NWSAlertsSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.name, f"NOAA {OFFICE} Active NWS Alerts")

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
        self.assertEqual(s.name, f"NOAA {OFFICE} Cloud Cover")

    def test_cloud_cover_unique_id(self):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        s = CloudCoverSensor(COORD, OFFICE, LAT, LON)
        uid = s.unique_id
        self.assertIn(OFFICE.lower(), uid.lower())
        self.assertTrue(uid.startswith("noaa_"))

    def test_radar_timestamp_name(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertEqual(s.name, f"NOAA {OFFICE} Radar Timestamp")

    def test_radar_timestamp_unique_id(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_radar_timestamp")

    def test_forecast_discussion_name(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertEqual(s.name, f"NOAA {OFFICE} Forecast Discussion")

    def test_forecast_discussion_unique_id(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertEqual(s.unique_id, f"noaa_{OFFICE}_forecast_discussion")


# ---------------------------------------------------------------------------
# Cross-cutting: all names should slug to noaa_{office}_*
# ---------------------------------------------------------------------------

class TestNamingConventionFormat(unittest.TestCase):
    """Verify all sensor names follow the NOAA {OFFICE} {Metric} pattern."""

    def _slug(self, name):
        """Simple slugify matching HA behavior for entity_id."""
        return name.lower().replace(" ", "_").replace("-", "_")

    def test_all_names_produce_correct_entity_prefix(self):
        """Every location sensor name must start with 'NOAA {OFFICE}'."""
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

        # Build sensors with OFFICE code
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
            name = getattr(sensor, '_attr_name', None) or sensor.name
            slug = self._slug(name)
            self.assertTrue(
                slug.startswith(expected_prefix),
                f"Sensor name '{name}' slugifies to '{slug}' — "
                f"expected prefix '{expected_prefix}'"
            )


# ---------------------------------------------------------------------------
# Device grouping: all entities use the same device per office
# ---------------------------------------------------------------------------

DOMAIN = "noaa_it_all"


class TestDeviceInfoGrouping(unittest.TestCase):
    """Verify all entities for a given office share a single device."""

    def _expected_device_info(self):
        """Return the expected device_info dict for OFFICE."""
        return {
            "identifiers": {(DOMAIN, f"noaa_{OFFICE}")},
            "name": f"NOAA {OFFICE}",
            "manufacturer": "NOAA",
        }

    # -- weather observation sensors -----------------------------------------

    def test_temperature_device_info(self):
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        s = TemperatureSensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_humidity_device_info(self):
        from noaa_it_all.sensors.weather_observations import HumiditySensor
        s = HumiditySensor(COORD, OFFICE, latitude=LAT, longitude=LON)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- space weather sensors -----------------------------------------------

    def test_geomagnetic_device_info(self):
        from noaa_it_all.sensors.space_weather import GeomagneticSensor
        s = GeomagneticSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_kp_index_device_info(self):
        from noaa_it_all.sensors.space_weather import PlanetaryKIndexSensor
        s = PlanetaryKIndexSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_aurora_next_time_device_info(self):
        from noaa_it_all.sensors.space_weather import AuroraNextTimeSensor
        s = AuroraNextTimeSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_solar_radiation_device_info(self):
        from noaa_it_all.sensors.space_weather import SolarRadiationStormAlertsSensor
        s = SolarRadiationStormAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- surf sensors --------------------------------------------------------

    def test_rip_current_device_info(self):
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        s = RipCurrentRiskSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_surf_height_device_info(self):
        from noaa_it_all.sensors.surf import SurfHeightSensor
        s = SurfHeightSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_water_temperature_device_info(self):
        from noaa_it_all.sensors.surf import WaterTemperatureSensor
        s = WaterTemperatureSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- hurricane sensors ---------------------------------------------------

    def test_hurricane_alerts_device_info(self):
        from noaa_it_all.sensors.hurricanes import HurricaneAlertsSensor
        s = HurricaneAlertsSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_hurricane_activity_device_info(self):
        from noaa_it_all.sensors.hurricanes import HurricaneActivitySensor
        s = HurricaneActivitySensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- forecast sensors ----------------------------------------------------

    def test_extended_forecast_device_info(self):
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        s = ExtendedForecastSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- alerts sensor -------------------------------------------------------

    def test_nws_alerts_device_info(self):
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        s = NWSAlertsSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- weather extra sensors -----------------------------------------------

    def test_cloud_cover_device_info(self):
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor
        s = CloudCoverSensor(COORD, OFFICE, LAT, LON)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_radar_timestamp_device_info(self):
        from noaa_it_all.sensors.weather_extra import RadarTimestampSensor
        s = RadarTimestampSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    def test_forecast_discussion_device_info(self):
        from noaa_it_all.sensors.weather_extra import ForecastDiscussionSensor
        s = ForecastDiscussionSensor(COORD, OFFICE)
        self.assertEqual(s.device_info, self._expected_device_info())

    # -- cross-cutting: every sensor uses the SAME device --------------------

    def test_all_sensors_share_one_device(self):
        """All office-specific sensors must share identical device_info."""
        from noaa_it_all.sensors.weather_observations import TemperatureSensor
        from noaa_it_all.sensors.space_weather import (
            GeomagneticSensor, AuroraNextTimeSensor,
        )
        from noaa_it_all.sensors.surf import RipCurrentRiskSensor
        from noaa_it_all.sensors.hurricanes import HurricaneAlertsSensor
        from noaa_it_all.sensors.forecasts import ExtendedForecastSensor
        from noaa_it_all.sensors.alerts import NWSAlertsSensor
        from noaa_it_all.sensors.weather_extra import CloudCoverSensor

        sensors = [
            TemperatureSensor(COORD, OFFICE, latitude=LAT, longitude=LON),
            GeomagneticSensor(COORD, OFFICE),
            AuroraNextTimeSensor(COORD, OFFICE),
            RipCurrentRiskSensor(COORD, OFFICE),
            HurricaneAlertsSensor(COORD, OFFICE),
            ExtendedForecastSensor(COORD, OFFICE, LAT, LON),
            NWSAlertsSensor(COORD, OFFICE, LAT, LON),
            CloudCoverSensor(COORD, OFFICE, LAT, LON),
        ]

        expected = self._expected_device_info()
        for sensor in sensors:
            self.assertEqual(
                sensor.device_info, expected,
                f"{type(sensor).__name__}.device_info does not match — "
                f"all entities for office {OFFICE} must share the same device"
            )


if __name__ == "__main__":
    unittest.main()
