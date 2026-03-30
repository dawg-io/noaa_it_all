"""Weather observation sensors for NOAA Integration.

Provides current conditions from the nearest NWS observation station:
temperature, humidity, wind, pressure, dewpoint, visibility, sky
conditions, and feels-like temperature.
"""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
from homeassistant.helpers.entity import Entity, DeviceInfo

from ..const import (
    NWS_POINTS_URL, NWS_OBSERVATIONS_URL, REQUEST_TIMEOUT,
    USER_AGENT, OFFICE_STATION_IDS, DOMAIN,
)
from ..parsers import (
    celsius_to_fahrenheit,
    kmh_to_mph,
    pascals_to_inhg,
    meters_to_miles,
    degrees_to_cardinal,
)

_LOGGER = logging.getLogger(__name__)


class WeatherObservationSensor(Entity):
    """Base class for weather observation sensors."""

    def __init__(self, office_code, observation_field, sensor_name, latitude=None, longitude=None,
                 unit=None, icon=None, device_class=None):
        """Initialize the weather observation sensor."""
        self._office_code = office_code
        self._observation_field = observation_field
        self._sensor_name = sensor_name
        self._latitude = latitude
        self._longitude = longitude
        self._unit = unit
        self._icon_name = icon
        self._device_class = device_class
        self._state = None
        self._attributes = {}
        self._station_id = None
        self._station_fetched = False

        # Fall back to office-based station mapping if no lat/lon provided
        if latitude is None or longitude is None:
            self._station_id = OFFICE_STATION_IDS.get(office_code)
            self._station_fetched = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA Weather - {self._sensor_name}'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return the icon."""
        return self._icon_name

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        field_name = self._observation_field.replace('.', '_')
        # Include lat/lon in unique ID when available to avoid conflicts
        # Note: Coordinate formatting must match config_flow.py for consistency
        if self._latitude is not None and self._longitude is not None:
            # Round to 4 decimal places for uniqueness while avoiding float precision issues
            lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
            lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
            return f"noaa_{self._office_code}_{lat_str}_{lon_str}_{field_name}"
        return f"noaa_{self._office_code}_{field_name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new weather observation data."""
        # Fetch station ID from lat/lon if not already fetched
        if not self._station_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_station_from_location()

        if not self._station_id:
            _LOGGER.error("Unable to find weather station for coordinates (lat: %s, lon: %s) or office %s",
                          self._latitude, self._longitude, self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Unable to find weather station for the specified coordinates'}
            self._attr_available = False
            return

        try:
            url = NWS_OBSERVATIONS_URL.format(station=self._station_id)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})

            # Extract the value based on the observation field
            value = self._extract_value(properties)

            self._state = value
            self._attributes = {
                'office_code': self._office_code,
                'station_id': self._station_id,
                'station_name': properties.get('stationName', 'Unknown'),
                'timestamp': properties.get('timestamp', 'Unknown'),
            }

            _LOGGER.debug("Updated %s for %s: %s", self._sensor_name, self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching weather observation for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching weather observation for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing weather observation for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}'}

    async def _async_fetch_station_from_location(self):
        """Fetch the nearest observation station from latitude and longitude."""
        try:
            # Get point metadata from weather.gov API
            points_url = NWS_POINTS_URL.format(lat=self._latitude, lon=self._longitude)
            _LOGGER.debug("Fetching station for lat=%s, lon=%s from %s",
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
            stations_url = properties.get('observationStations')

            if not stations_url:
                _LOGGER.error("No observation stations URL found for lat=%s, lon=%s",
                              self._latitude, self._longitude)
                self._station_fetched = True
                return

            # Fetch list of nearby stations
            _LOGGER.debug("Fetching stations list from %s", stations_url)
            async with session.get(
                stations_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                stations_data = await response.json()
            stations_list = stations_data.get('features', [])

            if stations_list:
                # Use the first (nearest) station
                station_id = stations_list[0].get('properties', {}).get('stationIdentifier')
                # Validate station_id is a non-empty string
                if station_id and isinstance(station_id, str) and station_id.strip():
                    self._station_id = station_id.strip()
                    _LOGGER.info("Found station %s for lat=%s, lon=%s",
                                 self._station_id, self._latitude, self._longitude)
                else:
                    _LOGGER.warning("Station found but has no valid identifier for lat=%s, lon=%s",
                                    self._latitude, self._longitude)
            else:
                _LOGGER.warning("No stations found for lat=%s, lon=%s",
                                self._latitude, self._longitude)

            self._station_fetched = True

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout fetching station for lat=%s, lon=%s",
                          self._latitude, self._longitude)
            self._station_fetched = True
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching station for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._station_fetched = True
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing station data for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._station_fetched = True

    def _extract_value(self, properties):
        """Extract and convert the observation value from the API response."""
        # Navigate nested fields (e.g., 'temperature.value')
        field_parts = self._observation_field.split('.')
        value = properties
        for part in field_parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        if value is None:
            return None

        # Handle specific conversions based on the field
        return self._convert_value(value)

    def _convert_value(self, value):
        """Convert the value to the appropriate format and units."""
        # Default implementation - override in subclasses if needed
        if isinstance(value, (int, float)):
            return round(value, 1)
        return value


class TemperatureSensor(WeatherObservationSensor):
    """Temperature sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the temperature sensor."""
        super().__init__(
            office_code,
            'temperature.value',
            'Temperature',
            latitude=latitude,
            longitude=longitude,
            unit='°F',
            icon='mdi:thermometer',
            device_class='temperature'
        )

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return celsius_to_fahrenheit(value)


class HumiditySensor(WeatherObservationSensor):
    """Relative humidity sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the humidity sensor."""
        super().__init__(
            office_code,
            'relativeHumidity.value',
            'Humidity',
            latitude=latitude,
            longitude=longitude,
            unit='%',
            icon='mdi:water-percent',
            device_class='humidity'
        )

    def _convert_value(self, value):
        """Round humidity to integer."""
        if value is None:
            return None
        return round(value)


class WindSpeedSensor(WeatherObservationSensor):
    """Wind speed sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the wind speed sensor."""
        super().__init__(
            office_code,
            'windSpeed.value',
            'Wind Speed',
            latitude=latitude,
            longitude=longitude,
            unit='mph',
            icon='mdi:weather-windy'
        )

    def _convert_value(self, value):
        """Convert km/h to mph."""
        return kmh_to_mph(value)


class WindDirectionSensor(WeatherObservationSensor):
    """Wind direction sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the wind direction sensor."""
        super().__init__(
            office_code,
            'windDirection.value',
            'Wind Direction',
            latitude=latitude,
            longitude=longitude,
            unit='°',
            icon='mdi:compass'
        )

    def _convert_value(self, value):
        """Convert wind direction to round integer."""
        if value is None:
            return None
        return round(value)

    async def async_update(self):
        """Fetch new weather observation data and add cardinal direction."""
        await super().async_update()
        # Add cardinal direction to attributes after base update
        if self._state is not None and self._state != 'Error':
            cardinal = degrees_to_cardinal(self._state)
            self._attributes['cardinal_direction'] = cardinal


class BarometricPressureSensor(WeatherObservationSensor):
    """Barometric pressure sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the barometric pressure sensor."""
        super().__init__(
            office_code,
            'barometricPressure.value',
            'Barometric Pressure',
            latitude=latitude,
            longitude=longitude,
            unit='inHg',
            icon='mdi:gauge',
            device_class='pressure'
        )

    def _convert_value(self, value):
        """Convert Pascals to inches of mercury."""
        return pascals_to_inhg(value)


class DewpointSensor(WeatherObservationSensor):
    """Dewpoint sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the dewpoint sensor."""
        super().__init__(
            office_code,
            'dewpoint.value',
            'Dewpoint',
            latitude=latitude,
            longitude=longitude,
            unit='°F',
            icon='mdi:water',
            device_class='temperature'
        )

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return celsius_to_fahrenheit(value)


class VisibilitySensor(WeatherObservationSensor):
    """Visibility sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the visibility sensor."""
        super().__init__(
            office_code,
            'visibility.value',
            'Visibility',
            latitude=latitude,
            longitude=longitude,
            unit='mi',
            icon='mdi:eye'
        )

    def _convert_value(self, value):
        """Convert meters to miles."""
        return meters_to_miles(value)


class SkyConditionsSensor(WeatherObservationSensor):
    """Sky conditions sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the sky conditions sensor."""
        super().__init__(
            office_code,
            'textDescription',
            'Sky Conditions',
            latitude=latitude,
            longitude=longitude,
            icon='mdi:weather-partly-cloudy'
        )

    def _convert_value(self, value):
        """Return the text description as-is."""
        return value if value else 'Unknown'


class FeelsLikeSensor(WeatherObservationSensor):
    """Feels-like temperature sensor (wind chill or heat index)."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the feels-like sensor."""
        super().__init__(
            office_code,
            'combined',  # Special handling needed
            'Feels Like',
            latitude=latitude,
            longitude=longitude,
            unit='°F',
            icon='mdi:thermometer-lines',
            device_class='temperature'
        )

    def _extract_value(self, properties):
        """Extract wind chill or heat index depending on which is available."""
        # Check for wind chill first (cold conditions)
        wind_chill = properties.get('windChill', {})
        if wind_chill and wind_chill.get('value') is not None:
            value = wind_chill.get('value')
            self._attributes['feels_like_type'] = 'Wind Chill'
            return self._convert_value(value)

        # Check for heat index (hot conditions)
        heat_index = properties.get('heatIndex', {})
        if heat_index and heat_index.get('value') is not None:
            value = heat_index.get('value')
            self._attributes['feels_like_type'] = 'Heat Index'
            return self._convert_value(value)

        # Neither available, return actual temperature
        temperature = properties.get('temperature', {})
        if temperature and temperature.get('value') is not None:
            value = temperature.get('value')
            self._attributes['feels_like_type'] = 'Actual Temperature'
            return self._convert_value(value)

        return None

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return celsius_to_fahrenheit(value)
