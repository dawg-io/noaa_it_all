"""Extra weather sensors for NOAA Integration.

Covers cloud cover (gridpoint data), radar timestamp, and area forecast
discussion (AFD) text.
"""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
import re
from homeassistant.helpers.entity import Entity, DeviceInfo

from ..const import (
    NWS_POINTS_URL, NWS_AFD_URL, REQUEST_TIMEOUT,
    USER_AGENT, OFFICE_RADAR_SITES, DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CloudCoverSensor(Entity):
    """Representation of Cloud Cover sensor for specific location."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = None
        self._attributes = {}
        self._gridpoint_url = None
        self._grid_fetched = False

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Cloud Cover'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return '%'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:cloud-percent'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        return f"noaa_{self._office_code}_{lat_str}_{lon_str}_cloud_cover"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new cloud cover data."""
        # Fetch gridpoint URL from lat/lon if not already fetched
        if not self._grid_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_gridpoint_url()

        if not self._gridpoint_url:
            _LOGGER.error("Unable to get gridpoint URL for coordinates (lat: %s, lon: %s)",
                          self._latitude, self._longitude)
            self._state = None
            self._attributes = {'error': 'Unable to get gridpoint URL for the specified coordinates',
                                'availability': 'Not available for this location'}
            self._attr_available = False
            return

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                self._gridpoint_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})
            sky_cover = properties.get('skyCover', {})

            # Get current sky cover value
            if sky_cover and 'values' in sky_cover:
                values = sky_cover['values']
                if values and len(values) > 0:
                    # Get the most recent value
                    current_value = values[0].get('value')
                    if current_value is not None:
                        self._state = round(current_value)
                        self._attributes = {
                            'office_code': self._office_code,
                            'latitude': self._latitude,
                            'longitude': self._longitude,
                            'valid_time': values[0].get('validTime', 'Unknown'),
                            'availability': 'Available from NWS gridpoint data'
                        }
                        _LOGGER.debug("Updated cloud cover for %s: %s%%", self._office_code, self._state)
                        return

            # No data available
            self._state = None
            self._attributes = {
                'office_code': self._office_code,
                'latitude': self._latitude,
                'longitude': self._longitude,
                'availability': 'Data not available at this time'
            }
            _LOGGER.debug("No cloud cover data available for %s", self._office_code)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching cloud cover for %s", self._office_code)
            self._state = None
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching cloud cover for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Request error: {e}'}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing cloud cover for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Parse error: {e}'}

    async def _async_fetch_gridpoint_url(self):
        """Fetch gridpoint URL from latitude and longitude."""
        try:
            points_url = NWS_POINTS_URL.format(lat=self._latitude, lon=self._longitude)
            _LOGGER.debug("Fetching gridpoint URL for lat=%s, lon=%s from %s",
                          self._latitude, self._longitude, points_url)

            session = async_get_clientsession(self.hass)
            async with session.get(
                points_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            properties = data.get('properties', {})

            # Get the gridpoint URL
            gridpoint_url = properties.get('forecastGridData')

            if gridpoint_url:
                self._gridpoint_url = gridpoint_url
                _LOGGER.info("Found gridpoint URL for lat=%s, lon=%s: %s",
                             self._latitude, self._longitude, self._gridpoint_url)
            else:
                _LOGGER.error("No gridpoint URL found for lat=%s, lon=%s",
                              self._latitude, self._longitude)

            self._grid_fetched = True

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout fetching gridpoint URL for lat=%s, lon=%s",
                          self._latitude, self._longitude)
            self._grid_fetched = True
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching gridpoint URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing gridpoint URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True


class RadarTimestampSensor(Entity):
    """Representation of Radar Timestamp sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._radar_site = OFFICE_RADAR_SITES.get(office_code)

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Radar Timestamp'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:radar'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_radar_timestamp"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch radar timestamp from HTTP headers."""
        if not self._radar_site:
            _LOGGER.error("No radar site mapping found for office code: %s", self._office_code)
            self._state = None
            self._attributes = {
                'office_code': self._office_code,
                'availability': 'Not available for this office location'
            }
            return

        try:
            from ..const import NWS_RADAR_BASE_URL
            radar_url = NWS_RADAR_BASE_URL.format(radar=self._radar_site)

            session = async_get_clientsession(self.hass)
            async with session.head(
                radar_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                last_modified = response.headers.get('Last-Modified')
            self._attr_available = True

            if last_modified:
                # Parse the timestamp
                from email.utils import parsedate_to_datetime
                timestamp = parsedate_to_datetime(last_modified)
                self._state = timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
                self._attributes = {
                    'office_code': self._office_code,
                    'radar_site': self._radar_site,
                    'timestamp_iso': timestamp.isoformat(),
                    'radar_url': radar_url,
                    'availability': 'Available from NWS radar images'
                }
                _LOGGER.debug("Updated radar timestamp for %s: %s", self._office_code, self._state)
            else:
                _LOGGER.warning("No Last-Modified header found for radar %s", self._radar_site)
                self._state = None
                self._attributes = {
                    'office_code': self._office_code,
                    'radar_site': self._radar_site,
                    'availability': 'Timestamp not available'
                }

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching radar timestamp for %s", self._office_code)
            self._state = None
            self._attributes = {'error': 'Timeout fetching radar data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching radar timestamp for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Error parsing radar timestamp for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Parse error: {e}'}


class ForecastDiscussionSensor(Entity):
    """Representation of Forecast Discussion sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Forecast Discussion'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:text-box-outline'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_forecast_discussion"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch forecast discussion from NWS."""
        try:
            url = NWS_AFD_URL.format(office=self._office_code)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                html_content = await response.text()
            self._attr_available = True

            # Extract text from <pre> tag which contains the forecast discussion
            pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', html_content, re.DOTALL | re.IGNORECASE)

            if pre_match:
                discussion_text = pre_match.group(1).strip()

                # Clean up HTML entities
                discussion_text = discussion_text.replace('&nbsp;', ' ')
                discussion_text = discussion_text.replace('&amp;', '&')
                discussion_text = discussion_text.replace('&lt;', '<')
                discussion_text = discussion_text.replace('&gt;', '>')

                # Extract issue time if available
                issue_time_match = re.search(r'(\d{3,4}\s+(?:AM|PM)\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{4})',
                                             discussion_text, re.IGNORECASE)
                issue_time = issue_time_match.group(1) if issue_time_match else 'Unknown'

                # Create a summary (first 200 characters)
                summary = discussion_text[:200] + '...' if len(discussion_text) > 200 else discussion_text

                self._state = 'Available'
                self._attributes = {
                    'office_code': self._office_code,
                    'issue_time': issue_time,
                    'summary': summary,
                    'full_text': discussion_text,
                    'text_length': len(discussion_text),
                    'availability': 'Available from NWS Area Forecast Discussion (AFD)'
                }
                _LOGGER.debug("Updated forecast discussion for %s: %d characters",
                              self._office_code, len(discussion_text))
            else:
                _LOGGER.warning("Could not extract forecast discussion text for %s", self._office_code)
                self._state = None
                self._attributes = {
                    'office_code': self._office_code,
                    'availability': 'Unable to parse forecast discussion'
                }

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching forecast discussion for %s", self._office_code)
            self._state = None
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching forecast discussion for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Error parsing forecast discussion for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Parse error: {e}'}
