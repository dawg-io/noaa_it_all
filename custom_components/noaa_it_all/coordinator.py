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
from datetime import timedelta
from email.utils import parsedate_to_datetime

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    REQUEST_TIMEOUT, USER_AGENT,
    NWS_POINTS_URL, NWS_OBSERVATIONS_URL, NWS_ALERTS_URL,
    NWS_SRF_URL, NWS_AFD_URL, NWS_RADAR_BASE_URL,
    COOPS_WATER_TEMP_URL, NDBC_REALTIME_URL,
    OFFICE_STATION_IDS,
)
from .parsers import parse_coops_water_temperature, parse_ndbc_wave_height

_LOGGER = logging.getLogger(__name__)

DEFAULT_UPDATE_INTERVAL = timedelta(minutes=10)

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
        data: dict = {}

        # --- DST ---
        try:
            async with session.get(_DST_URL, timeout=timeout) as resp:
                resp.raise_for_status()
                data["dst"] = await resp.json()
        except Exception as err:
            _LOGGER.warning("Error fetching DST data: %s", err)
            data["dst"] = None

        # --- K-index ---
        try:
            async with session.get(_KP_INDEX_URL, timeout=timeout) as resp:
                resp.raise_for_status()
                data["kp_index"] = await resp.json()
        except Exception as err:
            _LOGGER.warning("Error fetching K-index data: %s", err)
            data["kp_index"] = None

        # --- SWPC alerts ---
        try:
            async with session.get(_SPACE_ALERTS_URL, timeout=timeout) as resp:
                resp.raise_for_status()
                data["space_alerts"] = await resp.json()
        except Exception as err:
            _LOGGER.warning("Error fetching space weather alerts: %s", err)
            data["space_alerts"] = None

        if all(v is None for v in data.values()):
            raise UpdateFailed("All space weather API requests failed")

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
        data: dict = {}

        try:
            async with session.get(
                _HURRICANE_ALERTS_URL, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                data["alerts"] = await resp.json()
        except Exception as err:
            _LOGGER.warning("Error fetching hurricane alerts: %s", err)
            data["alerts"] = None

        try:
            async with session.get(
                _CURRENT_STORMS_URL, timeout=timeout
            ) as resp:
                resp.raise_for_status()
                data["storms"] = await resp.json()
        except Exception as err:
            _LOGGER.warning("Error fetching current storms: %s", err)
            data["storms"] = None

        if all(v is None for v in data.values()):
            raise UpdateFailed("All hurricane API requests failed")

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
        latitude: float | None,
        longitude: float | None,
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
        self.station_id: str | None = OFFICE_STATION_IDS.get(office_code)
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
            _LOGGER.error(
                "Error resolving station for lat=%s, lon=%s: %s",
                self.latitude, self.longitude, err,
            )
            self._station_fetched = True


# -------------------------------------------------------------------
# Surf Zone Forecast (office-specific)
# -------------------------------------------------------------------

class SurfCoordinator(DataUpdateCoordinator):
    """Fetch SRF text, CO-OPS water temperature and NDBC wave height."""

    def __init__(
        self,
        hass: HomeAssistant,
        office_code: str,
        tide_station: str | None = None,
        buoy_station: str | None = None,
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
        self._forecast_url: str | None = None
        self._hourly_forecast_url: str | None = None
        self._urls_fetched: bool = False

    async def _async_update_data(self) -> dict:
        session = async_get_clientsession(self.hass)
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)

        if not self._urls_fetched:
            await self._resolve_forecast_urls(session, timeout)

        data: dict = {}

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
                data["hourly"] = None
        else:
            data["hourly"] = None

        if all(v is None for v in data.values()):
            raise UpdateFailed("All forecast API requests failed")

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
            _LOGGER.error(
                "Error resolving forecast URLs for lat=%s, lon=%s: %s",
                self.latitude, self.longitude, err,
            )
            self._urls_fetched = True


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
        self._gridpoint_url: str | None = None
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
            _LOGGER.error(
                "Error resolving gridpoint URL for lat=%s, lon=%s: %s",
                self.latitude, self.longitude, err,
            )
            self._grid_fetched = True


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
