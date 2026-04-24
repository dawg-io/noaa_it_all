"""Sensor platform for NOAA Integration.

This module provides the platform setup entry points for Home Assistant.
All sensor entity classes live in dedicated domain modules under the
``sensors`` package — see ``sensors/__init__.py`` for the full list.
"""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, DOMAIN,
    HURRICANE_SENSORS_ADDED_KEY,
)

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


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform (legacy YAML support)."""
    _LOGGER.error(
        "Legacy YAML configuration for NOAA sensors is no longer supported and "
        "will not create any entities. Please remove the YAML configuration "
        "from configuration.yaml and re-add the integration via the Home "
        "Assistant UI config flow."
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA sensors from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

    data = hass.data[DOMAIN][config_entry.entry_id]
    space_coord = data["space_weather_coordinator"]
    hurricane_coord = data["hurricane_coordinator"]
    surf_coord = data["surf_coordinator"]
    observations_coord = data["observations_coordinator"]
    forecast_coord = data["forecast_coordinator"]
    alerts_coord = data["alerts_coordinator"]
    cloud_cover_coord = data["cloud_cover_coordinator"]
    radar_coord = data["radar_timestamp_coordinator"]
    discussion_coord = data["forecast_discussion_coordinator"]

    entities = [
        # Space weather (global, use SpaceWeatherCoordinator)
        GeomagneticSensor(space_coord, office_code),
        GeomagneticSensorInterpretation(space_coord, office_code),
        PlanetaryKIndexSensor(space_coord, office_code),
        PlanetaryKIndexSensorRating(space_coord, office_code),
        AuroraNextTimeSensor(space_coord, office_code),
        AuroraDurationSensor(space_coord, office_code),
        AuroraVisibilityProbabilitySensor(space_coord, office_code),
        SolarRadiationStormAlertsSensor(space_coord, office_code),

        # Surf (office-specific, use SurfCoordinator)
        RipCurrentRiskSensor(surf_coord, office_code),
        SurfHeightSensor(surf_coord, office_code),
        WaterTemperatureSensor(surf_coord, office_code),
    ]

    # Hurricane sensors are global (NHC) and grouped under a single
    # dedicated NOAA Hurricane device. Only add them once across all
    # configured NWS offices to prevent duplicates.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(HURRICANE_SENSORS_ADDED_KEY):
        entities.extend([
            HurricaneAlertsSensor(hurricane_coord),
            HurricaneActivitySensor(hurricane_coord),
        ])
        domain_data[HURRICANE_SENSORS_ADDED_KEY] = True

    # Observation sensors (location-specific)
    if observations_coord:
        entities.extend([
            TemperatureSensor(observations_coord, office_code, latitude, longitude),
            HumiditySensor(observations_coord, office_code, latitude, longitude),
            WindSpeedSensor(observations_coord, office_code, latitude, longitude),
            WindDirectionSensor(observations_coord, office_code, latitude, longitude),
            BarometricPressureSensor(observations_coord, office_code, latitude, longitude),
            DewpointSensor(observations_coord, office_code, latitude, longitude),
            VisibilitySensor(observations_coord, office_code, latitude, longitude),
            SkyConditionsSensor(observations_coord, office_code, latitude, longitude),
            FeelsLikeSensor(observations_coord, office_code, latitude, longitude),
        ])

    # Forecast sensors (location-specific)
    if forecast_coord:
        entities.extend([
            ExtendedForecastSensor(forecast_coord, office_code, latitude, longitude),
            HourlyForecastSensor(forecast_coord, office_code, latitude, longitude),
        ])

    # NWS alerts sensor (location-specific)
    if alerts_coord:
        entities.append(NWSAlertsSensor(alerts_coord, office_code, latitude, longitude))

    # Cloud cover sensor (location-specific)
    if cloud_cover_coord:
        entities.append(CloudCoverSensor(cloud_cover_coord, office_code, latitude, longitude))

    # Radar timestamp sensor (office-specific, may be None if no radar site)
    if radar_coord:
        entities.append(RadarTimestampSensor(radar_coord, office_code))

    # Forecast discussion sensor (office-specific)
    entities.append(ForecastDiscussionSensor(discussion_coord, office_code))

    async_add_entities(entities)
