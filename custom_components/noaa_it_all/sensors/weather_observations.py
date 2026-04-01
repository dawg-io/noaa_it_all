"""Weather observation sensors for NOAA Integration.

Provides current conditions from the nearest NWS observation station:
temperature, humidity, wind, pressure, dewpoint, visibility, sky
conditions, and feels-like temperature.
"""

import logging
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..parsers import (
    celsius_to_fahrenheit,
    kmh_to_mph,
    pascals_to_inhg,
    meters_to_miles,
    degrees_to_cardinal,
)

_LOGGER = logging.getLogger(__name__)


class WeatherObservationSensor(CoordinatorEntity):
    """Base class for weather observation sensors."""

    def __init__(self, coordinator, office_code, observation_field, sensor_name,
                 latitude=None, longitude=None, unit=None, icon=None, device_class=None):
        """Initialize the weather observation sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._observation_field = observation_field
        self._sensor_name = sensor_name
        self._latitude = latitude
        self._longitude = longitude
        self._unit = unit
        self._icon_name = icon
        self._device_class = device_class
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} {self._sensor_name}'

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        properties = self.coordinator.data.get("properties", {})
        return self._extract_value(properties)

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
        if not self.coordinator.data:
            return self._attributes
        properties = self.coordinator.data.get("properties", {})
        return {
            'office_code': self._office_code,
            'station_id': self.coordinator.data.get("station_id"),
            'station_name': properties.get('stationName', 'Unknown'),
            'timestamp': properties.get('timestamp', 'Unknown'),
        }

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
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )

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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the temperature sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the humidity sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the wind speed sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the wind direction sensor."""
        super().__init__(
            coordinator,
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

    @property
    def extra_state_attributes(self):
        """Return state attributes with cardinal direction."""
        attrs = super().extra_state_attributes
        if self.state is not None:
            try:
                attrs['cardinal_direction'] = degrees_to_cardinal(self.state)
            except (TypeError, ValueError) as err:
                _LOGGER.debug("Could not convert wind direction %s to cardinal: %s", self.state, err)
        return attrs


class BarometricPressureSensor(WeatherObservationSensor):
    """Barometric pressure sensor."""

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the barometric pressure sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the dewpoint sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the visibility sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the sky conditions sensor."""
        super().__init__(
            coordinator,
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

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the feels-like sensor."""
        super().__init__(
            coordinator,
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
            return self._convert_value(wind_chill.get('value'))

        # Check for heat index (hot conditions)
        heat_index = properties.get('heatIndex', {})
        if heat_index and heat_index.get('value') is not None:
            return self._convert_value(heat_index.get('value'))

        # Neither available, return actual temperature
        temperature = properties.get('temperature', {})
        if temperature and temperature.get('value') is not None:
            return self._convert_value(temperature.get('value'))

        return None

    @property
    def extra_state_attributes(self):
        """Return state attributes with feels-like type."""
        attrs = super().extra_state_attributes
        if self.coordinator.data:
            properties = self.coordinator.data.get("properties", {})
            wind_chill = properties.get('windChill', {})
            heat_index = properties.get('heatIndex', {})
            if wind_chill and wind_chill.get('value') is not None:
                attrs['feels_like_type'] = 'Wind Chill'
            elif heat_index and heat_index.get('value') is not None:
                attrs['feels_like_type'] = 'Heat Index'
            else:
                attrs['feels_like_type'] = 'Actual Temperature'
        return attrs

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return celsius_to_fahrenheit(value)
