"""NOAA image entities.

Every entity here follows the same shape, provided by :class:`NoaaImageEntity`:
the image is fetched from NOAA on a background timer and the last frame that
came back successfully is kept in memory.  ``async_image()`` only ever hands
back that cached copy, so a transient upstream failure -- a DNS timeout, an
unreachable network, a 503 from NOAA -- leaves the previous picture on the
dashboard instead of blanking the tile.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import timedelta

import aiohttp
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import (
    CONF_OFFICE_CODE, CONF_RADAR_LOOP_HOURS,
    DEFAULT_RADAR_LOOP_HOURS, DEFAULT_SCAN_INTERVAL, DOMAIN,
    HURRICANE_DEVICE_ID, HURRICANE_DEVICE_NAME,
    HURRICANE_IMAGES_ADDED_KEY,
    IMAGE_FAILURE_ERROR_AFTER, IMAGE_FAILURE_WARN_AFTER,
    IMAGE_FETCH_TIMEOUT, IMAGE_MAX_BYTES,
    NWS_RADAR_BASE_URL, NWS_RADAR_LOOP_URL,
    OFFICE_RADAR_SITES, RADAR_FRAME_DIR,
    RADAR_LOOP_MAX_FRAMES, RADAR_LOOP_MAX_HOURS, RADAR_LOOP_MIN_FRAMES,
    USER_AGENT,
)
from .entry_config import resolve_entry_config
from .radar_loop import (
    RadarFrameStore, assemble_gif, parse_http_date, select_frames,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)

BASE_IMAGE_URL = ('https://services.swpc.noaa.gov/images/animations/geoelectric/'
                  'InterMagEarthScope/EmapGraphics_1m/latest.png')
AURORA_URL = ('https://services.swpc.noaa.gov/images/animations/ovation/'
              'north/latest.jpg')

# NOAA Hurricane Image Sources
HURRICANE_OUTLOOK_URL = 'https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png'

# NOAA GOES Satellite Image Sources
GOES_AIRMASS_URL = 'https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/AirMass/1250x750.jpg'
GOES_GEOCOLOR_URL = 'https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/1250x750.jpg'

# Failures that mean "the network or NOAA is having a moment" rather than
# "this integration is asking for the wrong thing".  ``asyncio.TimeoutError``
# has to be listed explicitly: a ``ClientTimeout`` expiry raises it, and it is
# *not* an ``aiohttp.ClientError``, so it would otherwise be reported as an
# unexpected error.
_TRANSIENT_FETCH_ERRORS = (
    aiohttp.ClientConnectorError,   # DNS failure, refused, network unreachable
    aiohttp.ClientOSError,
    aiohttp.ServerDisconnectedError,
    aiohttp.ServerTimeoutError,
    asyncio.TimeoutError,
)


def _hurricane_device_info() -> DeviceInfo:
    """Return the shared device info for all NOAA Hurricane image entities.

    Hurricane / NHC tropical-cyclone data is global and is not tied to any
    configured NWS office, so all hurricane image entities share a single
    dedicated device named ``NOAA Hurricane``.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, HURRICANE_DEVICE_ID)},
        name=HURRICANE_DEVICE_NAME,
        manufacturer="NOAA",
    )


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Geoelectric Field Image entity (legacy YAML support)."""
    _LOGGER.error(
        "Legacy YAML configuration for NOAA images is no longer supported. "
        "Please remove the YAML configuration and re-add the integration "
        "via the Home Assistant UI config flow."
    )
    return


def radar_loop_hours(config_entry) -> int:
    """Return the configured radar loop length in hours, clamped to range.

    Anything unusable -- absent, non-numeric, negative, absurd -- resolves to a
    number the rest of the code can rely on rather than raising during setup.
    """
    raw = resolve_entry_config(config_entry).get(
        CONF_RADAR_LOOP_HOURS, DEFAULT_RADAR_LOOP_HOURS
    )
    try:
        hours = int(raw)
    except (TypeError, ValueError):
        _LOGGER.warning(
            "Ignoring an unusable radar loop duration (%r); falling back to %d hours",
            raw, DEFAULT_RADAR_LOOP_HOURS,
        )
        return DEFAULT_RADAR_LOOP_HOURS
    return max(0, min(hours, RADAR_LOOP_MAX_HOURS))


async def async_discard_unused_radar_frames(hass, keep=None) -> None:
    """Delete stored frames for radar sites nothing is collecting any more.

    ``keep`` is the site this entry has just claimed, if any.  Every other
    directory is checked against the sites the remaining entries are actually
    building loops for, so switching office, or setting the duration to 0 --
    which the options screen promises will "store nothing" -- reclaims the
    disk instead of orphaning it until the integration is deleted.
    """
    base = hass.config.path(DOMAIN, RADAR_FRAME_DIR)

    wanted = set()
    if keep:
        wanted.add(keep)
    for entry in hass.config_entries.async_entries(DOMAIN):
        if radar_loop_hours(entry) <= 0:
            continue
        site = OFFICE_RADAR_SITES.get(
            resolve_entry_config(entry).get(CONF_OFFICE_CODE)
        )
        if site:
            wanted.add(site)

    try:
        present = await hass.async_add_executor_job(_list_radar_frame_dirs, base)
    except Exception as err:  # noqa: BLE001 - housekeeping must never break setup
        _LOGGER.debug("Could not list stored radar frames: %s", err)
        return

    for site in present:
        if site in wanted:
            continue
        _LOGGER.info(
            "Removing stored radar frames for %s; no configured office is "
            "building a loop from it any more", site,
        )
        await RadarFrameStore(hass, base, site).async_remove_all()


def _list_radar_frame_dirs(base: str) -> list[str]:
    """Return the radar site directories under ``base`` (executor side)."""
    try:
        return [
            name for name in os.listdir(base)
            if os.path.isdir(os.path.join(base, name))
        ]
    except FileNotFoundError:
        return []


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA image entities from config entry."""
    office_code = resolve_entry_config(config_entry)[CONF_OFFICE_CODE]

    # Global image entities (grouped under office device)
    geoelectric_image_entity = GeoelectricFieldImageEntity(hass, office_code)
    aurora_image_entity = AuroraForecastImageEntity(hass, office_code)

    entities = [
        geoelectric_image_entity,
        aurora_image_entity,
    ]

    # Hurricane image entities are global (NHC) and must only be added
    # once across all configured NWS offices, so they don't appear under
    # every office-specific device. Track the owning config entry's
    # entry_id so that if the owner is unloaded while other entries
    # remain we can release ownership and trigger a remaining entry to
    # re-create the entities.
    domain_data = hass.data.setdefault(DOMAIN, {})
    if not domain_data.get(HURRICANE_IMAGES_ADDED_KEY):
        entities.extend([
            HurricaneOutlookImageEntity(hass),
            GOESAirMassImageEntity(hass),
            GOESGeoColorImageEntity(hass),
        ])
        domain_data[HURRICANE_IMAGES_ADDED_KEY] = config_entry.entry_id

        def _release_hurricane_image_ownership() -> None:
            """Release hurricane-image ownership and re-create on a remaining entry.

            Fires when the owning config entry is unloaded. If other entries
            remain, clear the flag and reload one of them so its
            ``async_setup_entry`` re-adds the global hurricane images;
            otherwise the entities would disappear until Home Assistant
            restarts.
            """
            if domain_data.get(HURRICANE_IMAGES_ADDED_KEY) != config_entry.entry_id:
                return
            domain_data.pop(HURRICANE_IMAGES_ADDED_KEY, None)
            remaining = [
                e for e in hass.config_entries.async_entries(DOMAIN)
                if e.entry_id != config_entry.entry_id
            ]
            if remaining:
                target_entry_id = remaining[0].entry_id

                async def _reload_for_hurricane_images() -> None:
                    try:
                        await hass.config_entries.async_reload(target_entry_id)
                    except Exception:  # noqa: BLE001
                        _LOGGER.exception(
                            "Failed to reload entry %s to re-create global "
                            "hurricane images", target_entry_id,
                        )

                hass.async_create_task(_reload_for_hurricane_images())

        config_entry.async_on_unload(_release_hurricane_image_ownership)

    # Location-specific radar image entities
    radar_site = OFFICE_RADAR_SITES.get(office_code)

    if radar_site:
        # Add radar image entities for this location
        base_reflectivity_image = RadarBaseReflectivityImageEntity(hass, office_code, radar_site)
        loop_hours = radar_loop_hours(config_entry)
        radar_loop_image = RadarLoopImageEntity(
            hass, office_code, radar_site, loop_hours=loop_hours
        )
        entities.extend([base_reflectivity_image, radar_loop_image])
        # Setup runs again on every options change, so this is where a switch
        # away from a radar site -- or the loop being turned off entirely --
        # becomes visible.  Nothing else would ever clean those frames up:
        # async_remove_entry only knows the site the entry ends on, and a
        # store that is no longer constructed never prunes.
        hass.async_create_task(
            async_discard_unused_radar_frames(hass, keep=(
                radar_site if loop_hours > 0 else None
            ))
        )
        _LOGGER.info("Added radar image entities for office %s using radar site %s", office_code, radar_site)
    else:
        _LOGGER.warning("No radar site mapping found for office %s", office_code)

    # No ``update_before_add``: the first fetch is scheduled by
    # ``async_added_to_hass`` once the entity actually exists, so a slow or
    # unreachable NOAA can never hold up setting up the config entry.
    async_add_entities(entities)


class NoaaImageEntity(ImageEntity):
    """Base class for the NOAA image entities.

    Subclasses supply the upstream URL, the content type and a short label
    used in log messages; everything else -- fetching, caching, failure
    handling and the refresh timer -- lives here.

    The important behaviour is that ``async_image()`` never performs I/O.  It
    hands back whatever was last fetched successfully, and a failed fetch
    changes nothing at all, so a transient upstream failure is invisible to
    the dashboard: the previous frame stays on screen until a later refresh
    replaces it.

    Subclasses must assign anything ``_base_url()`` reads *before* calling
    ``super().__init__(hass)``; the base constructor resolves the first URL.
    """

    # Overridden per subclass; Home Assistant defaults everything to JPEG,
    # which is wrong for the PNG and GIF sources below.
    _attr_content_type = "image/jpeg"

    # Short human-readable subject used in log messages, e.g. "aurora forecast".
    _log_label = "NOAA"

    # Upstream URL without the cache-busting query string.  Subclasses whose
    # URL depends on instance state override ``_base_url()`` instead.
    _url = ""

    def __init__(self, hass) -> None:
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        # Note the name: Home Assistant's own ImageEntity owns ``_cached_image``
        # and stores an ``Image`` dataclass in it, so the raw bytes need a
        # attribute of their own.
        self._last_image_bytes: bytes | None = None
        # What was last fetched from the upstream URL, which for most entities
        # is the same object as ``_last_image_bytes``.  The radar loop breaks
        # that equivalence -- it displays a GIF it assembled from many fetches
        # -- so conditional revalidation and the 304 short-circuit have to key
        # off the fetched frame rather than the displayed picture.
        self._last_fetched_bytes: bytes | None = None
        # Revalidation state per upstream resource: {url: (etag, last_modified,
        # bytes)}.  The radar loop fetches two different resources through this
        # one entity, so a single slot would mean an ETag from one being
        # offered as a validator for the other -- and each fetch evicting the
        # other's, leaving neither able to revalidate.
        self._resource_cache: dict[str, tuple] = {}
        self._attr_image_last_updated = None
        self._last_etag: str | None = None
        self._last_modified: str | None = None
        self._failure_count = 0
        self._image_url = self.get_cache_busted_url()

    # -- URL handling ----------------------------------------------------

    def _base_url(self) -> str:
        """Return the upstream URL without cache busting."""
        return self._url

    def get_cache_busted_url(self, url: str | None = None) -> str:
        """Return an upstream URL with a coarse timestamp appended.

        The timestamp is rounded down to a 10-minute bucket: NOAA does not
        publish these images more often than that, and a coarse bucket keeps
        upstream and CDN caching effective while still defeating a stale
        cached copy.

        ``url`` defaults to this entity's own; the radar loop passes its
        fallback URL so that it is busted too rather than being served a stale
        copy from a CDN.
        """
        timestamp = dt_util.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'
        return f"{url or self._base_url()}?t={timestamp}"

    # -- Home Assistant plumbing -----------------------------------------

    async def async_added_to_hass(self) -> None:
        """Fetch the first frame and start the background refresh timer."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_scheduled_refresh, SCAN_INTERVAL
            )
        )
        # Kick off the first fetch as a scheduled call rather than awaiting it
        # here: entity setup must not block on a NOAA round trip, and during
        # the outages this class guards against that round trip is precisely
        # what hangs.
        self.async_on_remove(
            async_call_later(self.hass, 0, self._async_scheduled_refresh)
        )

    @property
    def entity_picture(self) -> str | None:
        """Return the picture URL, preferring Home Assistant's image proxy.

        Once a frame has been fetched the browser is pointed at
        ``/api/image_proxy/...``, which is what lets the cached copy survive a
        NOAA outage.  Before that first fetch ``image_last_updated`` is None
        and the base class returns None, which would render an empty card --
        so fall back to the upstream URL, on the grounds that the browser may
        well have working connectivity when Home Assistant does not.  That is
        exactly the case when Home Assistant restarts while its own resolver
        is broken.
        """
        return super().entity_picture or self._image_url

    async def async_image(self) -> bytes | None:
        """Return the bytes of the most recently fetched image.

        Deliberately does no I/O: a refresh failure must not be able to blank
        a picture we already have, and a slow NOAA must not be able to blow
        Home Assistant's 10-second image-proxy budget.  ``None`` (rather than
        ``b""``) is returned when nothing has ever been fetched, matching the
        upstream signature.
        """
        return self._last_image_bytes

    def _write_state_if_added(self) -> None:
        """Push new state, but only once Home Assistant has added the entity.

        A refresh that completes before the entity is added -- or after it has
        been removed -- must not raise ``NoEntitySpecifiedError``, which is
        the startup-error regression fixed in c7ed6e6.
        """
        if self.hass is None or self.entity_id is None:
            return
        self.async_write_ha_state()

    # -- Fetching --------------------------------------------------------

    async def _async_scheduled_refresh(self, now=None) -> None:
        """Refresh the cached image and publish the new state if it changed."""
        if await self._async_update_cache():
            self._write_state_if_added()

    async def _async_update_cache(self) -> bool:
        """Fetch the image and cache it.

        Returns True when the cached bytes actually changed, so the caller
        knows whether a state write is warranted.  A failed fetch changes
        nothing at all -- neither the cached bytes nor ``image_last_updated``
        -- which is what keeps the previous frame on the dashboard.
        """
        content = await self._async_fetch_image()
        if content is None:
            return False

        self._note_success()

        if content == self._last_image_bytes:
            _LOGGER.debug(
                "The %s image is unchanged (%d bytes)", self._log_label, len(content)
            )
            return False

        self._last_image_bytes = content
        self._attr_image_last_updated = dt_util.utcnow()
        _LOGGER.debug(
            "Fetched the %s image (%d bytes)", self._log_label, len(content)
        )
        return True

    def _note_success(self) -> None:
        """Reset the failure counter, announcing a recovery if there was one."""
        if self._failure_count >= IMAGE_FAILURE_WARN_AFTER:
            _LOGGER.info(
                "The %s image is available again after %d failed attempts",
                self._log_label, self._failure_count,
            )
        self._failure_count = 0

    def _conditional_headers(self, resource: str) -> dict[str, str]:
        """Return revalidation headers for the copy already in hand.

        The refresh runs on a timer whether or not anyone is looking at the
        dashboard, so revalidating keeps the steady-state cost close to zero
        for sources that publish infrequently.

        Validators are only offered back to the resource they came from.  An
        entity that fetches more than one URL would otherwise be asking "has
        it changed since?" about a different file entirely, and a server that
        answered 304 to that would hand back the wrong image.
        """
        headers = {"User-Agent": USER_AGENT}
        cached = self._resource_cache.get(resource)
        if cached is None:
            return headers
        etag, last_modified, _ = cached
        if etag:
            headers["If-None-Match"] = etag
        elif last_modified:
            headers["If-Modified-Since"] = last_modified
        return headers

    async def _async_fetch_image(self, url: str | None = None) -> bytes | None:
        """Fetch the image from NOAA, returning None on any failure.

        No failure path may touch ``_last_image_bytes``, ``_last_etag``,
        ``_last_modified`` or ``image_last_updated``.  That invariant is what
        keeps a blip from blanking the picture.

        ``url`` overrides the entity's own URL, which the radar loop uses to
        fall back to NOAA's ready-made animation without reimplementing any of
        the error handling below.
        """
        # The cache-busting query string changes every ten minutes, so identity
        # is tracked by the underlying resource rather than the fetched URL.
        resource = url or self._base_url()
        self._image_url = self.get_cache_busted_url(resource)
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=IMAGE_FETCH_TIMEOUT)
            async with session.get(
                self._image_url,
                timeout=timeout,
                headers=self._conditional_headers(resource),
            ) as response:
                if response.status == 304 and resource in self._resource_cache:
                    _LOGGER.debug(
                        "The %s image is unchanged upstream (HTTP 304)",
                        self._log_label,
                    )
                    # Republish this resource's validators as the current ones:
                    # callers read ``_last_modified`` straight after a fetch to
                    # date what came back, and a 304 still describes this
                    # resource, not whichever one was fetched most recently.
                    etag, last_modified, cached = self._resource_cache[resource]
                    self._last_etag = etag
                    self._last_modified = last_modified
                    self._last_fetched_bytes = cached
                    return cached
                if response.status != 200:
                    self._log_failure(
                        f"HTTP {response.status}",
                        transient=response.status >= 500,
                    )
                    return None
                content_type = response.headers.get('content-type', '')
                content_type = content_type.split(';')[0].strip().lower()
                if 'image' not in content_type:
                    self._log_failure(
                        f"expected an image but the content type was {content_type!r}",
                        transient=False,
                    )
                    return None
                content = await response.read()
                etag = response.headers.get('etag')
                last_modified = response.headers.get('last-modified')
        except _TRANSIENT_FETCH_ERRORS as err:
            self._log_failure(f"{err}" or type(err).__name__, transient=True)
            return None
        except aiohttp.ClientError as err:
            self._log_failure(f"{err}" or type(err).__name__, transient=False)
            return None
        except Exception as err:  # noqa: BLE001
            self._log_failure(f"unexpected error: {err}", transient=False)
            return None

        if not content:
            self._log_failure("the response body was empty", transient=False)
            return None
        if len(content) > IMAGE_MAX_BYTES:
            self._log_failure(
                f"the response was {len(content)} bytes, over the "
                f"{IMAGE_MAX_BYTES} byte limit",
                transient=False,
            )
            return None

        # Serve what NOAA actually sent rather than the class default.
        self._attr_content_type = content_type
        self._last_etag = etag
        self._last_modified = last_modified
        self._last_fetched_bytes = content
        self._resource_cache[resource] = (etag, last_modified, content)
        return content

    def _log_failure(self, reason: str, *, transient: bool) -> None:
        """Record a failed fetch and log it at a level that fits its duration.

        A NOAA image source being briefly unreachable is normal for a
        ``cloud_polling`` integration and is not worth an error per blip, so
        transient failures start at debug while a cached frame is still being
        served, warn once the outage has lasted a while, and only escalate to
        error when it is sustained -- and then only periodically.

        A non-transient failure (a 404, a content type that is not an image)
        means the URL or our expectations are wrong rather than the weather,
        so it always warns.
        """
        self._failure_count += 1
        count = self._failure_count

        if not transient:
            level = logging.WARNING
        elif self._last_image_bytes is None and count < IMAGE_FAILURE_WARN_AFTER:
            # Nothing to fall back on, so the user does see a blank card.
            level = logging.WARNING
        elif count == IMAGE_FAILURE_WARN_AFTER:
            level = logging.WARNING
        elif count >= IMAGE_FAILURE_ERROR_AFTER and count % IMAGE_FAILURE_ERROR_AFTER == 0:
            level = logging.ERROR
        else:
            level = logging.DEBUG

        if self._last_image_bytes is None:
            _LOGGER.log(
                level,
                "Could not fetch the %s image (attempt %d, no image cached yet): %s",
                self._log_label, count, reason,
            )
        else:
            _LOGGER.log(
                level,
                "Could not refresh the %s image (attempt %d); still showing the "
                "copy fetched at %s: %s",
                self._log_label, count, self._attr_image_last_updated, reason,
            )


class GeoelectricFieldImageEntity(NoaaImageEntity):
    """Representation of the Geoelectric Field Image."""

    _attr_content_type = "image/png"
    _log_label = "geoelectric field"
    _url = BASE_IMAGE_URL

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        self._office_code = office_code
        super().__init__(hass)

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Geoelectric Field Image'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_geoelectric_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class AuroraForecastImageEntity(NoaaImageEntity):
    """Representation of the aurora Field Image."""

    _attr_content_type = "image/jpeg"
    _log_label = "aurora forecast"
    _url = AURORA_URL

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        self._office_code = office_code
        super().__init__(hass)

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Aurora Forecast Image'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_aurora_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class HurricaneOutlookImageEntity(NoaaImageEntity):
    """Representation of the Hurricane Outlook Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("Outlook Image") to produce the entity ID
    ``image.noaa_hurricane_outlook_image``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/png"
    _log_label = "hurricane outlook"
    _url = HURRICANE_OUTLOOK_URL

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this entity is global (NHC).
        """
        super().__init__(hass)

    @property
    def name(self):
        """Return the local entity name."""
        return 'Outlook Image'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_outlook_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()


class RadarBaseReflectivityImageEntity(NoaaImageEntity):
    """Representation of the Radar Base Reflectivity Image for a specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the office weather device name (e.g.
    "NOAA ILM Weather") with the local entity name ("Radar Base
    Reflectivity") to produce the entity ID
    ``image.noaa_ilm_weather_radar_base_reflectivity``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/gif"

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar image entity."""
        self._office_code = office_code
        self._radar_site = radar_site
        self._log_label = f"radar base reflectivity for {office_code}"
        super().__init__(hass)

    def _base_url(self) -> str:
        """Return the NEXRAD base reflectivity URL for this radar site."""
        return NWS_RADAR_BASE_URL.format(radar=self._radar_site)

    @property
    def name(self):
        """Return the local entity name."""
        return 'Radar Base Reflectivity'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code.lower()}_weather_radar_base_reflectivity'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class RadarLoopImageEntity(NoaaImageEntity):
    """An animated NEXRAD loop, either NOAA's own or one assembled here.

    NOAA publishes a ready-made animation, but it is fixed at ten frames
    covering roughly fifty minutes and the server keeps only those ten frames,
    so a longer loop cannot be downloaded.  When ``loop_hours`` is set this
    entity instead collects one frame per refresh into
    :class:`~.radar_loop.RadarFrameStore` and assembles the animation itself,
    which means the loop starts short after a fresh install and fills out over
    the hours that follow.  Frames outlive restarts, so that happens once
    rather than on every reboot.

    ``loop_hours = 0`` restores the previous behaviour exactly: NOAA's loop,
    proxied unchanged, with nothing written to disk.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the office weather device name (e.g.
    "NOAA ILM Weather") with the local entity name ("Radar Loop") to
    produce the entity ID ``image.noaa_ilm_weather_radar_loop``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/gif"

    def __init__(self, hass, office_code, radar_site, loop_hours=0):
        """Initialize the radar loop image entity."""
        self._office_code = office_code
        self._radar_site = radar_site
        self._log_label = f"radar loop for {office_code}"
        self._loop_hours = loop_hours
        self._store = None
        # Whether the picture currently on screen is NOAA's animation rather
        # than one built here.  True until the buffer has enough frames to
        # improve on it, and again whenever assembly fails.
        self._serving_upstream = True
        self._frame_count = 0
        self._window_start = None
        self._window_end = None
        if loop_hours > 0:
            self._store = RadarFrameStore(
                hass,
                hass.config.path(DOMAIN, RADAR_FRAME_DIR),
                radar_site,
            )
        super().__init__(hass)

    @property
    def _building_locally(self) -> bool:
        """True when this entity assembles the loop rather than proxying it."""
        return self._store is not None

    @property
    def _window(self) -> timedelta:
        """Return how far back the loop reaches."""
        return timedelta(hours=self._loop_hours)

    def _base_url(self) -> str:
        """Return the URL each refresh fetches.

        Building locally means collecting single scans, so the refresh targets
        the latest frame rather than NOAA's finished animation.
        """
        if self._building_locally:
            return NWS_RADAR_BASE_URL.format(radar=self._radar_site)
        return NWS_RADAR_LOOP_URL.format(radar=self._radar_site)

    @property
    def extra_state_attributes(self):
        """Expose what the loop actually covers, for templates and debugging.

        A loop that is quietly shorter than asked for -- because the buffer is
        still filling, or because Pillow is missing -- is otherwise invisible.
        """
        return {
            # Describes the animation actually being served, not the setting:
            # a local loop that has fallen back to NOAA's says so.
            "loop_mode": "upstream" if self._serving_upstream else "local",
            "loop_hours": self._loop_hours,
            "frame_count": self._frame_count,
            "window_start": (
                self._window_start.isoformat() if self._window_start else None
            ),
            "window_end": (
                self._window_end.isoformat() if self._window_end else None
            ),
        }

    async def async_added_to_hass(self) -> None:
        """Start the refresh timer, and prune anything now out of window.

        Pruning here rather than on the first refresh means shortening the
        duration takes effect as soon as the entry reloads, instead of leaving
        stale frames on disk for another refresh interval.
        """
        await super().async_added_to_hass()
        if self._building_locally:
            self.async_on_remove(
                async_call_later(self.hass, 0, self._async_prune)
            )

    async def _async_prune(self, now=None) -> None:
        """Drop frames outside the configured window."""
        await self._store.async_prune(self._window, dt_util.utcnow())

    async def _async_update_cache(self) -> bool:
        """Collect the latest scan and rebuild the loop from what we hold.

        Returns True only when the displayed animation actually changed.  Every
        failure path returns False without touching the cached bytes, so the
        previous loop stays on the dashboard.
        """
        if not self._building_locally:
            return await super()._async_update_cache()

        frame = await self._async_fetch_image()
        if frame is None:
            return False
        self._note_success()

        # Last-Modified is when NOAA published the scan, which puts frames on
        # the real four-to-six minute volume-scan cadence rather than on our
        # arbitrary refresh boundary -- and makes two refreshes that see the
        # same scan resolve to the same file, so dedup costs nothing.
        # Hashing the bytes instead would be actively wrong: two consecutive
        # scans of a clear sky are genuinely identical, so a quiet night would
        # collapse to a single frame and the loop would cut straight from
        # "clear" to "storm" with no sense of time passing.
        timestamp = parse_http_date(self._last_modified)
        if timestamp is None:
            timestamp = dt_util.utcnow().replace(second=0, microsecond=0)

        added = await self._store.async_add_frame(timestamp, frame)
        # Pruned every refresh rather than only when something was stored: a
        # radar site stuck on one scan for hours -- maintenance, an outage --
        # would otherwise never prune at all, and the window would quietly
        # stretch past what was asked for.
        await self._store.async_prune(self._window, dt_util.utcnow())
        if not added and self._last_image_bytes is not None:
            # Same scan as last time and we already have a loop built from it.
            return False

        return await self._async_rebuild_loop()

    async def _async_rebuild_loop(self) -> bool:
        """Assemble the stored frames, falling back to NOAA's loop if needed."""
        frames = await self._store.async_frames()
        if len(frames) < RADAR_LOOP_MIN_FRAMES:
            _LOGGER.debug(
                "Only %d radar frames stored for %s; showing NOAA's own loop "
                "until the buffer fills", len(frames), self._office_code,
            )
            return await self._async_serve_upstream_loop()

        # Sampling and encoding go to the executor together.  Both are pure
        # CPU over the frame list, this runs on a timer whether or not anyone
        # is looking at the dashboard, and splitting them would put the
        # sampler's work back on the event loop for nothing.
        loop = await self.hass.async_add_executor_job(
            self._build_loop, frames, dt_util.utcnow()
        )
        if loop is None:
            return await self._async_serve_upstream_loop()

        # The window is described from the frames the encoder actually used,
        # not the ones it was offered: unreadable frames and any shed to get
        # under the size limit are not in the animation, and reporting them
        # would hide exactly the shortfall these attributes exist to show.
        used = set(loop.paths)
        covered = [timestamp for timestamp, path in frames if path in used]
        self._serving_upstream = False
        self._frame_count = len(loop.paths)
        self._window_start = covered[0] if covered else None
        self._window_end = covered[-1] if covered else None

        if loop.data == self._last_image_bytes:
            return False
        self._last_image_bytes = loop.data
        self._attr_content_type = "image/gif"
        self._attr_image_last_updated = dt_util.utcnow()
        return True

    def _build_loop(self, frames, now):
        """Sample the stored frames and encode them (executor side).

        Returns None when the sample is too thin to beat NOAA's own loop.  The
        floor is applied here, to the frames that will actually be encoded --
        checking it against everything on disk would let a window with a long
        outage in the middle ship a three-frame animation in place of NOAA's
        ten, which is the outcome the floor exists to prevent.
        """
        paths = select_frames(
            frames,
            window=self._window,
            max_frames=RADAR_LOOP_MAX_FRAMES,
            now=now,
        )
        if len(paths) < RADAR_LOOP_MIN_FRAMES:
            _LOGGER.debug(
                "Only %d of %d stored radar frames for %s fall inside the "
                "loop window; showing NOAA's own loop instead",
                len(paths), len(frames), self._office_code,
            )
            return None
        return assemble_gif(paths)

    async def _async_serve_upstream_loop(self) -> bool:
        """Show NOAA's own animation instead of one we could not build.

        Used while the buffer is still filling and whenever assembly fails, so
        the card is never blank and never worse than it was before this
        feature existed.
        """
        content = await self._async_fetch_image(
            NWS_RADAR_LOOP_URL.format(radar=self._radar_site)
        )
        if content is None or content == self._last_image_bytes:
            return False
        self._serving_upstream = True
        self._frame_count = 0
        self._window_start = None
        self._window_end = None
        self._last_image_bytes = content
        self._attr_image_last_updated = dt_util.utcnow()
        return True

    @property
    def name(self):
        """Return the local entity name."""
        return 'Radar Loop'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code.lower()}_weather_radar_loop'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class GOESAirMassImageEntity(NoaaImageEntity):
    """Representation of the GOES-19 Air Mass RGB Satellite Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("GOES Air Mass") to produce the entity ID
    ``image.noaa_hurricane_goes_air_mass``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"
    _log_label = "GOES Air Mass"
    _url = GOES_AIRMASS_URL

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this satellite image is global and is grouped under the
        NOAA Hurricane device alongside the other tropical-cyclone
        tracking images.
        """
        super().__init__(hass)

    @property
    def name(self):
        """Return the local entity name."""
        return 'GOES Air Mass'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_goes_air_mass'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()


class GOESGeoColorImageEntity(NoaaImageEntity):
    """Representation of the GOES-19 GeoColor Satellite Image.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name ("NOAA Hurricane") with the
    local entity name ("GOES Geocolor") to produce the entity ID
    ``image.noaa_hurricane_goes_geocolor``.
    """

    _attr_has_entity_name = True
    _attr_content_type = "image/jpeg"
    _log_label = "GOES GeoColor"
    _url = GOES_GEOCOLOR_URL

    def __init__(self, hass, office_code=None):
        """Initialize the image entity.

        ``office_code`` is accepted for backward compatibility but is
        unused: this satellite image is global and is grouped under the
        NOAA Hurricane device alongside the other tropical-cyclone
        tracking images.
        """
        super().__init__(hass)

    @property
    def name(self):
        """Return the local entity name."""
        return 'GOES Geocolor'

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_goes_geocolor'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return _hurricane_device_info()
