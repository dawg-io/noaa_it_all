"""Weather platform for NOAA Integration."""
import logging
import re
from datetime import datetime, timedelta
from typing import List, Optional

from homeassistant.components.weather import (
    ATTR_WEATHER_PRECIPITATION_UNIT,
    ATTR_WEATHER_PRESSURE_UNIT,
    ATTR_WEATHER_TEMPERATURE_UNIT,
    ATTR_WEATHER_VISIBILITY_UNIT,
    ATTR_WEATHER_WIND_SPEED_UNIT,
    DOMAIN as WEATHER_DOMAIN,
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
)
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfLength,
    UnitOfPrecipitationDepth,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_OFFICE_CODE,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    DOMAIN,
)
from .entry_config import resolve_entry_config
from .parsers import meters_to_kilometers, pascals_to_hectopascals

_LOGGER = logging.getLogger(__name__)

# Kilometers in a mile: the international mile is exactly 1.609344 km.
_KM_PER_MILE = 1.609344


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA weather entity from config entry."""
    conf = resolve_entry_config(config_entry)
    office_code = conf[CONF_OFFICE_CODE]
    latitude = conf.get(CONF_LATITUDE)
    longitude = conf.get(CONF_LONGITUDE)

    if latitude is None or longitude is None:
        _LOGGER.error("Weather entity requires latitude and longitude")
        return

    data = hass.data[DOMAIN][config_entry.entry_id]
    observations_coord = data["observations_coordinator"]
    forecast_coord = data["forecast_coordinator"]

    if not observations_coord:
        _LOGGER.error("No observations coordinator available")
        return

    weather_entity = NOAAWeather(
        observations_coord, forecast_coord, office_code, latitude, longitude
    )
    async_add_entities([weather_entity])


class NOAAWeather(CoordinatorEntity, WeatherEntity):
    """Representation of NOAA weather data.

    The native units are the metric ones NWS reports observations in, so Home
    Assistant converts each observation once, to the units in the entity's
    settings: US customary ones unless others are chosen there. NWS gives the
    forecast in °F and mph, which is converted to the native units.
    """

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.KILOMETERS
    _attr_supported_features = (
        WeatherEntityFeature.FORECAST_DAILY | WeatherEntityFeature.FORECAST_HOURLY
    )

    def __init__(self, observations_coordinator, forecast_coordinator,
                 office_code: str, latitude: float, longitude: float):
        """Initialize the NOAA weather entity."""
        super().__init__(observations_coordinator)
        self._forecast_coordinator = forecast_coordinator
        self._office_code = office_code
        self._latitude = latitude
        self._longitude = longitude

    def get_initial_entity_options(self):
        """Return US customary units for the entity's settings, for Home Assistant to store.

        It stores them when it first registers the entity, as the units chosen in
        its settings, so they are shown whatever the unit system. One registered
        before has none, and shows the units of the unit system.

        Home Assistant's docstring says component base classes implement this and
        integrations shouldn't extend it, but a weather entity has no suggested
        units, and WeatherEntity doesn't implement it in 2026.3.0 to 2026.10.1.
        Should it start to, its weather options are kept and the units here win.
        """
        options = dict(super().get_initial_entity_options() or {})
        options[WEATHER_DOMAIN] = {
            **(options.get(WEATHER_DOMAIN) or {}),
            ATTR_WEATHER_TEMPERATURE_UNIT: UnitOfTemperature.FAHRENHEIT,
            ATTR_WEATHER_PRESSURE_UNIT: UnitOfPressure.INHG,
            ATTR_WEATHER_WIND_SPEED_UNIT: UnitOfSpeed.MILES_PER_HOUR,
            ATTR_WEATHER_VISIBILITY_UNIT: UnitOfLength.MILES,
            ATTR_WEATHER_PRECIPITATION_UNIT: UnitOfPrecipitationDepth.INCHES,
        }
        return options

    async def async_added_to_hass(self) -> None:
        """Process coordinator data immediately when added to HA."""
        await super().async_added_to_hass()
        # Subscribe to forecast coordinator updates.  Forecast data is
        # read directly from the coordinator in async_forecast_*(), so
        # we only need to tell HA to re-read state — no need to
        # re-parse observation data via _handle_coordinator_update().
        if self._forecast_coordinator:
            self.async_on_remove(
                self._forecast_coordinator.async_add_listener(
                    self._handle_forecast_update
                )
            )
        # Immediately process any data that the coordinators already
        # fetched during integration setup so the entity does not sit
        # empty until the first scheduled poll.
        self._handle_coordinator_update()

    def _handle_forecast_update(self) -> None:
        """Notify HA that forecast data changed (lightweight)."""
        # Forecast subscribers -- the weather card -- are only sent a new
        # forecast when told; otherwise they keep whatever they received when
        # they subscribed.
        self.hass.async_create_task(self.async_update_listeners(None))
        self.async_write_ha_state()

    @property
    def name(self) -> str:
        """Return the name of the entity."""
        return f"NOAA {self._office_code} Weather"

    @property
    def unique_id(self) -> str:
        """Return a unique ID for this entity."""
        lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
        lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
        return f"noaa_{self._office_code}_{lat_str}_{lon_str}_weather"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, f"noaa_{self._office_code}_weather")},
            name=f"NOAA {self._office_code} Weather",
            manufacturer="NOAA",
        )

    @property
    def extra_state_attributes(self) -> dict:
        """Return entity specific state attributes."""
        attributes = {}

        # Compute precipitation probability directly from forecast coordinator
        if self._forecast_coordinator and self._forecast_coordinator.data:
            hourly_data = self._forecast_coordinator.data.get("hourly")
            if hourly_data:
                periods = hourly_data.get("properties", {}).get("periods", [])
                if periods:
                    precip_prob = self._extract_precipitation_probability(periods[0])
                    if precip_prob is not None:
                        attributes["precipitation_probability"] = precip_prob

        if self.coordinator.data:
            station_id = self.coordinator.data.get("station_id")
            if station_id:
                attributes["station_id"] = station_id

        return attributes

    def _handle_coordinator_update(self) -> None:
        """Process observation data from coordinator."""
        if self.coordinator.data:
            properties = self.coordinator.data.get("properties", {})

            # Temperature (°C)
            self._attr_native_temperature = self._get_value(properties, "temperature", "value")

            # Humidity
            humidity = self._get_value(properties, "relativeHumidity", "value")
            self._attr_humidity = round(humidity) if humidity is not None else None

            # Pressure (Pa to hPa), as the Barometric Pressure sensor has it
            self._attr_native_pressure = pascals_to_hectopascals(
                self._get_value(properties, "barometricPressure", "value")
            )

            # Condition
            text_description = properties.get("textDescription")
            timestamp = properties.get("timestamp")
            self._attr_condition = self._map_condition(text_description, timestamp)

            # Dewpoint (°C)
            self._attr_native_dew_point = self._get_value(properties, "dewpoint", "value")

            # Visibility (m to km), as the Visibility sensor has it
            self._attr_native_visibility = meters_to_kilometers(
                self._get_value(properties, "visibility", "value")
            )

            # Wind speed (km/h)
            self._attr_native_wind_speed = self._get_value(properties, "windSpeed", "value")

            # Wind direction
            wind_dir = self._get_value(properties, "windDirection", "value")
            self._attr_wind_bearing = round(wind_dir) if wind_dir is not None else None

            # Apparent temperature (wind chill or heat index, fallback to actual temp)
            wind_chill_c = self._get_value(properties, "windChill", "value")
            heat_index_c = self._get_value(properties, "heatIndex", "value")
            if wind_chill_c is not None:
                self._attr_native_apparent_temperature = wind_chill_c
            elif heat_index_c is not None:
                self._attr_native_apparent_temperature = heat_index_c
            else:
                self._attr_native_apparent_temperature = self._attr_native_temperature

            self._attr_cloud_coverage = None

        super()._handle_coordinator_update()

    async def async_forecast_daily(self) -> Optional[List[Forecast]]:
        """Return the daily forecast."""
        if not self._forecast_coordinator or not self._forecast_coordinator.data:
            return None

        extended_data = self._forecast_coordinator.data.get("extended")
        if not extended_data:
            return None

        try:
            properties = extended_data.get("properties", {})
            periods = properties.get("periods", [])

            if not periods:
                return None

            # Convert NWS periods to Home Assistant forecast format
            # NWS returns alternating day and night periods
            # We pair them to get both high (day) and low (night) temperatures
            forecasts = []
            i = 0

            while i < len(periods) and len(forecasts) < 7:
                period = periods[i]

                # Find the daytime period
                if period.get("isDaytime", False):
                    day_period = period
                    # Look for the following night period for low temp
                    night_period = periods[i + 1] if i + 1 < len(periods) else None

                    i += 2  # Move past both day and night
                else:
                    # If we start with night (e.g., querying in evening), this is tonight
                    night_period = period
                    day_period = periods[i + 1] if i + 1 < len(periods) else None

                    # If there's a following day period, it's actually tomorrow
                    # So we create a forecast for "today" using tonight's low
                    if day_period and day_period.get("isDaytime", False):
                        # Parse tonight's start time to determine the calendar date
                        night_dt = self._period_start(night_period)

                        # Determine today's datetime string (set to 6 AM on tonight's calendar date)
                        if night_dt is not None:
                            today_dt = night_dt.replace(
                                hour=6, minute=0, second=0, microsecond=0
                            )
                            today_datetime = today_dt.isoformat()
                        else:
                            today_datetime = night_period.get("startTime")

                        # Only include a "today" forecast entry if tonight's calendar date
                        # matches the current local date (i.e., we are still before midnight
                        # today).  After midnight the night period belongs to yesterday.
                        is_tonight_today = (
                            night_dt is not None
                            and night_dt.date() == datetime.now(night_dt.tzinfo).date()
                        )
                        # After midnight NWS starts with an Overnight period on the same
                        # date as the day period after it, which gets that date's entry.
                        day_dt = self._period_start(day_period)
                        is_early_morning = (
                            night_dt is not None and day_dt is not None
                            and night_dt.date() == day_dt.date()
                        )

                        if is_tonight_today and not is_early_morning:
                            # Today's daytime period has passed, so NWS has no
                            # forecast high left for it.
                            forecast = Forecast(
                                datetime=today_datetime,
                                native_temperature=None,
                                native_templow=self._forecast_temperature(night_period),
                                condition=self._map_condition(
                                    night_period.get("shortForecast"),
                                    night_period.get("startTime")
                                ),
                                precipitation_probability=(
                                    self._extract_precipitation_probability(night_period)
                                ),
                                native_wind_speed=self._parse_wind_speed(
                                    night_period.get("windSpeed")
                                ),
                                wind_bearing=self._parse_wind_direction(
                                    night_period.get("windDirection")
                                ),
                            )
                            forecasts.append(forecast)
                            _LOGGER.debug(
                                "Created today forecast with low=%s (queried in evening)",
                                night_period.get("temperature")
                            )
                        else:
                            _LOGGER.debug(
                                "Skipping today forecast - night period belongs to "
                                "yesterday or to the day period after it"
                            )
                        i += 1
                        continue
                    else:
                        # No following day period, skip this night
                        i += 1
                        continue

                # Create forecast from day/night pair
                if day_period:
                    forecast = Forecast(
                        datetime=self._adjust_forecast_date(
                            day_period.get("startTime")
                        ),
                        native_temperature=self._forecast_temperature(day_period),
                        native_templow=self._forecast_temperature(night_period),
                        condition=self._map_condition(
                            day_period.get("shortForecast"),
                            day_period.get("startTime")
                        ),
                        precipitation_probability=(
                            self._extract_precipitation_probability(day_period)
                        ),
                        native_wind_speed=self._parse_wind_speed(
                            day_period.get("windSpeed")
                        ),
                        wind_bearing=self._parse_wind_direction(
                            day_period.get("windDirection")
                        ),
                    )
                    forecasts.append(forecast)

            _LOGGER.debug("Retrieved %d daily forecast periods", len(forecasts))
            return forecasts

        except Exception as e:
            _LOGGER.error("Error parsing daily forecast data: %s", e)
            return None

    async def async_forecast_hourly(self) -> Optional[List[Forecast]]:
        """Return the hourly forecast."""
        if not self._forecast_coordinator or not self._forecast_coordinator.data:
            return None

        hourly_data = self._forecast_coordinator.data.get("hourly")
        if not hourly_data:
            return None

        try:
            properties = hourly_data.get("properties", {})
            periods = properties.get("periods", [])

            if not periods:
                return None

            forecasts = []
            for period in periods[:48]:
                forecast = Forecast(
                    datetime=period.get("startTime"),
                    native_temperature=self._forecast_temperature(period),
                    condition=self._map_condition(
                        period.get("shortForecast"),
                        period.get("startTime")
                    ),
                    precipitation_probability=(
                        self._extract_precipitation_probability(period)
                    ),
                    native_wind_speed=self._parse_wind_speed(period.get("windSpeed")),
                    wind_bearing=self._parse_wind_direction(
                        period.get("windDirection")
                    ),
                )
                forecasts.append(forecast)

            _LOGGER.debug("Retrieved %d hourly forecast periods", len(forecasts))
            return forecasts

        except Exception as e:
            _LOGGER.error("Error parsing hourly forecast data: %s", e)
            return None

    @staticmethod
    def _get_value(properties: dict, *keys) -> Optional[float]:
        """Safely get a nested value from properties."""
        value = properties
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    @staticmethod
    def _forecast_temperature(period: Optional[dict]) -> Optional[float]:
        """Return a forecast period's temperature in °C, or None.

        NWS gives the forecast in °F, or in °C when asked for SI units, and says
        which in ``temperatureUnit``. The value isn't rounded: Home Assistant
        converts it to the entity's temperature unit and rounds it for display,
        so in °F it shows NWS's whole °F.
        """
        if not period:
            return None
        temperature = period.get("temperature")
        if isinstance(temperature, bool) or not isinstance(temperature, (int, float)):
            return None
        if period.get("temperatureUnit") == "C":
            return temperature
        return (temperature - 32) * 5 / 9

    @staticmethod
    def _map_condition(description: Optional[str], timestamp: Optional[str] = None) -> Optional[str]:
        """Map NOAA weather description to Home Assistant condition."""
        if not description:
            return None

        # Normalize the description
        desc_lower = description.lower()

        # Determine if it's day or night based on timestamp
        is_night = False
        if timestamp:
            try:
                dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
                # Simple heuristic: night is between 8 PM and 6 AM
                hour = dt.hour
                is_night = hour >= 20 or hour < 6
            except (ValueError, AttributeError):
                pass

        # Map conditions - order matters, check most specific first
        if "thunderstorm" in desc_lower or "t-storm" in desc_lower or "tstorm" in desc_lower:
            return "lightning-rainy"
        if "tornado" in desc_lower:
            return "exceptional"
        if "hail" in desc_lower:
            return "hail"
        if "blizzard" in desc_lower or "snow storm" in desc_lower:
            return "snowy"
        if "ice" in desc_lower or "freezing rain" in desc_lower or "sleet" in desc_lower:
            return "snowy-rainy"
        if "snow" in desc_lower or "flurries" in desc_lower:
            return "snowy"
        if "heavy rain" in desc_lower or "downpour" in desc_lower:
            return "pouring"
        if "rain" in desc_lower or "shower" in desc_lower or "drizzle" in desc_lower:
            return "rainy"
        if "fog" in desc_lower or "mist" in desc_lower:
            return "fog"
        if "overcast" in desc_lower:
            return "cloudy"
        if "partly cloudy" in desc_lower or "mostly clear" in desc_lower or "partly sunny" in desc_lower:
            return "partlycloudy"
        if "mostly sunny" in desc_lower:
            return "partlycloudy"
        # After the partly-cloudy checks, which it would otherwise swallow.
        # "Mostly Cloudy" lands here too, as in Home Assistant's own NWS
        # integration.
        if "cloudy" in desc_lower:
            return "cloudy"
        if "clear" in desc_lower or "fair" in desc_lower or "sunny" in desc_lower:
            return "clear-night" if is_night else "sunny"
        if "wind" in desc_lower and ("gust" in desc_lower or "strong" in desc_lower):
            return "windy"

        # Default to partly cloudy if we can't determine
        return "partlycloudy"

    @staticmethod
    def _extract_precipitation_probability(period: dict) -> Optional[int]:
        """Extract precipitation probability from forecast period."""
        # Extract from the probabilityOfPrecipitation field in the API response
        prob_data = period.get("probabilityOfPrecipitation")
        if prob_data and isinstance(prob_data, dict):
            value = prob_data.get("value")
            if value is not None:
                return int(value)

        # Fallback: try to parse from detailed forecast text
        detailed = period.get("detailedForecast", "")

        # Look for patterns like "Chance of precipitation is 60%"
        match = re.search(r"chance of precipitation is (\d+)%", detailed.lower())
        if match:
            return int(match.group(1))

        # Look for patterns like "60% chance"
        match = re.search(r"(\d+)%\s+chance", detailed.lower())
        if match:
            return int(match.group(1))

        return None

    @staticmethod
    def _parse_wind_speed(wind_speed_str: Optional[str]) -> Optional[float]:
        """Parse NWS's forecast wind speed, such as '5 to 10 mph', to its average in km/h."""
        if not wind_speed_str or not isinstance(wind_speed_str, str):
            return None

        # Try to extract numbers from the string
        numbers = re.findall(r'\d+', wind_speed_str)
        if numbers:
            # If range like "5 to 10", take average
            if len(numbers) >= 2:
                speed = (int(numbers[0]) + int(numbers[1])) / 2
            else:
                speed = float(numbers[0])
            # NWS gives mph, or km/h when asked for SI units.
            if "km/h" in wind_speed_str:
                return speed
            return speed * _KM_PER_MILE

        return None

    @staticmethod
    def _parse_wind_direction(direction_str: Optional[str]) -> Optional[int]:
        """Parse wind direction from cardinal direction to degrees."""
        if not direction_str:
            return None

        # Map cardinal directions to degrees
        direction_map = {
            "N": 0, "NNE": 22, "NE": 45, "ENE": 67,
            "E": 90, "ESE": 112, "SE": 135, "SSE": 157,
            "S": 180, "SSW": 202, "SW": 225, "WSW": 247,
            "W": 270, "WNW": 292, "NW": 315, "NNW": 337,
        }

        direction_upper = direction_str.upper().strip()
        return direction_map.get(direction_upper)

    @staticmethod
    def _period_start(period: Optional[dict]) -> Optional[datetime]:
        """Return when a forecast period starts, in the offset NWS gives it, or None."""
        try:
            return datetime.fromisoformat(period.get("startTime").replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            _LOGGER.debug("Could not parse forecast period startTime: %s", e)
            return None

    @staticmethod
    def _adjust_forecast_date(timestamp: Optional[str]) -> Optional[str]:
        """Adjust forecast date to use 3 AM cutoff instead of midnight.

        If a forecast period's start time is before 3 AM, adjust to previous day.
        This ensures weather days are grouped with the 3 AM cutoff convention.

        Args:
            timestamp: ISO format timestamp string from NWS API

        Returns:
            Adjusted timestamp in ISO format, or original timestamp if parsing fails
        """
        if not timestamp:
            return timestamp

        try:
            # Parse the ISO timestamp
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            # If the forecast time is before 3 AM, shift to previous day at midnight
            # This aligns with the weather day convention where the "day" extends until 3 AM
            if dt.hour < 3:
                adjusted_dt = dt.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
                return adjusted_dt.isoformat()

            return timestamp
        except (ValueError, AttributeError) as e:
            # If parsing fails, return original timestamp
            _LOGGER.debug("Failed to parse timestamp %s: %s", timestamp, e)
            return timestamp
