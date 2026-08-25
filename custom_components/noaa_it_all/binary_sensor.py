"""Binary sensor platform for NOAA Integration."""
import logging
import re

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, DOMAIN,
    METEOR_ACTIVE_MIN_RATE, METEOR_ACTIVE_MIN_SCORE,
    ECLIPSE_VISIBLE_MIN_COVERAGE, ECLIPSE_VISIBLE_LEAD_MINUTES,
    ECLIPSE_UPCOMING_DAYS, ECLIPSE_UPCOMING_MIN_COVERAGE,
)
from .entry_config import resolve_entry_config
from .sensors.meteor_showers import space_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up binary sensor platform (legacy YAML support)."""
    _LOGGER.warning("NOAA binary sensors require location configuration. Please use config flow setup.")
    return


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA binary sensors from config entry."""
    conf = resolve_entry_config(config_entry)
    office_code = conf[CONF_OFFICE_CODE]
    latitude = conf.get(CONF_LATITUDE)
    longitude = conf.get(CONF_LONGITUDE)

    data = hass.data[DOMAIN][config_entry.entry_id]
    surf_coord = data["surf_coordinator"]
    alerts_coord = data["alerts_coordinator"]
    meteor_coord = data["meteor_coordinator"]
    eclipse_coord = data["eclipse_coordinator"]

    entities = [UnsafeToSwimBinarySensor(surf_coord, office_code)]

    if alerts_coord and latitude is not None and longitude is not None:
        entities.extend([
            SevereWeatherAlertBinarySensor(alerts_coord, office_code, latitude, longitude),
            FloodWinterAlertBinarySensor(alerts_coord, office_code, latitude, longitude),
            HeatAirQualityAlertBinarySensor(alerts_coord, office_code, latitude, longitude),
            ActiveAlertsGeneralBinarySensor(alerts_coord, office_code, latitude, longitude),
        ])

    if meteor_coord:
        entities.append(MeteorShowerActiveBinarySensor(meteor_coord, office_code))

    if eclipse_coord:
        entities.extend([
            EclipseVisibleNowBinarySensor(eclipse_coord, office_code),
            EclipseComingUpBinarySensor(eclipse_coord, office_code),
        ])

    async_add_entities(entities)


class UnsafeToSwimBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for unsafe swimming conditions based on rip current forecasts."""

    _attr_has_entity_name = True

    _HIGH_RISK_PATTERNS = [
        r"high\s+rip\s+current\s+risk",
        r"dangerous\s+rip\s+currents",
        r"high\s+surf\s+and\s+dangerous\s+rip\s+currents",
        r"rip\s+current\s+risk\s+is\s+high",
    ]

    _MODERATE_RISK_PATTERNS = [
        r"moderate\s+rip\s+current\s+risk",
        r"rip\s+current\s+risk\s+is\s+moderate",
        r"moderate\s+surf\s+and\s+rip\s+currents",
    ]

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_unsafe_to_swim"
        self._attr_name = "Unsafe to Swim"

    def _check_risk(self):
        """Return (high_risk_found, moderate_risk_found) from coordinator data."""
        if not self.coordinator.data:
            return False, False
        forecast_text = self.coordinator.data.get("forecast_text", "")
        high = any(re.search(p, forecast_text) for p in self._HIGH_RISK_PATTERNS)
        moderate = any(re.search(p, forecast_text) for p in self._MODERATE_RISK_PATTERNS)
        return high, moderate

    @property
    def is_on(self):
        """Return true if unsafe to swim."""
        high, _ = self._check_risk()
        return high

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:swim-off'
        return 'mdi:swim'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        high_risk_found, moderate_risk_found = self._check_risk()
        risk_level = "High" if high_risk_found else ("Moderate" if moderate_risk_found else "Low")
        return {
            'office_code': self._office_code,
            'risk_level': risk_level,
            'forecast_source': self.coordinator.data.get("source_url", ""),
            'last_updated': 'Available in forecast',
            'high_risk_detected': high_risk_found,
            'moderate_risk_detected': moderate_risk_found,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_surf")},
            name=f"NOAA {self._office_code} Surf",
            manufacturer="NOAA"
        )


class SevereWeatherAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for severe/hazardous weather warnings (tornado, thunderstorm, etc.)."""

    _attr_has_entity_name = True

    _SEVERE_EVENTS = [
        'tornado warning', 'tornado watch',
        'severe thunderstorm warning', 'severe thunderstorm watch',
        'severe weather statement',
        'hurricane warning', 'hurricane watch',
        'tropical storm warning', 'tropical storm watch',
        'extreme wind warning', 'high wind warning', 'high wind watch',
        'hazardous weather outlook',
        'special weather statement',
        'hazardous seas warning', 'hazardous seas watch',
        'storm surge warning', 'storm surge watch',
        'tsunami warning', 'tsunami watch', 'tsunami advisory',
        'typhoon warning', 'typhoon watch',
    ]

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_severe_weather_alert"
        self._attr_name = "Severe Weather Alert"

    def _get_filtered_alerts(self):
        """Return list of active severe weather alerts from coordinator data."""
        if not self.coordinator.data:
            return []
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', '').lower()
            status = props.get('status', '').lower()
            if status == 'actual' and any(se in event for se in self._SEVERE_EVENTS):
                active_alerts.append({
                    'event': props.get('event', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
        return active_alerts

    @property
    def is_on(self):
        """Return true if there is an active severe weather alert."""
        return len(self._get_filtered_alerts()) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:weather-lightning'
        return 'mdi:weather-partly-cloudy'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alerts': active_alerts[:5],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class FloodWinterAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for flood and winter weather alerts."""

    _attr_has_entity_name = True

    _FLOOD_WINTER_EVENTS = [
        'flood warning', 'flood watch', 'flash flood warning', 'flash flood watch',
        'coastal flood warning', 'coastal flood watch', 'lakeshore flood warning',
        'flood advisory', 'coastal flood advisory', 'lakeshore flood advisory',
        'flood statement', 'flash flood statement', 'coastal flood statement', 'lakeshore flood statement',
        'winter storm warning', 'winter storm watch', 'winter weather advisory',
        'blizzard warning', 'ice storm warning', 'lake effect snow warning',
        'heavy snow warning', 'snow squall warning',
        'freezing rain advisory', 'freezing fog advisory', 'sleet advisory',
        'wind chill warning', 'wind chill advisory',
        'extreme cold warning', 'extreme cold watch', 'cold weather advisory',
    ]

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_flood_winter_alert"
        self._attr_name = "Flood/Winter Alert"

    def _get_filtered_alerts(self):
        """Return list of active flood/winter alerts from coordinator data."""
        if not self.coordinator.data:
            return []
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', '').lower()
            status = props.get('status', '').lower()
            if status == 'actual' and any(fe in event for fe in self._FLOOD_WINTER_EVENTS):
                active_alerts.append({
                    'event': props.get('event', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
        return active_alerts

    @property
    def is_on(self):
        """Return true if there is an active flood or winter weather alert."""
        return len(self._get_filtered_alerts()) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:snowflake-alert'
        return 'mdi:weather-snowy'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alerts': active_alerts[:5],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class HeatAirQualityAlertBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for heat, air quality, and other environmental advisories."""

    _attr_has_entity_name = True

    _HEAT_AIRQUALITY_EVENTS = [
        'excessive heat warning', 'excessive heat watch', 'heat advisory',
        'extreme heat warning', 'extreme heat watch',
        'air quality alert', 'air stagnation advisory',
        'red flag warning', 'fire weather watch', 'extreme fire danger',
        'dense fog advisory', 'dense smoke advisory',
        'dust storm warning', 'blowing dust advisory', 'blowing dust warning',
        'freeze warning', 'freeze watch', 'frost advisory',
        'ashfall warning', 'ashfall advisory',
        'volcano warning',
    ]

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_heat_air_quality_alert"
        self._attr_name = "Heat/Air Quality Alert"

    def _get_filtered_alerts(self):
        """Return list of active heat/air quality alerts from coordinator data."""
        if not self.coordinator.data:
            return []
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', '').lower()
            status = props.get('status', '').lower()
            if status == 'actual' and any(he in event for he in self._HEAT_AIRQUALITY_EVENTS):
                active_alerts.append({
                    'event': props.get('event', 'Unknown'),
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
        return active_alerts

    @property
    def is_on(self):
        """Return true if there is an active heat or air quality alert."""
        return len(self._get_filtered_alerts()) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:fire-alert'
        return 'mdi:thermometer'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alerts': active_alerts[:5],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class ActiveAlertsGeneralBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor for general active NWS alerts for the configured location."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_active_alerts"
        self._attr_name = "Active Alerts"

    def _get_filtered_alerts(self):
        """Return list of all active alerts and type counts from coordinator data."""
        if not self.coordinator.data:
            return [], {}
        features = self.coordinator.data.get("features", [])
        active_alerts = []
        alert_types = {}
        for feature in features:
            props = feature.get('properties', {})
            event = props.get('event', 'Unknown')
            status = props.get('status', '').lower()
            if status == 'actual':
                active_alerts.append({
                    'event': event,
                    'headline': props.get('headline', 'No headline'),
                    'severity': props.get('severity', 'Unknown'),
                    'urgency': props.get('urgency', 'Unknown'),
                    'certainty': props.get('certainty', 'Unknown'),
                    'area': props.get('areaDesc', 'Unknown area'),
                    'effective': props.get('effective', 'Unknown'),
                    'expires': props.get('expires', 'Unknown'),
                    'description': props.get('description', '')[:200],
                })
                alert_types[event] = alert_types.get(event, 0) + 1
        return active_alerts, alert_types

    @property
    def is_on(self):
        """Return true if there are any active alerts."""
        active_alerts, _ = self._get_filtered_alerts()
        return len(active_alerts) > 0

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:alert'
        return 'mdi:check-circle'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return self._attributes
        active_alerts, alert_types = self._get_filtered_alerts()
        return {
            'office_code': self._office_code,
            'alert_count': len(active_alerts),
            'alert_types': alert_types,
            'alerts': active_alerts[:10],
            'latitude': self._latitude,
            'longitude': self._longitude,
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA"
        )


class MeteorShowerActiveBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor that turns on when a meteor shower is genuinely worth going outside for.

    This is the entity to trigger automations from. It is deliberately *not* a bare "is any
    shower active" flag: with around thirty showers catalogued something is technically active on
    most nights of the year, so such a flag would sit permanently on. Instead it requires a real
    predicted rate and usable sky geometry.

    Measured over 2026 from Wilmington NC that turns on for roughly 50 nights, clustered tightly
    around the major showers — about thirteen for the Perseids, eight for the Orionids, seven for
    the Geminids. That is not an arbitrary number: with a published activity slope of 0.2 the
    Perseids genuinely stay above five meteors an hour for about six days either side of
    maximum. Raise ``METEOR_ACTIVE_MIN_RATE`` if you only want to hear about the peak nights.

    Like the other binary sensors in this module it sets ``_attr_has_entity_name``, matching the
    sensor convention, so the entity ID carries the ``space`` device segment
    (``binary_sensor.noaa_ilm_space_meteor_shower_active``) and reads as a sibling of the meteor
    sensors rather than an orphan.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code
        self._attr_unique_id = f"noaa_{office_code}_meteor_shower_active"

    @property
    def name(self):
        """Return the local name of the binary sensor."""
        return "Meteor Shower Active"

    @property
    def _best(self):
        """Return tonight's best shower entry, or None when nothing is active."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("best")

    @property
    def is_on(self):
        """Return true when a worthwhile shower is observable tonight."""
        best = self._best
        if not best:
            return False
        return (
            best['expected_per_hour'] >= METEOR_ACTIVE_MIN_RATE
            and best['viewing_score'] >= METEOR_ACTIVE_MIN_SCORE
        )

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:meteor'
        return 'mdi:weather-night'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            'office_code': self._office_code,
            'minimum_rate': METEOR_ACTIVE_MIN_RATE,
            'minimum_score': METEOR_ACTIVE_MIN_SCORE,
        }
        best = self._best
        if not best:
            return attrs

        attrs.update({
            'shower': best['name'],
            'shower_code': best['code'],
            'zhr_now': best['zhr_now'],
            'expected_per_hour': best['expected_per_hour'],
            'viewing_score': best['viewing_score'],
            'rating': best['rating'],
            'peak_local': best['peak_local'],
            'days_until': best['days_until'],
            'is_peak_night': best['is_peak_night'],
            'best_window_start': best['best_window_start'],
            'best_window_end': best['best_window_end'],
            'limiting_factor': best['limiting_factor'],
        })
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return space_device_info(self._office_code)


class _EclipseBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Shared plumbing for the two eclipse binary sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def _forecast(self):
        """Return the coordinator payload, or an empty dict before the first refresh."""
        return self.coordinator.data or {}

    def _describe(self, eclipse):
        """Return the attributes both sensors publish about an eclipse."""
        return {
            'eclipse': eclipse['name'],
            'kind': eclipse['kind'],
            'eclipse_type': eclipse['type'],
            'disc_covered': eclipse['disc_covered'],
            'viewing_score': eclipse['viewing_score'],
            'rating': eclipse['rating'],
            'starts_local': eclipse['start_local'],
            'maximum_local': eclipse['max_local'],
            'ends_local': eclipse['end_local'],
            'altitude_when_visible': eclipse['altitude_when_visible'],
            'look_towards': eclipse['direction_when_visible'],
            'limiting_factor': eclipse['limiting_factor'],
            # Repeated on both sensors rather than left to the score sensor: an automation that
            # announces an eclipse is exactly the thing that sends somebody outside to look at
            # it, so the warning has to be reachable from the entity that fired.
            'eye_protection_required': eclipse['eye_protection_required'],
            'safe_without_filter': eclipse['safe_unfiltered'],
            'eye_safety': eclipse['eye_safety'],
        }

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return space_device_info(self._office_code)


class EclipseVisibleNowBinarySensor(_EclipseBinarySensor):
    """Turns on when there is an eclipse to go outside and look at, right now.

    This is the one to trigger an announcement from. It comes on
    ``ECLIPSE_VISIBLE_LEAD_MINUTES`` before first contact -- long enough to find the eclipse
    glasses -- and goes off at last contact.

    Two conditions. The eclipse has to be genuinely visible from here -- which already means the
    body is above the horizon for some worthwhile part of it, an eclipse happening under your feet
    being no use -- and it has to cover at least ``ECLIPSE_VISIBLE_MIN_COVERAGE`` of the disc,
    because a 3% nibble at the edge of the Sun is invisible without a filter and would only teach
    people to ignore this sensor.

    It deliberately does *not* also require the body to be up at greatest eclipse. That sounds
    like the same question and is not: when the Moon sets partway through a total lunar eclipse
    you can still watch most of it, and gating on the instant of maximum turns the alert off for
    the entire event.

    Expect it on for a few hours a year at most, and in many years not at all.
    """

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator, office_code)
        self._attr_unique_id = f"noaa_{office_code}_eclipse_visible_now"

    @property
    def name(self):
        """Return the local name of the binary sensor."""
        return "Eclipse Visible Now"

    @property
    def _eclipse(self):
        """Return the eclipse under way or about to start, or ``None``."""
        forecast = self._forecast
        current = forecast.get('current')
        if current:
            return current
        upcoming = forecast.get('next')
        if not upcoming:
            return None
        # Against first contact, not maximum. A lunar eclipse runs nearly three hours from one to
        # the other, so measuring the lead against maximum makes this branch unreachable: by the
        # time it would be within an hour of maximum the eclipse has long since started and is
        # being reported as 'current' instead. The documented hour of warning became none at all.
        hours = upcoming.get('hours_until_start')
        if hours is None or hours < 0:
            return None
        if hours * 60.0 <= ECLIPSE_VISIBLE_LEAD_MINUTES:
            return upcoming
        return None

    @property
    def is_on(self):
        """Return true when an eclipse worth watching is happening or imminent."""
        eclipse = self._eclipse
        if not eclipse:
            return False
        return (
            eclipse['visible']
            and eclipse['disc_covered'] >= ECLIPSE_VISIBLE_MIN_COVERAGE
        )

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:weather-sunny-alert'
        return 'mdi:weather-sunny-off'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            'office_code': self._office_code,
            'minimum_disc_covered': ECLIPSE_VISIBLE_MIN_COVERAGE,
            'lead_minutes': ECLIPSE_VISIBLE_LEAD_MINUTES,
        }
        eclipse = self._eclipse
        if not eclipse:
            return attrs
        attrs.update(self._describe(eclipse))
        attrs.update({
            'in_progress': eclipse['in_progress'],
            'minutes_until': round(eclipse['hours_until_start'] * 60.0, 1),
            'watch_from_local': eclipse['visible_start_local'],
            'watch_until_local': eclipse['visible_end_local'],
            'totality_starts_local': eclipse['central_start_local'],
            'totality_ends_local': eclipse['central_end_local'],
            'totality_seconds': eclipse['central_duration_s'],
        })
        return attrs


class EclipseComingUpBinarySensor(_EclipseBinarySensor):
    """Turns on when a worthwhile eclipse is close enough to plan around.

    The companion to Eclipse Visible Now, and deliberately a different question. That one is
    "look up"; this one is "book the day off, and order the glasses". It comes on
    ``ECLIPSE_UPCOMING_DAYS`` before an eclipse that will cover at least
    ``ECLIPSE_UPCOMING_MIN_COVERAGE`` of the disc from here -- a higher bar than the live alert,
    because a partial eclipse worth glancing at is not a partial eclipse worth a calendar entry.
    """

    def __init__(self, coordinator, office_code):
        """Initialize the binary sensor."""
        super().__init__(coordinator, office_code)
        self._attr_unique_id = f"noaa_{office_code}_eclipse_coming_up"

    @property
    def name(self):
        """Return the local name of the binary sensor."""
        return "Eclipse Coming Up"

    @property
    def _eclipse(self):
        """Return the next visible eclipse, or ``None``."""
        return self._forecast.get('current') or self._forecast.get('next')

    @property
    def is_on(self):
        """Return true when a worthwhile eclipse is within the planning window."""
        eclipse = self._eclipse
        if not eclipse:
            return False
        days = eclipse.get('days_until')
        if days is None or days > ECLIPSE_UPCOMING_DAYS:
            return False
        return (
            eclipse['visible']
            and eclipse['disc_covered'] >= ECLIPSE_UPCOMING_MIN_COVERAGE
        )

    @property
    def icon(self):
        """Return the icon."""
        if self.is_on:
            return 'mdi:calendar-star'
        return 'mdi:calendar-blank'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {
            'office_code': self._office_code,
            'minimum_disc_covered': ECLIPSE_UPCOMING_MIN_COVERAGE,
            'window_days': ECLIPSE_UPCOMING_DAYS,
        }
        eclipse = self._eclipse
        if not eclipse:
            return attrs
        attrs.update(self._describe(eclipse))
        attrs.update({
            'date': eclipse['date'],
            'days_until': eclipse['days_until'],
            'visible_fraction': eclipse['visible_fraction'],
        })
        return attrs
