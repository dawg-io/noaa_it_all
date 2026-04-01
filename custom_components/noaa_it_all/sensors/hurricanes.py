"""Hurricane sensors for NOAA Integration."""

import logging
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..parsers import classify_hurricane_activity

_LOGGER = logging.getLogger(__name__)


class HurricaneAlertsSensor(CoordinatorEntity):
    """Representation of Hurricane Alerts sensor."""

    def __init__(self, coordinator, office_code):
        """Initialize the hurricane alerts sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Hurricane Alerts'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        alerts_data = self.coordinator.data.get("alerts") or {}
        features = alerts_data.get("features", [])
        return len(features)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        alerts_data = self.coordinator.data.get("alerts") or {}
        features = alerts_data.get("features", [])
        alerts = []
        for feature in features[:5]:
            properties = feature.get('properties', {})
            alerts.append({
                'event': properties.get('event', 'Unknown'),
                'headline': properties.get('headline', 'No headline'),
                'area': properties.get('areaDesc', 'Unknown area'),
                'severity': properties.get('severity', 'Unknown'),
                'urgency': properties.get('urgency', 'Unknown'),
                'sent': properties.get('sent', 'Unknown')
            })
        return {'alerts': alerts}

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_hurricane_alerts'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class HurricaneActivitySensor(CoordinatorEntity):
    """Representation of Hurricane Activity sensor for general hurricane status."""

    def __init__(self, coordinator, office_code):
        """Initialize the hurricane activity sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Hurricane Activity'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        state, _ = self._compute_activity()
        return state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        _, attrs = self._compute_activity()
        return attrs

    def _compute_activity(self):
        """Compute hurricane activity state and attributes from coordinator data."""
        alerts_data = self.coordinator.data.get("alerts") or {}
        storms_data = self.coordinator.data.get("storms") or {}
        active_storms = storms_data.get("activeStorms", [])
        features = alerts_data.get("features", [])
        return classify_hurricane_activity(active_storms, features)

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_hurricane_activity'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )
