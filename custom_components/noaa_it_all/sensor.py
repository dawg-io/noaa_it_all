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
    CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, CONF_MARINE_ZONE, DOMAIN,
)
from .entry_config import resolve_entry_config
from .offices import (
    SURF_HEIGHT, WATER_TEMPERATURE, is_hurricane_entry, is_marine_entry, is_space_entry,
    is_surf_entry,
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
    MarineForecastSensor,
    MarinePeriodSensor,
    MarineHazardSensor,
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
    MeteorShowerActivitySensor,
    NextMeteorShowerSensor,
    MeteorViewingScoreSensor,
    NextEclipseSensor,
    NextEclipseTimeSensor,
    EclipseCoverageSensor,
    EclipseViewingScoreSensor,
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
    conf = resolve_entry_config(config_entry)
    data = hass.data[DOMAIN][config_entry.entry_id]
    if is_hurricane_entry(conf):
        # The hurricane entry has no office or location.
        hurricane_coord = data["hurricane_coordinator"]
        async_add_entities([
            HurricaneAlertsSensor(hurricane_coord),
            HurricaneActivitySensor(hurricane_coord),
        ])
        return
    if is_marine_entry(conf):
        marine_coord = data["marine_forecast_coordinator"]
        office_code, zone = conf[CONF_OFFICE_CODE], conf[CONF_MARINE_ZONE]
        entities = [
            MarinePeriodSensor(marine_coord, office_code, zone),
            MarineForecastSensor(marine_coord, office_code, zone),
        ]
        alerts_coord = data.get("marine_alerts_coordinator")
        if alerts_coord is not None:
            entities.append(MarineHazardSensor(alerts_coord, office_code, zone))
        async_add_entities(entities)
        return

    office_code = conf[CONF_OFFICE_CODE]
    latitude = conf.get(CONF_LATITUDE)
    longitude = conf.get(CONF_LONGITUDE)
    if is_surf_entry(conf):
        # What the office has data for, plus any carried over from 0.7.x.
        surf_coord = data["surf_coordinator"]
        made = data["surf_entities"]
        entities = [RipCurrentRiskSensor(surf_coord, office_code)]
        if WATER_TEMPERATURE in made:
            entities.append(WaterTemperatureSensor(surf_coord, office_code))
        if SURF_HEIGHT in made:
            entities.append(SurfHeightSensor(surf_coord, office_code))
        async_add_entities(entities)
        return
    if is_space_entry(conf):
        async_add_entities(_space_sensors(data, office_code, latitude, longitude))
        return

    observations_coord = data["observations_coordinator"]
    forecast_coord = data["forecast_coordinator"]
    alerts_coord = data["alerts_coordinator"]
    cloud_cover_coord = data["cloud_cover_coordinator"]
    radar_coord = data["radar_timestamp_coordinator"]
    discussion_coord = data["forecast_discussion_coordinator"]

    entities = []

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


def _space_sensors(data, office_code, latitude, longitude):
    """Return a Space entry's sensors: space weather, aurora, meteors and eclipses."""
    space_coord = data["space_weather_coordinator"]
    meteor_coord = data["meteor_coordinator"]
    eclipse_coord = data["eclipse_coordinator"]
    return [
        # Space weather is global; aurora goes by the office's or location's magnetic latitude.
        GeomagneticSensor(space_coord, office_code),
        GeomagneticSensorInterpretation(space_coord, office_code),
        PlanetaryKIndexSensor(space_coord, office_code),
        PlanetaryKIndexSensorRating(space_coord, office_code),
        AuroraNextTimeSensor(space_coord, office_code, latitude, longitude),
        AuroraDurationSensor(space_coord, office_code, latitude, longitude),
        AuroraVisibilityProbabilitySensor(space_coord, office_code, latitude, longitude),
        SolarRadiationStormAlertsSensor(space_coord, office_code, latitude, longitude),
        MeteorShowerActivitySensor(meteor_coord, office_code),
        NextMeteorShowerSensor(meteor_coord, office_code),
        MeteorViewingScoreSensor(meteor_coord, office_code),
        NextEclipseSensor(eclipse_coord, office_code),
        NextEclipseTimeSensor(eclipse_coord, office_code),
        EclipseCoverageSensor(eclipse_coord, office_code),
        EclipseViewingScoreSensor(eclipse_coord, office_code),
    ]
