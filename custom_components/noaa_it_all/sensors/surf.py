"""Surf / ocean sensors for NOAA Integration.

Covers rip current risk, surf height and water temperature from NWS
Surf Zone Forecasts (SRF product).
"""

import logging
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..parsers import (
    parse_rip_current_risk, parse_surf_height, parse_water_temperature,
    normalize_numeric,
)

_LOGGER = logging.getLogger(__name__)


class RipCurrentRiskSensor(CoordinatorEntity):
    """Representation of Rip Current Risk sensor for specific NWS office location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_rip_current_risk"
        self._attr_name = "NOAA Surf - Rip Current Risk"

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        text = self.coordinator.data.get("forecast_text", "")
        return parse_rip_current_risk(text)

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:waves'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        return {
            'office_code': self._office_code,
            'forecast_source': self.coordinator.data.get("source_url", ""),
            'last_updated': 'Check forecast for timestamp',
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )


class SurfHeightSensor(CoordinatorEntity):
    """Representation of Surf Height sensor for specific NWS office location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_surf_height"
        self._attr_name = "NOAA Surf - Surf Height"

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        # Prefer NDBC API wave height, fall back to SRF text parsing
        wave_ft = self.coordinator.data.get("wave_height_ft")
        if wave_ft is not None:
            return wave_ft
        text = self.coordinator.data.get("forecast_text", "")
        return normalize_numeric(parse_surf_height(text))

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
        if not self.coordinator.data:
            return self._attributes
        attrs = {
            'office_code': self._office_code,
            'forecast_source': self.coordinator.data.get("source_url", ""),
            'last_updated': 'Check forecast for timestamp',
        }
        wave_source = self.coordinator.data.get("wave_height_source")
        if wave_source:
            attrs['wave_height_source'] = wave_source
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )


class WaterTemperatureSensor(CoordinatorEntity):
    """Representation of Water Temperature sensor for specific NWS office location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_water_temperature"
        self._attr_name = "NOAA Surf - Water Temperature"

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        # Prefer CO-OPS API water temp, fall back to SRF text parsing
        water_temp = self.coordinator.data.get("water_temp_f")
        if water_temp is not None:
            return water_temp
        text = self.coordinator.data.get("forecast_text", "")
        return normalize_numeric(parse_water_temperature(text))

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
        if not self.coordinator.data:
            return self._attributes
        attrs = {
            'office_code': self._office_code,
            'forecast_source': self.coordinator.data.get("source_url", ""),
            'last_updated': 'Check forecast for timestamp',
        }
        temp_source = self.coordinator.data.get("water_temp_source")
        if temp_source:
            attrs['water_temp_source'] = temp_source
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )
