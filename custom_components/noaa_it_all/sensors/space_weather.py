"""Space weather sensors for NOAA Integration.

Covers geomagnetic storms, planetary K-index, aurora forecasts, and
solar radiation storm alerts.
"""

import logging
import math
from functools import lru_cache
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import datetime, timedelta, timezone

from ..astro import NAUTICAL_TWILIGHT_DEG, find_window_below
from ..const import (
    AURORA_KP_THRESHOLDS, OFFICE_COORDINATES, SOLAR_RADIATION_STORM_SCALES, DOMAIN,
)
from ..offices import magnetic_latitude
from ..parsers import (
    interpret_dst_value,
    rate_kp_index,
    calculate_aurora_duration,
    calculate_aurora_probability,
    get_visibility_class,
    get_required_kp,
    next_aurora_period,
    extract_storm_scale,
    extract_time_from_message,
    calculate_alert_duration,
    extract_impacts,
    get_severity_level,
    assess_location_risk,
    radiation_storm_products_in_effect,
)

_LOGGER = logging.getLogger(__name__)


# A newest Dst older than this means the feed has stopped updating.
_DST_STALE_AFTER = timedelta(hours=2)

# Aurora Next Time before its state has been read.
_NOT_READ = object()

# Aurora needs a dark sky: the Sun at least 12 degrees below the horizon,
# from nautical dusk to nautical dawn.
_AURORA_SUN_BELOW = NAUTICAL_TWILIGHT_DEG

# The nights Aurora Next Time looks at, from the one before today's UTC date
# (a night still under way) to the one SWPC's 3-day Kp forecast ends in.
_AURORA_NIGHTS = range(-1, 4)


def _ceil_minute(moment):
    """Return the moment rounded up to a whole minute."""
    floor = moment.replace(second=0, microsecond=0)
    return floor if floor == moment else floor + timedelta(minutes=1)


@lru_cache(maxsize=32)
def _dark_windows(today, latitude, longitude):
    """Return when it is dark enough for aurora around a day's Kp forecast, as ``(start, end)`` UTC times.

    Each start is rounded up and each end down to the minute, so nightfall is
    never early and has no seconds. They depend only on the day and place, so
    they are worked out once a day for each location.
    """
    windows = []
    for days in _AURORA_NIGHTS:
        window = find_window_below(today + timedelta(days=days), latitude, longitude, _AURORA_SUN_BELOW)
        if window is not None:
            start, end = _ceil_minute(window[0]), window[1].replace(second=0, microsecond=0)
            if start < end:
                windows.append((start, end))
    return tuple(windows)


def _newest_dst(coordinator):
    """Return the newest Dst sample as (nT to one decimal, its time), or None.

    SWPC's Geospace model feed has a sample a minute for the last hour or so,
    oldest first, and runs some 20 to 30 minutes ahead, as the model works
    from solar wind measured upstream of Earth. The sample with the latest
    time and a finite value is used, whatever the order. None when the fetch
    failed, nothing is usable, or the newest is over two hours old.
    """
    if coordinator.data is None:
        return None
    dst_data = coordinator.data.get("dst")
    if not isinstance(dst_data, list):
        return None
    newest = None
    for sample in dst_data:
        if not isinstance(sample, dict):
            continue
        value = sample.get('dst')
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        try:
            time = datetime.fromisoformat(sample["time_tag"])
        except (KeyError, TypeError, ValueError):
            continue
        if time.tzinfo is None:
            time = time.replace(tzinfo=timezone.utc)
        if newest is None or time > newest[1]:
            # Adding 0.0 turns -0.0 into 0.0.
            newest = (round(value, 1) + 0.0, time)
    if newest is None or datetime.now(timezone.utc) - newest[1] > _DST_STALE_AFTER:
        return None
    return newest


class GeomagneticSensor(CoordinatorEntity, SensorEntity):
    """Representation of the Geomagnetic Storm sensor: the newest Dst, in nT.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_geomagnetic_storm``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Geomagnetic Storm"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_geomagnetic_storm'

    @property
    def native_value(self):
        """Return the newest Dst, to one decimal."""
        newest = _newest_dst(self.coordinator)
        return newest[0] if newest else None

    @property
    def extra_state_attributes(self):
        """Return the time of the sample, which can be ahead of now."""
        newest = _newest_dst(self.coordinator)
        return {'timestamp': newest[1].isoformat()} if newest else {}

    @property
    def native_unit_of_measurement(self):
        """Return the unit: nanotesla."""
        return "nT"

    @property
    def state_class(self):
        """Return the state class, so Home Assistant keeps statistics."""
        return SensorStateClass.MEASUREMENT

    @property
    def suggested_display_precision(self):
        """Return how many decimals to show."""
        return 1

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class GeomagneticSensorInterpretation(CoordinatorEntity):
    """Representation of the Geomagnetic Storm Interpretation sensor.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_geomagnetic_storm_interpretation``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the interpretation sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def state(self):
        """Return the interpretation of the newest Dst, as Geomagnetic Storm shows it."""
        newest = _newest_dst(self.coordinator)
        if newest is None:
            return None
        return interpret_dst_value(newest[0])

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Geomagnetic Storm Interpretation"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_geomagnetic_storm_interpretation'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class PlanetaryKIndexSensor(CoordinatorEntity):
    """Representation of the Planetary K-index sensor.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_planetary_k_index``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the Planetary K-index sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Planetary K-index"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_planetary_k_index'

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        kp_data = self.coordinator.data.get("kp_index", [])
        if kp_data and len(kp_data) > 0:
            return kp_data[-1].get('kp_index')
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class PlanetaryKIndexSensorRating(CoordinatorEntity):
    """Representation of the Planetary K-index Rating sensor.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_planetary_k_index_rating``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the Planetary K-index Rating."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def state(self):
        """Return the state of the sensor rating."""
        if self.coordinator.data is None:
            return None
        kp_data = self.coordinator.data.get("kp_index", [])
        if kp_data and len(kp_data) > 0:
            kp_value = kp_data[-1].get('kp_index')
            if kp_value is not None:
                return rate_kp_index(kp_value)
        return None

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Planetary K-index Rating"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f'noaa_{self._office_code}_planetary_k_index_rating'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class AuroraNextTimeSensor(CoordinatorEntity, SensorEntity):
    """When aurora may next be visible here, from SWPC's 3-day Kp forecast.

    The state is the start of the next 3-hour forecast period whose Kp
    reaches the Kp this location needs, or nightfall when that comes later
    in the period. Periods in daylight don't count. It is unknown when none
    in the forecast does, or the forecast or the darkness can't be worked out.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_aurora_next_time``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._period = _NOT_READ

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Aurora Next Time"

    @property
    def device_class(self):
        """Return the device class: the state is a time."""
        return SensorDeviceClass.TIMESTAMP

    def _required_kp(self):
        """Return the Kp aurora needs to be visible here."""
        office_lat = magnetic_latitude(self._office_code, self._latitude, self._longitude)
        return get_required_kp(office_lat, AURORA_KP_THRESHOLDS)

    def _dark(self, now):
        """Return when it is dark here around the forecast, or None without a location."""
        if self._latitude is not None and self._longitude is not None:
            latitude, longitude = self._latitude, self._longitude
        elif self._office_code in OFFICE_COORDINATES:
            latitude, longitude = OFFICE_COORDINATES[self._office_code]
        else:
            return None
        return list(_dark_windows(now.date(), latitude, longitude))

    def _next_period(self):
        """Return the next forecast period aurora may be visible in, or None."""
        if self.coordinator.data is None:
            return None
        now = datetime.now(timezone.utc)
        try:
            dark = self._dark(now)
        except Exception as err:  # noqa: BLE001 - any failure reads unknown
            # Unknown, rather than a time that may be in daylight.
            _LOGGER.warning("Could not work out when it is dark for Aurora Next Time: %r", err)
            return None
        return next_aurora_period(self.coordinator.data.get("kp_forecast"), self._required_kp(), now, dark)

    @property
    def native_value(self):
        """Return when that period starts, or None."""
        # Kept for the attributes, which Home Assistant reads after the state
        # in the same write, so that both describe the same period.
        self._period = self._next_period()
        return self._period["start"] if self._period else None

    @property
    def extra_state_attributes(self):
        """Return the period's forecast Kp, the Kp needed here and the current Kp."""
        if self.coordinator.data is None:
            return {}
        period = self._next_period() if self._period is _NOT_READ else self._period
        kp_data = self.coordinator.data.get("kp_index")
        latest = kp_data[-1] if isinstance(kp_data, list) and kp_data else None
        current_kp = latest.get('kp_index') if isinstance(latest, dict) else None
        return {
            'predicted_kp': period["kp"] if period else None,
            'required_kp': self._required_kp(),
            'current_kp': current_kp if isinstance(current_kp, (int, float)) else None,
            'magnetic_latitude': magnetic_latitude(self._office_code, self._latitude, self._longitude),
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_aurora_next_time"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:weather-night"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class AuroraDurationSensor(CoordinatorEntity):
    """Representation of Aurora Duration sensor for specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_aurora_duration``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Aurora Duration"

    def _get_kp_and_lat(self):
        """Extract current Kp index and office magnetic latitude."""
        if self.coordinator.data is None:
            return None, None
        kp_data = self.coordinator.data.get("kp_index", [])
        if not kp_data or len(kp_data) == 0:
            return None, None
        current_kp = kp_data[-1].get('kp_index', 0)
        office_lat = magnetic_latitude(self._office_code, self._latitude, self._longitude)
        return current_kp, office_lat

    @property
    def state(self):
        """Return the state of the sensor."""
        current_kp, office_lat = self._get_kp_and_lat()
        if current_kp is None:
            return None
        return calculate_aurora_duration(current_kp, office_lat)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        current_kp, office_lat = self._get_kp_and_lat()
        if current_kp is None:
            return {}
        return {
            'current_kp': current_kp,
            'magnetic_latitude': office_lat,
            'intensity': 'High' if current_kp >= 6 else 'Moderate' if current_kp >= 4 else 'Low'
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_aurora_duration"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:timer-outline"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "hours"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class AuroraVisibilityProbabilitySensor(CoordinatorEntity):
    """Representation of Aurora Visibility Probability sensor for specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_aurora_visibility_probability``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Aurora Visibility Probability"

    def _get_kp_and_lat(self):
        """Extract current Kp index and office magnetic latitude."""
        if self.coordinator.data is None:
            return None, None
        kp_data = self.coordinator.data.get("kp_index", [])
        if not kp_data or len(kp_data) == 0:
            return None, None
        current_kp = kp_data[-1].get('kp_index', 0)
        office_lat = magnetic_latitude(self._office_code, self._latitude, self._longitude)
        return current_kp, office_lat

    def _compute_probability(self):
        """Compute aurora probability and related attributes."""
        current_kp, office_lat = self._get_kp_and_lat()
        if current_kp is None:
            return None, {}
        probability = calculate_aurora_probability(current_kp, office_lat)
        attributes = {
            'current_kp': current_kp,
            'magnetic_latitude': office_lat,
            'visibility_class': get_visibility_class(probability),
            'required_kp': get_required_kp(office_lat, AURORA_KP_THRESHOLDS)
        }
        return probability, attributes

    @property
    def state(self):
        """Return the state of the sensor."""
        probability, _ = self._compute_probability()
        return probability

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        _, attributes = self._compute_probability()
        return attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_aurora_visibility_probability"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:percent"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )


class SolarRadiationStormAlertsSensor(CoordinatorEntity):
    """Representation of Solar Radiation Storm Alerts sensor for specific location.

    Uses ``_attr_has_entity_name = True`` so that Home Assistant
    automatically combines the device name with the entity name to
    create entity IDs like ``sensor.noaa_ilm_space_solar_radiation_storm_alerts``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude=None, longitude=None):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude

    @property
    def name(self):
        """Return the name of the sensor (local name only).

        With ``_attr_has_entity_name = True``, Home Assistant combines
        the device name with this local name to create the full entity name.
        """
        return "Solar Radiation Storm Alerts"

    def _products_in_effect(self):
        """Return the solar radiation storm warnings and alerts in effect.

        None when there is no data or the alerts fetch failed, or returned
        something other than a list, so the sensor reads unknown rather than 0.
        """
        if self.coordinator.data is None:
            return None
        alerts_data = self.coordinator.data.get("space_alerts")
        if not isinstance(alerts_data, list):
            return None
        return radiation_storm_products_in_effect(alerts_data, datetime.now(timezone.utc))

    @property
    def state(self):
        """Return the number of products in effect, parsed or not."""
        products = self._products_in_effect()
        if products is None:
            return None
        return len(products)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        products = self._products_in_effect()
        if products is None:
            return {}
        alerts = [
            info for info in map(self._parse_solar_radiation_alert, products) if info
        ]
        office_lat = magnetic_latitude(
            self._office_code, self._latitude, self._longitude, default=45.0
        )
        return {
            'alerts': alerts[:5],
            'office_code': self._office_code,
            'magnetic_latitude': office_lat,
            'location_impact_risk': assess_location_risk(office_lat, alerts),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'total_alerts': len(products)
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_solar_radiation_storm_alerts"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:radioactive"

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "alerts"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_space")},
            name=f"NOAA {self._office_code} Space",
            manufacturer="NOAA"
        )

    def _parse_solar_radiation_alert(self, alert):
        """Parse a solar radiation storm alert for relevant information."""
        try:
            message = alert.get('message', '')
            product_id = alert.get('product_id', '')
            issue_datetime = alert.get('issue_datetime', '')

            scale = extract_storm_scale(message, product_id)
            # A warning gives the time it is valid for.
            begin_time = (extract_time_from_message(message, 'begin time')
                          or extract_time_from_message(message, 'valid from'))
            end_time = (extract_time_from_message(message, 'end time')
                        or extract_time_from_message(message, 'now valid until')
                        or extract_time_from_message(message, 'valid to'))
            duration = calculate_alert_duration(begin_time, end_time)
            impacts = extract_impacts(message)

            alert_info = {
                'product_id': product_id,
                'scale': scale,
                'scale_description': SOLAR_RADIATION_STORM_SCALES.get(
                    scale, {}
                ).get('name', 'Unknown'),
                'begin_time': begin_time,
                'end_time': end_time,
                'duration_hours': duration,
                'impacts': impacts,
                'issue_time': issue_datetime,
                'severity': get_severity_level(scale),
                'message_summary': (
                    message[:200] + '...' if len(message) > 200 else message
                )
            }

            return alert_info

        except Exception as e:
            _LOGGER.warning("Failed to parse solar radiation alert: %s", e)
            return None
