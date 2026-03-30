"""Space weather sensors for NOAA Integration.

Covers geomagnetic storms, planetary K-index, aurora forecasts, and
solar radiation storm alerts.
"""

import logging
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from datetime import timedelta, datetime, timezone

from ..const import (
    OFFICE_MAGNETIC_LATITUDES,
    AURORA_KP_THRESHOLDS, SOLAR_RADIATION_STORM_SCALES,
    SOLAR_RADIATION_KEYWORDS, DOMAIN,
)
from ..parsers import (
    interpret_dst_value,
    rate_kp_index,
    calculate_aurora_visibility,
    calculate_aurora_duration,
    calculate_aurora_probability,
    get_visibility_class,
    get_required_kp,
    extract_storm_scale,
    extract_time_from_message,
    calculate_alert_duration,
    extract_impacts,
    get_severity_level,
    assess_location_risk,
)

_LOGGER = logging.getLogger(__name__)


class GeomagneticSensor(CoordinatorEntity):
    """Representation of the Geomagnetic Storm sensor."""

    def __init__(self, coordinator):
        """Initialize the sensor."""
        super().__init__(coordinator)

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Geomagnetic Storm'

    @property
    def state(self):
        """Return the state of the sensor."""
        if self.coordinator.data is None:
            return None
        dst_data = self.coordinator.data.get("dst", [])
        if dst_data and len(dst_data) > 0:
            return dst_data[0].get('dst')
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class GeomagneticSensorInterpretation(CoordinatorEntity):
    """Representation of the Geomagnetic Storm Interpretation sensor."""

    def __init__(self, coordinator):
        """Initialize the interpretation sensor."""
        super().__init__(coordinator)

    @property
    def state(self):
        """Return the interpretation of the geomagnetic storm."""
        if self.coordinator.data is None:
            return None
        dst_data = self.coordinator.data.get("dst", [])
        if dst_data and len(dst_data) > 0:
            dst_value = dst_data[0].get('dst')
            if dst_value is not None:
                return interpret_dst_value(dst_value)
        return None

    @property
    def name(self):
        """Return the name of the interpretation sensor."""
        return 'NOAA Space - Geomagnetic Storm Interpretation'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class PlanetaryKIndexSensor(CoordinatorEntity):
    """Representation of the Planetary K-index sensor."""

    def __init__(self, coordinator):
        """Initialize the Planetary K-index sensor."""
        super().__init__(coordinator)

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Planetary K-index'

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
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class PlanetaryKIndexSensorRating(CoordinatorEntity):
    """Representation of the Planetary K-index Rating sensor."""

    def __init__(self, coordinator):
        """Initialize the Planetary K-index Rating."""
        super().__init__(coordinator)

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
        """Return the name of the sensor."""
        return 'NOAA Space - Planetary K-index Rating'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class AuroraNextTimeSensor(CoordinatorEntity):
    """Representation of Aurora Next Time sensor for specific location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Aurora Next Time'

    def _compute_aurora_timing(self):
        """Compute aurora timing state and attributes from coordinator data."""
        if self.coordinator.data is None:
            return None, {}
        kp_data = self.coordinator.data.get("kp_index", [])
        if not kp_data or len(kp_data) == 0:
            return 'No Data', {'error': 'No Kp index data available'}

        current_kp = kp_data[-1].get('kp_index', 0)
        office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 0)

        aurora_possible = calculate_aurora_visibility(
            current_kp, office_lat, AURORA_KP_THRESHOLDS
        )

        if aurora_possible:
            next_time = datetime.now(timezone.utc) + timedelta(minutes=30)
            state = next_time.strftime('%Y-%m-%d %H:%M UTC')
            attributes = {
                'current_kp': current_kp,
                'magnetic_latitude': office_lat,
                'conditions': 'Favorable',
                'confidence': 'High' if current_kp >= 5 else 'Moderate'
            }
        else:
            if current_kp < 3:
                estimated_hours = 12 + (3 - current_kp) * 6
            else:
                estimated_hours = 6

            next_time = datetime.now(timezone.utc) + timedelta(hours=estimated_hours)
            state = next_time.strftime('%Y-%m-%d %H:%M UTC')
            attributes = {
                'current_kp': current_kp,
                'magnetic_latitude': office_lat,
                'conditions': 'Waiting for activity',
                'confidence': 'Low'
            }

        return state, attributes

    @property
    def state(self):
        """Return the state of the sensor."""
        state, _ = self._compute_aurora_timing()
        return state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        _, attributes = self._compute_aurora_timing()
        return attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"aurora_next_time_{self._office_code}"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:weather-night"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class AuroraDurationSensor(CoordinatorEntity):
    """Representation of Aurora Duration sensor for specific location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Aurora Duration'

    def _get_kp_and_lat(self):
        """Extract current Kp index and office magnetic latitude from coordinator data."""
        if self.coordinator.data is None:
            return None, None
        kp_data = self.coordinator.data.get("kp_index", [])
        if not kp_data or len(kp_data) == 0:
            return None, None
        current_kp = kp_data[-1].get('kp_index', 0)
        office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 0)
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
        return f"aurora_duration_{self._office_code}"

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
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class AuroraVisibilityProbabilitySensor(CoordinatorEntity):
    """Representation of Aurora Visibility Probability sensor for specific location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Aurora Visibility Probability'

    def _get_kp_and_lat(self):
        """Extract current Kp index and office magnetic latitude from coordinator data."""
        if self.coordinator.data is None:
            return None, None
        kp_data = self.coordinator.data.get("kp_index", [])
        if not kp_data or len(kp_data) == 0:
            return None, None
        current_kp = kp_data[-1].get('kp_index', 0)
        office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 0)
        return current_kp, office_lat

    def _compute_probability(self):
        """Compute aurora probability and related attributes from coordinator data."""
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
        return f"aurora_visibility_probability_{self._office_code}"

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
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )


class SolarRadiationStormAlertsSensor(CoordinatorEntity):
    """Representation of Solar Radiation Storm Alerts sensor for specific location."""

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Solar Radiation Storm Alerts'

    def _get_solar_radiation_alerts(self):
        """Filter and parse solar radiation alerts from coordinator data."""
        if self.coordinator.data is None:
            return None
        alerts_data = self.coordinator.data.get("space_alerts", [])
        if not alerts_data:
            return []

        solar_radiation_alerts = []
        for alert in alerts_data:
            message = alert.get('message', '').lower()
            product_id = alert.get('product_id', '')

            is_solar_radiation = any(keyword in message for keyword in SOLAR_RADIATION_KEYWORDS)
            is_solar_product = product_id.startswith(('S1', 'S2', 'S3', 'S4', 'S5', 'TIVA', 'EF3'))

            if is_solar_radiation or is_solar_product:
                alert_info = self._parse_solar_radiation_alert(alert)
                if alert_info:
                    solar_radiation_alerts.append(alert_info)

        return solar_radiation_alerts

    @property
    def state(self):
        """Return the state of the sensor."""
        alerts = self._get_solar_radiation_alerts()
        if alerts is None:
            return None
        return len(alerts)

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        alerts = self._get_solar_radiation_alerts()
        if alerts is None:
            return {}
        office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 45.0)
        return {
            'alerts': alerts[:5],
            'office_code': self._office_code,
            'magnetic_latitude': office_lat,
            'location_impact_risk': assess_location_risk(office_lat, alerts),
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'total_alerts': len(alerts)
        }

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"solar_radiation_storm_alerts_{self._office_code}"

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
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )

    def _parse_solar_radiation_alert(self, alert):
        """Parse a solar radiation storm alert for relevant information."""
        try:
            message = alert.get('message', '')
            product_id = alert.get('product_id', '')
            issue_datetime = alert.get('issue_datetime', '')

            scale = extract_storm_scale(message, product_id)
            begin_time = extract_time_from_message(message, 'begin time')
            end_time = extract_time_from_message(message, 'end time')
            duration = calculate_alert_duration(begin_time, end_time)
            impacts = extract_impacts(message)

            alert_info = {
                'product_id': product_id,
                'scale': scale,
                'scale_description': SOLAR_RADIATION_STORM_SCALES.get(scale, {}).get('name', 'Unknown'),
                'begin_time': begin_time,
                'end_time': end_time,
                'duration_hours': duration,
                'impacts': impacts,
                'issue_time': issue_datetime,
                'severity': get_severity_level(scale),
                'message_summary': message[:200] + '...' if len(message) > 200 else message
            }

            return alert_info

        except Exception as e:
            _LOGGER.warning("Failed to parse solar radiation alert: %s", e)
            return None
