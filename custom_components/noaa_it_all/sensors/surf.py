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

# Home Assistant turns a state longer than this into "unknown".
_MAX_STATE_LENGTH = 255


def _fit_state(text):
    """Shorten text to a state's length, at a word, ending with "…"."""
    if len(text) <= _MAX_STATE_LENGTH:
        return text
    cut = text[:_MAX_STATE_LENGTH - 1]
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut.rstrip(" .,;") + "…"


class RipCurrentRiskSensor(CoordinatorEntity):
    """Representation of Rip Current Risk sensor for specific NWS office location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_surf_rip_current_risk``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_rip_current_risk"

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Rip Current Risk"

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        text = self.coordinator.data.get("forecast_text")
        if text is None:
            # The surf zone forecast could not be fetched: unknown, not Low.
            return None
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
            identifiers={(DOMAIN, f"noaa_{self._office_code}_surf")},
            name=f"NOAA {self._office_code} Surf",
            manufacturer="NOAA"
        )


class SurfHeightSensor(CoordinatorEntity):
    """Representation of Surf Height sensor for specific NWS office location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_surf_surf_height``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_surf_height"

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Surf Height"

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
            identifiers={(DOMAIN, f"noaa_{self._office_code}_surf")},
            name=f"NOAA {self._office_code} Surf",
            manufacturer="NOAA"
        )


class WaterTemperatureSensor(CoordinatorEntity):
    """Representation of Water Temperature sensor for specific NWS office location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_surf_water_temperature``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_water_temperature"

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Water Temperature"

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
            identifiers={(DOMAIN, f"noaa_{self._office_code}_surf")},
            name=f"NOAA {self._office_code} Surf",
            manufacturer="NOAA"
        )


class MarineSensor(CoordinatorEntity):
    """Base for the sensors of one marine zone's nearshore forecast (NWS NSH).

    Each zone has its own marine entry and device, "NOAA LMZ741 Marine", so
    entity IDs look like ``sensor.noaa_lmz741_marine_forecast``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, marine_zone, key):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._marine_zone = marine_zone
        self._attr_unique_id = f"noaa_{marine_zone}_marine_{key}"

    def _forecast(self):
        data = self.coordinator.data
        if not data:
            return None
        return data.get("forecast")

    def _first_period(self):
        forecast = self._forecast()
        if not forecast or not forecast.get("periods"):
            return None
        return forecast["periods"][0]

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._marine_zone}_marine")},
            name=f"NOAA {self._marine_zone} Marine",
            manufacturer="NOAA"
        )


class MarinePeriodSensor(MarineSensor):
    """The name of the forecast period the Forecast sensor shows ("Rest Of Today")."""

    def __init__(self, coordinator, office_code, marine_zone):
        """Initialize the sensor."""
        super().__init__(coordinator, office_code, marine_zone, "period")

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Period"

    @property
    def state(self):
        """Return the first period's name."""
        period = self._first_period()
        return period["name"] if period else None

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-clock"


class MarineForecastSensor(MarineSensor):
    """The forecast for the first period of one marine zone.

    The state is the period's forecast (for example "West winds 10 to 20 kt.
    Waves 1 to 2 ft."), shortened if it is too long for a state. The Period
    sensor and the ``period`` attribute name it ("Rest Of Today"). Every period
    is in the ``periods`` attribute as ``{"name", "detailed_forecast"}``.
    """

    def __init__(self, coordinator, office_code, marine_zone):
        """Initialize the sensor."""
        super().__init__(coordinator, office_code, marine_zone, "forecast")

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Forecast"

    @property
    def state(self):
        """Return the first period's forecast."""
        period = self._first_period()
        if period is None or not period["detailed_forecast"]:
            return None
        return _fit_state(period["detailed_forecast"])

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:sail-boat"

    @property
    def extra_state_attributes(self):
        """Return every period plus zone and issuance details."""
        forecast = self._forecast()
        if not forecast:
            return {"periods": []}
        data = self.coordinator.data
        period = self._first_period()
        return {
            "period": period["name"] if period else None,
            "zone": forecast.get("zone"),
            "zone_name": forecast.get("zone_name"),
            "office_code": self._office_code,
            "issued": forecast.get("issued"),
            "issuance_time": data.get("issuance_time"),
            "product_id": data.get("product_id"),
            "headlines": forecast.get("headlines", []),
            "period_count": len(forecast.get("periods", [])),
            "periods": forecast.get("periods", []),
            "forecast_source": data.get("source_url", ""),
        }


class MarineHazardSensor(MarineSensor):
    """The most severe NWS marine hazard in effect for the zone, or "None".

    Reads the zone's active NWS alerts, so a Small Craft Advisory, Gale
    Warning or Storm Warning shows from the moment it takes effect until it
    ends or is cancelled. Issued hazards that have not started yet, and
    watches, are only in the attributes. When the alerts cannot be fetched the
    sensor is unavailable, never "None".
    """

    def __init__(self, coordinator, office_code, marine_zone):
        """Initialize the sensor."""
        super().__init__(coordinator, office_code, marine_zone, "hazard")

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Hazard"

    @property
    def state(self):
        """Return the most severe hazard in effect, or "None"."""
        data = self.coordinator.data
        if not data:
            return None
        return data.get("hazard") or "None"

    @property
    def icon(self):
        """Return the icon."""
        data = self.coordinator.data
        if data and data.get("hazard"):
            return "mdi:alert"
        return "mdi:check-circle-outline"

    @property
    def extra_state_attributes(self):
        """Return the hazards in effect, those still to start, and watches."""
        data = self.coordinator.data
        if not data:
            return {}
        return {
            "zone": self._marine_zone,
            "office_code": self._office_code,
            "hazard_count": len(data.get("hazards", [])),
            "hazards": data.get("hazards", []),
            "upcoming": data.get("upcoming", []),
            "watches": data.get("watches", []),
            "alerts_source": data.get("source_url", ""),
        }
