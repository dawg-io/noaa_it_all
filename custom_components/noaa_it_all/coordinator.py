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
    NWS_SRF_URL, NWS_AFD_URL, NWS_RADAR_BASE_URL,
    COOPS_WATER_TEMP_URL, NDBC_REALTIME_URL,
    OFFICE_STATION_IDS,
    METEOR_SCAN_INTERVAL, METEOR_UPCOMING_COUNT,
    ECLIPSE_SCAN_INTERVAL, ECLIPSE_APPROACH_SCAN_INTERVAL, ECLIPSE_ACTIVE_SCAN_INTERVAL,
    ECLIPSE_APPROACH_WINDOW_HOURS, ECLIPSE_UPCOMING_COUNT, ECLIPSE_MAX_CATALOG_SCAN,
    ECLIPSE_INCLUDE_PENUMBRAL,
)
from .meteor import build_meteor_forecast
from .meteor_catalog import METEOR_SHOWERS
from .eclipse import build_eclipse_forecast
from .eclipse_catalog import SOLAR_ECLIPSES
from .parsers import parse_coops_water_temperature, parse_ndbc_wave_height

_LOGGER = logging.getLogger(__name__)

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=DEFAULT_SCAN_INTERVAL)


def _describe(err: Exception) -> str:
    """Render an exception for an UpdateFailed message.

    Several aiohttp errors have an empty ``str()``, which would otherwise
    reduce the reason to nothing at all.
    """
    text = str(err)
    return f"{type(err).__name__}: {text}" if text else type(err).__name__


# Space weather API endpoints
_DST_URL = "https://services.swpc.noaa.gov/json/geospace/geospace_dst_1_hour.json"
_KP_INDEX_URL = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
_SPACE_ALERTS_URL = "https://services.swpc.noaa.gov/products/alerts.json"

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
    """Fetch geomagnetic DST, planetary K-index, and SWPC alerts."""

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
            raise UpdateFailed(f"Error fetching NWS alerts: {err}") from err


# -------------------------------------------------------------------
# Weather Observations (location-specific)
# -------------------------------------------------------------------

class ObservationsCoordinator(DataUpdateCoordinator):
    """Resolve nearest station and fetch latest observations."""

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
        self.station_id: Optional[str] = OFFICE_STATION_IDS.get(office_code)
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

        if not self.station_id:
            raise UpdateFailed(
                f"No observation station for office {self.office_code}"
            )

        url = NWS_OBSERVATIONS_URL.format(station=self.station_id)
        try:
            async with session.get(
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                data = await resp.json()
            return {
                "properties": data.get("properties", {}),
                "station_id": self.station_id,
            }
        except Exception as err:
            raise UpdateFailed(
                f"Error fetching observations: {err}"
            ) from err

    async def _resolve_station(self, session, timeout) -> None:
        """Fetch the nearest observation station from lat/lon."""
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
                _LOGGER.error(
                    "No observation stations URL for lat=%s, lon=%s",
                    self.latitude, self.longitude,
                )
                self._station_fetched = True
                return

            async with session.get(
                stations_url,
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            ) as resp:
                resp.raise_for_status()
                stations_data = await resp.json()

            stations_list = stations_data.get("features", [])
            if stations_list:
                sid = (
                    stations_list[0]
                    .get("properties", {})
                    .get("stationIdentifier")
                )
                if sid and isinstance(sid, str) and sid.strip():
                    self.station_id = sid.strip()
                    _LOGGER.info(
                        "Found station %s for lat=%s, lon=%s",
                        self.station_id, self.latitude, self.longitude,
                    )
            self._station_fetched = True
        except Exception as err:
            # Not latched on failure -- see the note in
            # ForecastCoordinator._resolve_forecast_urls. A transient failure
            # here would otherwise leave station_id None for good.
            _LOGGER.warning(
                "Could not resolve observation station for lat=%s, lon=%s, "
                "will retry on the next update: %s",
                self.latitude, self.longitude, err,
            )


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
            _LOGGER.warning("Error fetching SRF forecast: %s", err)
            result["forecast_text"] = ""
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
                _LOGGER.warning("Error fetching extended forecast: %s", err)
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
                _LOGGER.warning("Error fetching hourly forecast: %s", err)
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
                "Could not resolve forecast URLs for lat=%s, lon=%s, will "
                "retry on the next update: %s",
                self.latitude, self.longitude, err,
            )


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
                f"No gridpoint URL for lat={self.latitude}, lon={self.longitude}"
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
                f"Error fetching cloud cover: {err}"
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
                "Could not resolve gridpoint URL for lat=%s, lon=%s, will "
                "retry on the next update: %s",
                self.latitude, self.longitude, err,
            )


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
                f"Error fetching radar timestamp: {err}"
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
                f"Error fetching forecast discussion: {err}"
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
