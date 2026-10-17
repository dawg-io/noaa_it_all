"""Weather observation sensors for NOAA Integration.

Provides current conditions from the nearest NWS observation station:
temperature, humidity, wind, pressure, dewpoint, visibility, sky
conditions, and feels-like temperature.

NWS reports observations in metric units. The sensors report them as they
are, with a device class, and suggest US customary units, so Home Assistant
shows them in °F, mph, inHg and miles in any install, or in the unit chosen
in an entity's settings.
"""

import logging
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..parsers import degrees_to_cardinal, meters_to_kilometers, pascals_to_hectopascals

_LOGGER = logging.getLogger(__name__)


class WeatherObservationSensor(CoordinatorEntity, SensorEntity):
    """Base class for weather observation sensors.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_weather_temperature``.
    """

    _attr_has_entity_name = True
    # The field whose observation time is this sensor's timestamp, when it is
    # not the one in observation_field.
    _time_field = None

    def __init__(self, coordinator, office_code, observation_field, sensor_name,
                 latitude=None, longitude=None, unit=None, icon=None, device_class=None,
                 precision=None, suggested_unit=None):
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
        self._precision = precision
        self._suggested_unit = suggested_unit
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return self._sensor_name

    @property
    def native_value(self):
        """Return the observed value, in the unit NWS reports it in."""
        if self.coordinator.data is None:
            return None
        properties = self.coordinator.data.get("properties", {})
        return self._extract_value(properties)

    @property
    def native_unit_of_measurement(self):
        """Return the unit of the observed value; Home Assistant converts it."""
        return self._unit

    @property
    def suggested_unit_of_measurement(self):
        """Return the US customary unit to show unless one is chosen in the entity's settings.

        Home Assistant stores it when it first sees the sensor, and again when the
        unit system is changed with its option to update existing entities, so a
        restart doesn't change the unit either.
        """
        return self._suggested_unit

    @property
    def suggested_display_precision(self):
        """Return how many decimals to show, in the suggested unit, or the native one without it."""
        return self._precision

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
        # A value carried from an earlier observation says when it was made.
        field = self._time_field or self._observation_field.split('.')[0]
        field_times = self.coordinator.data.get("field_times") or {}
        return {
            'office_code': self._office_code,
            'station_id': self.coordinator.data.get("station_id"),
            'station_name': properties.get('stationName', 'Unknown'),
            'timestamp': field_times.get(field) or properties.get('timestamp', 'Unknown'),
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
        """Return the value as NWS reports it.

        It isn't rounded, so a value Home Assistant converts comes out as
        before; Home Assistant rounds it to the suggested display precision.
        """
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
            unit='°C',
            icon='mdi:thermometer',
            device_class=SensorDeviceClass.TEMPERATURE,
            precision=1,
            suggested_unit='°F',
        )


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
            device_class=SensorDeviceClass.HUMIDITY
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
            unit='km/h',
            icon='mdi:weather-windy',
            device_class=SensorDeviceClass.WIND_SPEED,
            precision=1,
            suggested_unit='mph',
        )


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
        degrees = self.native_value
        if degrees is not None:
            try:
                attrs['cardinal_direction'] = degrees_to_cardinal(degrees)
            except (TypeError, ValueError) as err:
                _LOGGER.debug("Could not convert wind direction %s to cardinal: %s", degrees, err)
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
            unit='hPa',
            icon='mdi:gauge',
            # Atmospheric pressure, rather than pressure, converts to inHg.
            device_class=SensorDeviceClass.ATMOSPHERIC_PRESSURE,
            # In inHg; Home Assistant shows hPa to 1 decimal.
            precision=2,
            suggested_unit='inHg',
        )

    def _convert_value(self, value):
        """Convert pascals to hectopascals."""
        return pascals_to_hectopascals(value)


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
            unit='°C',
            icon='mdi:water',
            device_class=SensorDeviceClass.TEMPERATURE,
            precision=1,
            suggested_unit='°F',
        )


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
            unit='km',
            icon='mdi:eye',
            device_class=SensorDeviceClass.DISTANCE,
            precision=1,
            suggested_unit='mi',
        )

    def _convert_value(self, value):
        """Convert meters to kilometers."""
        return meters_to_kilometers(value)


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

    # Wind chill, heat index and temperature all come from the observation
    # the temperature came from.
    _time_field = 'temperature'

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the feels-like sensor."""
        super().__init__(
            coordinator,
            office_code,
            'combined',  # Special handling needed
            'Feels Like',
            latitude=latitude,
            longitude=longitude,
            unit='°C',
            icon='mdi:thermometer-lines',
            device_class=SensorDeviceClass.TEMPERATURE,
            precision=1,
            suggested_unit='°F',
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
