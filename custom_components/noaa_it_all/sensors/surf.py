"""Surf / ocean sensors for NOAA Integration.

Covers rip current risk, surf height and water temperature from NWS
Surf Zone Forecasts (SRF product).
"""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
from homeassistant.helpers.entity import Entity, DeviceInfo

from ..const import NWS_SRF_URL, REQUEST_TIMEOUT, USER_AGENT, DOMAIN
from ..parsers import parse_rip_current_risk, parse_surf_height, parse_water_temperature

_LOGGER = logging.getLogger(__name__)


class RipCurrentRiskSensor(Entity):
    """Representation of Rip Current Risk sensor for specific NWS office location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_rip_current_risk"
        self._attr_name = "NOAA Surf - Rip Current Risk"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:waves'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new rip current risk data for the specific location."""
        try:
            url = NWS_SRF_URL.format(office=self._office_code)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                forecast_text = (await response.text()).lower()
            self._attr_available = True

            risk_level = parse_rip_current_risk(forecast_text)

            self._state = risk_level
            self._attributes = {
                'office_code': self._office_code,
                'forecast_source': url,
                'last_updated': 'Check forecast for timestamp',
            }

            _LOGGER.debug("Updated rip current risk for %s: %s", self._office_code, risk_level)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}


class SurfHeightSensor(Entity):
    """Representation of Surf Height sensor for specific NWS office location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_surf_height"
        self._attr_name = "NOAA Surf - Surf Height"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'ft'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:wave'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new surf height data for the specific location."""
        try:
            url = NWS_SRF_URL.format(office=self._office_code)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                forecast_text = (await response.text()).lower()
            self._attr_available = True

            surf_height = parse_surf_height(forecast_text)

            self._state = surf_height if surf_height else "Unknown"
            self._attributes = {
                'office_code': self._office_code,
                'forecast_source': url,
                'last_updated': 'Check forecast for timestamp',
            }

            _LOGGER.debug("Updated surf height for %s: %s", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}


class WaterTemperatureSensor(Entity):
    """Representation of Water Temperature sensor for specific NWS office location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_water_temperature"
        self._attr_name = "NOAA Surf - Water Temperature"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return '°F'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:thermometer-water'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new water temperature data for the specific location."""
        try:
            url = NWS_SRF_URL.format(office=self._office_code)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                forecast_text = (await response.text()).lower()
            self._attr_available = True

            water_temp = parse_water_temperature(forecast_text)

            self._state = water_temp if water_temp else "Unknown"
            self._attributes = {
                'office_code': self._office_code,
                'forecast_source': url,
                'last_updated': 'Check forecast for timestamp',
            }

            _LOGGER.debug("Updated water temperature for %s: %s", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}
