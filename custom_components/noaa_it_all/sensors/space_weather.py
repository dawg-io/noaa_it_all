"""Space weather sensors for NOAA Integration.

Covers geomagnetic storms, planetary K-index, aurora forecasts, and
solar radiation storm alerts.
"""

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
from homeassistant.helpers.entity import Entity, DeviceInfo
from datetime import timedelta, datetime, timezone

from ..const import (
    REQUEST_TIMEOUT, OFFICE_MAGNETIC_LATITUDES,
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

# NOAA Space Weather Alerts
NOAA_SPACE_WEATHER_ALERTS_URL = 'https://services.swpc.noaa.gov/products/alerts.json'


class GeomagneticSensor(Entity):
    """Representation of the Geomagnetic Storm sensor."""

    def __init__(self, interpreter):
        """Initialize the sensor."""
        self._state = None
        self.interpreter = interpreter  # Store the interpreter

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Geomagnetic Storm'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new state data for the sensor."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                'https://services.swpc.noaa.gov/json/geospace/geospace_dst_1_hour.json',
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            if data and len(data) > 0:
                self._state = data[0].get('dst', 'Error')
                self.interpreter.process_geomagnetic_data(self._state)
                _LOGGER.debug("Successfully updated geomagnetic sensor with value: %s", self._state)
            else:
                _LOGGER.warning("Empty response from NOAA geomagnetic API")
                self._state = 'Error'

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching geomagnetic data from NOAA API")
            self._state = 'Error'
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching geomagnetic data from NOAA API: %s", e)
            self._state = 'Error'
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing geomagnetic data from NOAA API: %s", e)
            self._state = 'Error'


class GeomagneticSensorInterpretation(Entity):
    """Representation of the Geomagnetic Storm Interpretation sensor."""

    def __init__(self):
        """Initialize the interpretation sensor."""
        self._state = None
        self._interpretation = None

    @property
    def state(self):
        """Return the interpretation of the geomagnetic storm."""
        return self._interpretation

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

    def process_geomagnetic_data(self, dst_value):
        """Process the Dst value and determine the interpretation."""
        self._state = dst_value
        _LOGGER.debug("Processing Dst value: %s", self._state)
        self._interpretation = interpret_dst_value(dst_value)
        if self._interpretation.startswith('Error'):
            _LOGGER.warning("Invalid Dst value received: %s", self._state)
        else:
            _LOGGER.debug("Geomagnetic interpretation: %s", self._interpretation)


class PlanetaryKIndexSensor(Entity):
    """Representation of the Planetary K-index sensor."""

    def __init__(self, processor):
        """Initialize the Planetary K-index sensor and pass in the processor."""
        self._state = None
        self.processor = processor  # Store the processor

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Planetary K-index'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_space")},
            name="NOAA Space",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new state data for the K-index."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                'https://services.swpc.noaa.gov/json/planetary_k_index_1m.json',
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            if data and len(data) > 0:
                self._state = data[-1].get('kp_index', 'unknown')
                # Call the processor to handle the K-index value
                self.processor.process_solar_flux(self._state)
                _LOGGER.debug("Successfully updated K-index sensor with value: %s", self._state)
            else:
                _LOGGER.warning("Empty response from NOAA K-index API")
                self._state = 'unknown'

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching K-index data from NOAA API")
            self._state = 'unknown'
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching K-index data from NOAA API: %s", e)
            self._state = 'unknown'
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing K-index data from NOAA API: %s", e)
            self._state = 'unknown'


class PlanetaryKIndexSensorRating(Entity):
    """Representation of the Planetary K-index Rating sensor."""

    def __init__(self):
        """Initialize the Planetary K-index Rating."""
        self._state = None
        self._rating = None

    @property
    def state(self):
        """Return the state of the sensor rating."""
        return self._rating

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

    def process_solar_flux(self, solar_flux_value):
        """Process the Solar Flux value."""
        self._state = solar_flux_value
        _LOGGER.debug("Processing K-index value: %s", self._state)
        self._rating = rate_kp_index(solar_flux_value)
        if self._rating == 'unknown':
            _LOGGER.warning("Unknown K-index value received")
        else:
            _LOGGER.debug("K-index rating: %s", self._rating)


class AuroraNextTimeSensor(Entity):
    """Representation of Aurora Next Time sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Aurora Next Time'

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

    async def async_update(self):
        """Calculate next aurora timing based on current geomagnetic conditions."""
        try:
            # Get current Kp index data
            session = async_get_clientsession(self.hass)
            async with session.get(
                'https://services.swpc.noaa.gov/json/planetary_k_index_1m.json',
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            if not data or len(data) == 0:
                self._state = 'No Data'
                self._attributes = {'error': 'No Kp index data available'}
                return

            current_kp = data[-1].get('kp_index', 0)
            office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 0)

            # Determine if aurora is likely based on location and Kp
            aurora_possible = calculate_aurora_visibility(
                current_kp, office_lat, AURORA_KP_THRESHOLDS
            )

            if aurora_possible:
                # If conditions are good now, aurora could be visible soon
                next_time = datetime.now(timezone.utc) + timedelta(minutes=30)
                self._state = next_time.strftime('%Y-%m-%d %H:%M UTC')
                self._attributes = {
                    'current_kp': current_kp,
                    'magnetic_latitude': office_lat,
                    'conditions': 'Favorable',
                    'confidence': 'High' if current_kp >= 5 else 'Moderate'
                }
            else:
                # Estimate when conditions might improve
                if current_kp < 3:
                    estimated_hours = 12 + (3 - current_kp) * 6
                else:
                    estimated_hours = 6

                next_time = datetime.now(timezone.utc) + timedelta(hours=estimated_hours)
                self._state = next_time.strftime('%Y-%m-%d %H:%M UTC')
                self._attributes = {
                    'current_kp': current_kp,
                    'magnetic_latitude': office_lat,
                    'conditions': 'Waiting for activity',
                    'confidence': 'Low'
                }

            _LOGGER.debug("Updated aurora next time for %s: %s", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching Kp index data for aurora prediction")
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching Kp index data for aurora prediction: %s", e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}


class AuroraDurationSensor(Entity):
    """Representation of Aurora Duration sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Aurora Duration'

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

    async def async_update(self):
        """Calculate aurora duration based on geomagnetic conditions."""
        try:
            # Get current Kp index and geomagnetic data
            session = async_get_clientsession(self.hass)
            async with session.get(
                'https://services.swpc.noaa.gov/json/planetary_k_index_1m.json',
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            if not data or len(data) == 0:
                self._state = 0
                self._attributes = {'error': 'No Kp index data available'}
                return

            current_kp = data[-1].get('kp_index', 0)
            office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 0)

            # Calculate duration based on Kp intensity and location
            self._state = calculate_aurora_duration(current_kp, office_lat)
            self._attributes = {
                'current_kp': current_kp,
                'magnetic_latitude': office_lat,
                'intensity': 'High' if current_kp >= 6 else 'Moderate' if current_kp >= 4 else 'Low'
            }

            _LOGGER.debug("Updated aurora duration for %s: %s hours", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching Kp index data for aurora duration")
            self._state = 0
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching Kp index data for aurora duration: %s", e)
            self._state = 0
            self._attributes = {'error': f'Request error: {e}'}


class AuroraVisibilityProbabilitySensor(Entity):
    """Representation of Aurora Visibility Probability sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Aurora Visibility Probability'

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

    async def async_update(self):
        """Calculate aurora visibility probability based on conditions and location."""
        try:
            # Get current Kp index and geomagnetic data
            session = async_get_clientsession(self.hass)
            async with session.get(
                'https://services.swpc.noaa.gov/json/planetary_k_index_1m.json',
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            if not data or len(data) == 0:
                self._state = 0
                self._attributes = {'error': 'No Kp index data available'}
                return

            current_kp = data[-1].get('kp_index', 0)
            office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 0)

            # Calculate probability based on Kp and magnetic latitude
            probability = calculate_aurora_probability(current_kp, office_lat)

            self._state = probability
            self._attributes = {
                'current_kp': current_kp,
                'magnetic_latitude': office_lat,
                'visibility_class': get_visibility_class(probability),
                'required_kp': get_required_kp(office_lat, AURORA_KP_THRESHOLDS)
            }

            _LOGGER.debug("Updated aurora visibility probability for %s: %s%%", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching Kp index data for aurora probability")
            self._state = 0
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching Kp index data for aurora probability: %s", e)
            self._state = 0
            self._attributes = {'error': f'Request error: {e}'}


class SolarRadiationStormAlertsSensor(Entity):
    """Representation of Solar Radiation Storm Alerts sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Space - Solar Radiation Storm Alerts'

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

    async def async_update(self):
        """Fetch solar radiation storm alerts from NOAA."""
        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                NOAA_SPACE_WEATHER_ALERTS_URL,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                alerts_data = await response.json()
            self._attr_available = True
            if not alerts_data:
                self._state = 0
                self._attributes = {'alerts': [], 'last_updated': datetime.now(timezone.utc).isoformat()}
                return

            # Filter alerts for solar radiation storm related content
            solar_radiation_alerts = []
            for alert in alerts_data:
                message = alert.get('message', '').lower()
                product_id = alert.get('product_id', '')

                # Check for solar radiation storm keywords or specific product IDs
                is_solar_radiation = any(keyword in message for keyword in SOLAR_RADIATION_KEYWORDS)
                is_solar_product = product_id.startswith(('S1', 'S2', 'S3', 'S4', 'S5', 'TIVA', 'EF3'))

                if is_solar_radiation or is_solar_product:
                    # Parse alert for relevant information
                    alert_info = self._parse_solar_radiation_alert(alert)
                    if alert_info:
                        solar_radiation_alerts.append(alert_info)

            self._state = len(solar_radiation_alerts)

            # Get office location for relevance scoring
            office_lat = OFFICE_MAGNETIC_LATITUDES.get(self._office_code, 45.0)

            self._attributes = {
                'alerts': solar_radiation_alerts[:5],  # Limit to 5 most recent
                'office_code': self._office_code,
                'magnetic_latitude': office_lat,
                'location_impact_risk': assess_location_risk(office_lat, solar_radiation_alerts),
                'last_updated': datetime.now(timezone.utc).isoformat(),
                'total_alerts': len(solar_radiation_alerts)
            }

            _LOGGER.debug("Successfully updated solar radiation storm alerts for %s: %d alerts",
                          self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching solar radiation alerts from NOAA API")
            self._state = 'Error'
            self._attributes = {'error': 'Request timeout'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching solar radiation alerts from NOAA API: %s", e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing solar radiation alerts from NOAA API: %s", e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}'}

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
