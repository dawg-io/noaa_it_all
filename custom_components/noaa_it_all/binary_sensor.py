"""Binary sensor platform for NOAA Integration."""
import logging
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import re
from datetime import timedelta

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE,
                    NWS_SRF_URL, NWS_ALERTS_URL, REQUEST_TIMEOUT, USER_AGENT, DOMAIN)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up binary sensor platform (legacy YAML support)."""
    # For legacy YAML setup, we can't provide location-specific data
    _LOGGER.warning("NOAA binary sensors require location configuration. Please use config flow setup.")
    return


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA binary sensors from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

    entities = [
        UnsafeToSwimBinarySensor(office_code),
    ]

    # Add location-specific alert binary sensors
    if latitude is not None and longitude is not None:
        entities.extend([
            SevereWeatherAlertBinarySensor(office_code, latitude, longitude),
            FloodWinterAlertBinarySensor(office_code, latitude, longitude),
            HeatAirQualityAlertBinarySensor(office_code, latitude, longitude),
            ActiveAlertsGeneralBinarySensor(office_code, latitude, longitude),
        ])

    async_add_entities(entities, True)


class UnsafeToSwimBinarySensor(BinarySensorEntity):
    """Binary sensor for unsafe swimming conditions based on rip current forecasts."""

    def __init__(self, office_code):
        """Initialize the binary sensor."""
        self._office_code = office_code
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_unsafe_to_swim"
        self._attr_name = f"NOAA {office_code} Unsafe to Swim"

    @property
    def is_on(self):
        """Return true if unsafe to swim."""
        return self._state

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self._state:
            return 'mdi:swim-off'
        return 'mdi:swim'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_surf")},
            name="NOAA Surf",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Update the binary sensor."""
        try:
            # Fetch surf zone forecast for the specific NWS office
            url = NWS_SRF_URL.format(office=self._office_code)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                forecast_text = (await response.text()).lower()
            self._attr_available = True

            # Look for rip current risk indicators in the forecast text
            high_risk_patterns = [
                r"high\s+rip\s+current\s+risk",
                r"dangerous\s+rip\s+currents",
                r"high\s+surf\s+and\s+dangerous\s+rip\s+currents",
                r"rip\s+current\s+risk\s+is\s+high",
            ]

            moderate_risk_patterns = [
                r"moderate\s+rip\s+current\s+risk",
                r"rip\s+current\s+risk\s+is\s+moderate",
                r"moderate\s+surf\s+and\s+rip\s+currents",
            ]

            # Check for high risk conditions (unsafe to swim)
            high_risk_found = any(re.search(pattern, forecast_text) for pattern in high_risk_patterns)
            moderate_risk_found = any(re.search(pattern, forecast_text) for pattern in moderate_risk_patterns)

            # Set unsafe if high risk is found
            self._state = high_risk_found

            # Extract additional information
            risk_level = "High" if high_risk_found else ("Moderate" if moderate_risk_found else "Low")

            self._attributes = {
                'office_code': self._office_code,
                'risk_level': risk_level,
                'forecast_source': url,
                'last_updated': 'Available in forecast',
                'high_risk_detected': high_risk_found,
                'moderate_risk_detected': moderate_risk_found,
            }

            _LOGGER.debug("Updated unsafe to swim sensor for %s: %s (risk: %s)",
                          self._office_code, self._state, risk_level)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Unexpected error updating unsafe to swim sensor for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Unexpected error: {e}'}


class SevereWeatherAlertBinarySensor(BinarySensorEntity):
    """Binary sensor for severe/hazardous weather warnings (tornado, thunderstorm, etc.)."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_severe_weather_alert"
        self._attr_name = f"NOAA {office_code} Severe Weather Alert"

    @property
    def is_on(self):
        """Return true if there is an active severe weather alert."""
        return self._state

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self._state:
            return 'mdi:weather-lightning'
        return 'mdi:weather-partly-cloudy'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_weather_{self._office_code}")},
            name=f"NOAA Weather {self._office_code}",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Update the binary sensor."""
        try:
            url = NWS_ALERTS_URL.format(lat=self._latitude, lon=self._longitude)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            features = data.get('features', [])

            # Filter for severe weather events
            severe_events = [
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
                'typhoon warning', 'typhoon watch'
            ]

            active_alerts = []
            for feature in features:
                props = feature.get('properties', {})
                event = props.get('event', '').lower()
                status = props.get('status', '').lower()

                # Only include actual alerts (not tests or drafts)
                if status == 'actual' and any(severe_event in event for severe_event in severe_events):
                    active_alerts.append({
                        'event': props.get('event', 'Unknown'),
                        'headline': props.get('headline', 'No headline'),
                        'severity': props.get('severity', 'Unknown'),
                        'urgency': props.get('urgency', 'Unknown'),
                        'certainty': props.get('certainty', 'Unknown'),
                        'area': props.get('areaDesc', 'Unknown area'),
                        'effective': props.get('effective', 'Unknown'),
                        'expires': props.get('expires', 'Unknown'),
                        'description': props.get('description', '')[:200]
                    })

            self._state = len(active_alerts) > 0
            self._attributes = {
                'office_code': self._office_code,
                'alert_count': len(active_alerts),
                'alerts': active_alerts[:5],  # Limit to 5 most recent
                'latitude': self._latitude,
                'longitude': self._longitude,
            }

            _LOGGER.debug("Updated severe weather alert sensor for %s: %s (%d alerts)",
                          self._office_code, self._state, len(active_alerts))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching NWS alerts for %s", self._office_code)
            self._attributes = {'error': 'Timeout fetching alerts'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching NWS alerts for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Unexpected error updating severe weather alert sensor for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Unexpected error: {e}'}


class FloodWinterAlertBinarySensor(BinarySensorEntity):
    """Binary sensor for flood and winter weather alerts."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_flood_winter_alert"
        self._attr_name = f"NOAA {office_code} Flood/Winter Alert"

    @property
    def is_on(self):
        """Return true if there is an active flood or winter weather alert."""
        return self._state

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self._state:
            return 'mdi:snowflake-alert'
        return 'mdi:weather-snowy'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_weather_{self._office_code}")},
            name=f"NOAA Weather {self._office_code}",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Update the binary sensor."""
        try:
            url = NWS_ALERTS_URL.format(lat=self._latitude, lon=self._longitude)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            features = data.get('features', [])

            # Filter for flood and winter weather events
            flood_winter_events = [
                'flood warning', 'flood watch', 'flash flood warning', 'flash flood watch',
                'coastal flood warning', 'coastal flood watch', 'lakeshore flood warning',
                'flood advisory', 'coastal flood advisory', 'lakeshore flood advisory',
                'flood statement', 'flash flood statement', 'coastal flood statement', 'lakeshore flood statement',
                'winter storm warning', 'winter storm watch', 'winter weather advisory',
                'blizzard warning', 'ice storm warning', 'lake effect snow warning',
                'heavy snow warning', 'snow squall warning',
                'freezing rain advisory', 'freezing fog advisory', 'sleet advisory',
                'wind chill warning', 'wind chill advisory',
                'extreme cold warning', 'extreme cold watch', 'cold weather advisory'
            ]

            active_alerts = []
            for feature in features:
                props = feature.get('properties', {})
                event = props.get('event', '').lower()
                status = props.get('status', '').lower()

                # Only include actual alerts (not tests or drafts)
                if status == 'actual' and any(flood_event in event for flood_event in flood_winter_events):
                    active_alerts.append({
                        'event': props.get('event', 'Unknown'),
                        'headline': props.get('headline', 'No headline'),
                        'severity': props.get('severity', 'Unknown'),
                        'urgency': props.get('urgency', 'Unknown'),
                        'certainty': props.get('certainty', 'Unknown'),
                        'area': props.get('areaDesc', 'Unknown area'),
                        'effective': props.get('effective', 'Unknown'),
                        'expires': props.get('expires', 'Unknown'),
                        'description': props.get('description', '')[:200]
                    })

            self._state = len(active_alerts) > 0
            self._attributes = {
                'office_code': self._office_code,
                'alert_count': len(active_alerts),
                'alerts': active_alerts[:5],  # Limit to 5 most recent
                'latitude': self._latitude,
                'longitude': self._longitude,
            }

            _LOGGER.debug("Updated flood/winter alert sensor for %s: %s (%d alerts)",
                          self._office_code, self._state, len(active_alerts))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching NWS alerts for %s", self._office_code)
            self._attributes = {'error': 'Timeout fetching alerts'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching NWS alerts for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Unexpected error updating flood/winter alert sensor for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Unexpected error: {e}'}


class HeatAirQualityAlertBinarySensor(BinarySensorEntity):
    """Binary sensor for heat, air quality, and other environmental advisories."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_heat_air_quality_alert"
        self._attr_name = f"NOAA {office_code} Heat/Air Quality Alert"

    @property
    def is_on(self):
        """Return true if there is an active heat or air quality alert."""
        return self._state

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self._state:
            return 'mdi:fire-alert'
        return 'mdi:thermometer'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_weather_{self._office_code}")},
            name=f"NOAA Weather {self._office_code}",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Update the binary sensor."""
        try:
            url = NWS_ALERTS_URL.format(lat=self._latitude, lon=self._longitude)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            features = data.get('features', [])

            # Filter for heat, air quality, and environmental alerts
            heat_airquality_events = [
                'excessive heat warning', 'excessive heat watch', 'heat advisory',
                'extreme heat warning', 'extreme heat watch',
                'air quality alert', 'air stagnation advisory',
                'red flag warning', 'fire weather watch', 'extreme fire danger',
                'dense fog advisory', 'dense smoke advisory',
                'dust storm warning', 'blowing dust advisory', 'blowing dust warning',
                'freeze warning', 'freeze watch', 'frost advisory',
                'ashfall warning', 'ashfall advisory',
                'volcano warning'
            ]

            active_alerts = []
            for feature in features:
                props = feature.get('properties', {})
                event = props.get('event', '').lower()
                status = props.get('status', '').lower()

                # Only include actual alerts (not tests or drafts)
                if status == 'actual' and any(heat_event in event for heat_event in heat_airquality_events):
                    active_alerts.append({
                        'event': props.get('event', 'Unknown'),
                        'headline': props.get('headline', 'No headline'),
                        'severity': props.get('severity', 'Unknown'),
                        'urgency': props.get('urgency', 'Unknown'),
                        'certainty': props.get('certainty', 'Unknown'),
                        'area': props.get('areaDesc', 'Unknown area'),
                        'effective': props.get('effective', 'Unknown'),
                        'expires': props.get('expires', 'Unknown'),
                        'description': props.get('description', '')[:200]
                    })

            self._state = len(active_alerts) > 0
            self._attributes = {
                'office_code': self._office_code,
                'alert_count': len(active_alerts),
                'alerts': active_alerts[:5],  # Limit to 5 most recent
                'latitude': self._latitude,
                'longitude': self._longitude,
            }

            _LOGGER.debug("Updated heat/air quality alert sensor for %s: %s (%d alerts)",
                          self._office_code, self._state, len(active_alerts))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching NWS alerts for %s", self._office_code)
            self._attributes = {'error': 'Timeout fetching alerts'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching NWS alerts for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Unexpected error updating heat/air quality alert sensor for %s: %s",
                          self._office_code, e)
            self._attributes = {'error': f'Unexpected error: {e}'}


class ActiveAlertsGeneralBinarySensor(BinarySensorEntity):
    """Binary sensor for general active NWS alerts for the configured location."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the binary sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = False
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_active_alerts"
        self._attr_name = f"NOAA {office_code} Active Alerts"

    @property
    def is_on(self):
        """Return true if there are any active alerts."""
        return self._state

    @property
    def device_class(self):
        """Return the device class."""
        return 'safety'

    @property
    def icon(self):
        """Return the icon."""
        if self._state:
            return 'mdi:alert'
        return 'mdi:check-circle'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_weather_{self._office_code}")},
            name=f"NOAA Weather {self._office_code}",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Update the binary sensor."""
        try:
            url = NWS_ALERTS_URL.format(lat=self._latitude, lon=self._longitude)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            features = data.get('features', [])

            # Filter all actual alerts (excluding tests and other non-actual alerts)
            active_alerts = []
            alert_types = {}

            for feature in features:
                props = feature.get('properties', {})
                event = props.get('event', 'Unknown')
                status = props.get('status', '').lower()

                # Only include actual alerts (not tests or drafts)
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
                        'description': props.get('description', '')[:200]
                    })

                    # Count by alert type
                    alert_types[event] = alert_types.get(event, 0) + 1

            self._state = len(active_alerts) > 0
            self._attributes = {
                'office_code': self._office_code,
                'alert_count': len(active_alerts),
                'alert_types': alert_types,
                'alerts': active_alerts[:10],  # Limit to 10 most recent
                'latitude': self._latitude,
                'longitude': self._longitude,
            }

            _LOGGER.debug("Updated active alerts sensor for %s: %s (%d alerts)",
                          self._office_code, self._state, len(active_alerts))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching NWS alerts for %s", self._office_code)
            self._attributes = {'error': 'Timeout fetching alerts'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching NWS alerts for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Unexpected error updating active alerts sensor for %s: %s", self._office_code, e)
            self._attributes = {'error': f'Unexpected error: {e}'}
