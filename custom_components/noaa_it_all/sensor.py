import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import asyncio
import logging
import re
from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from datetime import timedelta, datetime, timezone

from .const import (CONF_OFFICE_CODE, CONF_LATITUDE, CONF_LONGITUDE, NWS_SRF_URL, NWS_POINTS_URL,
                    NWS_ALERTS_URL, REQUEST_TIMEOUT, USER_AGENT, OFFICE_MAGNETIC_LATITUDES,
                    AURORA_KP_THRESHOLDS, SOLAR_RADIATION_STORM_SCALES, SOLAR_RADIATION_KEYWORDS,
                    OFFICE_STATION_IDS, NWS_OBSERVATIONS_URL, NWS_AFD_URL,
                    OFFICE_RADAR_SITES, DOMAIN)

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=5)  # Update every 5 minutes

# Forecast constants
MAX_FORECAST_PERIODS = 14  # 7 days (day + night for each day)
MAX_HOURLY_PERIODS = 48  # 48 hours of hourly forecasts


# NOAA Hurricane Data Sources
HURRICANE_ALERTS_URL = ('https://api.weather.gov/alerts?event=Hurricane%20Warning,Hurricane%20Watch,'
                        'Tropical%20Storm%20Warning,Tropical%20Storm%20Watch&active=true')
CURRENT_STORMS_URL = 'https://www.nhc.noaa.gov/CurrentStorms.json'

# NOAA Space Weather Alerts
NOAA_SPACE_WEATHER_ALERTS_URL = 'https://services.swpc.noaa.gov/products/alerts.json'


def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the sensor platform (legacy YAML support)."""
    _LOGGER.info("Setting up NOAA sensors (legacy YAML)")

    # Instantiate the processor for K-index and Dst interpretation
    planetary_k_index_rating = PlanetaryKIndexSensorRating()
    geomagnetic_interpretation = GeomagneticSensorInterpretation()

    # Instantiate hurricane sensors
    hurricane_alerts_sensor = HurricaneAlertsSensor()
    hurricane_activity_sensor = HurricaneActivitySensor()

    # Pass the processors to the sensors that will use them
    add_entities([GeomagneticSensor(geomagnetic_interpretation), PlanetaryKIndexSensor(planetary_k_index_rating),
                  planetary_k_index_rating, geomagnetic_interpretation, hurricane_alerts_sensor,
                  hurricane_activity_sensor])


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA sensors from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

    # Instantiate the processor for K-index and Dst interpretation
    planetary_k_index_rating = PlanetaryKIndexSensorRating()
    geomagnetic_interpretation = GeomagneticSensorInterpretation()

    # Instantiate hurricane sensors
    hurricane_alerts_sensor = HurricaneAlertsSensor()
    hurricane_activity_sensor = HurricaneActivitySensor()

    # Instantiate location-specific rip current sensors
    rip_current_risk_sensor = RipCurrentRiskSensor(office_code)
    surf_height_sensor = SurfHeightSensor(office_code)
    water_temperature_sensor = WaterTemperatureSensor(office_code)

    # Instantiate location-specific aurora alert sensors
    aurora_next_time_sensor = AuroraNextTimeSensor(office_code)
    aurora_duration_sensor = AuroraDurationSensor(office_code)
    aurora_visibility_probability_sensor = AuroraVisibilityProbabilitySensor(office_code)

    # Instantiate location-specific solar radiation storm alert sensor
    solar_radiation_storm_alerts_sensor = SolarRadiationStormAlertsSensor(office_code)

    # Instantiate location-specific weather observation sensors
    temperature_sensor = TemperatureSensor(office_code, latitude, longitude)
    humidity_sensor = HumiditySensor(office_code, latitude, longitude)
    wind_speed_sensor = WindSpeedSensor(office_code, latitude, longitude)
    wind_direction_sensor = WindDirectionSensor(office_code, latitude, longitude)
    barometric_pressure_sensor = BarometricPressureSensor(office_code, latitude, longitude)
    dewpoint_sensor = DewpointSensor(office_code, latitude, longitude)
    visibility_sensor = VisibilitySensor(office_code, latitude, longitude)
    sky_conditions_sensor = SkyConditionsSensor(office_code, latitude, longitude)
    feels_like_sensor = FeelsLikeSensor(office_code, latitude, longitude)

    # Instantiate location-specific forecast sensors
    extended_forecast_sensor = ExtendedForecastSensor(office_code, latitude, longitude)
    hourly_forecast_sensor = HourlyForecastSensor(office_code, latitude, longitude)

    # Instantiate location-specific NWS alerts sensor
    nws_alerts_sensor = None
    if latitude is not None and longitude is not None:
        nws_alerts_sensor = NWSAlertsSensor(office_code, latitude, longitude)

    # Instantiate optional secondary sensors
    cloud_cover_sensor = None
    radar_timestamp_sensor = RadarTimestampSensor(office_code)
    forecast_discussion_sensor = ForecastDiscussionSensor(office_code)

    # Cloud cover requires lat/lon for gridpoint data
    if latitude is not None and longitude is not None:
        cloud_cover_sensor = CloudCoverSensor(office_code, latitude, longitude)

    entities = [
        GeomagneticSensor(geomagnetic_interpretation),
        PlanetaryKIndexSensor(planetary_k_index_rating),
        # planetary_k_index_rating,
        # geomagnetic_interpretation,
        hurricane_alerts_sensor,
        hurricane_activity_sensor,
        rip_current_risk_sensor,
        surf_height_sensor,
        water_temperature_sensor,
        aurora_next_time_sensor,
        aurora_duration_sensor,
        aurora_visibility_probability_sensor,
        solar_radiation_storm_alerts_sensor,
        temperature_sensor,
        humidity_sensor,
        wind_speed_sensor,
        wind_direction_sensor,
        barometric_pressure_sensor,
        dewpoint_sensor,
        visibility_sensor,
        sky_conditions_sensor,
        feels_like_sensor,
        extended_forecast_sensor,
        hourly_forecast_sensor,
        radar_timestamp_sensor,
        forecast_discussion_sensor,
    ]

    # Add NWS alerts sensor if location is configured
    if nws_alerts_sensor:
        entities.append(nws_alerts_sensor)

    # Add cloud cover sensor if location is configured
    if cloud_cover_sensor:
        entities.append(cloud_cover_sensor)

    async_add_entities(entities, True)


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

        # Interpretation based on the Dst value
        if isinstance(self._state, (int, float)):  # Ensure it's a valid numeric value
            if self._state > -20:
                self._interpretation = 'No Storm (Quiet conditions)'
            elif -20 > self._state >= -50:
                self._interpretation = 'Minor Storm'
            elif -50 > self._state >= -100:
                self._interpretation = 'Moderate Storm'
            elif -100 > self._state >= -200:
                self._interpretation = 'Strong Storm'
            else:
                self._interpretation = 'Severe Storm'
            _LOGGER.debug("Geomagnetic interpretation: %s", self._interpretation)
        else:
            self._interpretation = 'Error: Invalid Dst value'
            _LOGGER.warning("Invalid Dst value received: %s", self._state)


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

        # Determine the rating based on the K-index value
        if self._state != 'unknown':  # Ensure valid state
            if self._state < 2:
                self._rating = 'low'
            elif 2 <= self._state < 5:
                self._rating = 'moderate'
            else:
                self._rating = 'high'
            _LOGGER.debug("K-index rating: %s", self._rating)
        else:
            self._rating = 'unknown'
            _LOGGER.warning("Unknown K-index value received")


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

            # Count alert types
            hurricane_warnings = 0
            hurricane_watches = 0
            tropical_warnings = 0
            tropical_watches = 0

            for feature in features:
                event = feature.get('properties', {}).get('event', '').lower()
                if 'hurricane warning' in event:
                    hurricane_warnings += 1
                elif 'hurricane watch' in event:
                    hurricane_watches += 1
                elif 'tropical storm warning' in event:
                    tropical_warnings += 1
                elif 'tropical storm watch' in event:
                    tropical_watches += 1

            # Process active storms
            hurricanes = 0
            tropical_storms = 0
            other_storms = 0
            storm_details = []

            for storm in active_storms:
                classification = storm.get('classification', '').upper()
                storm_info = {
                    'name': storm.get('name', 'Unknown'),
                    'classification': classification,
                    'intensity': storm.get('intensity', 'Unknown'),
                    'pressure': storm.get('pressure', 'Unknown'),
                    'latitude': storm.get('latitude', 'Unknown'),
                    'longitude': storm.get('longitude', 'Unknown'),
                    'movement_dir': storm.get('movementDir', 'Unknown'),
                    'movement_speed': storm.get('movementSpeed', 'Unknown'),
                    'last_update': storm.get('lastUpdate', 'Unknown')
                }
                storm_details.append(storm_info)

                if classification in ['H1', 'H2', 'H3', 'H4', 'H5', 'HU']:
                    hurricanes += 1
                elif classification in ['TS', 'TD']:
                    tropical_storms += 1
                else:
                    other_storms += 1

            # Determine overall activity state based on active storms and alerts
            total_storms = len(active_storms)
            if hurricane_warnings > 0 or hurricanes > 0:
                if hurricanes > 0:
                    self._state = f'High - {hurricanes} Active Hurricane(s)'
                else:
                    self._state = 'High - Hurricane Warnings Active'
            elif hurricane_watches > 0:
                self._state = 'Moderate - Hurricane Watches Active'
            elif tropical_warnings > 0 or tropical_storms > 0:
                if tropical_storms > 0:
                    self._state = f'Moderate - {tropical_storms} Active Tropical Storm(s)'
                else:
                    self._state = 'Moderate - Tropical Storm Warnings Active'
            elif tropical_watches > 0:
                self._state = 'Low - Tropical Storm Watches Active'
            elif other_storms > 0:
                self._state = f'Low - {other_storms} Other Storm System(s) Active'
            else:
                self._state = 'Quiet - No Active Storms or Alerts'

            self._attributes = {
                'total_active_storms': total_storms,
                'hurricanes': hurricanes,
                'tropical_storms': tropical_storms,
                'other_storms': other_storms,
                'hurricane_warnings': hurricane_warnings,
                'hurricane_watches': hurricane_watches,
                'tropical_warnings': tropical_warnings,
                'tropical_watches': tropical_watches,
                'total_alerts': len(features),
                'storm_details': storm_details
            }
            _LOGGER.debug("Successfully updated hurricane activity sensor: %s (storms: %d, alerts: %d)",
                          self._state, total_storms, len(features))

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


class RipCurrentRiskSensor(Entity):
    """Representation of Rip Current Risk sensor for specific NWS office location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_rip_current_risk"
        self._attr_name = "NOAA Surf - Rip Current Risk"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:waves'

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
        """Fetch new rip current risk data for the specific location."""
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
            if re.search(r"high\s+rip\s+current\s+risk|dangerous\s+rip\s+currents|"
                         r"rip\s+current\s+risk\s+is\s+high", forecast_text):
                risk_level = "High"
            elif re.search(r"moderate\s+rip\s+current\s+risk|rip\s+current\s+risk\s+is\s+moderate",
                           forecast_text):
                risk_level = "Moderate"
            elif re.search(r"low\s+rip\s+current\s+risk|rip\s+current\s+risk\s+is\s+low", forecast_text):
                risk_level = "Low"
            else:
                # If no specific rip current mention, assume low risk
                risk_level = "Low"

            self._state = risk_level
            self._attributes = {
                'office_code': self._office_code,
                'forecast_source': url,
                'last_updated': 'Check forecast for timestamp',
            }

            _LOGGER.debug("Updated rip current risk for %s: %s", self._office_code, risk_level)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}


class SurfHeightSensor(Entity):
    """Representation of Surf Height sensor for specific NWS office location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_surf_height"
        self._attr_name = "NOAA Surf - Surf Height"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return 'ft'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:wave'

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
        """Fetch new surf height data for the specific location."""
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

            # Look for surf height patterns from actual NWS format
            # Examples: "surf height.................2 to 4 feet." or "surf height 6 to 9 feet."
            height_patterns = [
                r"surf\s+height\.+(\d+)\s+to\s+(\d+)\s+feet",
                r"surf\s+height\s+(\d+)\s+to\s+(\d+)\s+feet",
                r"surf\s+height\.+(\d+)\s+feet",
                r"surf\s+height\s+(\d+)\s+feet",
                # Also check for patterns in daily forecasts
                r"surf\s+height\s+(\d+)\s+to\s+(\d+)\s+feet",
                r"surf\s+(\d+)\s+to\s+(\d+)\s+feet",
            ]

            surf_height = None
            for pattern in height_patterns:
                match = re.search(pattern, forecast_text)
                if match:
                    if len(match.groups()) == 2:
                        # Range pattern (e.g., "2 to 4 feet")
                        low = int(match.group(1))
                        high = int(match.group(2))
                        surf_height = f"{low}-{high}"
                    else:
                        # Single value pattern (e.g., "3 feet")
                        surf_height = match.group(1)
                    break

            self._state = surf_height if surf_height else "Unknown"
            self._attributes = {
                'office_code': self._office_code,
                'forecast_source': url,
                'last_updated': 'Check forecast for timestamp',
            }

            _LOGGER.debug("Updated surf height for %s: %s", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}


class WaterTemperatureSensor(Entity):
    """Representation of Water Temperature sensor for specific NWS office location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._attr_unique_id = f"noaa_{office_code}_water_temperature"
        self._attr_name = "NOAA Surf - Water Temperature"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return '°F'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:thermometer-water'

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
        """Fetch new water temperature data for the specific location."""
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

            # Look for water temperature patterns from actual NWS format
            # Examples: "water temperature...........in the mid 80s." or "water temperature in the upper 70s"
            temp_patterns = [
                r"water\s+temperature\.+in\s+the\s+(upper|mid|lower)\s+(\d+)s",
                r"water\s+temperature\s+in\s+the\s+(upper|mid|lower)\s+(\d+)s",
                r"water\s+temperature\.+around\s+(\d+)",
                r"water\s+temperature\s+around\s+(\d+)",
                r"water\s+temperature\.+(\d+)\s*(?:degrees?|°?f?)",
                r"water\s+temp\.+(\d+)\s*(?:degrees?|°?f?)",
            ]

            water_temp = None
            for pattern in temp_patterns:
                match = re.search(pattern, forecast_text)
                if match:
                    if "upper" in match.groups():
                        # Upper range (e.g., "upper 80s" = ~85-89)
                        base_temp = int(match.groups()[-1])  # Get the number part
                        water_temp = f"{base_temp + 5}-{base_temp + 9}"
                    elif "mid" in match.groups():
                        # Mid range (e.g., "mid 80s" = ~83-87)
                        base_temp = int(match.groups()[-1])  # Get the number part
                        water_temp = f"{base_temp + 3}-{base_temp + 7}"
                    elif "lower" in match.groups():
                        # Lower range (e.g., "lower 80s" = ~80-84)
                        base_temp = int(match.groups()[-1])  # Get the number part
                        water_temp = f"{base_temp}-{base_temp + 4}"
                    else:
                        # Exact temperature
                        water_temp = match.groups()[-1]  # Get the last (number) group
                    break

            self._state = water_temp if water_temp else "Unknown"
            self._attributes = {
                'office_code': self._office_code,
                'forecast_source': url,
                'last_updated': 'Check forecast for timestamp',
            }

            _LOGGER.debug("Updated water temperature for %s: %s", self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching surf zone forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching surf zone forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}


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
            aurora_possible = self._calculate_aurora_visibility(current_kp, office_lat)

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
                    estimated_hours = 12 + (3 - current_kp) * 6  # More hours if Kp is very low
                else:
                    estimated_hours = 6  # Moderate activity, could improve soon

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

    def _calculate_aurora_visibility(self, kp_index, magnetic_latitude):
        """Calculate if aurora is visible based on Kp and location."""
        for threshold_name, threshold_data in AURORA_KP_THRESHOLDS.items():
            if magnetic_latitude >= threshold_data["min_lat"]:
                return kp_index >= threshold_data["kp_threshold"]
        return False


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
            if current_kp >= 7:
                duration = 4 + (current_kp - 7) * 2  # 4-8 hours for strong storms
            elif current_kp >= 5:
                duration = 2 + (current_kp - 5) * 1  # 2-4 hours for moderate activity
            elif current_kp >= 3:
                duration = 1 + (current_kp - 3) * 0.5  # 1-2 hours for minor activity
            else:
                duration = 0  # No significant activity

            # Adjust for latitude - higher latitudes see longer aurora
            if office_lat >= 50:
                duration *= 1.3  # 30% longer at high latitudes
            elif office_lat >= 40:
                duration *= 1.1  # 10% longer at mid latitudes

            self._state = round(duration, 1)
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
            probability = self._calculate_probability(current_kp, office_lat)

            self._state = probability
            self._attributes = {
                'current_kp': current_kp,
                'magnetic_latitude': office_lat,
                'visibility_class': self._get_visibility_class(probability),
                'required_kp': self._get_required_kp(office_lat)
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

    def _calculate_probability(self, kp_index, magnetic_latitude):
        """Calculate visibility probability based on Kp and location."""
        # Base probability calculation
        if magnetic_latitude >= 55:  # Very high latitude
            if kp_index >= 3:
                probability = min(90, 30 + (kp_index - 3) * 15)
            else:
                probability = kp_index * 10
        elif magnetic_latitude >= 50:  # High latitude
            if kp_index >= 4:
                probability = min(80, 20 + (kp_index - 4) * 15)
            else:
                probability = max(0, (kp_index - 2) * 10)
        elif magnetic_latitude >= 40:  # Mid latitude
            if kp_index >= 5:
                probability = min(70, 15 + (kp_index - 5) * 15)
            else:
                probability = max(0, (kp_index - 4) * 8)
        elif magnetic_latitude >= 30:  # Low latitude
            if kp_index >= 7:
                probability = min(50, 10 + (kp_index - 7) * 15)
            else:
                probability = max(0, (kp_index - 6) * 5)
        else:  # Very low latitude
            if kp_index >= 8:
                probability = min(30, (kp_index - 8) * 10)
            else:
                probability = 0

        return round(probability)

    def _get_visibility_class(self, probability):
        """Get visibility class based on probability."""
        if probability >= 70:
            return "Excellent"
        elif probability >= 50:
            return "Good"
        elif probability >= 30:
            return "Fair"
        elif probability >= 10:
            return "Poor"
        else:
            return "None"

    def _get_required_kp(self, magnetic_latitude):
        """Get minimum Kp index required for visibility at this latitude."""
        for threshold_name, threshold_data in AURORA_KP_THRESHOLDS.items():
            if magnetic_latitude >= threshold_data["min_lat"]:
                return threshold_data["kp_threshold"]
        return 9


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
                'location_impact_risk': self._assess_location_risk(office_lat, solar_radiation_alerts),
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

            # Extract storm scale from message or product ID
            scale = self._extract_storm_scale(message, product_id)

            # Extract timing information
            begin_time = self._extract_time_from_message(message, 'begin time')
            end_time = self._extract_time_from_message(message, 'end time')
            duration = self._calculate_duration(begin_time, end_time)

            # Extract potential impacts
            impacts = self._extract_impacts(message)

            alert_info = {
                'product_id': product_id,
                'scale': scale,
                'scale_description': SOLAR_RADIATION_STORM_SCALES.get(scale, {}).get('name', 'Unknown'),
                'begin_time': begin_time,
                'end_time': end_time,
                'duration_hours': duration,
                'impacts': impacts,
                'issue_time': issue_datetime,
                'severity': self._get_severity_level(scale),
                'message_summary': message[:200] + '...' if len(message) > 200 else message
            }

            return alert_info

        except Exception as e:
            _LOGGER.warning("Failed to parse solar radiation alert: %s", e)
            return None

    def _extract_storm_scale(self, message, product_id):
        """Extract S1-S5 storm scale from message or product ID."""
        # Check product ID first
        for scale in ['S5', 'S4', 'S3', 'S2', 'S1']:  # Check higher scales first
            if product_id.startswith(scale):
                return scale

        # Check message content for scale references
        message_upper = message.upper()
        for scale in ['S5', 'S4', 'S3', 'S2', 'S1']:
            if f'SCALE {scale}' in message_upper or f'{scale} (' in message_upper:
                return scale

        # If no specific scale found, classify based on keywords
        if any(keyword in message.lower() for keyword in ['extreme', 'severe']):
            return 'S4'
        elif any(keyword in message.lower() for keyword in ['strong', 'major']):
            return 'S3'
        elif any(keyword in message.lower() for keyword in ['moderate']):
            return 'S2'
        elif any(keyword in message.lower() for keyword in ['minor']):
            return 'S1'

        return 'Unknown'

    def _extract_time_from_message(self, message, time_type):
        """Extract time information from alert message."""
        try:
            # Look for time patterns like "Begin Time: 2025 Aug 10 1145 UTC"
            time_pattern = rf'{time_type}:\s*(\d{{4}}\s+\w{{3}}\s+\d{{1,2}}\s+\d{{4}}\s+UTC)'
            match = re.search(time_pattern, message, re.IGNORECASE)
            if match:
                return match.group(1)
        except Exception:
            pass
        return None

    def _calculate_duration(self, begin_time, end_time):
        """Calculate duration between begin and end times."""
        if not begin_time or not end_time:
            return None
        try:
            # Parse times and calculate duration
            # This is a simplified implementation
            return "TBD"  # Would need proper datetime parsing
        except Exception:
            return None

    def _extract_impacts(self, message):
        """Extract potential impacts from alert message."""
        impacts = []
        message_lower = message.lower()

        if 'satellite' in message_lower:
            impacts.append('Satellite operations')
        if 'radio' in message_lower or 'communication' in message_lower:
            impacts.append('Radio communications')
        if 'navigation' in message_lower or 'gps' in message_lower:
            impacts.append('Navigation systems')
        if 'radiation' in message_lower and ('hazard' in message_lower or 'risk' in message_lower):
            impacts.append('Radiation exposure risk')
        if 'polar' in message_lower:
            impacts.append('Polar region effects')

        return impacts

    def _get_severity_level(self, scale):
        """Get severity level based on storm scale."""
        severity_map = {
            'S5': 'Extreme',
            'S4': 'Severe',
            'S3': 'Strong',
            'S2': 'Moderate',
            'S1': 'Minor',
            'Unknown': 'Unknown'
        }
        return severity_map.get(scale, 'Unknown')

    def _assess_location_risk(self, magnetic_latitude, alerts):
        """Assess location-specific risk based on magnetic latitude and current alerts."""
        if not alerts:
            return 'Low'

        # Higher latitudes are more affected by solar radiation storms
        base_risk = 'Low'
        if magnetic_latitude >= 60.0:
            base_risk = 'High'
        elif magnetic_latitude >= 45.0:
            base_risk = 'Moderate'
        elif magnetic_latitude >= 30.0:
            base_risk = 'Low'

        # Increase risk based on active alerts
        max_scale = 'S1'
        for alert in alerts:
            scale = alert.get('scale', 'S1')
            if scale in ['S4', 'S5']:
                return 'High'
            elif scale == 'S3':
                max_scale = 'S3'
            elif scale == 'S2' and max_scale not in ['S3', 'S4', 'S5']:
                max_scale = 'S2'

        if max_scale in ['S3', 'S4', 'S5'] and base_risk == 'Low':
            return 'Moderate'
        elif max_scale in ['S4', 'S5']:
            return 'High'

        return base_risk


class WeatherObservationSensor(Entity):
    """Base class for weather observation sensors."""

    def __init__(self, office_code, observation_field, sensor_name, latitude=None, longitude=None,
                 unit=None, icon=None, device_class=None):
        """Initialize the weather observation sensor."""
        self._office_code = office_code
        self._observation_field = observation_field
        self._sensor_name = sensor_name
        self._latitude = latitude
        self._longitude = longitude
        self._unit = unit
        self._icon_name = icon
        self._device_class = device_class
        self._state = None
        self._attributes = {}
        self._station_id = None
        self._station_fetched = False

        # Fall back to office-based station mapping if no lat/lon provided
        if latitude is None or longitude is None:
            self._station_id = OFFICE_STATION_IDS.get(office_code)
            self._station_fetched = True

    @property
    def name(self):
        """Return the name of the sensor."""
        return f'NOAA Weather - {self._sensor_name}'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return self._unit

    @property
    def icon(self):
        """Return the icon."""
        return self._icon_name

    @property
    def device_class(self):
        """Return the device class."""
        return self._device_class

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        field_name = self._observation_field.replace('.', '_')
        # Include lat/lon in unique ID when available to avoid conflicts
        # Note: Coordinate formatting must match config_flow.py for consistency
        if self._latitude is not None and self._longitude is not None:
            # Round to 4 decimal places for uniqueness while avoiding float precision issues
            lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
            lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
            return f"noaa_{self._office_code}_{lat_str}_{lon_str}_{field_name}"
        return f"noaa_{self._office_code}_{field_name}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new weather observation data."""
        # Fetch station ID from lat/lon if not already fetched
        if not self._station_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_station_from_location()

        if not self._station_id:
            _LOGGER.error("Unable to find weather station for coordinates (lat: %s, lon: %s) or office %s",
                          self._latitude, self._longitude, self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Unable to find weather station for the specified coordinates'}
            return

        try:
            url = NWS_OBSERVATIONS_URL.format(station=self._station_id)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})

            # Extract the value based on the observation field
            value = self._extract_value(properties)

            self._state = value
            self._attributes = {
                'office_code': self._office_code,
                'station_id': self._station_id,
                'station_name': properties.get('stationName', 'Unknown'),
                'timestamp': properties.get('timestamp', 'Unknown'),
            }

            _LOGGER.debug("Updated %s for %s: %s", self._sensor_name, self._office_code, self._state)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching weather observation for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching weather observation for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}'}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing weather observation for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}'}

    async def _async_fetch_station_from_location(self):
        """Fetch the nearest observation station from latitude and longitude."""
        try:
            # Get point metadata from weather.gov API
            points_url = NWS_POINTS_URL.format(lat=self._latitude, lon=self._longitude)
            _LOGGER.debug("Fetching station for lat=%s, lon=%s from %s",
                          self._latitude, self._longitude, points_url)

            session = async_get_clientsession(self.hass)
            async with session.get(
                points_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()

            properties = data.get('properties', {})
            stations_url = properties.get('observationStations')

            if not stations_url:
                _LOGGER.error("No observation stations URL found for lat=%s, lon=%s",
                              self._latitude, self._longitude)
                self._station_fetched = True
                return

            # Fetch list of nearby stations
            _LOGGER.debug("Fetching stations list from %s", stations_url)
            async with session.get(
                stations_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                stations_data = await response.json()
            stations_list = stations_data.get('features', [])

            if stations_list:
                # Use the first (nearest) station
                station_id = stations_list[0].get('properties', {}).get('stationIdentifier')
                # Validate station_id is a non-empty string
                if station_id and isinstance(station_id, str) and station_id.strip():
                    self._station_id = station_id.strip()
                    _LOGGER.info("Found station %s for lat=%s, lon=%s",
                                 self._station_id, self._latitude, self._longitude)
                else:
                    _LOGGER.warning("Station found but has no valid identifier for lat=%s, lon=%s",
                                    self._latitude, self._longitude)
            else:
                _LOGGER.warning("No stations found for lat=%s, lon=%s",
                                self._latitude, self._longitude)

            self._station_fetched = True

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout fetching station for lat=%s, lon=%s",
                          self._latitude, self._longitude)
            self._station_fetched = True
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching station for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._station_fetched = True
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing station data for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._station_fetched = True

    def _extract_value(self, properties):
        """Extract and convert the observation value from the API response."""
        # Navigate nested fields (e.g., 'temperature.value')
        field_parts = self._observation_field.split('.')
        value = properties
        for part in field_parts:
            if isinstance(value, dict):
                value = value.get(part)
            else:
                return None

        if value is None:
            return None

        # Handle specific conversions based on the field
        return self._convert_value(value)

    def _convert_value(self, value):
        """Convert the value to the appropriate format and units."""
        # Default implementation - override in subclasses if needed
        if isinstance(value, (int, float)):
            return round(value, 1)
        return value

    def _celsius_to_fahrenheit(self, celsius):
        """Convert Celsius to Fahrenheit."""
        if celsius is None:
            return None
        fahrenheit = (celsius * 9/5) + 32
        return round(fahrenheit, 1)


class TemperatureSensor(WeatherObservationSensor):
    """Temperature sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the temperature sensor."""
        super().__init__(
            office_code,
            'temperature.value',
            'Temperature',
            latitude=latitude,
            longitude=longitude,
            unit='°F',
            icon='mdi:thermometer',
            device_class='temperature'
        )

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return self._celsius_to_fahrenheit(value)


class HumiditySensor(WeatherObservationSensor):
    """Relative humidity sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the humidity sensor."""
        super().__init__(
            office_code,
            'relativeHumidity.value',
            'Humidity',
            latitude=latitude,
            longitude=longitude,
            unit='%',
            icon='mdi:water-percent',
            device_class='humidity'
        )

    def _convert_value(self, value):
        """Round humidity to integer."""
        if value is None:
            return None
        return round(value)


class WindSpeedSensor(WeatherObservationSensor):
    """Wind speed sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the wind speed sensor."""
        super().__init__(
            office_code,
            'windSpeed.value',
            'Wind Speed',
            latitude=latitude,
            longitude=longitude,
            unit='mph',
            icon='mdi:weather-windy'
        )

    def _convert_value(self, value):
        """Convert km/h to mph."""
        if value is None:
            return None
        # API returns km/h, convert to mph
        mph = value * 0.621371
        return round(mph, 1)


class WindDirectionSensor(WeatherObservationSensor):
    """Wind direction sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the wind direction sensor."""
        super().__init__(
            office_code,
            'windDirection.value',
            'Wind Direction',
            latitude=latitude,
            longitude=longitude,
            unit='°',
            icon='mdi:compass'
        )

    def _convert_value(self, value):
        """Convert wind direction to round integer."""
        if value is None:
            return None
        return round(value)

    async def async_update(self):
        """Fetch new weather observation data and add cardinal direction."""
        await super().async_update()
        # Add cardinal direction to attributes after base update
        if self._state is not None and self._state != 'Error':
            cardinal = self._degrees_to_cardinal(self._state)
            self._attributes['cardinal_direction'] = cardinal

    def _degrees_to_cardinal(self, degrees):
        """Convert degrees to cardinal direction."""
        directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                      'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
        idx = round(degrees / 22.5) % 16
        return directions[idx]


class BarometricPressureSensor(WeatherObservationSensor):
    """Barometric pressure sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the barometric pressure sensor."""
        super().__init__(
            office_code,
            'barometricPressure.value',
            'Barometric Pressure',
            latitude=latitude,
            longitude=longitude,
            unit='inHg',
            icon='mdi:gauge',
            device_class='pressure'
        )

    def _convert_value(self, value):
        """Convert Pascals to inches of mercury."""
        if value is None:
            return None
        # API returns Pascals, convert to inHg
        inhg = value * 0.00029530
        return round(inhg, 2)


class DewpointSensor(WeatherObservationSensor):
    """Dewpoint sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the dewpoint sensor."""
        super().__init__(
            office_code,
            'dewpoint.value',
            'Dewpoint',
            latitude=latitude,
            longitude=longitude,
            unit='°F',
            icon='mdi:water',
            device_class='temperature'
        )

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return self._celsius_to_fahrenheit(value)


class VisibilitySensor(WeatherObservationSensor):
    """Visibility sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the visibility sensor."""
        super().__init__(
            office_code,
            'visibility.value',
            'Visibility',
            latitude=latitude,
            longitude=longitude,
            unit='mi',
            icon='mdi:eye'
        )

    def _convert_value(self, value):
        """Convert meters to miles."""
        if value is None:
            return None
        # API returns meters, convert to miles
        miles = value * 0.000621371
        return round(miles, 1)


class SkyConditionsSensor(WeatherObservationSensor):
    """Sky conditions sensor."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the sky conditions sensor."""
        super().__init__(
            office_code,
            'textDescription',
            'Sky Conditions',
            latitude=latitude,
            longitude=longitude,
            icon='mdi:weather-partly-cloudy'
        )

    def _convert_value(self, value):
        """Return the text description as-is."""
        return value if value else 'Unknown'


class FeelsLikeSensor(WeatherObservationSensor):
    """Feels-like temperature sensor (wind chill or heat index)."""

    def __init__(self, office_code, latitude=None, longitude=None):
        """Initialize the feels-like sensor."""
        super().__init__(
            office_code,
            'combined',  # Special handling needed
            'Feels Like',
            latitude=latitude,
            longitude=longitude,
            unit='°F',
            icon='mdi:thermometer-lines',
            device_class='temperature'
        )

    def _extract_value(self, properties):
        """Extract wind chill or heat index depending on which is available."""
        # Check for wind chill first (cold conditions)
        wind_chill = properties.get('windChill', {})
        if wind_chill and wind_chill.get('value') is not None:
            value = wind_chill.get('value')
            self._attributes['feels_like_type'] = 'Wind Chill'
            return self._convert_value(value)

        # Check for heat index (hot conditions)
        heat_index = properties.get('heatIndex', {})
        if heat_index and heat_index.get('value') is not None:
            value = heat_index.get('value')
            self._attributes['feels_like_type'] = 'Heat Index'
            return self._convert_value(value)

        # Neither available, return actual temperature
        temperature = properties.get('temperature', {})
        if temperature and temperature.get('value') is not None:
            value = temperature.get('value')
            self._attributes['feels_like_type'] = 'Actual Temperature'
            return self._convert_value(value)

        return None

    def _convert_value(self, value):
        """Convert Celsius to Fahrenheit."""
        return self._celsius_to_fahrenheit(value)


class ForecastBaseSensor(Entity):
    """Base class for forecast sensors."""

    def __init__(self, office_code, latitude, longitude, forecast_type):
        """Initialize the base forecast sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._forecast_type = forecast_type  # 'forecast' or 'forecastHourly'
        self._state = None
        self._attributes = {}
        self._forecast_url = None
        self._grid_fetched = False

    def _format_coordinates_for_id(self):
        """Format coordinates for unique ID generation."""
        if self._latitude is not None and self._longitude is not None:
            lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
            lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
            return f"{lat_str}_{lon_str}"
        return None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def _async_fetch_forecast_url(self):
        """Fetch forecast URL from latitude and longitude."""
        try:
            points_url = NWS_POINTS_URL.format(lat=self._latitude, lon=self._longitude)
            _LOGGER.debug("Fetching forecast URL for lat=%s, lon=%s from %s",
                          self._latitude, self._longitude, points_url)

            session = async_get_clientsession(self.hass)
            async with session.get(
                points_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            properties = data.get('properties', {})

            # Get the forecast URL directly from the points API
            forecast_url = properties.get(self._forecast_type)

            if forecast_url:
                self._forecast_url = forecast_url
                _LOGGER.info("Found %s URL for lat=%s, lon=%s: %s",
                             self._forecast_type, self._latitude, self._longitude, self._forecast_url)
            else:
                _LOGGER.error("No %s URL found for lat=%s, lon=%s",
                              self._forecast_type, self._latitude, self._longitude)

            self._grid_fetched = True

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout fetching forecast URL for lat=%s, lon=%s",
                          self._latitude, self._longitude)
            self._grid_fetched = True
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching forecast URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing forecast URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True


class ExtendedForecastSensor(ForecastBaseSensor):
    """Representation of Extended (7-day) Forecast sensor."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(office_code, latitude, longitude, 'forecast')
        # Initialize with empty periods list to prevent template errors before first update
        self._attributes = {'periods': []}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Extended Forecast'

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
        coords = self._format_coordinates_for_id()
        if coords:
            return f"noaa_{self._office_code}_{coords}_extended_forecast"
        return f"noaa_{self._office_code}_extended_forecast"

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:weather-partly-cloudy'

    async def async_update(self):
        """Fetch new extended forecast data."""
        # Fetch forecast URL from lat/lon if not already fetched
        if not self._grid_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_forecast_url()

        if not self._forecast_url:
            _LOGGER.error("Unable to get forecast URL for coordinates (lat: %s, lon: %s)",
                          self._latitude, self._longitude)
            self._state = 'Error'
            self._attributes = {'error': 'Unable to get forecast URL for the specified coordinates', 'periods': []}
            return

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                self._forecast_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})
            periods = properties.get('periods', [])

            if not periods:
                self._state = 'No forecast available'
                self._attributes = {'error': 'No forecast periods found', 'periods': []}
                return

            # Create a formatted text summary of the forecast
            forecast_text = self._format_forecast_text(periods)
            self._state = f"{len(periods)} periods"

            # Store detailed forecast in attributes
            self._attributes = {
                'office_code': self._office_code,
                'forecast_text': forecast_text,
                'generated_at': properties.get('generatedAt', 'Unknown'),
                'update_time': properties.get('updateTime', 'Unknown'),
                'periods': self._format_periods(periods[:MAX_FORECAST_PERIODS])
            }

            _LOGGER.debug("Updated extended forecast for %s: %d periods", self._office_code, len(periods))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching extended forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast', 'periods': []}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching extended forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}', 'periods': []}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing extended forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}', 'periods': []}

    def _format_forecast_text(self, periods):
        """Format forecast periods into readable text."""
        lines = []
        for period in periods[:MAX_FORECAST_PERIODS]:
            name = period.get('name', 'Unknown')
            detailed = period.get('detailedForecast', 'No details available')
            lines.append(f"{name}: {detailed}")
        return "\n\n".join(lines)

    def _format_periods(self, periods):
        """Format periods for attributes with key information."""
        formatted = []
        for period in periods:
            formatted.append({
                'name': period.get('name', 'Unknown'),
                'temperature': period.get('temperature'),
                'temperature_unit': period.get('temperatureUnit', 'F'),
                'wind_speed': period.get('windSpeed', 'Unknown'),
                'wind_direction': period.get('windDirection', 'Unknown'),
                'short_forecast': period.get('shortForecast', 'Unknown'),
                'detailed_forecast': period.get('detailedForecast', 'No details available'),
                'start_time': period.get('startTime', 'Unknown'),
                'is_daytime': period.get('isDaytime', False),
                'icon': period.get('icon', '')
            })
        return formatted


class HourlyForecastSensor(ForecastBaseSensor):
    """Representation of Hourly Forecast sensor."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        super().__init__(office_code, latitude, longitude, 'forecastHourly')
        # Initialize with empty hourly_periods list to prevent template errors before first update
        self._attributes = {'hourly_periods': []}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Hourly Forecast'

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
        coords = self._format_coordinates_for_id()
        if coords:
            return f"noaa_{self._office_code}_{coords}_hourly_forecast"
        return f"noaa_{self._office_code}_hourly_forecast"

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:clock-outline'

    async def async_update(self):
        """Fetch new hourly forecast data."""
        # Fetch forecast URL from lat/lon if not already fetched
        if not self._grid_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_forecast_url()

        if not self._forecast_url:
            _LOGGER.error("Unable to get hourly forecast URL for coordinates (lat: %s, lon: %s)",
                          self._latitude, self._longitude)
            self._state = 'Error'
            self._attributes = {
                'error': 'Unable to get hourly forecast URL for the specified coordinates',
                'hourly_periods': []
            }
            return

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                self._forecast_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})
            periods = properties.get('periods', [])

            if not periods:
                self._state = 'No forecast available'
                self._attributes = {'error': 'No forecast periods found', 'hourly_periods': []}
                return

            # Get current hour forecast
            current_period = periods[0] if periods else {}
            self._state = current_period.get('temperature', 'Unknown')

            # Store hourly forecast in attributes
            self._attributes = {
                'office_code': self._office_code,
                'current_hour': {
                    'temperature': current_period.get('temperature'),
                    'temperature_unit': current_period.get('temperatureUnit', 'F'),
                    'wind_speed': current_period.get('windSpeed', 'Unknown'),
                    'wind_direction': current_period.get('windDirection', 'Unknown'),
                    'short_forecast': current_period.get('shortForecast', 'Unknown'),
                    'start_time': current_period.get('startTime', 'Unknown'),
                    'icon': current_period.get('icon', '')
                },
                'generated_at': properties.get('generatedAt', 'Unknown'),
                'update_time': properties.get('updateTime', 'Unknown'),
                'hourly_periods': self._format_hourly_periods(periods[:MAX_HOURLY_PERIODS])
            }

            _LOGGER.debug("Updated hourly forecast for %s: %d periods", self._office_code, len(periods))

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching hourly forecast for %s", self._office_code)
            self._state = 'Error'
            self._attributes = {'error': 'Timeout fetching forecast', 'hourly_periods': []}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching hourly forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Request error: {e}', 'hourly_periods': []}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing hourly forecast for %s: %s", self._office_code, e)
            self._state = 'Error'
            self._attributes = {'error': f'Parse error: {e}', 'hourly_periods': []}

    def _format_hourly_periods(self, periods):
        """Format hourly periods for attributes with key information."""
        formatted = []
        for period in periods:
            # Safely extract precipitation probability
            precip_prob = period.get('probabilityOfPrecipitation')
            precip_value = 0
            if precip_prob and isinstance(precip_prob, dict):
                precip_value = precip_prob.get('value', 0)
            elif isinstance(precip_prob, (int, float)):
                precip_value = precip_prob

            formatted.append({
                'start_time': period.get('startTime', 'Unknown'),
                'temperature': period.get('temperature'),
                'temperature_unit': period.get('temperatureUnit', 'F'),
                'wind_speed': period.get('windSpeed', 'Unknown'),
                'wind_direction': period.get('windDirection', 'Unknown'),
                'short_forecast': period.get('shortForecast', 'Unknown'),
                'precipitation_probability': precip_value,
                'is_daytime': period.get('isDaytime', False),
                'icon': period.get('icon', '')
            })
        return formatted


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

            # Parse all actual alerts
            active_alerts = []
            alert_summary = {
                'warnings': 0,
                'watches': 0,
                'advisories': 0,
                'statements': 0,
                'by_severity': {'Extreme': 0, 'Severe': 0, 'Moderate': 0, 'Minor': 0, 'Unknown': 0},
                'by_urgency': {'Immediate': 0, 'Expected': 0, 'Future': 0, 'Past': 0, 'Unknown': 0},
                'event_types': {}
            }

            for feature in features:
                props = feature.get('properties', {})
                status = props.get('status', '').lower()

                # Only include actual alerts (not tests or drafts)
                if status == 'actual':
                    event = props.get('event', 'Unknown')
                    severity = props.get('severity', 'Unknown')
                    urgency = props.get('urgency', 'Unknown')

                    alert_info = {
                        'event': event,
                        'headline': props.get('headline', 'No headline'),
                        'severity': severity,
                        'urgency': urgency,
                        'certainty': props.get('certainty', 'Unknown'),
                        'area': props.get('areaDesc', 'Unknown area'),
                        'effective': props.get('effective', 'Unknown'),
                        'onset': props.get('onset', 'Unknown'),
                        'expires': props.get('expires', 'Unknown'),
                        'ends': props.get('ends', 'Unknown'),
                        'status': props.get('status', 'Unknown'),
                        'message_type': props.get('messageType', 'Unknown'),
                        'category': props.get('category', 'Unknown'),
                        'sender': props.get('senderName', 'Unknown'),
                        'instruction': props.get('instruction', 'None')[:200] if props.get('instruction') else None,
                        'description': props.get('description', '')[:300]
                    }
                    active_alerts.append(alert_info)

                    # Update summary statistics
                    event_lower = event.lower()
                    if 'warning' in event_lower:
                        alert_summary['warnings'] += 1
                    elif 'watch' in event_lower:
                        alert_summary['watches'] += 1
                    elif 'advisory' in event_lower:
                        alert_summary['advisories'] += 1
                    elif 'statement' in event_lower:
                        alert_summary['statements'] += 1

                    # Normalize severity and urgency to known keys, defaulting to 'Unknown'
                    normalized_severity = severity if severity in alert_summary['by_severity'] else 'Unknown'
                    normalized_urgency = urgency if urgency in alert_summary['by_urgency'] else 'Unknown'

                    alert_summary['by_severity'][normalized_severity] += 1
                    alert_summary['by_urgency'][normalized_urgency] += 1
                    alert_summary['event_types'][event] = alert_summary['event_types'].get(event, 0) + 1

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


class CloudCoverSensor(Entity):
    """Representation of Cloud Cover sensor for specific location."""

    def __init__(self, office_code, latitude, longitude):
        """Initialize the sensor."""
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude
        self._state = None
        self._attributes = {}
        self._gridpoint_url = None
        self._grid_fetched = False

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Cloud Cover'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

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
        return self._attributes

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
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch new cloud cover data."""
        # Fetch gridpoint URL from lat/lon if not already fetched
        if not self._grid_fetched and self._latitude is not None and self._longitude is not None:
            await self._async_fetch_gridpoint_url()

        if not self._gridpoint_url:
            _LOGGER.error("Unable to get gridpoint URL for coordinates (lat: %s, lon: %s)",
                          self._latitude, self._longitude)
            self._state = None
            self._attributes = {'error': 'Unable to get gridpoint URL for the specified coordinates',
                                'availability': 'Not available for this location'}
            return

        try:
            session = async_get_clientsession(self.hass)
            async with session.get(
                self._gridpoint_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            self._attr_available = True
            properties = data.get('properties', {})
            sky_cover = properties.get('skyCover', {})

            # Get current sky cover value
            if sky_cover and 'values' in sky_cover:
                values = sky_cover['values']
                if values and len(values) > 0:
                    # Get the most recent value
                    current_value = values[0].get('value')
                    if current_value is not None:
                        self._state = round(current_value)
                        self._attributes = {
                            'office_code': self._office_code,
                            'latitude': self._latitude,
                            'longitude': self._longitude,
                            'valid_time': values[0].get('validTime', 'Unknown'),
                            'availability': 'Available from NWS gridpoint data'
                        }
                        _LOGGER.debug("Updated cloud cover for %s: %s%%", self._office_code, self._state)
                        return

            # No data available
            self._state = None
            self._attributes = {
                'office_code': self._office_code,
                'latitude': self._latitude,
                'longitude': self._longitude,
                'availability': 'Data not available at this time'
            }
            _LOGGER.debug("No cloud cover data available for %s", self._office_code)

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching cloud cover for %s", self._office_code)
            self._state = None
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching cloud cover for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Request error: {e}'}
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing cloud cover for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Parse error: {e}'}

    async def _async_fetch_gridpoint_url(self):
        """Fetch gridpoint URL from latitude and longitude."""
        try:
            points_url = NWS_POINTS_URL.format(lat=self._latitude, lon=self._longitude)
            _LOGGER.debug("Fetching gridpoint URL for lat=%s, lon=%s from %s",
                          self._latitude, self._longitude, points_url)

            session = async_get_clientsession(self.hass)
            async with session.get(
                points_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                data = await response.json()
            properties = data.get('properties', {})

            # Get the gridpoint URL
            gridpoint_url = properties.get('forecastGridData')

            if gridpoint_url:
                self._gridpoint_url = gridpoint_url
                _LOGGER.info("Found gridpoint URL for lat=%s, lon=%s: %s",
                             self._latitude, self._longitude, self._gridpoint_url)
            else:
                _LOGGER.error("No gridpoint URL found for lat=%s, lon=%s",
                              self._latitude, self._longitude)

            self._grid_fetched = True

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout fetching gridpoint URL for lat=%s, lon=%s",
                          self._latitude, self._longitude)
            self._grid_fetched = True
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching gridpoint URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True
        except (ValueError, KeyError) as e:
            self._attr_available = False
            _LOGGER.error("Error parsing gridpoint URL for lat=%s, lon=%s: %s",
                          self._latitude, self._longitude, e)
            self._grid_fetched = True


class RadarTimestampSensor(Entity):
    """Representation of Radar Timestamp sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}
        self._radar_site = OFFICE_RADAR_SITES.get(office_code)

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Radar Timestamp'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:radar'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_radar_timestamp"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch radar timestamp from HTTP headers."""
        if not self._radar_site:
            _LOGGER.error("No radar site mapping found for office code: %s", self._office_code)
            self._state = None
            self._attributes = {
                'office_code': self._office_code,
                'availability': 'Not available for this office location'
            }
            return

        try:
            # Use NWS_RADAR_BASE_URL from const if it's defined, otherwise construct URL
            from .const import NWS_RADAR_BASE_URL
            radar_url = NWS_RADAR_BASE_URL.format(radar=self._radar_site)

            session = async_get_clientsession(self.hass)
            async with session.head(
                radar_url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                last_modified = response.headers.get('Last-Modified')
            self._attr_available = True

            if last_modified:
                # Parse the timestamp
                from email.utils import parsedate_to_datetime
                timestamp = parsedate_to_datetime(last_modified)
                self._state = timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')
                self._attributes = {
                    'office_code': self._office_code,
                    'radar_site': self._radar_site,
                    'timestamp_iso': timestamp.isoformat(),
                    'radar_url': radar_url,
                    'availability': 'Available from NWS radar images'
                }
                _LOGGER.debug("Updated radar timestamp for %s: %s", self._office_code, self._state)
            else:
                _LOGGER.warning("No Last-Modified header found for radar %s", self._radar_site)
                self._state = None
                self._attributes = {
                    'office_code': self._office_code,
                    'radar_site': self._radar_site,
                    'availability': 'Timestamp not available'
                }

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching radar timestamp for %s", self._office_code)
            self._state = None
            self._attributes = {'error': 'Timeout fetching radar data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching radar timestamp for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Error parsing radar timestamp for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Parse error: {e}'}


class ForecastDiscussionSensor(Entity):
    """Representation of Forecast Discussion sensor for specific location."""

    def __init__(self, office_code):
        """Initialize the sensor."""
        self._office_code = office_code
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        """Return the name of the sensor."""
        return 'NOAA Weather - Forecast Discussion'

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:text-box-outline'

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_forecast_discussion"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, "noaa_weather")},
            name="NOAA Weather",
            manufacturer="NOAA"
        )

    async def async_update(self):
        """Fetch forecast discussion from NWS."""
        try:
            url = NWS_AFD_URL.format(office=self._office_code)
            session = async_get_clientsession(self.hass)
            async with session.get(
                url,
                headers={'User-Agent': USER_AGENT},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
            ) as response:
                response.raise_for_status()
                html_content = await response.text()
            self._attr_available = True

            # Extract text from <pre> tag which contains the forecast discussion
            pre_match = re.search(r'<pre[^>]*>(.*?)</pre>', html_content, re.DOTALL | re.IGNORECASE)

            if pre_match:
                discussion_text = pre_match.group(1).strip()

                # Clean up HTML entities
                discussion_text = discussion_text.replace('&nbsp;', ' ')
                discussion_text = discussion_text.replace('&amp;', '&')
                discussion_text = discussion_text.replace('&lt;', '<')
                discussion_text = discussion_text.replace('&gt;', '>')

                # Extract issue time if available
                issue_time_match = re.search(r'(\d{3,4}\s+(?:AM|PM)\s+\w{3}\s+\w{3}\s+\d{1,2}\s+\d{4})',
                                             discussion_text, re.IGNORECASE)
                issue_time = issue_time_match.group(1) if issue_time_match else 'Unknown'

                # Create a summary (first 200 characters)
                summary = discussion_text[:200] + '...' if len(discussion_text) > 200 else discussion_text

                self._state = 'Available'
                self._attributes = {
                    'office_code': self._office_code,
                    'issue_time': issue_time,
                    'summary': summary,
                    'full_text': discussion_text,
                    'text_length': len(discussion_text),
                    'availability': 'Available from NWS Area Forecast Discussion (AFD)'
                }
                _LOGGER.debug("Updated forecast discussion for %s: %d characters",
                              self._office_code, len(discussion_text))
            else:
                _LOGGER.warning("Could not extract forecast discussion text for %s", self._office_code)
                self._state = None
                self._attributes = {
                    'office_code': self._office_code,
                    'availability': 'Unable to parse forecast discussion'
                }

        except asyncio.TimeoutError:
            self._attr_available = False
            _LOGGER.error("Timeout when fetching forecast discussion for %s", self._office_code)
            self._state = None
            self._attributes = {'error': 'Timeout fetching data'}
        except aiohttp.ClientError as e:
            self._attr_available = False
            _LOGGER.error("Error fetching forecast discussion for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Request error: {e}'}
        except Exception as e:
            self._attr_available = False
            _LOGGER.error("Error parsing forecast discussion for %s: %s", self._office_code, e)
            self._state = None
            self._attributes = {'error': f'Parse error: {e}'}
