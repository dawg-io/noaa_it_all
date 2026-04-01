"""Forecast sensors for NOAA Integration.

Covers extended (7-day) and hourly NWS forecast data.
"""

import logging
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..parsers import format_forecast_text, format_forecast_periods, format_hourly_periods

_LOGGER = logging.getLogger(__name__)

# Forecast constants
MAX_FORECAST_PERIODS = 14  # 7 days (day + night for each day)
MAX_HOURLY_PERIODS = 48  # 48 hours of hourly forecasts


class ForecastBaseSensor(CoordinatorEntity):
    """Base class for forecast sensors."""

    def __init__(self, coordinator, office_code, latitude, longitude, forecast_type):
        """Initialize the base forecast sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._forecast_type = forecast_type  # 'forecast' or 'forecastHourly'
        self._state = None
        self._attributes = {}

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
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class ExtendedForecastSensor(ForecastBaseSensor):
    """Representation of Extended (7-day) Forecast sensor."""

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(coordinator, office_code, latitude, longitude, 'forecast')
        self._attributes = {'periods': []}

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} Extended Forecast'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.get("extended"):
            return self._state
        properties = self.coordinator.data["extended"].get("properties", {})
        periods = properties.get("periods", [])
        if not periods:
            return "No forecast available"
        return f"{len(periods)} periods"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data or not self.coordinator.data.get("extended"):
            return self._attributes
        properties = self.coordinator.data["extended"].get("properties", {})
        periods = properties.get("periods", [])
        if not periods:
            return {'error': 'No forecast periods found', 'periods': []}
        forecast_text = format_forecast_text(periods, MAX_FORECAST_PERIODS)
        return {
            'office_code': self._office_code,
            'forecast_text': forecast_text,
            'generated_at': properties.get('generatedAt', 'Unknown'),
            'update_time': properties.get('updateTime', 'Unknown'),
            'periods': format_forecast_periods(periods[:MAX_FORECAST_PERIODS])
        }

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


class HourlyForecastSensor(ForecastBaseSensor):
    """Representation of Hourly Forecast sensor."""

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(coordinator, office_code, latitude, longitude, 'forecastHourly')
        self._attributes = {'hourly_periods': []}

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} Hourly Forecast'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or not self.coordinator.data.get("hourly"):
            return self._state
        properties = self.coordinator.data["hourly"].get("properties", {})
        periods = properties.get("periods", [])
        if not periods:
            return "No forecast available"
        return periods[0].get('temperature', 'Unknown')

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data or not self.coordinator.data.get("hourly"):
            return self._attributes
        properties = self.coordinator.data["hourly"].get("properties", {})
        periods = properties.get("periods", [])
        if not periods:
            return {'error': 'No forecast periods found', 'hourly_periods': []}
        current_period = periods[0]
        return {
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
