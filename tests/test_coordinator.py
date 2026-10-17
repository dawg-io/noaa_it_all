"""Tests for coordinator.py fetch behaviour using mocked HA modules.

``coordinator.py`` had no behavioural coverage at all, which is how the
resolve-latch bug fixed alongside these tests survived: a single transient
failure of the NWS Points API permanently retired the lookup, so every later
refresh raised ``All forecast API requests failed`` until Home Assistant was
restarted.
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_coordinator = MagicMock()
_aiohttp = MagicMock()


class _UpdateFailed(Exception):
    """Stand-in for homeassistant...update_coordinator.UpdateFailed."""


class _DataUpdateCoordinator:
    """Enough of DataUpdateCoordinator for the subclasses to construct."""

    def __init__(self, hass, logger, name=None, update_interval=None):
        self.hass = hass
        self.logger = logger
        self.name = name
        self.update_interval = update_interval


_ha_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator
_ha_coordinator.UpdateFailed = _UpdateFailed

# ``aiohttp`` is mocked wholesale, so its exception classes are MagicMocks and
# cannot appear in an ``except`` clause. The coordinators only catch bare
# Exception, but ClientTimeout still has to be callable.
_aiohttp.ClientTimeout = lambda **kwargs: kwargs
# Raised by a response's json() when its body doesn't arrive whole.
_aiohttp.ClientPayloadError = type("ClientPayloadError", (Exception,), {})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    # Importing noaa_it_all.coordinator imports the package __init__ first,
    # so its Home Assistant imports need stubbing too.
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "aiohttp": _aiohttp,
    # parsers.py uses 3.10+ union syntax and meteor pulls in heavy deps.
    "noaa_it_all.parsers": MagicMock(),
    "noaa_it_all.meteor": MagicMock(),
    "noaa_it_all.meteor_catalog": MagicMock(),
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


HASS = MagicMock()


def _run(coro):
    """Run a coroutine on a private loop, leaving the ambient one intact."""
    previous = None
    try:
        previous = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        pass
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(previous)


# ---------------------------------------------------------------------------
# Fake aiohttp session
# ---------------------------------------------------------------------------
class _FakeResponse:
    def __init__(self, payload=None, raise_for_status=None):
        self._payload = payload if payload is not None else {}
        self._raise = raise_for_status

    def raise_for_status(self):
        if self._raise is not None:
            raise self._raise

    async def json(self):
        return self._payload


class _FakeGet:
    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Serves a canned result per URL substring, or one result for everything."""

    def __init__(self, default=None, by_url=None):
        self._default = default
        self._by_url = by_url or {}
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for fragment, result in self._by_url.items():
            if fragment in url:
                return _FakeGet(result)
        return _FakeGet(self._default)


def _with_session(session):
    return patch(
        "noaa_it_all.coordinator.async_get_clientsession", return_value=session
    )


class TestForecastResolveRetry(unittest.TestCase):
    """A failed Points API lookup must not disable forecasts permanently.

    ``_resolve_forecast_urls`` used to set ``_urls_fetched = True`` in its
    except branch as well as on success. One transient failure therefore left
    both forecast URLs None with no way to ever retry, and every subsequent
    refresh raised ``All forecast API requests failed`` -- forever, or until
    Home Assistant restarted. That is the recurring error this fixes.
    """

    def _make(self):
        from noaa_it_all.coordinator import ForecastCoordinator
        return ForecastCoordinator(HASS, "ILM", 34.2, -77.9)

    POINTS = {
        "properties": {
            "forecast": "https://api.weather.gov/gridpoints/ILM/1,2/forecast",
            "forecastHourly": (
                "https://api.weather.gov/gridpoints/ILM/1,2/forecast/hourly"
            ),
        }
    }

    def test_resolution_failure_does_not_latch(self):
        coordinator = self._make()
        session = _FakeSession(default=OSError("Network unreachable"))

        with _with_session(session):
            with self.assertRaises(Exception):
                _run(coordinator._async_update_data())

        self.assertFalse(
            coordinator._urls_fetched,
            "a failed lookup must stay retryable, not latch shut",
        )

    def test_next_refresh_recovers_after_a_failed_lookup(self):
        """The whole point: the coordinator heals on the next cycle."""
        coordinator = self._make()

        failing = _FakeSession(default=OSError("Network unreachable"))
        with _with_session(failing):
            with self.assertRaises(Exception):
                _run(coordinator._async_update_data())

        working = _FakeSession(
            by_url={
                "/points/": _FakeResponse(self.POINTS),
                "/forecast/hourly": _FakeResponse({"properties": {"periods": [2]}}),
                "/forecast": _FakeResponse({"properties": {"periods": [1]}}),
            }
        )
        with _with_session(working):
            data = _run(coordinator._async_update_data())

        self.assertTrue(coordinator._urls_fetched)
        self.assertIsNotNone(data["extended"])
        self.assertIsNotNone(data["hourly"])

    def test_successful_resolution_latches(self):
        """A resolved lookup is not repeated on every refresh."""
        coordinator = self._make()
        session = _FakeSession(
            by_url={
                "/points/": _FakeResponse(self.POINTS),
                "/forecast/hourly": _FakeResponse({"properties": {"periods": [2]}}),
                "/forecast": _FakeResponse({"properties": {"periods": [1]}}),
            }
        )
        with _with_session(session):
            _run(coordinator._async_update_data())
            _run(coordinator._async_update_data())

        points_calls = [c for c in session.calls if "/points/" in c[0]]
        self.assertEqual(len(points_calls), 1)

    def test_failure_message_names_the_cause(self):
        """The bare old message gave no clue why every request failed."""
        coordinator = self._make()
        session = _FakeSession(default=OSError("Network unreachable"))

        with _with_session(session):
            with self.assertRaises(Exception) as ctx:
                _run(coordinator._async_update_data())

        message = str(ctx.exception)
        self.assertIn("All forecast API requests failed", message)
        self.assertIn("Points API lookup", message)
        self.assertIn("Network unreachable", message)


class TestResolveRetryAcrossCoordinators(unittest.TestCase):
    """The same latch existed in the station and gridpoint lookups."""

    def test_observation_station_lookup_does_not_latch(self):
        from noaa_it_all.coordinator import ObservationsCoordinator
        coordinator = ObservationsCoordinator(HASS, "ZZZ", 34.2, -77.9)
        coordinator.station_id = None
        coordinator._station_fetched = False
        session = _FakeSession(default=OSError("Network unreachable"))

        with _with_session(session):
            _run(coordinator._resolve_station(session, {}))

        self.assertFalse(coordinator._station_fetched)

    def test_gridpoint_lookup_does_not_latch(self):
        from noaa_it_all.coordinator import CloudCoverCoordinator
        coordinator = CloudCoverCoordinator(HASS, "ILM", 34.2, -77.9)
        session = _FakeSession(default=OSError("Network unreachable"))

        with _with_session(session):
            _run(coordinator._resolve_gridpoint_url(session, {}))

        self.assertFalse(coordinator._grid_fetched)


def _observations(*readings, minutes_ago=10, step=20):
    """A station's observations response: newest first, ``step`` minutes apart."""
    now = datetime.now(timezone.utc)
    features = []
    for i, properties in enumerate(readings):
        stamp = now - timedelta(minutes=minutes_ago + i * step)
        features.append({"properties": {"timestamp": stamp.isoformat(), **properties}})
    return {"features": features}


class TestObservationStationFailover(unittest.TestCase):
    """A silent nearest station must not leave observations unavailable.

    Only the nearest station used to be kept, so when it stopped reporting
    every refresh failed with a 404 for as long as the outage lasted -- a
    restart resolved the same station again -- while the next station along
    was reporting normally.
    """

    STATIONS_URL = "https://api.weather.gov/gridpoints/ILM/1,2/stations"
    POINTS = {"properties": {"observationStations": STATIONS_URL}}

    @staticmethod
    def _observation():
        # Built per test: dated at import, it could age out of the window.
        return _observations({"temperature": {"value": 20.0}})

    def _make(self, latitude=34.2, longitude=-77.9):
        from noaa_it_all.coordinator import ObservationsCoordinator
        return ObservationsCoordinator(HASS, "ILM", latitude, longitude)

    def _session(self, latest, station_ids=("KAAA", "KBBB", "KCCC"), features=None):
        """Serve a station list, plus one result per station's latest obs."""
        if features is None:
            features = [
                {"properties": {"stationIdentifier": sid}}
                for sid in station_ids
            ]
        stations = {"features": features}
        by_url = {
            "/gridpoints/ILM/1,2/stations": _FakeResponse(stations),
            "/points/": _FakeResponse(self.POINTS),
        }
        for sid, result in latest.items():
            by_url[f"/stations/{sid}/observations"] = result
        return _FakeSession(default=OSError("unexpected URL"), by_url=by_url)

    def _refresh(self, coordinator, session):
        with _with_session(session):
            return _run(coordinator._async_update_data())

    @staticmethod
    def _not_found():
        return _FakeResponse(raise_for_status=Exception("404, message='Not Found'"))

    @staticmethod
    def _latest_urls(session):
        return [url for url, _ in session.calls if url.endswith("/observations")]

    def test_falls_back_to_the_next_station_in_the_same_refresh(self):
        coordinator = self._make()
        session = self._session({
            "KAAA": self._not_found(),
            "KBBB": _FakeResponse(self._observation()),
        })

        data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KBBB")
        self.assertEqual(data["properties"]["temperature"], {"value": 20.0})
        self.assertEqual(coordinator.station_id, "KBBB")
        self.assertEqual(
            [url.split("/")[4] for url in self._latest_urls(session)],
            ["KAAA", "KBBB"],
        )

    def test_returns_to_the_nearest_station_once_it_recovers(self):
        coordinator = self._make()
        self._refresh(coordinator, self._session({
            "KAAA": self._not_found(),
            "KBBB": _FakeResponse(self._observation()),
        }))

        recovered = self._session({"KAAA": _FakeResponse(self._observation())})
        data = self._refresh(coordinator, recovered)

        self.assertEqual(data["station_id"], "KAAA")
        self.assertEqual(coordinator.station_id, "KAAA")
        # The station list is kept; the lookup is not repeated.
        self.assertFalse(any("/points/" in url for url, _ in recovered.calls))

    def test_all_stations_failing_names_each_one_and_why(self):
        coordinator = self._make()
        session = self._session({
            "KAAA": self._not_found(),
            # str() of a timeout is empty; the reason must still be named.
            "KBBB": asyncio.TimeoutError(),
            "KCCC": OSError("Connection reset"),
        })

        with self.assertRaises(_UpdateFailed) as ctx:
            self._refresh(coordinator, session)

        message = str(ctx.exception)
        self.assertIn("Error fetching observations", message)
        self.assertIn("KAAA (Exception: 404, message='Not Found')", message)
        self.assertIn("KBBB (TimeoutError)", message)
        self.assertIn("KCCC (OSError: Connection reset)", message)
        # The underlying error is chained, so its traceback is not lost.
        self.assertIsInstance(ctx.exception.__cause__, OSError)

    def test_keeps_only_the_nearest_valid_stations(self):
        coordinator = self._make()
        session = self._session(
            {"KAAA": _FakeResponse(self._observation())},
            features=[
                {"properties": {"stationIdentifier": "KAAA"}},
                # Malformed entries are skipped, not fatal to the lookup.
                {"properties": None},
                None,
                "KZZZ",
                {"properties": {"stationIdentifier": "  "}},
                {"properties": {"stationIdentifier": " KAAA "}},
                {"properties": {"stationIdentifier": "KBBB"}},
                {"properties": {"stationIdentifier": "KCCC"}},
                {"properties": {"stationIdentifier": "KDDD"}},
            ],
        )

        with patch("noaa_it_all.coordinator.OBSERVATION_STATION_CANDIDATES", 3):
            self._refresh(coordinator, session)

        self.assertEqual(coordinator._stations, ["KAAA", "KBBB", "KCCC"])
        self.assertTrue(coordinator._station_fetched)

    def test_null_station_list_settles_on_the_office_station(self):
        coordinator = self._make()
        session = self._session({"KILM": _FakeResponse(self._observation())})
        session._by_url["/gridpoints/ILM/1,2/stations"] = _FakeResponse(
            {"features": None}
        )

        data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KILM")
        # Latched like an empty list, so the lookup is not repeated forever.
        self.assertTrue(coordinator._station_fetched)

    def test_a_body_that_is_not_an_object_falls_back(self):
        coordinator = self._make()
        session = self._session({
            "KAAA": _FakeResponse(["not", "an", "object"]),
            "KBBB": _FakeResponse(self._observation()),
        })

        data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KBBB")

    def test_a_station_change_is_logged_once(self):
        coordinator = self._make()
        down = {
            "KAAA": self._not_found(),
            "KBBB": _FakeResponse(self._observation()),
        }

        with self.assertLogs("noaa_it_all.coordinator", level="INFO") as logs:
            self._refresh(coordinator, self._session(down))
            self._refresh(coordinator, self._session(down))
            self._refresh(
                coordinator,
                self._session({"KAAA": _FakeResponse(self._observation())}),
            )

        warnings = [r for r in logs.records if r.levelname == "WARNING"]
        recovered = [r for r in logs.records if "answering again" in r.getMessage()]
        self.assertEqual(len(warnings), 1)
        self.assertIn("using KBBB instead", warnings[0].getMessage())
        self.assertEqual(len(recovered), 1)
        self.assertIn("KAAA", recovered[0].getMessage())

    def test_office_station_is_used_without_coordinates(self):
        coordinator = self._make(latitude=None, longitude=None)
        session = self._session({"KILM": _FakeResponse(self._observation())})

        data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KILM")
        self.assertEqual(
            [url for url, _ in session.calls],
            ["https://api.weather.gov/stations/KILM/observations"],
        )
        params = session.calls[0][1]["params"]
        self.assertTrue(params["start"].endswith("Z"))
        self.assertIn("limit", params)

    def test_office_station_is_used_when_the_lookup_fails(self):
        coordinator = self._make()
        session = self._session({"KILM": _FakeResponse(self._observation())})
        session._by_url["/points/"] = OSError("Network unreachable")

        data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KILM")
        self.assertFalse(coordinator._station_fetched)


class TestObservationGaps(unittest.TestCase):
    """A missing reading or a failed refresh must not blank the observations.

    The latest observation alone was used, so a field NWS left empty in it
    read as unknown, and a refresh where every station failed made every
    observation entity unavailable for ten minutes. Both left gaps in history.
    """

    STATIONS_URL = "https://api.weather.gov/gridpoints/ILM/1,2/stations"
    POINTS = {"properties": {"observationStations": STATIONS_URL}}

    def _make(self):
        from noaa_it_all.coordinator import ObservationsCoordinator
        return ObservationsCoordinator(HASS, "ILM", 34.2, -77.9)

    def _session(self, by_station):
        by_url = {
            "/gridpoints/ILM/1,2/stations": _FakeResponse({"features": [
                {"properties": {"stationIdentifier": sid}} for sid in ("KAAA", "KBBB")
            ]}),
            "/points/": _FakeResponse(self.POINTS),
        }
        for sid, result in by_station.items():
            by_url[f"/stations/{sid}/observations"] = result
        return _FakeSession(default=OSError("unexpected URL"), by_url=by_url)

    def _refresh(self, coordinator, session):
        with _with_session(session):
            return _run(coordinator._async_update_data())

    def _down(self):
        return self._session({
            "KAAA": OSError("Connection reset"),
            "KBBB": asyncio.TimeoutError(),
        })

    def test_missing_field_is_taken_from_the_previous_observation(self):
        coordinator = self._make()
        response = _observations(
            {"temperature": {"value": 29.0}, "relativeHumidity": {"value": None}},
            {"temperature": {"value": 28.0}, "relativeHumidity": {"value": 52.0}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        properties = data["properties"]
        self.assertEqual(properties["temperature"]["value"], 29.0)
        self.assertEqual(properties["relativeHumidity"]["value"], 52.0)
        newest, older = (f["properties"]["timestamp"] for f in response["features"])
        self.assertEqual(properties["timestamp"], newest)
        self.assertEqual(data["field_times"]["relativeHumidity"], older)
        self.assertEqual(data["field_times"]["temperature"], newest)

    def test_calm_wind_is_a_reading_not_a_gap(self):
        coordinator = self._make()
        response = _observations(
            {"windSpeed": {"value": 0}},
            {"windSpeed": {"value": 9.3}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        self.assertEqual(data["properties"]["windSpeed"]["value"], 0)

    def test_heat_index_and_wind_chill_are_not_carried_forward(self):
        # Their null means "does not apply now", not "missing".
        coordinator = self._make()
        response = _observations(
            {"temperature": {"value": 24.0}, "heatIndex": {"value": None}, "windChill": {"value": None}},
            {"temperature": {"value": 30.0}, "heatIndex": {"value": 33.0}, "windChill": {"value": 5.0}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        self.assertIsNone(data["properties"]["heatIndex"]["value"])
        self.assertIsNone(data["properties"]["windChill"]["value"])

    def test_variable_wind_keeps_no_direction(self):
        # NWS leaves the direction empty for variable wind but still gives a
        # speed. That empty direction is the reading, not a gap.
        coordinator = self._make()
        response = _observations(
            {"windSpeed": {"value": 5.6}, "windDirection": {"value": None}},
            {"windSpeed": {"value": 9.3}, "windDirection": {"value": 270}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        self.assertEqual(data["properties"]["windSpeed"]["value"], 5.6)
        self.assertIsNone(data["properties"]["windDirection"]["value"])
        self.assertNotIn("windDirection", data["field_times"])

    def test_missing_wind_takes_speed_and_direction_together(self):
        coordinator = self._make()
        response = _observations(
            {"windSpeed": {"value": None}, "windDirection": {"value": None}},
            {"windSpeed": {"value": 9.3}, "windDirection": {"value": 270}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        older = response["features"][1]["properties"]["timestamp"]
        self.assertEqual(data["properties"]["windSpeed"]["value"], 9.3)
        self.assertEqual(data["properties"]["windDirection"]["value"], 270)
        self.assertEqual(data["field_times"]["windDirection"], older)

    def test_wind_chill_and_heat_index_come_with_a_carried_temperature(self):
        # NWS works them out from the temperature, so an observation without a
        # temperature has neither. They come from where the temperature does.
        coordinator = self._make()
        response = _observations(
            {"temperature": {"value": None}, "windChill": {"value": None}, "heatIndex": {"value": None}},
            {"temperature": {"value": 0.0}, "windChill": {"value": -7.0}, "heatIndex": {"value": None}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        older = response["features"][1]["properties"]["timestamp"]
        self.assertEqual(data["properties"]["temperature"]["value"], 0.0)
        self.assertEqual(data["properties"]["windChill"]["value"], -7.0)
        self.assertEqual(data["field_times"]["windChill"], older)
        self.assertIsNone(data["properties"]["heatIndex"]["value"])

    def test_request_start_is_rounded_so_nws_can_cache_it(self):
        coordinator = self._make()
        session = self._session({"KAAA": _FakeResponse(_observations({"temperature": {"value": 20.0}}))})
        self._refresh(coordinator, session)

        start = next(kw["params"]["start"] for url, kw in session.calls if url.endswith("/observations"))
        when = datetime.strptime(start, "%Y-%m-%dT%H:%M:%SZ")
        self.assertEqual((when.minute % 10, when.second), (0, 0))

    def test_empty_sky_description_is_taken_from_the_previous_observation(self):
        coordinator = self._make()
        response = _observations({"textDescription": ""}, {"textDescription": "Mostly Clear"})
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        self.assertEqual(data["properties"]["textDescription"], "Mostly Clear")

    def test_field_missing_from_every_observation_stays_missing(self):
        coordinator = self._make()
        response = _observations(
            {"temperature": {"value": 29.0}, "dewpoint": {"value": None}},
            {"temperature": {"value": 28.0}, "dewpoint": {"value": None}},
        )
        data = self._refresh(coordinator, self._session({"KAAA": _FakeResponse(response)}))

        self.assertIsNone(data["properties"]["dewpoint"]["value"])
        self.assertNotIn("dewpoint", data["field_times"])

    def test_station_with_nothing_recent_falls_back_to_the_next(self):
        coordinator = self._make()
        session = self._session({
            "KAAA": _FakeResponse({"features": []}),
            "KBBB": _FakeResponse(_observations({"temperature": {"value": 20.0}})),
        })
        with self.assertLogs("noaa_it_all.coordinator", level="WARNING") as logs:
            data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KBBB")
        self.assertIn("KAAA (no observation in the last 2 hours)", logs.output[0])

    def test_observations_older_than_the_window_are_ignored(self):
        coordinator = self._make()
        session = self._session({
            "KAAA": _FakeResponse(_observations({"temperature": {"value": 20.0}}, minutes_ago=180)),
            "KBBB": _FakeResponse(_observations({"temperature": {"value": 21.0}})),
        })
        data = self._refresh(coordinator, session)

        self.assertEqual(data["station_id"], "KBBB")
        self.assertEqual(data["properties"]["temperature"]["value"], 21.0)

    def test_failed_refresh_keeps_the_last_observation(self):
        coordinator = self._make()
        good = self._refresh(coordinator, self._session({
            "KAAA": _FakeResponse(_observations({"temperature": {"value": 20.0}})),
        }))

        with self.assertLogs("noaa_it_all.coordinator", level="WARNING") as logs:
            kept = self._refresh(coordinator, self._down())
            kept_again = self._refresh(coordinator, self._down())

        self.assertEqual(kept, good)
        self.assertEqual(kept_again, good)
        # One warning for the outage, naming each station and why.
        self.assertEqual(len(logs.records), 1)
        self.assertIn("KAAA (OSError: Connection reset)", logs.output[0])
        self.assertIn("KBBB (TimeoutError)", logs.output[0])

    def test_last_observation_is_kept_for_at_most_an_hour(self):
        coordinator = self._make()
        self._refresh(coordinator, self._session({
            "KAAA": _FakeResponse(_observations({"temperature": {"value": 20.0}})),
        }))
        coordinator._last_success -= timedelta(minutes=61)

        with self.assertRaises(_UpdateFailed) as ctx:
            self._refresh(coordinator, self._down())

        self.assertIn("Error fetching observations", str(ctx.exception))

    def test_recovery_after_a_failed_refresh_is_logged(self):
        coordinator = self._make()
        good = self._session({
            "KAAA": _FakeResponse(_observations({"temperature": {"value": 20.0}})),
        })
        self._refresh(coordinator, good)
        with self.assertLogs("noaa_it_all.coordinator", level="WARNING"):
            self._refresh(coordinator, self._down())

        with self.assertLogs("noaa_it_all.coordinator", level="INFO") as logs:
            data = self._refresh(coordinator, good)

        self.assertEqual(data["properties"]["temperature"]["value"], 20.0)
        self.assertTrue(any("updating again" in r.getMessage() for r in logs.records))


class TestUserAgentIsAlwaysSent(unittest.TestCase):
    """Every NOAA request must identify the integration.

    The space weather and hurricane coordinators were the only ones that did
    not send one -- and one of the hurricane endpoints is api.weather.gov,
    which requires it.
    """

    def _assert_user_agent(self, coordinator, expected_calls):
        from noaa_it_all.const import USER_AGENT
        session = _FakeSession(default=_FakeResponse({"ok": True}))
        with _with_session(session):
            _run(coordinator._async_update_data())

        self.assertEqual(len(session.calls), expected_calls)
        for url, kwargs in session.calls:
            with self.subTest(url=url):
                self.assertEqual(
                    kwargs.get("headers", {}).get("User-Agent"), USER_AGENT
                )

    def test_space_weather_sends_user_agent(self):
        from noaa_it_all.coordinator import SpaceWeatherCoordinator
        self._assert_user_agent(SpaceWeatherCoordinator(HASS), 4)

    def test_hurricane_sends_user_agent(self):
        from noaa_it_all.coordinator import HurricaneCoordinator
        self._assert_user_agent(HurricaneCoordinator(HASS), 2)


class _BadJSONResponse(_FakeResponse):
    """A response whose body doesn't parse, as SWPC served twice on 2026-10-14."""

    async def json(self):
        raise ValueError("unexpected content after document: line 1 column 4904 (char 4903)")


class _EmptyResponse(_FakeResponse):
    """A response with an empty body, for which aiohttp's json() gives None."""

    async def json(self):
        return None


class _CutOffResponse(_FakeResponse):
    """A response whose body stops part way."""

    async def json(self):
        raise _aiohttp.ClientPayloadError("Response payload is not completed")


class _ResultsInTurn(_FakeSession):
    """Serves, for a URL containing a fragment, one result per call in turn."""

    def __init__(self, by_turn, default):
        super().__init__(default=default)
        self._by_turn = {fragment: list(results) for fragment, results in by_turn.items()}
        self.events = []

    def get(self, url, **kwargs):
        self.events.append(("get", url))
        for fragment, results in self._by_turn.items():
            if fragment in url:
                self.calls.append((url, kwargs))
                return _FakeGet(results.pop(0))
        return super().get(url, **kwargs)


class _InFlightSession(_FakeSession):
    """Counts how many requests are open at once."""

    def __init__(self, default):
        super().__init__(default=default)
        self.open = self.most_open = 0

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        session, result = self, self._default

        class _Get:
            async def __aenter__(self):
                session.open += 1
                session.most_open = max(session.most_open, session.open)
                await asyncio.sleep(0)
                return result

            async def __aexit__(self, *exc_info):
                session.open -= 1
                return False

        return _Get()


DST, KP_FORECAST = "geospace_dst", "k-index-forecast"
GOOD = _FakeResponse([{"ok": True}])


class TestSpaceWeatherFeeds(unittest.TestCase):
    """#86: the four SWPC feeds are fetched together, and a body that isn't JSON is fetched again."""

    def _update(self, session):
        from noaa_it_all.coordinator import SpaceWeatherCoordinator
        with _with_session(session), patch("noaa_it_all.coordinator._BAD_JSON_RETRY_DELAY", 0):
            return _run(SpaceWeatherCoordinator(HASS)._async_update_data())

    def _gets(self, session, fragment):
        return sum(fragment in url for url, _ in session.calls)

    def test_the_feeds_are_fetched_together(self):
        """One after another, a slow SWPC made the first refresh take up to four timeouts."""
        session = _InFlightSession(GOOD)
        data = self._update(session)
        self.assertEqual(session.most_open, 4)
        self.assertEqual(set(data), {"dst", "kp_index", "space_alerts", "kp_forecast"})

    def test_a_body_that_does_not_parse_is_fetched_once_more(self):
        session = _ResultsInTurn({DST: [_BadJSONResponse(), _FakeResponse([{"dst": -5}])]}, GOOD)
        data = self._update(session)
        self.assertEqual(data["dst"], [{"dst": -5}])
        self.assertEqual(self._gets(session, DST), 2)

    def test_an_empty_or_cut_off_body_is_fetched_once_more(self):
        for bad in (_EmptyResponse(), _CutOffResponse()):
            with self.subTest(type(bad).__name__):
                session = _ResultsInTurn({DST: [bad, _FakeResponse([{"dst": -5}])]}, GOOD)
                self.assertEqual(self._update(session)["dst"], [{"dst": -5}])

    def test_two_feeds_that_do_not_parse_in_one_refresh(self):
        """As on 2026-10-14, when Dst and the K-index forecast both came back bad."""
        session = _ResultsInTurn({
            DST: [_BadJSONResponse(), _FakeResponse([{"dst": -5}])],
            KP_FORECAST: [_BadJSONResponse(), _FakeResponse([{"kp": 3.0}])],
        }, GOOD)
        data = self._update(session)
        self.assertEqual((data["dst"], data["kp_forecast"]), ([{"dst": -5}], [{"kp": 3.0}]))

    def test_the_second_try_waits_and_asks_for_a_fresh_copy(self):
        from noaa_it_all.coordinator import SpaceWeatherCoordinator, _BAD_JSON_RETRY_DELAY
        session = _ResultsInTurn({DST: [_BadJSONResponse(), _FakeResponse([{"dst": -5}])]}, GOOD)

        async def wait(seconds):
            session.events.append(("wait", seconds))

        with _with_session(session), patch("noaa_it_all.coordinator.asyncio.sleep", side_effect=wait):
            _run(SpaceWeatherCoordinator(HASS)._async_update_data())
        dst_events = [event for event in session.events if event[0] == "wait" or DST in event[1]]
        self.assertEqual([kind for kind, _ in dst_events], ["get", "wait", "get"])
        self.assertEqual(dst_events[1][1], _BAD_JSON_RETRY_DELAY)
        (_, first), (_, second) = [call for call in session.calls if DST in call[0]]
        self.assertNotIn("Cache-Control", first["headers"])
        self.assertEqual(second["headers"]["Cache-Control"], "no-cache")

    def test_a_retry_does_not_hold_up_the_other_feeds(self):
        """While the bad feed waits to try again, the other three are fetched."""
        from noaa_it_all.coordinator import SpaceWeatherCoordinator
        session = _ResultsInTurn({DST: [_BadJSONResponse(), _FakeResponse([{"dst": -5}])]}, GOOD)
        requested_before_the_wait = []
        real_sleep = asyncio.sleep

        async def wait(seconds):
            await real_sleep(0)
            requested_before_the_wait.extend(url for kind, url in session.events if kind == "get")

        with _with_session(session), patch("noaa_it_all.coordinator.asyncio.sleep", side_effect=wait):
            _run(SpaceWeatherCoordinator(HASS)._async_update_data())
        self.assertEqual(len(set(requested_before_the_wait)), 4)

    def test_a_body_that_still_does_not_parse_reads_unknown(self):
        session = _ResultsInTurn({DST: [_BadJSONResponse(), _BadJSONResponse()]}, GOOD)
        with self.assertLogs("noaa_it_all.coordinator", "WARNING") as logs:
            data = self._update(session)
        self.assertIsNone(data["dst"])
        self.assertEqual(data["kp_index"], [{"ok": True}])
        self.assertIn("Error fetching DST data: ValueError: unexpected content after document", logs.output[0])

    def test_all_four_still_failing_names_each_cause(self):
        from noaa_it_all.coordinator import SpaceWeatherCoordinator
        session = _ResultsInTurn({"swpc": [_BadJSONResponse()] * 8}, GOOD)
        with _with_session(session), patch("noaa_it_all.coordinator._BAD_JSON_RETRY_DELAY", 0), \
                self.assertRaises(Exception) as failed:
            _run(SpaceWeatherCoordinator(HASS)._async_update_data())
        message = str(failed.exception)
        self.assertIn("All space weather API requests failed", message)
        for label in ("DST", "K-index", "space weather alerts", "K-index forecast"):
            self.assertIn(f"{label} (ValueError: unexpected content after document", message)

    def test_other_failures_are_not_fetched_again(self):
        """A connection error, or one that is also a ValueError, such as a certificate that fails."""
        import ssl
        for error in (OSError("Temporary failure in name resolution"),
                      ssl.SSLCertVerificationError("certificate verify failed")):
            with self.subTest(type(error).__name__):
                session = _ResultsInTurn({DST: [error]}, GOOD)
                self.assertIsNone(self._update(session)["dst"])
                self.assertEqual(self._gets(session, DST), 1)

    def test_a_failure_without_a_message_still_names_its_cause(self):
        session = _ResultsInTurn({DST: [asyncio.TimeoutError()]}, GOOD)
        with self.assertLogs("noaa_it_all.coordinator", "WARNING") as logs:
            self._update(session)
        self.assertIn("Error fetching DST data: TimeoutError", logs.output[0])


class TestFailureMessagesNameTheCause(unittest.TestCase):
    """``All X API requests failed`` on its own is not actionable."""

    def _failure_message(self, coordinator):
        session = _FakeSession(default=OSError("Temporary failure in name resolution"))
        with _with_session(session):
            with self.assertRaises(Exception) as ctx:
                _run(coordinator._async_update_data())
        return str(ctx.exception)

    def test_space_weather(self):
        from noaa_it_all.coordinator import SpaceWeatherCoordinator
        message = self._failure_message(SpaceWeatherCoordinator(HASS))
        self.assertIn("All space weather API requests failed", message)
        self.assertIn("Temporary failure in name resolution", message)
        for label in ("DST", "K-index", "space weather alerts", "K-index forecast"):
            self.assertIn(label, message)

    def test_hurricane(self):
        from noaa_it_all.coordinator import HurricaneCoordinator
        message = self._failure_message(HurricaneCoordinator(HASS))
        self.assertIn("All hurricane API requests failed", message)
        self.assertIn("Temporary failure in name resolution", message)
        for label in ("hurricane alerts", "current storms"):
            self.assertIn(label, message)

    def test_partial_failure_still_returns_data(self):
        """One dead endpoint must not fail the whole coordinator."""
        from noaa_it_all.coordinator import HurricaneCoordinator
        session = _FakeSession(
            by_url={
                "api.weather.gov": OSError("boom"),
                "nhc.noaa.gov": _FakeResponse({"activeStorms": []}),
            }
        )
        with _with_session(session):
            data = _run(HurricaneCoordinator(HASS)._async_update_data())

        self.assertIsNone(data["alerts"])
        self.assertIsNotNone(data["storms"])

    def test_the_remaining_coordinators_name_an_unnamed_failure(self):
        """#43: a timeout's empty message used to leave the reason blank."""
        from noaa_it_all.coordinator import (
            CloudCoverCoordinator, ForecastDiscussionCoordinator,
            NWSAlertsCoordinator, RadarTimestampCoordinator,
        )

        class _HeadSession(_FakeSession):
            def head(self, url, **kwargs):
                return self.get(url, **kwargs)

        cloud = CloudCoverCoordinator(HASS, "ILM", 34.2, -77.9)
        cloud._gridpoint_url = "https://api.weather.gov/gridpoints/ILM/1,2"
        cloud._grid_fetched = True
        for coordinator, label in (
            (NWSAlertsCoordinator(HASS, 34.2, -77.9), "Error fetching NWS alerts"),
            (cloud, "Error fetching cloud cover"),
            (RadarTimestampCoordinator(HASS, "ILM", "KLTX"), "Error fetching radar timestamp"),
            (ForecastDiscussionCoordinator(HASS, "ILM"), "Error fetching forecast discussion"),
        ):
            with self.subTest(label=label):
                session = _HeadSession(default=asyncio.TimeoutError())
                with _with_session(session), self.assertRaises(_UpdateFailed) as ctx:
                    _run(coordinator._async_update_data())
                self.assertEqual(f"{label}: TimeoutError", str(ctx.exception))

    def test_describe_leaves_out_the_request_url(self):
        """The URL of a location lookup holds the (followed) coordinates."""
        from noaa_it_all.coordinator import _describe

        class ClientResponseError(Exception):
            pass

        err = ClientResponseError(
            "503, message='Service Unavailable', "
            "url='https://api.weather.gov/alerts/active?point=39.7392,-104.9903'"
        )
        self.assertEqual(
            "ClientResponseError: 503, message='Service Unavailable'", _describe(err)
        )

    def test_failed_lookups_log_no_coordinates(self):
        from noaa_it_all.coordinator import (
            CloudCoverCoordinator, ForecastCoordinator, ObservationsCoordinator,
        )
        error = OSError("Cannot reach api.weather.gov")
        for coordinator, resolve in (
            (ObservationsCoordinator(HASS, "ILM", 39.7392, -104.9903), "_resolve_station"),
            (ForecastCoordinator(HASS, "ILM", 39.7392, -104.9903), "_resolve_forecast_urls"),
            (CloudCoverCoordinator(HASS, "ILM", 39.7392, -104.9903), "_resolve_gridpoint_url"),
        ):
            with self.subTest(resolve=resolve):
                session = _FakeSession(default=error)
                with _with_session(session), \
                        self.assertLogs("noaa_it_all.coordinator", level="DEBUG") as logs:
                    _run(getattr(coordinator, resolve)(session, {}))
                loud = [r.getMessage() for r in logs.records if r.levelname != "DEBUG"]
                self.assertTrue(loud)
                for message in loud:
                    self.assertNotIn("39.7392", message)
                    self.assertNotIn("104.9903", message)

    def test_a_missing_gridpoint_does_not_name_the_coordinates(self):
        from noaa_it_all.coordinator import CloudCoverCoordinator
        coordinator = CloudCoverCoordinator(HASS, "ILM", 39.7392, -104.9903)
        coordinator._grid_fetched = True  # resolved, but to nothing
        with _with_session(_FakeSession(default=OSError("unused"))), \
                self.assertRaises(_UpdateFailed) as ctx:
            _run(coordinator._async_update_data())
        self.assertNotIn("39.7392", str(ctx.exception))

    def test_describe_handles_an_empty_exception_string(self):
        """Several aiohttp errors stringify to '' and would say nothing."""
        from noaa_it_all.coordinator import _describe

        class _Silent(Exception):
            pass

        self.assertEqual(_describe(_Silent()), "_Silent")
        self.assertEqual(_describe(_Silent("why")), "_Silent: why")


class TestSurfForecastFailure(unittest.TestCase):
    """#33 P1.2: a failed surf zone forecast must not look like a calm one."""

    class _Response:
        def __init__(self, text="", payload=None):
            self._text = text
            self._payload = payload or {}

        def raise_for_status(self):
            pass

        async def text(self):
            return self._text

        async def json(self, **kwargs):
            return self._payload

    def _fetch(self, srf_result):
        from noaa_it_all.coordinator import SurfCoordinator
        session = _FakeSession(by_url={
            "product=SRF": srf_result,
            "tidesandcurrents": self._Response(payload={"data": []}),
            "ndbc.noaa.gov": self._Response(text="#YY MM DD"),
        })
        coordinator = SurfCoordinator(HASS, "ILM", tide_station="8658163", buoy_station="41110")
        with _with_session(session):
            return _run(coordinator._async_update_data())

    def test_failed_fetch_leaves_the_forecast_text_out(self):
        """Empty text parses as Low rip current risk, so it must be absent."""
        data = self._fetch(asyncio.TimeoutError())
        self.assertNotIn("forecast_text", data)

    def test_failed_fetch_keeps_the_other_sources(self):
        """No UpdateFailed: water temperature and wave height still update."""
        data = self._fetch(OSError("503"))
        self.assertIn("water_temp_f", data)
        self.assertIn("wave_height_ft", data)

    def test_successful_fetch_still_returns_the_text(self):
        data = self._fetch(self._Response(text="HIGH RIP CURRENT RISK"))
        self.assertEqual(data["forecast_text"], "high rip current risk")


class TestEclipseCoordinator(unittest.TestCase):
    """The eclipse coordinator computes rather than fetches, and re-paces itself.

    The re-pacing is the part worth testing. Every other coordinator here polls on a fixed
    interval because it watches something that drifts over hours; this one watches an event whose
    interesting part can last two minutes, so it has to tighten as that event approaches. It
    cannot be done in the entities -- Home Assistant only re-reads their state when a coordinator
    publishes -- so if this is wrong, "go outside now" fires after the eclipse has finished.
    """

    def _hass(self, timezone_name="America/New_York", elevation=10):
        hass = MagicMock()
        hass.config.time_zone = timezone_name
        hass.config.elevation = elevation

        async def _executor(func, *args):
            """Stand in for hass.async_add_executor_job, running inline."""
            return func(*args)

        hass.async_add_executor_job = _executor
        return hass

    def _coordinator(self, **kwargs):
        from noaa_it_all.coordinator import EclipseCoordinator
        return EclipseCoordinator(self._hass(**kwargs), "ILM", 34.2675, -77.9011)

    def test_it_produces_a_forecast_without_touching_the_network(self):
        from noaa_it_all.coordinator import EclipseCoordinator
        coordinator = self._coordinator()

        def _explode(*args, **kwargs):
            raise AssertionError("the eclipse coordinator must not perform network I/O")

        with patch("noaa_it_all.coordinator.async_get_clientsession", _explode):
            data = _run(coordinator._async_update_data())
        self.assertIn("upcoming", data)
        self.assertIsInstance(coordinator, EclipseCoordinator)

    def test_missing_coordinates_fail_cleanly(self):
        from noaa_it_all.coordinator import EclipseCoordinator
        coordinator = EclipseCoordinator(self._hass(), "ILM", None, None)
        with self.assertRaises(_UpdateFailed):
            _run(coordinator._async_update_data())

    def test_the_forecast_runs_off_the_event_loop(self):
        """A 75-100 ms computation belongs in an executor, and the repo says so itself.

        MeteorShowerCoordinator documents "well under 10 ms" as its reason for running inline;
        this one is an order of magnitude heavier and polls every minute while an eclipse is
        under way, so it takes the other branch of that same rule.
        """
        coordinator = self._coordinator()
        calls = []
        original = coordinator.hass.async_add_executor_job

        async def _record(func, *args):
            calls.append(func)
            return await original(func, *args)

        coordinator.hass.async_add_executor_job = _record
        _run(coordinator._async_update_data())
        self.assertEqual(len(calls), 1)

    def test_the_timezone_is_resolved_before_the_handoff(self):
        # ZoneInfo reads the tz database from disk and the resolver reads hass.config, so it has
        # to happen on the loop rather than inside the executor call.
        coordinator = self._coordinator()
        data = _run(coordinator._async_update_data())
        self.assertIn("upcoming", data)
        self.assertIsNotNone(coordinator._timezone.resolve(coordinator.hass))

    def test_the_default_interval_is_the_slow_one(self):
        from noaa_it_all.const import ECLIPSE_SCAN_INTERVAL
        from noaa_it_all.coordinator import EclipseCoordinator
        interval = EclipseCoordinator._interval_for(
            {"current": None, "next": {"hours_until": 400.0}}
        )
        self.assertEqual(interval.total_seconds() / 60.0, ECLIPSE_SCAN_INTERVAL)

    def test_it_tightens_as_an_eclipse_approaches(self):
        from noaa_it_all.const import (
            ECLIPSE_APPROACH_SCAN_INTERVAL, ECLIPSE_APPROACH_WINDOW_HOURS,
        )
        from noaa_it_all.coordinator import EclipseCoordinator
        interval = EclipseCoordinator._interval_for(
            {"current": None, "next": {"hours_until": ECLIPSE_APPROACH_WINDOW_HOURS - 1}}
        )
        self.assertEqual(interval.total_seconds() / 60.0, ECLIPSE_APPROACH_SCAN_INTERVAL)

    def test_it_tightens_further_once_one_is_under_way(self):
        from noaa_it_all.const import ECLIPSE_ACTIVE_SCAN_INTERVAL
        from noaa_it_all.coordinator import EclipseCoordinator
        interval = EclipseCoordinator._interval_for(
            {"current": {"hours_until": 0.0}, "next": None}
        )
        self.assertEqual(interval.total_seconds() / 60.0, ECLIPSE_ACTIVE_SCAN_INTERVAL)

    def test_an_empty_forecast_uses_the_slow_interval(self):
        from noaa_it_all.const import ECLIPSE_SCAN_INTERVAL
        from noaa_it_all.coordinator import EclipseCoordinator
        interval = EclipseCoordinator._interval_for({})
        self.assertEqual(interval.total_seconds() / 60.0, ECLIPSE_SCAN_INTERVAL)

    def test_a_refresh_actually_applies_the_new_interval(self):
        coordinator = self._coordinator()
        coordinator.update_interval = None
        _run(coordinator._async_update_data())
        self.assertIsNotNone(coordinator.update_interval)

    def test_the_catalog_exhausted_warning_is_logged_once_not_every_refresh(self):
        """Regression: an unlatched warning on an hourly poll is a log line every hour forever.

        The comment beside it already claimed it was said once, and it was not. Nobody can act on
        "the catalog ends in 2075" quickly enough for the twenty-fourth repetition to help.
        """
        from noaa_it_all.coordinator import EclipseCoordinator
        coordinator = self._coordinator()
        exhausted = {"catalog_exhausted": True, "catalog_last_year": 2075,
                     "current": None, "next": None}
        with patch("noaa_it_all.coordinator.build_eclipse_forecast", return_value=exhausted):
            with patch.object(EclipseCoordinator, "_interval_for", return_value=None):
                with self.assertLogs("noaa_it_all.coordinator", level="WARNING") as first:
                    _run(coordinator._async_update_data())
                self.assertEqual(len(first.output), 1)
                _run(coordinator._async_update_data())
                _run(coordinator._async_update_data())
        self.assertTrue(coordinator._warned_exhausted)

    def test_a_healthy_catalog_logs_no_warning(self):
        coordinator = self._coordinator()
        _run(coordinator._async_update_data())
        self.assertFalse(coordinator._warned_exhausted)

    def test_a_missing_elevation_falls_back_to_sea_level(self):
        self.assertEqual(self._coordinator(elevation=None)._elevation(), 0.0)

    def test_a_boolean_elevation_is_not_treated_as_a_number(self):
        # ``isinstance(True, int)`` is True in Python, so a config that somehow held a boolean
        # would otherwise put the observer one metre up.
        self.assertEqual(self._coordinator(elevation=True)._elevation(), 0.0)

    def test_a_real_elevation_is_used(self):
        self.assertEqual(self._coordinator(elevation=1200)._elevation(), 1200.0)

    def test_an_unknown_timezone_falls_back_to_utc_without_raising(self):
        coordinator = self._coordinator(timezone_name="Mars/Olympus_Mons")
        data = _run(coordinator._async_update_data())
        self.assertIn("upcoming", data)

    def test_the_timezone_is_resolved_once_and_cached(self):
        from noaa_it_all.coordinator import _ObserverTimezone
        cache = _ObserverTimezone()
        hass = self._hass()
        first = cache.resolve(hass)
        self.assertIs(cache.resolve(hass), first)


if __name__ == "__main__":
    unittest.main()
