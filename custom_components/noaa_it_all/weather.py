"""Weather platform for NOAA Integration."""
import logging
import re
from datetime import datetime, timedelta

from homeassistant.components.weather import (
    WeatherEntity,
    WeatherEntityFeature,
    Forecast,
)
from homeassistant.const import (
    UnitOfTemperature,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfLength,
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up NOAA weather entity from config entry."""
    office_code = config_entry.data[CONF_OFFICE_CODE]
    latitude = config_entry.data.get(CONF_LATITUDE)
    longitude = config_entry.data.get(CONF_LONGITUDE)

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
    """Representation of NOAA weather data."""

    _attr_native_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_native_pressure_unit = UnitOfPressure.INHG
    _attr_native_wind_speed_unit = UnitOfSpeed.MILES_PER_HOUR
    _attr_native_visibility_unit = UnitOfLength.MILES
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

            # Temperature (C to F)
            temp_c = self._get_value(properties, "temperature", "value")
            self._attr_native_temperature = self._celsius_to_fahrenheit(temp_c)

            # Humidity
            humidity = self._get_value(properties, "relativeHumidity", "value")
            self._attr_humidity = round(humidity) if humidity is not None else None

            # Pressure (Pa to inHg)
            pressure_pa = self._get_value(properties, "barometricPressure", "value")
            if pressure_pa is not None:
                self._attr_native_pressure = round(pressure_pa * 0.00029530, 2)
            else:
                self._attr_native_pressure = None

            # Condition
            text_description = properties.get("textDescription")
            timestamp = properties.get("timestamp")
            self._attr_condition = self._map_condition(text_description, timestamp)

            # Dewpoint (C to F)
            dewpoint_c = self._get_value(properties, "dewpoint", "value")
            self._attr_native_dew_point = self._celsius_to_fahrenheit(dewpoint_c)

            # Visibility (m to mi)
            visibility_m = self._get_value(properties, "visibility", "value")
            if visibility_m is not None:
                self._attr_native_visibility = round(visibility_m * 0.000621371, 1)
            else:
                self._attr_native_visibility = None

            # Wind speed (km/h to mph)
            wind_speed_kmh = self._get_value(properties, "windSpeed", "value")
            if wind_speed_kmh is not None:
                self._attr_native_wind_speed = round(wind_speed_kmh * 0.621371, 1)
            else:
                self._attr_native_wind_speed = None

            # Wind direction
            wind_dir = self._get_value(properties, "windDirection", "value")
            self._attr_wind_bearing = round(wind_dir) if wind_dir is not None else None

            # Apparent temperature (wind chill or heat index, fallback to actual temp)
            wind_chill_c = self._get_value(properties, "windChill", "value")
            heat_index_c = self._get_value(properties, "heatIndex", "value")
            if wind_chill_c is not None:
                self._attr_native_apparent_temperature = self._celsius_to_fahrenheit(wind_chill_c)
            elif heat_index_c is not None:
                self._attr_native_apparent_temperature = self._celsius_to_fahrenheit(heat_index_c)
            else:
                self._attr_native_apparent_temperature = self._attr_native_temperature

            self._attr_cloud_coverage = None

        super()._handle_coordinator_update()

    async def async_forecast_daily(self) -> list[Forecast] | None:
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
            # Track today's high temperature for use when encountering tonight's period
            saved_today_high = None

            while i < len(periods) and len(forecasts) < 7:
                period = periods[i]

                # Find the daytime period
                if period.get("isDaytime", False):
                    day_period = period
                    # Look for the following night period for low temp
                    night_period = periods[i + 1] if i + 1 < len(periods) else None

                    # Save today's high temperature before moving forward
                    # This will be used if we encounter tonight's period later
                    saved_today_high = day_period.get("temperature")
                    _LOGGER.debug("Saved today's high temperature: %s", saved_today_high)

                    i += 2  # Move past both day and night
                else:
                    # If we start with night (e.g., querying in evening), this is tonight
                    # Use the saved high temperature from earlier today
                    night_period = period
                    day_period = periods[i + 1] if i + 1 < len(periods) else None

                    # If there's a following day period, it's actually tomorrow
                    # So we create a forecast for "today" using tonight's low
                    # and the saved high temp from earlier today
                    if day_period and day_period.get("isDaytime", False):
                        # Parse tonight's start time to determine the calendar date
                        night_dt = None
                        try:
                            night_dt = datetime.fromisoformat(
                                night_period.get("startTime").replace("Z", "+00:00")
                            )
                        except (ValueError, AttributeError) as e:
                            _LOGGER.debug("Could not parse night period startTime: %s", e)

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

                        if saved_today_high is not None or is_tonight_today:
                            # Use the saved daytime high when available; otherwise fall
                            # back to the current observed temperature.
                            high_temp = (
                                saved_today_high if saved_today_high is not None
                                else self._attr_native_temperature
                            )

                            forecast = Forecast(
                                datetime=today_datetime,
                                temperature=high_temp,
                                templow=night_period.get("temperature"),
                                condition=self._map_condition(
                                    night_period.get("shortForecast"),
                                    night_period.get("startTime")
                                ),
                                precipitation_probability=(
                                    self._extract_precipitation_probability(night_period)
                                ),
                                wind_speed=self._parse_wind_speed(
                                    night_period.get("windSpeed")
                                ),
                                wind_bearing=self._parse_wind_direction(
                                    night_period.get("windDirection")
                                ),
                            )
                            forecasts.append(forecast)
                            _LOGGER.debug(
                                "Created today forecast with high=%s, low=%s "
                                "(queried in evening)",
                                high_temp, night_period.get("temperature")
                            )
                        else:
                            _LOGGER.debug(
                                "Skipping today forecast - night period belongs to "
                                "yesterday and no saved high temperature available"
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
                        temperature=day_period.get("temperature"),
                        templow=(
                            night_period.get("temperature") if night_period else None
                        ),
                        condition=self._map_condition(
                            day_period.get("shortForecast"),
                            day_period.get("startTime")
                        ),
                        precipitation_probability=(
                            self._extract_precipitation_probability(day_period)
                        ),
                        wind_speed=self._parse_wind_speed(
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

    async def async_forecast_hourly(self) -> list[Forecast] | None:
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
                    temperature=period.get("temperature"),
                    condition=self._map_condition(
                        period.get("shortForecast"),
                        period.get("startTime")
                    ),
                    precipitation_probability=(
                        self._extract_precipitation_probability(period)
                    ),
                    wind_speed=self._parse_wind_speed(period.get("windSpeed")),
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
    def _get_value(properties: dict, *keys) -> float | None:
        """Safely get a nested value from properties."""
        value = properties
        for key in keys:
            if isinstance(value, dict):
                value = value.get(key)
            else:
                return None
        return value

    @staticmethod
    def _celsius_to_fahrenheit(celsius: float | None) -> float | None:
        """Convert Celsius to Fahrenheit."""
        if celsius is None:
            return None
        return round((celsius * 9 / 5) + 32, 1)

    @staticmethod
    def _map_condition(description: str | None, timestamp: str | None = None) -> str | None:
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
        if "cloudy" in desc_lower:
            return "cloudy"
        if "partly cloudy" in desc_lower or "mostly clear" in desc_lower or "partly sunny" in desc_lower:
            return "partlycloudy"
        if "mostly cloudy" in desc_lower or "mostly sunny" in desc_lower:
            return "partlycloudy"
        if "clear" in desc_lower or "fair" in desc_lower or "sunny" in desc_lower:
            return "clear-night" if is_night else "sunny"
        if "wind" in desc_lower and ("gust" in desc_lower or "strong" in desc_lower):
            return "windy"

        # Default to partly cloudy if we can't determine
        return "partlycloudy"

    @staticmethod
    def _extract_precipitation_probability(period: dict) -> int | None:
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
    def _parse_wind_speed(wind_speed_str: str | None) -> float | None:
        """Parse wind speed from string like '5 to 10 mph' to average value."""
        if not wind_speed_str:
            return None

        # Try to extract numbers from the string
        numbers = re.findall(r'\d+', wind_speed_str)
        if numbers:
            # If range like "5 to 10", take average
            if len(numbers) >= 2:
                return (int(numbers[0]) + int(numbers[1])) / 2
            # Single number
            return float(numbers[0])

        return None

    @staticmethod
    def _parse_wind_direction(direction_str: str | None) -> int | None:
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
    def _adjust_forecast_date(timestamp: str | None) -> str | None:
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
