"""NWS active alerts sensor for NOAA Integration."""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
from homeassistant.helpers.entity import Entity, DeviceInfo
from datetime import datetime, timezone

from ..const import NWS_ALERTS_URL, REQUEST_TIMEOUT, USER_AGENT, DOMAIN
from ..parsers import parse_nws_alert_features

_LOGGER = logging.getLogger(__name__)


class NWSAlertsSensor(Entity):
    """Representation of NWS Active Alerts sensor for specific location."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Active NWS Alerts'

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
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        return f"noaa_{self._office_code}_{lat_str}_{lon_str}_nws_alerts"

    @property
    def icon(self):
        """Return the icon."""
        if self._state and self._state > 0:
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

    async def async_update(self):
        """Fetch new NWS alerts data for the specific location."""
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

            active_alerts, alert_summary = parse_nws_alert_features(features)

            self._state = len(active_alerts)
            self._attributes = {
                'office_code': self._office_code,
                'latitude': self._latitude,
                'longitude': self._longitude,
                'alert_count': len(active_alerts),
                'summary': alert_summary,
                'alerts': active_alerts[:10],  # Limit to 10 most recent for display
                'total_alerts_available': len(active_alerts),
                'last_updated': datetime.now(timezone.utc).isoformat(),
            }

            _LOGGER.debug("Updated NWS alerts sensor for %s: %d alerts", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching NWS alerts for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching alerts'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching NWS alerts for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing NWS alerts for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}'}
