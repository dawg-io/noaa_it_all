"""Extra weather sensors for NOAA Integration.

Covers cloud cover (gridpoint data), radar timestamp, and area forecast
discussion (AFD) text.
"""

import logging
import re
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class CloudCoverSensor(CoordinatorEntity):
    """Representation of Cloud Cover sensor for specific location."""

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} Cloud Cover'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        properties = self.coordinator.data.get("properties", {})
        sky_cover = properties.get("skyCover", {})
        if sky_cover and "values" in sky_cover:
            values = sky_cover["values"]
            if values and len(values) > 0:
                current_value = values[0].get("value")
                if current_value is not None:
                    return round(current_value)
        return None

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return '%'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:cloud-percent'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            'office_code': self._office_code,
            'latitude': self._latitude,
            'longitude': self._longitude,
        }
        if not self.coordinator.data:
            return attrs
        properties = self.coordinator.data.get("properties", {})
        sky_cover = properties.get("skyCover", {})
        if sky_cover and "values" in sky_cover:
            values = sky_cover["values"]
            if values and len(values) > 0:
                attrs['valid_time'] = values[0].get('validTime', 'Unknown')
                attrs['availability'] = 'Available from NWS gridpoint data'
            else:
                attrs['availability'] = 'Data not available at this time'
        else:
            attrs['availability'] = 'Data not available at this time'
        return attrs

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        return f"noaa_{self._office_code}_{lat_str}_{lon_str}_cloud_cover"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class RadarTimestampSensor(CoordinatorEntity):
    """Representation of Radar Timestamp sensor for specific location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} Radar Timestamp'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        timestamp = self.coordinator.data.get("timestamp")
        if timestamp:
            return timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
        return None

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:radar'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        timestamp = self.coordinator.data.get("timestamp")
        radar_site = self.coordinator.data.get("radar_site")
        radar_url = self.coordinator.data.get("radar_url")
        if timestamp:
            return {
                'office_code': self._office_code,
                'radar_site': radar_site,
                'timestamp_iso': timestamp.isoformat(),
                'radar_url': radar_url,
                'availability': 'Available from NWS radar images'
            }
        return {
            'office_code': self._office_code,
            'radar_site': radar_site,
            'availability': 'Timestamp not available'
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_radar_timestamp"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class ForecastDiscussionSensor(CoordinatorEntity):
    """Representation of Forecast Discussion sensor for specific location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA {self._office_code} Forecast Discussion'

    @property
    def state(self):
        """Return the state of the sensor."""
        if not self.coordinator.data:
            return self._state
        text = self.coordinator.data.get("discussion_text")
        return 'Available' if text else None

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:text-box-outline'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        text = self.coordinator.data.get("discussion_text")
        if not text:
            return {
                'office_code': self._office_code,
                'availability': 'Unable to parse forecast discussion'
            }
        # Extract issue time if available
        issue_time_match = re.search(
            r'(\d{3,4}\s+(?:AM|PM)\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{4})',
            text, re.IGNORECASE
        )
        issue_time = issue_time_match.group(1) if issue_time_match else 'Unknown'
        summary = text[:200] + '...' if len(text) > 200 else text
        return {
            'office_code': self._office_code,
            'issue_time': issue_time,
            'summary': summary,
            'full_text': text,
            'text_length': len(text),
            'availability': 'Available from NWS Area Forecast Discussion (AFD)'
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_forecast_discussion"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )
