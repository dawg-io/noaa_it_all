# __init__.py
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .const import (
    DOMAIN, CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE,
    HURRICANE_COORDINATOR_KEY,
    HURRICANE_IMAGES_ADDED_KEY, HURRICANE_SENSORS_ADDED_KEY,
    OFFICE_RADAR_SITES, OFFICE_TIDE_STATIONS, OFFICE_BUOY_STATIONS,
    RADAR_FRAME_DIR,
)
from .entry_config import resolve_entry_config
from .radar_loop import RadarFrameStore
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
    MeteorShowerCoordinator,
    EclipseCoordinator,
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
    hass.data.setdefault(DOMAIN, {})
    domain_data = hass.data[DOMAIN]

    conf = resolve_entry_config(entry)
    office_code = conf[CONF_OFFICE_CODE]
    latitude = conf.get(CONF_LATITUDE)
    longitude = conf.get(CONF_LONGITUDE)

    _LOGGER.info("Setting up NOAA integration for %s", office_code)

    # ---- Create coordinators ----

    # Global coordinators (no location dependency)
    space_weather_coord = SpaceWeatherCoordinator(hass)

    # Hurricane data is global (NHC). Share a single HurricaneCoordinator
    # across all configured config entries so we only schedule one set of
    # polling tasks and only do one initial refresh on startup, regardless
    # of how many NWS offices are configured.
    hurricane_coord = domain_data.get(HURRICANE_COORDINATOR_KEY)
    hurricane_coord_is_new = hurricane_coord is None
    if hurricane_coord_is_new:
        hurricane_coord = HurricaneCoordinator(hass)
        domain_data[HURRICANE_COORDINATOR_KEY] = hurricane_coord

    # Office-specific coordinators
    tide_station = OFFICE_TIDE_STATIONS.get(office_code)
    buoy_station = OFFICE_BUOY_STATIONS.get(office_code)
    surf_coord = SurfCoordinator(hass, office_code, tide_station, buoy_station)
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
    meteor_coord = None
    eclipse_coord = None

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
        # Meteor showers are computed locally from a bundled catalog rather than fetched,
        # but they still need the observer's coordinates to place the radiant in the sky.
        meteor_coord = MeteorShowerCoordinator(
            hass, office_code, latitude, longitude
        )
        # Eclipses are the same story: bundled Besselian elements plus local astronomy, no
        # feed to poll, but the observer's coordinates decide almost everything about them.
        eclipse_coord = EclipseCoordinator(
            hass, office_code, latitude, longitude
        )

    # ---- Initial refresh (non-blocking, errors are logged) ----
    refresh_tasks = [
        space_weather_coord.async_refresh(),
        surf_coord.async_refresh(),
        discussion_coord.async_refresh(),
    ]
    # Only refresh the shared hurricane coordinator on the entry that
    # created it, to avoid redundant API calls when multiple offices
    # are configured.
    if hurricane_coord_is_new:
        refresh_tasks.append(hurricane_coord.async_refresh())
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
    if meteor_coord:
        refresh_tasks.append(meteor_coord.async_refresh())
    if eclipse_coord:
        refresh_tasks.append(eclipse_coord.async_refresh())

    await asyncio.gather(*refresh_tasks, return_exceptions=True)

    # ---- Store everything for platform setup ----
    hass.data[DOMAIN][entry.entry_id] = {
        "config": conf,
        "space_weather_coordinator": space_weather_coord,
        "hurricane_coordinator": hurricane_coord,
        "surf_coordinator": surf_coord,
        "forecast_discussion_coordinator": discussion_coord,
        "radar_timestamp_coordinator": radar_coord,
        "alerts_coordinator": alerts_coord,
        "observations_coordinator": observations_coord,
        "forecast_coordinator": forecast_coord,
        "cloud_cover_coordinator": cloud_cover_coord,
        "meteor_coordinator": meteor_coord,
        "eclipse_coordinator": eclipse_coord,
    }

    # Reload the entry whenever its options change. The coordinators capture
    # office_code/latitude/longitude at construction and offer no way to update
    # them afterwards, so a full reload is what makes a saved option take
    # effect. Registered via async_on_unload so the reload itself re-registers
    # it rather than stacking listeners.
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    # Load all platforms for the configured location
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Reload the entry so changed options are picked up by the coordinators."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

        # If no per-entry data remains, also clear the shared hurricane
        # coordinator and any leftover "added" flags so a fresh setup
        # re-creates the global hurricane entities. (Keys starting with
        # "_" are global state, not per-entry data.)
        remaining_entries = [
            k for k in hass.data[DOMAIN] if not k.startswith("_")
        ]
        if not remaining_entries:
            hass.data[DOMAIN].pop(HURRICANE_SENSORS_ADDED_KEY, None)
            hass.data[DOMAIN].pop(HURRICANE_IMAGES_ADDED_KEY, None)
            hass.data[DOMAIN].pop(HURRICANE_COORDINATOR_KEY, None)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the radar frames this entry accumulated.

    Home Assistant calls this when the integration is removed rather than
    merely unloaded.  A day of radar is a few megabytes per site that nothing
    else would ever clean up, and it sits in the configuration directory, so it
    would otherwise ride along in every backup forever.
    """
    office_code = resolve_entry_config(entry).get(CONF_OFFICE_CODE)
    radar_site = OFFICE_RADAR_SITES.get(office_code)
    if not radar_site:
        return

    # Frames are keyed by radar site, and neighbouring offices can share one.
    # Removing this entry must not take another entry's history with it.
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry.entry_id:
            continue
        other_office = resolve_entry_config(other).get(CONF_OFFICE_CODE)
        if OFFICE_RADAR_SITES.get(other_office) == radar_site:
            _LOGGER.debug(
                "Keeping stored radar frames for %s; another entry still uses it",
                radar_site,
            )
            return

    store = RadarFrameStore(
        hass, hass.config.path(DOMAIN, RADAR_FRAME_DIR), radar_site
    )
    await store.async_remove_all()
    _LOGGER.info("Removed stored radar frames for %s", radar_site)


# Legacy function for YAML setup
def setup(hass, config):
    """Set up the NOAA component (legacy YAML support)."""
    _LOGGER.info("Setting up NOAA integration (legacy YAML)")

    # Load the platform for sensor
    discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)

    # Load the platform for image
    discovery.load_platform(hass, 'image', DOMAIN, {}, config)

    return True
