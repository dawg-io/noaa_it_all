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
        self._assert_user_agent(SpaceWeatherCoordinator(HASS), 3)

    def test_hurricane_sends_user_agent(self):
        from noaa_it_all.coordinator import HurricaneCoordinator
        self._assert_user_agent(HurricaneCoordinator(HASS), 2)


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
        for label in ("DST", "K-index", "space weather alerts"):
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

    def test_describe_handles_an_empty_exception_string(self):
        """Several aiohttp errors stringify to '' and would say nothing."""
        from noaa_it_all.coordinator import _describe

        class _Silent(Exception):
            pass

        self.assertEqual(_describe(_Silent()), "_Silent")
        self.assertEqual(_describe(_Silent("why")), "_Silent: why")


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
