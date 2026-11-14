"""Extra weather sensors for NOAA Integration.

Covers cloud cover and the snowfall forecast (gridpoint data), radar
timestamp, and area forecast discussion (AFD) text.
"""

import logging
from datetime import datetime, timedelta, timezone

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from ..coordinator import _ObserverTimezone
from ..parsers import find_issue_time, hourly_precipitation, precipitation_between

_LOGGER = logging.getLogger(__name__)


class CloudCoverSensor(CoordinatorEntity):
    """Representation of Cloud Cover sensor for specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_weather_cloud_cover``.
    """

    _attr_has_entity_name = True

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
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Cloud Cover"

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


# mm in each unit Home Assistant offers for a precipitation sensor, and the
# decimals the attributes are rounded to in it.
_MM_PER_UNIT = {"mm": 1.0, "cm": 10.0, "in": 25.4}
_ATTRIBUTE_DECIMALS = {"mm": 1, "cm": 2, "in": 2}
# NWS forecasts snow about three days out; this bounds the attribute list
# however far a gridpoint series reaches.
_MAX_FORECAST_DAYS = 8


def _now(tz):
    """Return the current time in ``tz`` (patched in tests)."""
    return datetime.now(tz)


class SnowfallForecastSensor(CoordinatorEntity, SensorEntity):
    """NWS's forecast snowfall for the next 24 hours, from the gridpoint data.

    The state is the depth of new snow, not its water equivalent, which the
    weather entity's forecast ``precipitation`` has. It is in mm natively and
    shown in inches unless another unit is chosen. The ``days`` attribute has
    the snow and ice for each local date, today's from now to midnight, and
    ``ice_next_24h`` the ice over the same 24 hours as the state; attributes
    are in the unit the state is shown in. A window the forecast doesn't
    fully cover, or any while the last gridpoint fetch failed, is unknown
    rather than 0.

    Uses ``_attr_has_entity_name = True``, so the entity ID is like
    ``sensor.noaa_ilm_weather_snowfall_forecast``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._timezone = _ObserverTimezone()

    @property
    def name(self):
        """Return the name of the sensor (local name only)."""
        return "Snowfall Forecast"

    @property
    def device_class(self):
        """Return the device class, so Home Assistant converts the unit."""
        return SensorDeviceClass.PRECIPITATION

    @property
    def native_unit_of_measurement(self):
        """Return the unit NWS gives snowfall in."""
        return "mm"

    @property
    def suggested_unit_of_measurement(self):
        """Return the US customary unit to show unless one is chosen in the entity's settings."""
        return "in"

    @property
    def suggested_display_precision(self):
        """Return how many decimals to show in the suggested unit."""
        return 1

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:snowflake"

    def _series(self, key):
        """Return a gridpoint series by hour, or None when the last fetch failed."""
        coordinator = self.coordinator
        if not coordinator.data or not coordinator.last_update_success:
            return None
        return hourly_precipitation(coordinator.data.get("properties"), key)

    def _local_now(self):
        """Return now in Home Assistant's time zone, which the days are dates in."""
        hass = getattr(self, "hass", None)
        return _now(self._timezone.resolve(hass) if hass is not None else timezone.utc)

    def _next_24h(self, now):
        """Return the 24 whole hours from the start of this hour, as NWS's hourly values go."""
        hour = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
        return hour, hour + timedelta(hours=24)

    @property
    def native_value(self):
        """Return the forecast snowfall in mm over the next 24 hours, or None."""
        return precipitation_between(self._series("snowfallAmount"), *self._next_24h(self._local_now()))

    def _display(self, mm):
        """Return an amount in mm in the unit the state is shown in, rounded."""
        if mm is None:
            return None
        unit = getattr(self, "unit_of_measurement", None)
        if unit not in _MM_PER_UNIT:
            unit = "mm"
        return round(mm / _MM_PER_UNIT[unit], _ATTRIBUTE_DECIMALS[unit])

    @property
    def extra_state_attributes(self):
        """Return the ice over the next 24 hours and each day's snow and ice."""
        snow = self._series("snowfallAmount")
        ice = self._series("iceAccumulation")
        now = self._local_now()
        attrs = {
            "ice_next_24h": self._display(precipitation_between(ice, *self._next_24h(now))),
            "days": [],
        }
        known = list(snow or {}) + list(ice or {})
        if not known:
            return attrs
        last_hour = max(known)
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        for day in range(_MAX_FORECAST_DAYS):
            start = midnight + timedelta(days=day)
            if start > last_hour:
                break
            # Wall-clock arithmetic in the zone, so a DST day is 23 or 25 hours.
            end = start + timedelta(days=1)
            start = max(start, now)
            attrs["days"].append({
                "date": start.date().isoformat(),
                "snowfall": self._display(precipitation_between(snow, start, end)),
                "ice": self._display(precipitation_between(ice, start, end)),
            })
        return attrs

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        return f"noaa_{self._office_code}_{lat_str}_{lon_str}_snowfall_forecast"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class RadarTimestampSensor(CoordinatorEntity):
    """Representation of Radar Timestamp sensor for specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_weather_radar_timestamp``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Radar Timestamp"

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
    """Representation of Forecast Discussion sensor for specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_weather_forecast_discussion``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Forecast Discussion"

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
        issue_time = find_issue_time(text) or 'Unknown'
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
