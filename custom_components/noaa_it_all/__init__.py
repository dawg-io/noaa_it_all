# __init__.py
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .const import (
    DOMAIN, CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE,
    OFFICE_RADAR_SITES,
)
from .coordinator import (
    SpaceWeatherCoordinator,
    HurricaneCoordinator,
    NWSAlertsCoordinator,
    ObservationsCoordinator,
    SurfCoordinator,
    ForecastCoordinator,
    CloudCoverCoordinator,
    RadarTimestampCoordinator,
    ForecastDiscussionCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "image", "binary_sensor", "weather"]


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the NOAA component from YAML configuration."""
    _LOGGER.info("Setting up NOAA integration from YAML")

    # For backward compatibility with YAML configuration
    if DOMAIN in config:
        # Load platforms for legacy YAML setup without location configuration
        discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)
        discovery.load_platform(hass, 'image', DOMAIN, {}, config)

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up NOAA Integration from a config entry."""
    _LOGGER.info("Setting up NOAA integration for %s", entry.data.get("office_code"))

    hass.data.setdefault(DOMAIN, {})

    office_code = entry.data[CONF_OFFICE_CODE]
    latitude = entry.data.get(CONF_LATITUDE)
    longitude = entry.data.get(CONF_LONGITUDE)

    # ---- Create coordinators ----

    # Global coordinators (no location dependency)
    space_weather_coord = SpaceWeatherCoordinator(hass)
    hurricane_coord = HurricaneCoordinator(hass)

    # Office-specific coordinators
    surf_coord = SurfCoordinator(hass, office_code)
    discussion_coord = ForecastDiscussionCoordinator(hass, office_code)

    radar_site = OFFICE_RADAR_SITES.get(office_code)
    radar_coord = (
        RadarTimestampCoordinator(hass, office_code, radar_site)
        if radar_site else None
    )

    # Location-specific coordinators (require lat/lon)
    alerts_coord = None
    observations_coord = None
    forecast_coord = None
    cloud_cover_coord = None

    if latitude is not None and longitude is not None:
        alerts_coord = NWSAlertsCoordinator(hass, latitude, longitude)
        observations_coord = ObservationsCoordinator(
            hass, office_code, latitude, longitude
        )
        forecast_coord = ForecastCoordinator(
            hass, office_code, latitude, longitude
        )
        cloud_cover_coord = CloudCoverCoordinator(
            hass, office_code, latitude, longitude
        )

    # ---- Initial refresh (non-blocking, errors are logged) ----
    refresh_tasks = [
        space_weather_coord.async_refresh(),
        hurricane_coord.async_refresh(),
        surf_coord.async_refresh(),
        discussion_coord.async_refresh(),
    ]
    if radar_coord:
        refresh_tasks.append(radar_coord.async_refresh())
    if alerts_coord:
        refresh_tasks.append(alerts_coord.async_refresh())
    if observations_coord:
        refresh_tasks.append(observations_coord.async_refresh())
    if forecast_coord:
        refresh_tasks.append(forecast_coord.async_refresh())
    if cloud_cover_coord:
        refresh_tasks.append(cloud_cover_coord.async_refresh())

    await asyncio.gather(*refresh_tasks, return_exceptions=True)

    # ---- Store everything for platform setup ----
    hass.data[DOMAIN][entry.entry_id] = {
        "config": entry.data,
        "space_weather_coordinator": space_weather_coord,
        "hurricane_coordinator": hurricane_coord,
        "surf_coordinator": surf_coord,
        "forecast_discussion_coordinator": discussion_coord,
        "radar_timestamp_coordinator": radar_coord,
        "alerts_coordinator": alerts_coord,
        "observations_coordinator": observations_coord,
        "forecast_coordinator": forecast_coord,
        "cloud_cover_coordinator": cloud_cover_coord,
    }

    # Load all platforms for the configured location
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


# Legacy function for YAML setup
def setup(hass, config):
    """Set up the NOAA component (legacy YAML support)."""
    _LOGGER.info("Setting up NOAA integration (legacy YAML)")

    # Load the platform for sensor
    discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)

    # Load the platform for image
    discovery.load_platform(hass, 'image', DOMAIN, {}, config)

    return True
