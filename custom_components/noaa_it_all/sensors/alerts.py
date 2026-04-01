"""NWS active alerts sensor for NOAA Integration."""

import logging
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, timezone

from ..const import DOMAIN
from ..parsers import parse_nws_alert_features

_LOGGER = logging.getLogger(__name__)


class NWSAlertsSensor(CoordinatorEntity):
    """Representation of NWS Active Alerts sensor for specific location."""

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} Active NWS Alerts'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return None
        features = self.coordinator.data.get("features", [])
        active_alerts, _ = parse_nws_alert_features(features)
        return len(active_alerts)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        features = self.coordinator.data.get("features", [])
        active_alerts, alert_summary = parse_nws_alert_features(features)
        return {
            'office_code': self._office_code,
            'latitude': self._latitude,
            'longitude': self._longitude,
            'alert_count': len(active_alerts),
            'summary': alert_summary,
            'alerts': active_alerts[:10],
            'total_alerts_available': len(active_alerts),
            'last_updated': datetime.now(timezone.utc).isoformat(),
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        return f"noaa_{self._office_code}_{lat_str}_{lon_str}_nws_alerts"

    @property
    def icon(self):
        """Return the icon."""
        if self.state and self.state > 0:
            return 'mdi:alert-circle'
        return 'mdi:check-circle-outline'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_weather_{self._office_code}")},
            name=f"NOAA Weather {self._office_code}",
            manufacturer="NOAA"
        )
