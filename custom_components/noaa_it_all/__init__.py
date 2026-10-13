# __init__.py
import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    discovery,
    entity_registry as er,
)

from .const import (
    DOMAIN, CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, CONF_MARINE_ZONE,
    CONF_ENTRY_TYPE, CONF_SURF_OFFICE_CODE,
    ENTRY_TYPE_HURRICANE, ENTRY_TYPE_SURF, ENTRY_TYPE_WEATHER,
    HURRICANE_DEVICE_ID,
    OFFICE_TIDE_STATIONS, OFFICE_BUOY_STATIONS,
    RADAR_FRAME_DIR,
)
from .config_flow import add_entry_by_import
from .entry_config import resolve_entry_config
from .offices import (
    ALL_SURF_ENTITIES,
    HURRICANE_ENTITIES,
    is_hurricane_entry,
    is_marine_entry,
    is_surf_entry,
    radar_site as entry_radar_site,
    surf_entities,
    surf_office,
)
from .radar_loop import RadarFrameStore
from .coordinator import (
    SpaceWeatherCoordinator,
    HurricaneCoordinator,
    NWSAlertsCoordinator,
    ObservationsCoordinator,
    SurfCoordinator,
    MarineForecastCoordinator,
    ForecastCoordinator,
    CloudCoverCoordinator,
    RadarTimestampCoordinator,
    ForecastDiscussionCoordinator,
    MeteorShowerCoordinator,
    EclipseCoordinator,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "image", "binary_sensor", "weather"]
# A surf entry only has the surf sensors and Unsafe to Swim.
SURF_PLATFORMS = ["sensor", "binary_sensor"]
# The hurricane entry has the hurricane sensors and the outlook and GOES images.
HURRICANE_PLATFORMS = ["sensor", "image"]
# A marine entry has its zone's Period and Forecast sensors.
MARINE_PLATFORMS = ["sensor"]


def _platforms(conf):
    """Return the platforms an entry sets up."""
    if is_surf_entry(conf):
        return SURF_PLATFORMS
    if is_hurricane_entry(conf):
        return HURRICANE_PLATFORMS
    if is_marine_entry(conf):
        return MARINE_PLATFORMS
    return PLATFORMS


# YAML setup was removed: the sensor and image platforms have no
# async_setup_platform, so "noaa_it_all:" in YAML creates nothing. This logs
# that and raises a repair telling the user to add the integration instead.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict):
    """Set up the NOAA component from YAML configuration."""
    _LOGGER.info("Setting up NOAA integration from YAML")

    # For backward compatibility with YAML configuration
    if DOMAIN in config:
        # Load platforms for legacy YAML setup without location configuration
        discovery.load_platform(hass, 'sensor', DOMAIN, {}, config)
        discovery.load_platform(hass, 'image', DOMAIN, {}, config)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Split an entry from before 0.8.0 into weather, surf and hurricane entries.

    A version 1 entry was a location with its office's surf inside, and the
    first of them also hosted the hurricane entities. It becomes a weather
    entry. Its surf office gets a surf entry, and the hurricane entities get
    the hurricane entry; each takes over its device and entities when it sets
    up, keeping their entity IDs and history (see _async_adopt_entities). An
    entry that already exists, from another upgraded entry, is shared.
    """
    if entry.version > 2:
        # Written by a newer release; this one cannot read it.
        return False
    if entry.version == 2:
        return True

    conf = resolve_entry_config(entry)
    office = conf.get(CONF_OFFICE_CODE)
    surf = surf_office(conf)

    if surf != office:
        # A 0.8.0 test build named the surf device and entities after the
        # location's office although their data came from the surf office. No
        # surf entry can take them over, so they go.
        try:
            _async_release_surf_device(hass, entry, office)
        except Exception:  # noqa: BLE001 - leftovers must not block the upgrade
            _LOGGER.exception("Could not remove the old surf device for %s", office)

    data = {k: v for k, v in entry.data.items() if k != CONF_SURF_OFFICE_CODE}
    data[CONF_ENTRY_TYPE] = ENTRY_TYPE_WEATHER
    options = {k: v for k, v in entry.options.items() if k != CONF_SURF_OFFICE_CODE}
    title = entry.title
    if title.startswith("NOAA - "):
        title = "NOAA Weather - " + title[len("NOAA - "):]
    hass.config_entries.async_update_entry(
        entry, data=data, options=options, title=title, version=2
    )

    if surf:
        add_entry_by_import(hass, {CONF_ENTRY_TYPE: ENTRY_TYPE_SURF, CONF_OFFICE_CODE: surf})
    # Only the first entry to upgrade adds hurricanes. One that was disabled
    # upgrades when it is enabled, maybe long after the hurricane entry was
    # deleted on purpose.
    if not any(
        other.version >= 2
        for other in hass.config_entries.async_entries(DOMAIN)
        if other.entry_id != entry.entry_id
    ):
        add_entry_by_import(hass, {CONF_ENTRY_TYPE: ENTRY_TYPE_HURRICANE})
    _LOGGER.info(
        "Moved %s to a weather entry%s", entry.title,
        f" and its surf to a surf entry for {surf}" if surf else "",
    )
    return True


def _surf_device(hass: HomeAssistant, office: str):
    """Return the device the surf entities of ``office`` are grouped under."""
    return dr.async_get(hass).async_get_device(
        identifiers={(DOMAIN, f"noaa_{office}_surf")}
    )


def _async_release_surf_device(hass: HomeAssistant, entry: ConfigEntry, office: str) -> None:
    """Take an entry off its surf device; HA removes the device and its entities."""
    device = _surf_device(hass, office)
    if device is not None and entry.entry_id in device.config_entries:
        dr.async_get(hass).async_update_device(
            device.id, remove_config_entry_id=entry.entry_id
        )


def _async_adopt_entities(hass: HomeAssistant, entry: ConfigEntry, device_key: str, entities) -> None:
    """Take over a device and the entities a weather entry used to have.

    ``entities`` are (platform, unique ID) pairs: every entity the device can
    have. They are moved to this entry rather than recreated, so they keep
    their entity IDs and history. The order matters: Home Assistant deletes a
    device's entities that still belong to an entry the device is taken off,
    so the entities move before the old entry lets go of the device, and one
    left out of ``entities`` would go with it. Once done there is nothing left
    to do, so it runs on every setup.

    Home Assistant only clears "disabled by its config entry" when that entry
    is enabled, which this one already is, so the flag is cleared here for
    anything that came from a disabled entry.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    device = dev_reg.async_get_device(identifiers={(DOMAIN, device_key)})
    if device is not None and entry.entry_id not in device.config_entries:
        dev_reg.async_update_device(device.id, add_config_entry_id=entry.entry_id)
        if device.disabled_by is dr.DeviceEntryDisabler.CONFIG_ENTRY:
            dev_reg.async_update_device(device.id, disabled_by=None)

    for platform, unique_id in entities:
        entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, unique_id)
        if not entity_id:
            continue
        registered = ent_reg.async_get(entity_id)
        if registered.config_entry_id == entry.entry_id:
            continue
        changes = {"config_entry_id": entry.entry_id}
        if registered.disabled_by is er.RegistryEntryDisabler.CONFIG_ENTRY:
            changes["disabled_by"] = None
        ent_reg.async_update_entity(entity_id, **changes)

    if device is not None:
        for other in set(device.config_entries) - {entry.entry_id}:
            dev_reg.async_update_device(device.id, remove_config_entry_id=other)


def _async_adopt_safely(hass: HomeAssistant, entry: ConfigEntry, label: str, *args) -> None:
    """Adopt, logging a failure; the entry still sets up, under new entities."""
    try:
        _async_adopt_entities(hass, entry, *args)
    except Exception:  # noqa: BLE001 - must not stop the entry setting up
        _LOGGER.exception("Could not move the existing %s entities to their entry", label)


async def _async_setup_marine_entry(hass: HomeAssistant, entry: ConfigEntry, conf: dict) -> bool:
    """Set up a marine entry: one zone's Nearshore Marine Forecast."""
    marine_coord = MarineForecastCoordinator(
        hass, conf[CONF_OFFICE_CODE], conf[CONF_MARINE_ZONE]
    )
    await marine_coord.async_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "config": conf,
        "marine_forecast_coordinator": marine_coord,
    }
    await hass.config_entries.async_forward_entry_setups(entry, MARINE_PLATFORMS)
    return True


async def _async_setup_hurricane_entry(hass: HomeAssistant, entry: ConfigEntry, conf: dict) -> bool:
    """Set up the hurricane entry: NHC hurricane feeds and satellite images."""
    _async_adopt_safely(hass, entry, "hurricane", HURRICANE_DEVICE_ID, HURRICANE_ENTITIES)
    hurricane_coord = HurricaneCoordinator(hass)
    await hurricane_coord.async_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "config": conf,
        "hurricane_coordinator": hurricane_coord,
    }
    await hass.config_entries.async_forward_entry_setups(entry, HURRICANE_PLATFORMS)
    return True


def _surf_entities_to_create(hass: HomeAssistant, entry: ConfigEntry, office: str):
    """Return the surf entities a surf entry creates.

    What the office has data for, plus any it already has: a surf entity
    carried over from before 0.8.0 stays, with its history, even where the
    office has no station for it. Some read the value from the forecast text.
    """
    entities = surf_entities(office)
    try:
        ent_reg = er.async_get(hass)
        for platform, suffix in ALL_SURF_ENTITIES:
            if (platform, suffix) in entities:
                continue
            entity_id = ent_reg.async_get_entity_id(platform, DOMAIN, f"noaa_{office}_{suffix}")
            if entity_id and ent_reg.async_get(entity_id).config_entry_id == entry.entry_id:
                entities.append((platform, suffix))
    except Exception:  # noqa: BLE001 - fall back to what the office has data for
        _LOGGER.exception("Could not read the existing surf entities for %s", office)
    return entities


async def _async_setup_surf_entry(hass: HomeAssistant, entry: ConfigEntry, conf: dict) -> bool:
    """Set up a surf entry: one coastal office's Surf Zone Forecast."""
    office_code = conf[CONF_OFFICE_CODE]
    _LOGGER.info("Setting up NOAA surf for %s", office_code)
    _async_adopt_safely(
        hass, entry, f"{office_code} surf", f"noaa_{office_code}_surf",
        [(platform, f"noaa_{office_code}_{suffix}") for platform, suffix in ALL_SURF_ENTITIES],
    )

    surf_coord = SurfCoordinator(
        hass, office_code,
        OFFICE_TIDE_STATIONS.get(office_code),
        OFFICE_BUOY_STATIONS.get(office_code),
    )
    await surf_coord.async_refresh()
    hass.data[DOMAIN][entry.entry_id] = {
        "config": conf,
        "surf_coordinator": surf_coord,
        "surf_entities": _surf_entities_to_create(hass, entry, office_code),
    }
    await hass.config_entries.async_forward_entry_setups(entry, SURF_PLATFORMS)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up NOAA Integration from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    conf = resolve_entry_config(entry)
    if is_surf_entry(conf):
        return await _async_setup_surf_entry(hass, entry, conf)
    if is_hurricane_entry(conf):
        return await _async_setup_hurricane_entry(hass, entry, conf)
    if is_marine_entry(conf):
        return await _async_setup_marine_entry(hass, entry, conf)

    office_code = conf[CONF_OFFICE_CODE]
    latitude = conf.get(CONF_LATITUDE)
    longitude = conf.get(CONF_LONGITUDE)

    _LOGGER.info("Setting up NOAA integration for %s", office_code)

    # ---- Create coordinators ----

    # Global coordinators (no location dependency)
    space_weather_coord = SpaceWeatherCoordinator(hass)

    # Office-specific coordinators. Surf and hurricanes have entries of their own.
    discussion_coord = ForecastDiscussionCoordinator(hass, office_code)

    radar_site = entry_radar_site(conf)
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
    if meteor_coord:
        refresh_tasks.append(meteor_coord.async_refresh())
    if eclipse_coord:
        refresh_tasks.append(eclipse_coord.async_refresh())

    await asyncio.gather(*refresh_tasks, return_exceptions=True)

    # ---- Store everything for platform setup ----
    hass.data[DOMAIN][entry.entry_id] = {
        "config": conf,
        "space_weather_coordinator": space_weather_coord,
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
    unload_ok = await hass.config_entries.async_unload_platforms(
        entry, _platforms(resolve_entry_config(entry))
    )
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the radar frames this entry accumulated.

    Home Assistant calls this when the integration is removed rather than
    merely unloaded.  A day of radar is a few megabytes per site that nothing
    else would ever clean up, and it sits in the configuration directory, so it
    would otherwise ride along in every backup forever.
    """
    radar_site = entry_radar_site(resolve_entry_config(entry))
    if not radar_site:
        return

    # Frames are keyed by radar site, and neighbouring offices can share one.
    # Removing this entry must not take another entry's history with it.
    for other in hass.config_entries.async_entries(DOMAIN):
        if other.entry_id == entry.entry_id:
            continue
        if entry_radar_site(resolve_entry_config(other)) == radar_site:
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
