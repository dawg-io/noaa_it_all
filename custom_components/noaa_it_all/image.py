import aiohttp
import logging
from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from datetime import timedelta, datetime

from .const import (
    CONF_OFFICE_CODE, DOMAIN, NWS_RADAR_BASE_URL, NWS_RADAR_LOOP_URL,
    OFFICE_RADAR_SITES, REQUEST_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)  # Update every 5 minutes

BASE_IMAGE_URL = ('https://services.swpc.noaa.gov/images/animations/geoelectric/'
                  'InterMagEarthScope/EmapGraphics_1m/latest.png')
AURORA_URL = ('https://services.swpc.noaa.gov/experimental/images/aurora_dashboard/'
              'tonights_static_viewline_forecast.png')

# NOAA Hurricane Image Sources
HURRICANE_OUTLOOK_URL = 'https://www.nhc.noaa.gov/xgtwo/two_atl_2d0.png'

# NOAA GOES Satellite Image Sources
GOES_AIRMASS_URL = 'https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/AirMass/1250x750.jpg'
GOES_GEOCOLOR_URL = 'https://cdn.star.nesdis.noaa.gov/GOES19/ABI/CONUS/GEOCOLOR/1250x750.jpg'


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the Geoelectric Field Image entity (legacy YAML support)."""
    _LOGGER.error(
        "Legacy YAML configuration for NOAA images is no longer supported. "
        "Please remove the YAML configuration and re-add the integration "
        "via the Home Assistant UI config flow."
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA image entities from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]

    # Global image entities (grouped under office device)
    geoelectric_image_entity = GeoelectricFieldImageEntity(hass, office_code)
    aurora_image_entity = AuroraForecastImageEntity(hass, office_code)
    hurricane_outlook_image = HurricaneOutlookImageEntity(hass, office_code)
    goes_airmass_image = GOESAirMassImageEntity(hass, office_code)
    goes_geocolor_image = GOESGeoColorImageEntity(hass, office_code)

    # Location-specific radar image entities
    radar_site = OFFICE_RADAR_SITES.get(office_code)

    entities = [
        geoelectric_image_entity,
        aurora_image_entity,
        hurricane_outlook_image,
        goes_airmass_image,
        goes_geocolor_image,
    ]

    if radar_site:
        # Add radar image entities for this location
        base_reflectivity_image = RadarBaseReflectivityImageEntity(hass, office_code, radar_site)
        radar_loop_image = RadarLoopImageEntity(hass, office_code, radar_site)
        entities.extend([base_reflectivity_image, radar_loop_image])
        _LOGGER.info("Added radar image entities for office %s using radar site %s", office_code, radar_site)
    else:
        _LOGGER.warning("No radar site mapping found for office %s", office_code)

    async_add_entities(entities, True)


class GeoelectricFieldImageEntity(ImageEntity):
    """Representation of the Geoelectric Field Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Geoelectric Field Image'

    @property
    def entity_picture(self):
        """Return the URL of the latest geoelectric field image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_geoelectric_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since NOAA updates aren't more frequent
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{BASE_IMAGE_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated geoelectric field image URL")
        except Exception as e:
            _LOGGER.error("Error during geoelectric field image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched geoelectric field image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch geoelectric field image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching geoelectric field image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching geoelectric field image: %s", e)
        return b""


class AuroraForecastImageEntity(ImageEntity):
    """Representation of the aurora Field Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Aurora Forecast Image'

    @property
    def entity_picture(self):
        """Return the URL of the latest aurora forecast image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_aurora_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since NOAA updates aren't more frequent
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{AURORA_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated aurora forecast image URL")
        except Exception as e:
            _LOGGER.error("Error during aurora forecast image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched aurora forecast image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch aurora forecast image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching aurora forecast image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching aurora forecast image: %s", e)
        return b""


class HurricaneOutlookImageEntity(ImageEntity):
    """Representation of the Hurricane Outlook Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'Hurricane Outlook Image'

    @property
    def entity_picture(self):
        """Return the URL of the latest hurricane outlook image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_outlook_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{HURRICANE_OUTLOOK_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()
            _LOGGER.debug("Updated hurricane outlook image URL")
        except Exception as e:
            _LOGGER.error("Error during hurricane outlook image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched hurricane outlook image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch hurricane outlook image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching hurricane outlook image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching hurricane outlook image: %s", e)
        return b""


class RadarBaseReflectivityImageEntity(ImageEntity):
    """Representation of the Radar Base Reflectivity Image for a specific location."""

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._radar_site = radar_site
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return f'NOAA Weather - Radar Base Reflectivity ({self._office_code})'

    @property
    def entity_picture(self):
        """Return the URL of the latest radar base reflectivity image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_radar_base_reflectivity'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 10-minute intervals for cache busting since radar updates every 5-10 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        base_url = NWS_RADAR_BASE_URL.format(radar=self._radar_site)
        return f"{base_url}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated radar base reflectivity image URL for %s", self._office_code)
        except Exception as e:
            _LOGGER.error("Error during radar base reflectivity image update for %s: %s", self._office_code, e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s for radar %s",
                                        content_type, self._radar_site)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched radar base reflectivity image for %s (%d bytes)",
                                  self._office_code, len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch radar base reflectivity image for %s: HTTP %d",
                                    self._office_code, response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching radar base reflectivity image for %s: %s", self._office_code, e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching radar base reflectivity image for %s: %s",
                          self._office_code, e)
        return b""


class RadarLoopImageEntity(ImageEntity):
    """Representation of the Radar Loop Image (animated) for a specific location."""

    def __init__(self, hass, office_code, radar_site):
        """Initialize the radar loop image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._radar_site = radar_site
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return f'NOAA Weather - Radar Loop ({self._office_code})'

    @property
    def entity_picture(self):
        """Return the URL of the latest radar loop image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_radar_loop'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 10-minute intervals for cache busting since radar updates every 5-10 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        base_url = NWS_RADAR_LOOP_URL.format(radar=self._radar_site)
        return f"{base_url}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated radar loop image URL for %s", self._office_code)
        except Exception as e:
            _LOGGER.error("Error during radar loop image update for %s: %s",
                          self._office_code, e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s for radar %s",
                                        content_type, self._radar_site)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched radar loop image for %s (%d bytes)",
                                  self._office_code, len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch radar loop image for %s: HTTP %d",
                                    self._office_code, response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching radar loop image for %s: %s", self._office_code, e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching radar loop image for %s: %s",
                          self._office_code, e)
        return b""


class GOESAirMassImageEntity(ImageEntity):
    """Representation of the GOES-19 Air Mass RGB Satellite Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'NOAA Satellite - GOES Air Mass'

    @property
    def entity_picture(self):
        """Return the URL of the latest GOES Air Mass image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_goes_airmass_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since GOES updates every ~5 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{GOES_AIRMASS_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated GOES Air Mass image URL")
        except Exception as e:
            _LOGGER.error("Error during GOES Air Mass image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched GOES Air Mass image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch GOES Air Mass image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching GOES Air Mass image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching GOES Air Mass image: %s", e)
        return b""


class GOESGeoColorImageEntity(ImageEntity):
    """Representation of the GOES-19 GeoColor Satellite Image."""

    def __init__(self, hass, office_code):
        """Initialize the image entity."""
        super().__init__(hass)
        self.hass = hass
        self._office_code = office_code
        self._image_url = self.get_cache_busted_url()

    @property
    def name(self):
        """Return the name of the entity."""
        return 'NOAA Satellite - GOES GeoColor'

    @property
    def entity_picture(self):
        """Return the URL of the latest GOES GeoColor image."""
        return self._image_url

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_goes_geocolor_image'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}")},
            name=f"NOAA {self._office_code}",
            manufacturer="NOAA"
        )

    def get_cache_busted_url(self):
        """Add a timestamp to the URL to prevent caching."""
        # Use 5-minute intervals for cache busting since GOES updates every ~5 minutes
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        timestamp = timestamp[:-1] + '0'  # Round to 10-minute intervals
        return f"{GOES_GEOCOLOR_URL}?t={timestamp}"

    async def async_update(self):
        """Fetch and update the latest image content asynchronously."""
        try:
            # Fetch the image and update with cache busting
            self._image_url = self.get_cache_busted_url()
            self.async_write_ha_state()  # Notify Home Assistant of the state change
            _LOGGER.debug("Updated GOES GeoColor image URL")
        except Exception as e:
            _LOGGER.error("Error during GOES GeoColor image update: %s", e)

    async def async_image(self) -> bytes:
        """Return the bytes of the latest image."""
        try:
            session = async_get_clientsession(self.hass)
            timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            async with session.get(self._image_url, timeout=timeout) as response:
                if response.status == 200:
                    content_type = response.headers.get('content-type', '').lower()
                    if 'image' not in content_type:
                        _LOGGER.warning("Expected image content but got: %s", content_type)
                        return b""
                    content = await response.read()
                    _LOGGER.debug("Successfully fetched GOES GeoColor image (%d bytes)", len(content))
                    return content
                else:
                    _LOGGER.warning("Failed to fetch GOES GeoColor image: HTTP %d", response.status)
        except aiohttp.ClientError as e:
            _LOGGER.error("Error fetching GOES GeoColor image: %s", e)
        except Exception as e:
            _LOGGER.error("Unexpected error fetching GOES GeoColor image: %s", e)
        return b""
