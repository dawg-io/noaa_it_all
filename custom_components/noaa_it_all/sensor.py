"""Sensor platform for NOAA Integration.

This module provides the platform setup entry points for Home Assistant.
All sensor entity classes live in dedicated domain modules under the
``sensors`` package — see ``sensors/__init__.py`` for the full list.
"""

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE

# Re-export every sensor class so that existing code that imports
# directly from ``sensor`` continues to work.
from .sensors import (  # noqa: F401
    GeomagneticSensor,
    GeomagneticSensorInterpretation,
    PlanetaryKIndexSensor,
    PlanetaryKIndexSensorRating,
    HurricaneAlertsSensor,
    HurricaneActivitySensor,
    RipCurrentRiskSensor,
    SurfHeightSensor,
    WaterTemperatureSensor,
    AuroraNextTimeSensor,
    AuroraDurationSensor,
    AuroraVisibilityProbabilitySensor,
    SolarRadiationStormAlertsSensor,
    WeatherObservationSensor,
    TemperatureSensor,
    HumiditySensor,
    WindSpeedSensor,
    WindDirectionSensor,
    BarometricPressureSensor,
    DewpointSensor,
    VisibilitySensor,
    SkyConditionsSensor,
    FeelsLikeSensor,
    ForecastBaseSensor,
    ExtendedForecastSensor,
    HourlyForecastSensor,
    NWSAlertsSensor,
    CloudCoverSensor,
    RadarTimestampSensor,
    ForecastDiscussionSensor,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)  # Update every 5 minutes


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform (legacy YAML support)."""
    _LOGGER.info("Setting up NOAA sensors (legacy YAML)")

    # Instantiate the processor for K-index and Dst interpretation
    planetary_k_index_rating = PlanetaryKIndexSensorRating()
    geomagnetic_interpretation = GeomagneticSensorInterpretation()

    # Instantiate hurricane sensors
    hurricane_alerts_sensor = HurricaneAlertsSensor()
    hurricane_activity_sensor = HurricaneActivitySensor()

    # Pass the processors to the sensors that will use them
    add_entities([GeomagneticSensor(geomagnetic_interpretation), PlanetaryKIndexSensor(planetary_k_index_rating),
                  planetary_k_index_rating, geomagnetic_interpretation, hurricane_alerts_sensor,
                  hurricane_activity_sensor])


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA sensors from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

    # Instantiate the processor for K-index and Dst interpretation
    planetary_k_index_rating = PlanetaryKIndexSensorRating()
    geomagnetic_interpretation = GeomagneticSensorInterpretation()

    # Instantiate hurricane sensors
    hurricane_alerts_sensor = HurricaneAlertsSensor()
    hurricane_activity_sensor = HurricaneActivitySensor()

    # Instantiate location-specific rip current sensors
    rip_current_risk_sensor = RipCurrentRiskSensor(office_code)
    surf_height_sensor = SurfHeightSensor(office_code)
    water_temperature_sensor = WaterTemperatureSensor(office_code)

    # Instantiate location-specific aurora alert sensors
    aurora_next_time_sensor = AuroraNextTimeSensor(office_code)
    aurora_duration_sensor = AuroraDurationSensor(office_code)
    aurora_visibility_probability_sensor = AuroraVisibilityProbabilitySensor(office_code)

    # Instantiate location-specific solar radiation storm alert sensor
    solar_radiation_storm_alerts_sensor = SolarRadiationStormAlertsSensor(office_code)

    # Instantiate location-specific weather observation sensors
    temperature_sensor = TemperatureSensor(office_code, latitude, longitude)
    humidity_sensor = HumiditySensor(office_code, latitude, longitude)
    wind_speed_sensor = WindSpeedSensor(office_code, latitude, longitude)
    wind_direction_sensor = WindDirectionSensor(office_code, latitude, longitude)
    barometric_pressure_sensor = BarometricPressureSensor(office_code, latitude, longitude)
    dewpoint_sensor = DewpointSensor(office_code, latitude, longitude)
    visibility_sensor = VisibilitySensor(office_code, latitude, longitude)
    sky_conditions_sensor = SkyConditionsSensor(office_code, latitude, longitude)
    feels_like_sensor = FeelsLikeSensor(office_code, latitude, longitude)

    # Instantiate location-specific forecast sensors
    extended_forecast_sensor = ExtendedForecastSensor(office_code, latitude, longitude)
    hourly_forecast_sensor = HourlyForecastSensor(office_code, latitude, longitude)

    # Instantiate location-specific NWS alerts sensor
    nws_alerts_sensor = None
    if latitude is not None and longitude is not None:
        nws_alerts_sensor = NWSAlertsSensor(office_code, latitude, longitude)

    # Instantiate optional secondary sensors
    cloud_cover_sensor = None
    radar_timestamp_sensor = RadarTimestampSensor(office_code)
    forecast_discussion_sensor = ForecastDiscussionSensor(office_code)

    # Cloud cover requires lat/lon for gridpoint data
    if latitude is not None and longitude is not None:
        cloud_cover_sensor = CloudCoverSensor(office_code, latitude, longitude)

    entities = [
        GeomagneticSensor(geomagnetic_interpretation),
        PlanetaryKIndexSensor(planetary_k_index_rating),
        # planetary_k_index_rating,
        # geomagnetic_interpretation,
        hurricane_alerts_sensor,
        hurricane_activity_sensor,
        rip_current_risk_sensor,
        surf_height_sensor,
        water_temperature_sensor,
        aurora_next_time_sensor,
        aurora_duration_sensor,
        aurora_visibility_probability_sensor,
        solar_radiation_storm_alerts_sensor,
        temperature_sensor,
        humidity_sensor,
        wind_speed_sensor,
        wind_direction_sensor,
        barometric_pressure_sensor,
        dewpoint_sensor,
        visibility_sensor,
        sky_conditions_sensor,
        feels_like_sensor,
        extended_forecast_sensor,
        hourly_forecast_sensor,
        radar_timestamp_sensor,
        forecast_discussion_sensor,
    ]

    # Add NWS alerts sensor if location is configured
    if nws_alerts_sensor:
        entities.append(nws_alerts_sensor)

    # Add cloud cover sensor if location is configured
    if cloud_cover_sensor:
        entities.append(cloud_cover_sensor)

    async_add_entities(entities, True)
