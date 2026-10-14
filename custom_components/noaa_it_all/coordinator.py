"""DataUpdateCoordinators for NOAA Integration.

Each coordinator fetches data from one or more related NOAA/NWS API
endpoints and makes it available to all entities that share the same
data domain.  This eliminates redundant per-entity polling and
centralises caching, error handling and rate-limit control.

See https://developers.home-assistant.io/docs/integration_fetching_data/
"""

import logging
import re
import aiohttp
from functools import partial
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DEFAULT_SCAN_INTERVAL,
    REQUEST_TIMEOUT, USER_AGENT,
    NWS_POINTS_URL, NWS_OBSERVATIONS_URL, NWS_ALERTS_URL,
    NWS_SRF_URL, NWS_AFD_URL, NWS_RADAR_BASE_URL, NWS_NSH_URL, NSH_MAX_AGE_HOURS,
    COOPS_WATER_TEMP_URL, NDBC_REALTIME_URL,
    OFFICE_STATION_IDS, OBSERVATION_STATION_CANDIDATES,
    OBSERVATION_WINDOW_HOURS, OBSERVATION_LIMIT, OBSERVATION_KEEP_MINUTES,
    METEOR_SCAN_INTERVAL, METEOR_UPCOMING_COUNT,
    ECLIPSE_SCAN_INTERVAL, ECLIPSE_APPROACH_SCAN_INTERVAL, ECLIPSE_ACTIVE_SCAN_INTERVAL,
    ECLIPSE_APPROACH_WINDOW_HOURS, ECLIPSE_UPCOMING_COUNT, ECLIPSE_MAX_CATALOG_SCAN,
    ECLIPSE_INCLUDE_PENUMBRAL,
)
from .meteor import build_meteor_forecast
from .meteor_catalog import METEOR_SHOWERS
from .eclipse import build_eclipse_forecast
from .eclipse_catalog import SOLAR_ECLIPSES
from .parsers import (
    parse_coops_water_temperature, parse_ndbc_wave_height,
    parse_nearshore_forecast, product_is_stale,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)


# aiohttp's ClientResponseError ends its message with the request URL. For
# the location lookups that URL holds the coordinates, and the status and
# reason already say what went wrong.
_URL_SUFFIX = re.compile(r",\s*url=.*$", re.DOTALL)


def _describe(err: Exception) -> str:
    """Render an exception for a log line or an UpdateFailed message.

    Several aiohttp errors have an empty ``str()``, which would otherwise
    reduce the reason to nothing at all. The request URL is left out.
    """
    text = _URL_SUFFIX.sub("", str(err))
    return f"{type(err).__name__}: {text}" if text else type(err).__name__


# Space weather API endpoints
_DST_URL = "https://services.swpc.noaa.gov/json/geospace/geospace_dst_1_hour.json"
_KP_INDEX_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
_SPACE_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"
# SWPC's 3-day forecast of the planetary K-index, in 3-hour periods.
_KP_FORECAST_URL = "https://services.swpc.noaa.gov/products/noaa-planetary-k-index-forecast.json"

# Hurricane API endpoints
_HURRICANE_ALERTS_URL = (
    "https://api.weather.gov/alerts?event=Hurricane%20Warning,Hurricane%20Watch,"
    "Tropical%20Storm%20Warning,Tropical%20Storm%20Watch&active=true"
)
_CURRENT_STORMS_URL = "https://www.nhc.noaa.gov/CurrentStorms.json"


# -------------------------------------------------------------------
# Space Weather
# -------------------------------------------------------------------

class SpaceWeatherCoordinator(DataUpdateCoordinator):
    """Fetch geomagnetic DST, planetary K-index and its forecast, and SWPC alerts."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Space Weather",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        headers = {"User-Agent": USER_AGENT}
        data: dict = {}
        errors: list[str] = []

        endpoints = (
            ("dst", "DST", _DST_URL),
            ("kp_index", "K-index", _KP_INDEX_URL),
            ("space_alerts", "space weather alerts", _SPACE_ALERTS_URL),
            ("kp_forecast", "K-index forecast", _KP_FORECAST_URL),
        )
        for key, label, url in endpoints:
            try:
                async with session.get(
                    url, headers=headers, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    data[key] = await resp.json()
            except Exception as err:
                _LOGGER.warning("Error fetching %s data: %s", label, err)
                errors.append(f"{label} ({_describe(err)})")
                data[key] = None

        if all(v is None for v in data.values()):
            raise UpdateFailed(
                "All space weather API requests failed: " + "; ".join(errors)
            )

        return data


# -------------------------------------------------------------------
# Hurricane
# -------------------------------------------------------------------

class HurricaneCoordinator(DataUpdateCoordinator):
    """Fetch hurricane alerts and current storms."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Hurricanes",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        headers = {"User-Agent": USER_AGENT}
        data: dict = {}
        errors: list[str] = []

        endpoints = (
            ("alerts", "hurricane alerts", _HURRICANE_ALERTS_URL),
            ("storms", "current storms", _CURRENT_STORMS_URL),
        )
        for key, label, url in endpoints:
            try:
                async with session.get(
                    url, headers=headers, timeout=timeout
                ) as resp:
                    resp.raise_for_status()
                    data[key] = await resp.json()
            except Exception as err:
                _LOGGER.warning("Error fetching %s: %s", label, err)
                errors.append(f"{label} ({_describe(err)})")
                data[key] = None

        if all(v is None for v in data.values()):
            raise UpdateFailed(
                "All hurricane API requests failed: " + "; ".join(errors)
            )

        return data


# -------------------------------------------------------------------
# NWS Alerts (location-specific)
# -------------------------------------------------------------------

class NWSAlertsCoordinator(DataUpdateCoordinator):
    """Fetch NWS active alerts for a specific lat/lon."""

    def __init__(
        self, hass: HomeAssistant, latitude: float, longitude: float
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA NWS Alerts",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.latitude = latitude
        self.longitude = longitude

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        url = NWS_ALERTS_URL.format(lat=self.latitude, lon=self.longitude)

        try:
            async with session.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
            return {"features": data.get("features", [])}
        except Exception as err:
            raise UpdateFailed(f"Error fetching NWS alerts: {_describe(err)}") from err


# -------------------------------------------------------------------
# Weather Observations (location-specific)
# -------------------------------------------------------------------

# Fields every observation should have. When the newest leaves one empty, NWS
# just did not publish it that time, so the newest earlier observation that
# has it stands in.
_CARRIED_OBSERVATION_FIELDS = (
    "temperature", "dewpoint", "relativeHumidity", "windSpeed",
    "barometricPressure", "visibility", "textDescription",
)
# Fields that go with another, so they come from the observation it came from.
# Wind direction is empty for calm or variable wind, and wind chill and heat
# index whenever they do not apply: there, empty is the reading. Carried on
# their own, an old bearing or heat index would show as current.
_PAIRED_OBSERVATION_FIELDS = {
    "windDirection": "windSpeed",
    "windChill": "temperature",
    "heatIndex": "temperature",
}


def _observation_time(properties: dict) -> Optional[datetime]:
    """Return when an observation was made, or None if it does not say."""
    stamp = properties.get("timestamp")
    if not isinstance(stamp, str):
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _has_reading(value) -> bool:
    """Return True if an observation field holds a reading. Zero counts."""
    if isinstance(value, dict):
        return value.get("value") is not None
    return isinstance(value, str) and value.strip() != ""


def merge_observations(features, since: datetime) -> Optional[tuple[dict, dict]]:
    """Return the newest observation since ``since`` with its gaps filled.

    Returns ``(properties, field_times)``: the newest observation's properties,
    with each carried field that it left empty taken from the newest earlier
    observation that has it, each paired field taken from wherever its partner
    came from, and the time each of those fields was observed. Returns None if
    no observation is that recent.
    """
    recent = []
    for feature in features if isinstance(features, list) else []:
        properties = feature.get("properties") if isinstance(feature, dict) else None
        if not isinstance(properties, dict):
            continue
        when = _observation_time(properties)
        if when is not None and when >= since:
            recent.append((when, properties))
    if not recent:
        return None
    recent.sort(key=lambda item: item[0], reverse=True)

    newest = recent[0][1]
    merged = dict(newest)
    field_times = {}
    sources = {}
    for field in _CARRIED_OBSERVATION_FIELDS:
        for _, properties in recent:
            if _has_reading(properties.get(field)):
                merged[field] = properties[field]
                field_times[field] = properties.get("timestamp")
                sources[field] = properties
                break
    for field, partner in _PAIRED_OBSERVATION_FIELDS.items():
        source = sources.get(partner, newest)
        if field in source:
            merged[field] = source[field]
        if _has_reading(source.get(field)):
            field_times[field] = source.get("timestamp")
    return merged, field_times


class ObservationsCoordinator(DataUpdateCoordinator):
    """Resolve the nearest stations and fetch their recent observations.

    Only the nearest station used to be kept, so when it stopped reporting
    every refresh failed -- and a restart resolved the same station again --
    while the next station along was reporting normally. Now the nearest few
    are kept and the first with a recent observation is used. The nearest is
    still tried first on every refresh, so it takes over again once it recovers.

    Each refresh reads the last OBSERVATION_WINDOW_HOURS of observations, so a
    field NWS left empty in the newest one is filled from an earlier one rather
    than reading as unknown. When every station fails, the last observation is
    kept for up to OBSERVATION_KEEP_MINUTES rather than every observation
    entity going unavailable until the next refresh.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        latitude: Optional[float],
        longitude: Optional[float],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Observations",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code
        self.latitude = latitude
        self.longitude = longitude
        # The station in use: the office default until the lookup resolves
        # the nearest, then whichever station last answered. Compared against
        # to log a station change once rather than on every refresh.
        self.station_id: Optional[str] = OFFICE_STATION_IDS.get(office_code)
        # Nearest first, filled in by _resolve_station.
        self._stations: list[str] = []
        # The last successful refresh's data and when it happened, kept while
        # every station fails; and whether that is happening now, so the
        # outage is logged once and its end once.
        self._last_good: Optional[dict] = None
        self._last_success: Optional[datetime] = None
        self._failing = False
        # If latitude/longitude are provided, always attempt to resolve the nearest
        # station via the NWS Points API on first update, using OFFICE_STATION_IDS
        # only as a fallback if resolution fails.
        if self.latitude is not None and self.longitude is not None:
            self._station_fetched = False
        else:
            self._station_fetched = self.station_id is not None

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        # Resolve station from lat/lon on first run
        if (
            not self._station_fetched
            and self.latitude is not None
            and self.longitude is not None
        ):
            await self._resolve_station(session, timeout)

        stations = self._stations or (
            [self.station_id] if self.station_id else []
        )
        if not stations:
            raise UpdateFailed(
                f"No observation station for office {self.office_code}"
            )

        now = datetime.now(timezone.utc)
        # Rounded down to ten minutes, so successive refreshes ask for the same
        # URL and NWS can answer from its cache.
        since = now - timedelta(hours=OBSERVATION_WINDOW_HOURS)
        since = since.replace(minute=since.minute - since.minute % 10, second=0, microsecond=0)
        params = {
            "start": since.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "limit": OBSERVATION_LIMIT,
        }
        errors: list[str] = []
        last_err: Optional[Exception] = None
        for station in stations:
            url = NWS_OBSERVATIONS_URL.format(station=station)
            try:
                async with session.get(
                    url,
                    params=params,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                # Inside the try: a body that is not a JSON object is a
                # failed station too, not an escaped AttributeError.
                features = data.get("features")
            except Exception as err:
                _LOGGER.debug(
                    "Error fetching observations from station %s: %s",
                    station, err,
                )
                errors.append(f"{station} ({_describe(err)})")
                last_err = err
                continue

            merged = merge_observations(features, since)
            if merged is None:
                # Answering, but with nothing recent: it has stopped reporting.
                errors.append(
                    f"{station} (no observation in the last "
                    f"{OBSERVATION_WINDOW_HOURS} hours)"
                )
                continue
            properties, field_times = merged

            # Log only when the station changes, not on every refresh.
            if station != self.station_id:
                if errors:
                    _LOGGER.warning(
                        "Nearer observation stations are not reporting "
                        "(%s); using %s instead",
                        "; ".join(errors), station,
                    )
                else:
                    _LOGGER.info(
                        "Observation station %s is answering again", station
                    )
                self.station_id = station
            if self._failing:
                _LOGGER.info("Observations are updating again, from %s", station)
                self._failing = False
            self._last_success = now
            self._last_good = {
                "properties": properties,
                "field_times": field_times,
                "station_id": station,
            }
            return self._last_good

        return self._keep_last_observation(now, errors, last_err)

    def _keep_last_observation(
        self, now: datetime, errors: list[str], cause: Optional[Exception]
    ) -> dict:
        """Return the last observation while it is recent enough, else fail.

        Every station failing used to make every observation entity
        unavailable until the next refresh, leaving a gap in their history
        for what is usually a brief NWS outage.
        """
        message = "Error fetching observations: " + "; ".join(errors)
        keep = timedelta(minutes=OBSERVATION_KEEP_MINUTES)
        if (
            self._last_good is None
            or self._last_success is None
            or now - self._last_success > keep
        ):
            # Home Assistant logs this failure and the recovery from here.
            self._failing = False
            raise UpdateFailed(message) from cause
        if self._failing:
            _LOGGER.debug("%s", message)
        else:
            _LOGGER.warning(
                "%s. Showing the observation from %s until a station answers, "
                "for up to %d minutes",
                message,
                self._last_good["properties"].get("timestamp"),
                OBSERVATION_KEEP_MINUTES,
            )
            self._failing = True
        return self._last_good

    async def _resolve_station(self, session, timeout) -> None:
        """Fetch the observation stations nearest lat/lon."""
        try:
            points_url = NWS_POINTS_URL.format(
                lat=self.latitude, lon=self.longitude
            )
            async with session.get(
                points_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            stations_url = data.get("properties", {}).get("observationStations")
            if not stations_url:
                _LOGGER.error("The NWS Points API gave no observation stations URL")
                _LOGGER.debug("That lookup was for lat=%s, lon=%s", self.latitude, self.longitude)
                self._station_fetched = True
                return

            async with session.get(
                stations_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                stations_data = await resp.json()

            # The API lists stations nearest first. A malformed entry is
            # skipped rather than allowed to discard the valid ones.
            stations: list[str] = []
            for feature in stations_data.get("features") or []:
                properties = (
                    feature.get("properties") if isinstance(feature, dict) else None
                )
                if not isinstance(properties, dict):
                    continue
                sid = properties.get("stationIdentifier")
                sid = sid.strip() if isinstance(sid, str) else ""
                if sid and sid not in stations:
                    stations.append(sid)
                if len(stations) >= OBSERVATION_STATION_CANDIDATES:
                    break
            if stations:
                self._stations = stations
                self.station_id = stations[0]
                _LOGGER.info(
                    "Found observation stations %s for lat=%s, lon=%s",
                    ", ".join(stations), self.latitude, self.longitude,
                )
            self._station_fetched = True
        except Exception as err:
            # Not latched on failure -- see the note in
            # ForecastCoordinator._resolve_forecast_urls. A transient failure
            # here would otherwise leave station_id None for good.
            _LOGGER.warning(
                "Could not resolve the observation stations, will retry on the "
                "next update: %s", _describe(err),
            )
            _LOGGER.debug("That lookup was for lat=%s, lon=%s", self.latitude, self.longitude)


# -------------------------------------------------------------------
# Surf Zone Forecast (office-specific)
# -------------------------------------------------------------------

class SurfCoordinator(DataUpdateCoordinator):
    """Fetch SRF text, CO-OPS water temperature and NDBC wave height."""

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        tide_station: Optional[str] = None,
        buoy_station: Optional[str] = None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Surf",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code
        self.tide_station = tide_station
        self.buoy_station = buoy_station

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        result: dict = {}

        # 1. SRF text (rip current risk)
        srf_url = NWS_SRF_URL.format(office=self.office_code)
        try:
            async with session.get(
                srf_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                result["forecast_text"] = (await resp.text()).lower()
                result["source_url"] = srf_url
        except Exception as err:
            # Leave ``forecast_text`` out rather than empty: empty text parses
            # as Low risk, which would report a safe beach during a hazard.
            # No UpdateFailed either, so water temp and waves still update.
            _LOGGER.warning("Error fetching SRF forecast: %s", err)
            result["source_url"] = srf_url

        # 2. CO-OPS water temperature
        if self.tide_station:
            coops_url = COOPS_WATER_TEMP_URL.format(station=self.tide_station)
            try:
                async with session.get(
                    coops_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json(content_type=None)
                temp = parse_coops_water_temperature(data)
                if temp is not None:
                    result["water_temp_f"] = temp
                    result["water_temp_source"] = coops_url
            except Exception as err:
                _LOGGER.warning("Error fetching CO-OPS water temp: %s", err)

        # 3. NDBC wave height
        if self.buoy_station:
            ndbc_url = NDBC_REALTIME_URL.format(station=self.buoy_station)
            try:
                async with session.get(
                    ndbc_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    text = await resp.text()
                height = parse_ndbc_wave_height(text)
                if height is not None:
                    result["wave_height_ft"] = height
                    result["wave_height_source"] = ndbc_url
            except Exception as err:
                _LOGGER.warning("Error fetching NDBC wave height: %s", err)

        if (
            not result.get("forecast_text")
            and "water_temp_f" not in result
            and "wave_height_ft" not in result
        ):
            _LOGGER.debug("All surf data sources returned no usable data")

        return result


class MarineForecastCoordinator(DataUpdateCoordinator):
    """Fetch the NWS Nearshore Marine Forecast (NSH) and pick out one zone.

    The NSH product is issued per forecast office and covers several marine
    zones in one text. The api.weather.gov zone-forecast endpoint has no data
    for marine zones, so the product text itself is parsed.
    """

    def __init__(self, hass: HomeAssistant, office_code: str, marine_zone: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Marine Forecast",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code
        self.marine_zone = marine_zone

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        url = NWS_NSH_URL.format(office=self.office_code)

        try:
            async with session.get(
                url,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                product = await resp.json(content_type=None)
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching nearshore marine forecast ({_describe(err)})"
            ) from err

        product = product or {}
        issued = product.get("issuanceTime")
        if product_is_stale(issued, datetime.now(timezone.utc), NSH_MAX_AGE_HOURS):
            # The office has stopped issuing; NWS still serves its last one.
            raise UpdateFailed(
                f"The latest nearshore marine forecast from {self.office_code} "
                f"was issued at {issued}, over {NSH_MAX_AGE_HOURS} hours ago"
            )
        text = product.get("productText") or ""
        forecast = parse_nearshore_forecast(text, self.marine_zone)
        if forecast is None:
            raise UpdateFailed(
                f"Zone {self.marine_zone} was not found in the latest "
                f"nearshore marine forecast from {self.office_code}"
            )

        return {
            "forecast": forecast,
            "product_id": product.get("id"),
            "issuance_time": product.get("issuanceTime"),
            "source_url": url,
        }


# -------------------------------------------------------------------
# Forecasts (location-specific)
# -------------------------------------------------------------------

class ForecastCoordinator(DataUpdateCoordinator):
    """Resolve forecast URLs from Points API and fetch extended + hourly."""

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        latitude: float,
        longitude: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Forecasts",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code
        self.latitude = latitude
        self.longitude = longitude
        self._forecast_url: Optional[str] = None
        self._hourly_forecast_url: Optional[str] = None
        self._urls_fetched: bool = False
        self._resolve_error: Optional[str] = None

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        if not self._urls_fetched:
            self._resolve_error = None
            await self._resolve_forecast_urls(session, timeout)

        data: dict = {}
        errors: list[str] = []
        if self._resolve_error:
            errors.append(f"Points API lookup ({self._resolve_error})")

        if self._forecast_url:
            try:
                async with session.get(
                    self._forecast_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    data["extended"] = await resp.json()
            except Exception as err:
                _LOGGER.warning("Error fetching extended forecast: %s", _describe(err))
                errors.append(f"extended forecast ({_describe(err)})")
                data["extended"] = None
        else:
            data["extended"] = None

        if self._hourly_forecast_url:
            try:
                async with session.get(
                    self._hourly_forecast_url,
                    headers={"User-Agent": USER_AGENT},
                    timeout=timeout,
                ) as resp:
                    resp.raise_for_status()
                    data["hourly"] = await resp.json()
            except Exception as err:
                _LOGGER.warning("Error fetching hourly forecast: %s", _describe(err))
                errors.append(f"hourly forecast ({_describe(err)})")
                data["hourly"] = None
        else:
            data["hourly"] = None

        if all(v is None for v in data.values()):
            raise UpdateFailed(
                "All forecast API requests failed: "
                + ("; ".join(errors) if errors else "no forecast URL resolved")
            )

        return data

    async def _resolve_forecast_urls(self, session, timeout) -> None:
        """Fetch forecast URLs from the NWS Points API."""
        try:
            points_url = NWS_POINTS_URL.format(
                lat=self.latitude, lon=self.longitude
            )
            async with session.get(
                points_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            props = data.get("properties", {})
            self._forecast_url = props.get("forecast")
            self._hourly_forecast_url = props.get("forecastHourly")

            if self._forecast_url:
                _LOGGER.info("Found forecast URL: %s", self._forecast_url)
            if self._hourly_forecast_url:
                _LOGGER.info(
                    "Found hourly forecast URL: %s",
                    self._hourly_forecast_url,
                )
            self._urls_fetched = True
        except Exception as err:
            # Deliberately leave ``_urls_fetched`` False: latching it here
            # would retire the Points API lookup permanently, so a single
            # transient failure would leave both forecast URLs None and every
            # later refresh would raise "All forecast API requests failed"
            # until Home Assistant restarted. The coordinator only runs every
            # 10 minutes, so simply retrying next cycle is the right backoff.
            self._resolve_error = _describe(err)
            _LOGGER.warning(
                "Could not resolve forecast URLs, will retry on the next "
                "update: %s", _describe(err),
            )
            _LOGGER.debug("That lookup was for lat=%s, lon=%s", self.latitude, self.longitude)


# -------------------------------------------------------------------
# Cloud Cover (location-specific, gridpoint data)
# -------------------------------------------------------------------

class CloudCoverCoordinator(DataUpdateCoordinator):
    """Resolve gridpoint URL and fetch sky-cover data."""

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        latitude: float,
        longitude: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Cloud Cover",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code
        self.latitude = latitude
        self.longitude = longitude
        self._gridpoint_url: Optional[str] = None
        self._grid_fetched: bool = False

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        if not self._grid_fetched:
            await self._resolve_gridpoint_url(session, timeout)

        if not self._gridpoint_url:
            raise UpdateFailed(
                "No gridpoint URL resolved for the cloud cover location"
            )

        try:
            async with session.get(
                self._gridpoint_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
            return {"properties": data.get("properties", {})}
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching cloud cover: {_describe(err)}"
            ) from err

    async def _resolve_gridpoint_url(self, session, timeout) -> None:
        """Fetch gridpoint URL from the NWS Points API."""
        try:
            points_url = NWS_POINTS_URL.format(
                lat=self.latitude, lon=self.longitude
            )
            async with session.get(
                points_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()

            self._gridpoint_url = (
                data.get("properties", {}).get("forecastGridData")
            )
            if self._gridpoint_url:
                _LOGGER.info(
                    "Found gridpoint URL for lat=%s, lon=%s: %s",
                    self.latitude, self.longitude, self._gridpoint_url,
                )
            self._grid_fetched = True
        except Exception as err:
            # Not latched on failure -- see the note in
            # ForecastCoordinator._resolve_forecast_urls.
            _LOGGER.warning(
                "Could not resolve the gridpoint URL, will retry on the next "
                "update: %s", _describe(err),
            )
            _LOGGER.debug("That lookup was for lat=%s, lon=%s", self.latitude, self.longitude)


# -------------------------------------------------------------------
# Radar Timestamp (office-specific)
# -------------------------------------------------------------------

class RadarTimestampCoordinator(DataUpdateCoordinator):
    """Fetch Last-Modified header from radar image endpoint."""

    def __init__(
        self, hass: HomeAssistant, office_code: str, radar_site: str
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Radar Timestamp",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code
        self.radar_site = radar_site

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        radar_url = NWS_RADAR_BASE_URL.format(radar=self.radar_site)

        try:
            async with session.head(
                radar_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                last_modified = resp.headers.get("Last-Modified")

            if last_modified:
                timestamp = parsedate_to_datetime(last_modified)
                return {
                    "last_modified": last_modified,
                    "timestamp": timestamp,
                    "radar_site": self.radar_site,
                    "radar_url": radar_url,
                }
            return {
                "last_modified": None,
                "timestamp": None,
                "radar_site": self.radar_site,
                "radar_url": radar_url,
            }
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching radar timestamp: {_describe(err)}"
            ) from err


# -------------------------------------------------------------------
# Forecast Discussion (office-specific)
# -------------------------------------------------------------------

class ForecastDiscussionCoordinator(DataUpdateCoordinator):
    """Fetch Area Forecast Discussion (AFD) text for a specific office."""

    def __init__(self, hass: HomeAssistant, office_code: str) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Forecast Discussion",
            update_interval=DEFAULT_UPDATE_INTERVAL,
        )
        self.office_code = office_code

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
        url = NWS_AFD_URL.format(office=self.office_code)

        try:
            async with session.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                html_content = await resp.text()

            # Extract text from <pre> tag
            pre_match = re.search(
                r"<pre[^>]*>(.*?)</pre>",
                html_content,
                re.DOTALL | re.IGNORECASE,
            )
            if pre_match:
                text = pre_match.group(1).strip()
                text = text.replace("&nbsp;", " ")
                text = text.replace("&amp;", "&")
                text = text.replace("&lt;", "<")
                text = text.replace("&gt;", ">")
                return {"discussion_text": text}

            return {"discussion_text": None}
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching forecast discussion: {_describe(err)}"
            ) from err


# -------------------------------------------------------------------
# Locally computed forecasts (no network)
# -------------------------------------------------------------------

class _ObserverTimezone:
    """Resolves and caches the observer's timezone for a locally computed forecast.

    Held by composition rather than inherited. The two coordinators that compute rather than
    fetch both need to hand a ``tzinfo`` to a pure model that pre-formats local time strings, and
    both need the same two precautions -- but the test-suite substitutes a ``MagicMock`` for
    ``DataUpdateCoordinator``, and mixing a plain class into that raises a metaclass conflict at
    import time. A collaborator sidesteps the question entirely.

    The zone is read from ``hass.config.time_zone`` rather than through
    ``homeassistant.util.dt`` so this module keeps working under those same mocks, which stub
    ``homeassistant`` but not ``homeassistant.util``.

    The result is cached against the name it came from, because building a ``ZoneInfo`` reads the
    tz database from disk the first time a given key is used -- which without the cache happens
    on the event loop on every single refresh -- and because an unresolvable name would otherwise
    log the same warning every refresh, forever.
    """

    def __init__(self) -> None:
        """Initialize an empty cache."""
        self._name: Optional[str] = None
        self._zone = timezone.utc

    def resolve(self, hass) -> object:
        """Return the observer's timezone, falling back to UTC."""
        name = getattr(hass.config, "time_zone", None)
        if not isinstance(name, str):
            return timezone.utc
        if name == self._name:
            return self._zone

        try:
            resolved = ZoneInfo(name)
        except (ZoneInfoNotFoundError, ValueError):
            _LOGGER.warning("Unknown Home Assistant time zone %r; using UTC", name)
            resolved = timezone.utc

        self._name, self._zone = name, resolved
        return resolved


# -------------------------------------------------------------------
# Meteor Showers (location-specific)
# -------------------------------------------------------------------

class MeteorShowerCoordinator(DataUpdateCoordinator):
    """Compute the meteor shower viewing forecast for one observer.

    Unlike every other coordinator here, this one performs **no network I/O at all**. Meteor
    showers do not need a feed: Earth crosses the same debris streams at the same solar longitude
    every year, so the bundled catalog in ``meteor_catalog.py`` plus the positional astronomy in
    ``astro.py`` is enough to derive the whole forecast locally. NOAA and every other agency
    publish shower calendars as documents, not APIs, precisely because there is nothing to
    observe in real time.

    The computation is a few thousand trigonometric evaluations — well under 10 ms — so it runs
    inline rather than in an executor.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        latitude: float,
        longitude: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Meteor Showers",
            update_interval=timedelta(minutes=METEOR_SCAN_INTERVAL),
        )
        self.office_code = office_code
        self.latitude = latitude
        self.longitude = longitude
        self._timezone = _ObserverTimezone()

    async def _async_update_data(self) -> dict:
        if self.latitude is None or self.longitude is None:
            raise UpdateFailed("Meteor shower forecast requires a latitude and longitude")

        try:
            return build_meteor_forecast(
                datetime.now(timezone.utc),
                self.latitude,
                self.longitude,
                self._timezone.resolve(self.hass),
                METEOR_SHOWERS,
                upcoming_count=METEOR_UPCOMING_COUNT,
            )
        except Exception as err:
            raise UpdateFailed(
                f"Error computing meteor shower forecast: {err}"
            ) from err


# -------------------------------------------------------------------
# Eclipses (location-specific)
# -------------------------------------------------------------------

class EclipseCoordinator(DataUpdateCoordinator):
    """Compute the solar and lunar eclipse forecast for one observer.

    Like ``MeteorShowerCoordinator`` this performs **no network I/O**: lunar eclipses are derived
    from first principles and solar ones from the bundled Besselian elements in
    ``eclipse_catalog.py``. NASA publishes eclipse predictions as documents rather than as a feed,
    and there is nothing to observe in real time anyway -- the geometry was settled centuries ago.

    Unlike every other coordinator here, this one **changes its own update interval**. The others
    watch conditions that drift over hours; this one watches an event whose interesting part can
    last two minutes. Polling hourly is right when the next eclipse is three years away and
    hopeless when first contact is in ten. So the interval is re-derived on every refresh from
    how close the next eclipse is, which is the only way for a "go outside now" flag to be any
    use -- Home Assistant re-reads entity state when a coordinator publishes, so an entity that
    consulted the clock itself would simply never change.

    A full refresh measures 75-100 ms depending on the observer -- solving local circumstances
    for up to two dozen catalogued eclipses, most of which turn out to miss. That is an order of
    magnitude more than the meteor forecast next door, whose docstring gives "well under 10 ms"
    as its reason for running inline, so this one takes the other branch of the same rule and
    hands the work to an executor. It matters most in exactly the situation the tightened
    interval creates: a minute-by-minute poll while an eclipse is under way.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        latitude: float,
        longitude: float,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="NOAA Eclipses",
            update_interval=timedelta(minutes=ECLIPSE_SCAN_INTERVAL),
        )
        self.office_code = office_code
        self.latitude = latitude
        self.longitude = longitude
        self._timezone = _ObserverTimezone()
        self._warned_exhausted = False

    def _elevation(self) -> float:
        """Return the configured elevation in metres, or sea level if it is not usable.

        Worth about a second of contact time, so a missing or nonsensical value is not worth
        failing over -- but it is free to use when Home Assistant has one.
        """
        elevation = getattr(self.hass.config, "elevation", None)
        if isinstance(elevation, (int, float)) and not isinstance(elevation, bool):
            return float(elevation)
        return 0.0

    @staticmethod
    def _interval_for(forecast: dict) -> timedelta:
        """Return how soon to recompute, given what the forecast says is coming."""
        if forecast.get("current"):
            return timedelta(minutes=ECLIPSE_ACTIVE_SCAN_INTERVAL)
        upcoming = forecast.get("next")
        if upcoming and 0.0 <= upcoming.get("hours_until", 1e9) <= ECLIPSE_APPROACH_WINDOW_HOURS:
            return timedelta(minutes=ECLIPSE_APPROACH_SCAN_INTERVAL)
        return timedelta(minutes=ECLIPSE_SCAN_INTERVAL)

    async def _async_update_data(self) -> dict:
        if self.latitude is None or self.longitude is None:
            raise UpdateFailed("Eclipse forecast requires a latitude and longitude")

        # Resolved on the event loop, before handing off: the timezone cache exists precisely
        # because building a ZoneInfo reads the tz database from disk, and it reads hass.config.
        local_timezone = self._timezone.resolve(self.hass)
        elevation = self._elevation()

        try:
            forecast = await self.hass.async_add_executor_job(
                partial(
                    build_eclipse_forecast,
                    datetime.now(timezone.utc),
                    self.latitude,
                    self.longitude,
                    local_timezone,
                    SOLAR_ECLIPSES,
                    upcoming_count=ECLIPSE_UPCOMING_COUNT,
                    elevation_m=elevation,
                    include_penumbral=ECLIPSE_INCLUDE_PENUMBRAL,
                    max_catalog_scan=ECLIPSE_MAX_CATALOG_SCAN,
                )
            )
        except Exception as err:
            raise UpdateFailed(f"Error computing eclipse forecast: {err}") from err

        if forecast.get("catalog_exhausted") and not self._warned_exhausted:
            # Lunar eclipses keep working forever; only the solar half has a horizon. Saying so
            # once is more useful than silently becoming a lunar-only sensor -- and it has to be
            # *once*, latched: this runs every hour, so an unlatched warning would be tens of
            # thousands of identical log lines a year for a condition nobody can act on quickly.
            self._warned_exhausted = True
            _LOGGER.warning(
                "The bundled solar eclipse catalog ends in %s and is now exhausted; lunar "
                "eclipses are unaffected. Regenerate it with scripts/build_eclipse_catalog.py",
                forecast.get("catalog_last_year"),
            )

        self.update_interval = self._interval_for(forecast)
        return forecast
