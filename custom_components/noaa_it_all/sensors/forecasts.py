"""Forecast sensors for NOAA Integration.

Covers extended (7-day) and hourly NWS forecast data.
"""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
from homeassistant.helpers.entity import Entity, DeviceInfo

from ..const import NWS_POINTS_URL, REQUEST_TIMEOUT, USER_AGENT, DOMAIN
from ..parsers import format_forecast_text, format_forecast_periods, format_hourly_periods

_LOGGER = logging.getLogger(__name__)

# Forecast constants
MAX_FORECAST_PERIODS = 14  # 7 days (day + night for each day)
MAX_HOURLY_PERIODS = 48  # 48 hours of hourly forecasts


class ForecastBaseSensor(Entity):
    """Base class for forecast sensors."""

    def __init__(self, office_code, latitude, longitude, forecast_type):
        """Initialize the base forecast sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._forecast_type = forecast_type  # 'forecast' or 'forecastHourly'
        self._state = None
        self._attributes = {}
        self._forecast_url = None
        self._grid_fetched = False

    def _format_coordinates_for_id(self):
        """Format coordinates for unique ID generation."""
        if self._latitude is not None and self._longitude is not None:
            lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
            lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
            return f"{lat_str}_{lon_str}"
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def _async_fetch_forecast_url(self):
        """Fetch forecast URL from latitude and longitude."""
        try:
            points_url = NWS_POINTS_URL.format(lat=self._latitude, lon=self._longitude)
            _LOGGER.debug("Fetching forecast URL for lat=%s, lon=%s from %s",
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

            # Get the forecast URL directly from the points API
            forecast_url = properties.get(self._forecast_type)

            if forecast_url:
                self._forecast_url = forecast_url
                _LOGGER.info("Found %s URL for lat=%s, lon=%s: %s",
                             self._forecast_type, self._latitude, self._longitude, self._forecast_url)
            else:
                _LOGGER.error("No %s URL found for lat=%s, lon=%s",
                              self._forecast_type, self._latitude, self._longitude)

            self._grid_fetched = True

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout fetching forecast URL for lat=%s, lon=%s",
                          self._latitude, self._longitude)
            self._grid_fetched = True
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching forecast URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing forecast URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True


class ExtendedForecastSensor(ForecastBaseSensor):
    """Representation of Extended (7-day) Forecast sensor."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(office_code, latitude, longitude, 'forecast')
        # Initialize with empty periods list to prevent template errors before first update
        self._attributes = {'periods': []}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Extended Forecast'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        coords = self._format_coordinates_for_id()
        if coords:
            return f"noaa_{self._office_code}_{coords}_extended_forecast"
        return f"noaa_{self._office_code}_extended_forecast"

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:weather-partly-cloudy'

    async def async_update(self):
        """Fetch new extended forecast data."""
        # Fetch forecast URL from lat/lon if not already fetched
        if not self._grid_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_forecast_url()

        if not self._forecast_url:
            _LOGGER.error("Unable to get forecast URL for coordinates (lat: %s, lon: %s)",
                          self._latitude, self._longitude)
            self._state = 'Error'
            self._attributes = {'error': 'Unable to get forecast URL for the specified coordinates', 'periods': []}
            self._attr_available = False
            return

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                self._forecast_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})
            periods = properties.get('periods', [])

            if not periods:
                self._state = 'No forecast available'
                self._attributes = {'error': 'No forecast periods found', 'periods': []}
                return

            # Create a formatted text summary of the forecast
            forecast_text = format_forecast_text(periods, MAX_FORECAST_PERIODS)
            self._state = f"{len(periods)} periods"

            # Store detailed forecast in attributes
            self._attributes = {
                'office_code': self._office_code,
                'forecast_text': forecast_text,
                'generated_at': properties.get('generatedAt', 'Unknown'),
                'update_time': properties.get('updateTime', 'Unknown'),
                'periods': format_forecast_periods(periods[:MAX_FORECAST_PERIODS])
            }

            _LOGGER.debug("Updated extended forecast for %s: %d periods", self._office_code, len(periods))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching extended forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast', 'periods': []}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching extended forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}', 'periods': []}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing extended forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}', 'periods': []}


class HourlyForecastSensor(ForecastBaseSensor):
    """Representation of Hourly Forecast sensor."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(office_code, latitude, longitude, 'forecastHourly')
        # Initialize with empty hourly_periods list to prevent template errors before first update
        self._attributes = {'hourly_periods': []}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Hourly Forecast'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        coords = self._format_coordinates_for_id()
        if coords:
            return f"noaa_{self._office_code}_{coords}_hourly_forecast"
        return f"noaa_{self._office_code}_hourly_forecast"

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:clock-outline'

    async def async_update(self):
        """Fetch new hourly forecast data."""
        # Fetch forecast URL from lat/lon if not already fetched
        if not self._grid_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_forecast_url()

        if not self._forecast_url:
            _LOGGER.error("Unable to get hourly forecast URL for coordinates (lat: %s, lon: %s)",
                          self._latitude, self._longitude)
            self._state = 'Error'
            self._attributes = {
                'error': 'Unable to get hourly forecast URL for the specified coordinates',
                'hourly_periods': []
            }
            self._attr_available = False
            return

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                self._forecast_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})
            periods = properties.get('periods', [])

            if not periods:
                self._state = 'No forecast available'
                self._attributes = {'error': 'No forecast periods found', 'hourly_periods': []}
                return

            # Get current hour forecast
            current_period = periods[0] if periods else {}
            self._state = current_period.get('temperature', 'Unknown')

            # Store hourly forecast in attributes
            self._attributes = {
                'office_code': self._office_code,
                'current_hour': {
                    'temperature': current_period.get('temperature'),
                    'temperature_unit': current_period.get('temperatureUnit', 'F'),
                    'wind_speed': current_period.get('windSpeed', 'Unknown'),
                    'wind_direction': current_period.get('windDirection', 'Unknown'),
                    'short_forecast': current_period.get('shortForecast', 'Unknown'),
                    'start_time': current_period.get('startTime', 'Unknown'),
                    'icon': current_period.get('icon', '')
                },
                'generated_at': properties.get('generatedAt', 'Unknown'),
                'update_time': properties.get('updateTime', 'Unknown'),
                'hourly_periods': format_hourly_periods(periods[:MAX_HOURLY_PERIODS])
            }

            _LOGGER.debug("Updated hourly forecast for %s: %d periods", self._office_code, len(periods))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching hourly forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast', 'hourly_periods': []}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching hourly forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}', 'hourly_periods': []}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing hourly forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}', 'hourly_periods': []}
