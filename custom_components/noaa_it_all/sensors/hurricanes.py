"""Hurricane sensors for NOAA Integration."""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
from homeassistant.helpers.entity import Entity, DeviceInfo

from ..const import REQUEST_TIMEOUT, DOMAIN
from ..parsers import classify_hurricane_activity

_LOGGER = logging.getLogger(__name__)

# NOAA Hurricane Data Sources
HURRICANE_ALERTS_URL = (
    'https://api.weather.gov/alerts?event=Hurricane%20Warning,Hurricane%20Watch,'
    'Tropical%20Storm%20Warning,Tropical%20Storm%20Watch&active=true'
)
CURRENT_STORMS_URL = 'https://www.nhc.noaa.gov/CurrentStorms.json'


class HurricaneAlertsSensor(Entity):
    """Representation of Hurricane Alerts sensor."""

    def __init__(self):
        """Initialize the hurricane alerts sensor."""
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Hurricane Alerts'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_alerts'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new hurricane alert data."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                HURRICANE_ALERTS_URL,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            features = data.get('features', [])

            if features:
                self._state = len(features)
                alerts = []
                for feature in features[:5]:  # Limit to 5 most recent alerts
                    properties = feature.get('properties', {})
                    alerts.append({
                        'event': properties.get('event', 'Unknown'),
                        'headline': properties.get('headline', 'No headline'),
                        'area': properties.get('areaDesc', 'Unknown area'),
                        'severity': properties.get('severity', 'Unknown'),
                        'urgency': properties.get('urgency', 'Unknown'),
                        'sent': properties.get('sent', 'Unknown')
                    })
                self._attributes = {'alerts': alerts}
                _LOGGER.debug("Successfully updated hurricane alerts sensor with %d alerts", self._state)
            else:
                self._state = 0
                self._attributes = {'alerts': []}
                _LOGGER.debug("No active hurricane alerts found")

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching hurricane alerts from NWS API")
            self._state = 'Error'
            self._attributes = {}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching hurricane alerts from NWS API: %s", e)
            self._state = 'Error'
            self._attributes = {}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing hurricane alerts from NWS API: %s", e)
            self._state = 'Error'
            self._attributes = {}


class HurricaneActivitySensor(Entity):
    """Representation of Hurricane Activity sensor for general hurricane status."""

    def __init__(self):
        """Initialize the hurricane activity sensor."""
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Hurricane Activity'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return 'noaa_hurricane_activity'

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch hurricane activity status."""
        try:
            session = async_get_clientsession(self.hass)
            # First check for active storms from National Hurricane Center
            async with session.get(
                CURRENT_STORMS_URL,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as storms_response:
                storms_response.raise_for_status()
                storms_data = await storms_response.json()

            # Also check for active alerts
            async with session.get(
                HURRICANE_ALERTS_URL,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as alerts_response:
                alerts_response.raise_for_status()
                alerts_data = await alerts_response.json()

            self._attr_available = True
            active_storms = storms_data.get('activeStorms', [])
            features = alerts_data.get('features', [])

            self._state, self._attributes = classify_hurricane_activity(
                active_storms, features
            )

            _LOGGER.debug(
                "Successfully updated hurricane activity sensor: %s (storms: %d, alerts: %d)",
                self._state,
                self._attributes.get('total_active_storms', 0),
                self._attributes.get('total_alerts', 0),
            )

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching hurricane activity data")
            self._state = 'Error'
            self._attributes = {}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching hurricane activity data: %s", e)
            self._state = 'Error'
            self._attributes = {}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing hurricane activity data: %s", e)
            self._state = 'Error'
            self._attributes = {}
