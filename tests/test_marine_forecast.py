"""Tests for the Nearshore Marine Forecast (NSH) feature.

Covers the pure parser, the coordinator that fetches the product, and the
sensor that publishes one marine zone. The fixture is the real Chicago
(LOT) product text.
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
import sys
import unittest
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
_FIXTURES = os.path.join(_REPO, "tests", "fixtures")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

from parsers import (  # noqa: E402
    expand_ugc,
    normalize_marine_zone,
    classify_marine_alerts,
    parse_nearshore_forecast,
    product_is_stale,
)


def _fixture(office="lot"):
    with open(os.path.join(_FIXTURES, f"nsh_{office}.txt")) as f:
        return f.read()


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------
class TestExpandUgc(unittest.TestCase):

    def test_range_is_inclusive_and_expiry_is_ignored(self):
        self.assertEqual(expand_ugc("LMZ740>742-102115-"), ["LMZ740", "LMZ741", "LMZ742"])

    def test_bare_numbers_reuse_the_prefix(self):
        self.assertEqual(
            expand_ugc("LMZ740>742-744-102115-"),
            ["LMZ740", "LMZ741", "LMZ742", "LMZ744"],
        )

    def test_prefix_change_is_followed(self):
        self.assertEqual(expand_ugc("LMZ741-ILZ003-102115-"), ["LMZ741", "ILZ003"])

    def test_single_zone(self):
        self.assertEqual(expand_ugc("LMZ741-102115-"), ["LMZ741"])


class TestNormalizeMarineZone(unittest.TestCase):

    def test_accepts_and_uppercases(self):
        self.assertEqual(normalize_marine_zone(" lmz741 "), "LMZ741")

    def test_rejects_malformed(self):
        for bad in ("", "LMZ74", "LMC741", "741", "LMZ7411", None, 741):
            self.assertIsNone(normalize_marine_zone(bad), bad)


class TestProductIsStale(unittest.TestCase):

    _NOW = datetime(2026, 10, 13, 16, 0, tzinfo=timezone.utc)

    def test_older_than_the_limit(self):
        self.assertTrue(product_is_stale("2026-10-12T15:59:00+00:00", self._NOW, 24))

    def test_within_the_limit(self):
        self.assertFalse(product_is_stale("2026-10-12T16:01:00+00:00", self._NOW, 24))

    def test_other_time_zones(self):
        # 11:00 CDT is 16:00 UTC: issued a day and an hour before now.
        self.assertTrue(product_is_stale("2026-10-12T10:00:00-05:00", self._NOW, 24))
        self.assertFalse(product_is_stale("2026-10-13T10:00:00-05:00", self._NOW, 24))

    def test_unreadable_times_are_not_stale(self):
        for issued in (None, "", "yesterday", 1760371200, "2026-10-01T00:00:00"):
            self.assertFalse(product_is_stale(issued, self._NOW, 24), issued)


class TestParseNearshoreForecast(unittest.TestCase):

    def test_middle_zone_of_a_range_gets_its_own_block(self):
        result = parse_nearshore_forecast(_fixture(), "LMZ741")
        self.assertEqual(result["zone"], "LMZ741")
        self.assertEqual(
            [p["name"] for p in result["periods"]],
            ["Rest Of Today", "Tonight", "Sunday", "Sunday Night"],
        )

    def test_wrapped_lines_are_joined(self):
        periods = parse_nearshore_forecast(_fixture(), "LMZ741")["periods"]
        self.assertEqual(
            periods[1]["detailed_forecast"],
            "Southeast winds 15 to 20 kt diminishing to 10 to 15 kt. "
            "Mostly cloudy. Waves 2 to 4 ft.",
        )

    def test_zone_name_is_matched_by_position(self):
        result = parse_nearshore_forecast(_fixture(), "LMZ741")
        self.assertEqual(result["zone_name"], "Wilmette Harbor to Northerly Island IL")
        self.assertEqual(len(result["zone_names"]), 3)

    def test_issued_line_is_captured(self):
        result = parse_nearshore_forecast(_fixture(), "LMZ741")
        self.assertEqual(result["issued"], "951 AM CDT Sat Oct 10 2026")

    def test_second_block_is_distinct(self):
        result = parse_nearshore_forecast(_fixture(), "LMZ745")
        self.assertEqual(result["zone_name"], "Burns Harbor to Michigan City IN")
        self.assertIn("Waves around 1 ft.", result["periods"][-1]["detailed_forecast"])
        first_block = parse_nearshore_forecast(_fixture(), "LMZ740")
        self.assertNotEqual(first_block["periods"], result["periods"])

    def test_zone_not_in_product_returns_none(self):
        self.assertIsNone(parse_nearshore_forecast(_fixture(), "LMZ999"))

    def test_empty_inputs_return_none(self):
        self.assertIsNone(parse_nearshore_forecast("", "LMZ741"))
        self.assertIsNone(parse_nearshore_forecast(_fixture(), ""))

    def test_zone_is_case_insensitive(self):
        self.assertIsNotNone(parse_nearshore_forecast(_fixture(), "lmz741"))

    def test_wrapped_ugc_header(self):
        text = (
            "LMZ740>742-744-746-748-750-752-754-756-758-760-762-764-766-768-\n"
            "770-102115-\n"
            "Zone A-Zone B-Zone C-\n"
            "951 AM CDT Sat Oct 10 2026\n\n"
            ".TONIGHT...Calm. Waves 1 ft.\n\n$$\n"
        )
        result = parse_nearshore_forecast(text, "LMZ770")
        self.assertEqual(result["periods"][0]["name"], "Tonight")

    def test_headlines_before_the_first_period(self):
        text = (
            "LMZ741-102115-\nSome Zone IL-\n951 AM CDT Sat Oct 10 2026\n\n"
            "...SMALL CRAFT ADVISORY IN EFFECT UNTIL 10 PM CDT THIS EVENING...\n\n"
            ".TONIGHT...Southeast winds 20 to 25 kt. Waves 4 to 6 ft.\n\n$$\n"
        )
        result = parse_nearshore_forecast(text, "LMZ741")
        self.assertEqual(
            result["headlines"],
            ["SMALL CRAFT ADVISORY IN EFFECT UNTIL 10 PM CDT THIS EVENING"],
        )
        self.assertEqual(len(result["periods"]), 1)

    def test_multi_word_labels(self):
        text = (
            "LMZ741-102115-\nSome Zone IL-\n951 AM CDT Sat Oct 10 2026\n\n"
            ".WEDNESDAY THROUGH THURSDAY NIGHT...Variable winds. Waves 1 ft.\n\n$$\n"
        )
        result = parse_nearshore_forecast(text, "LMZ741")
        self.assertEqual(result["periods"][0]["name"], "Wednesday Through Thursday Night")

    def test_zone_name_is_none_when_names_do_not_line_up(self):
        text = (
            "LMZ740>742-102115-\nFirst Name IL-Second Name IL-\n951 AM CDT Sat Oct 10 2026\n\n"
            ".TONIGHT...Calm.\n\n$$\n"
        )
        result = parse_nearshore_forecast(text, "LMZ741")
        self.assertIsNone(result["zone_name"])

    def test_header_without_expiry_does_not_hang(self):
        self.assertIsNone(parse_nearshore_forecast("LMZ741\nno expiry here\n", "LMZ741"))

    def test_periods_found_without_an_issued_line(self):
        text = "LMZ741-102115-\nSome Zone IL-\n\n.TONIGHT...Calm. Waves 1 ft.\n\n$$\n"
        result = parse_nearshore_forecast(text, "LMZ741")
        self.assertIsNone(result["issued"])
        self.assertEqual(result["zone_name"], "Some Zone IL")
        self.assertEqual([p["name"] for p in result["periods"]], ["Tonight"])


class TestParseOtherOffices(unittest.TestCase):
    """Formats seen in real NSH products from other Great Lakes offices."""

    def test_wrapped_headline_is_joined(self):
        result = parse_nearshore_forecast(_fixture("cle"), "LEZ147")
        self.assertEqual(
            result["headlines"],
            ["SMALL CRAFT ADVISORY IN EFFECT FROM 11 PM EDT THIS EVENING THROUGH SUNDAY MORNING"],
        )
        self.assertEqual(result["periods"][0]["name"], "Tonight")

    def test_wrapped_zone_name_keeps_the_space(self):
        result = parse_nearshore_forecast(_fixture("dtx"), "LHZ421")
        self.assertEqual(
            result["zone_name"], "Outer Saginaw Bay SW of Alabaster to Port Austin MI to Inner Saginaw Bay"
        )

    def test_one_name_shared_by_several_zones(self):
        for zone in ("LEZ040", "LEZ041"):
            result = parse_nearshore_forecast(_fixture("buf"), zone)
            self.assertEqual(result["zone_name"], "Buffalo to Ripley along Lake Erie")

    def test_single_zone_name_with_a_hyphen(self):
        result = parse_nearshore_forecast(_fixture("dlh"), "LSZ121")
        self.assertEqual(result["zone_name"], "Chequamegon Bay-Bayfield to Oak Point WI")
        self.assertEqual(result["zone_names"], ["Chequamegon Bay-Bayfield to Oak Point WI"])

    def test_ambiguous_hyphenated_names_give_no_zone_name(self):
        result = parse_nearshore_forecast(_fixture("cle"), "LEZ148")
        self.assertIsNone(result["zone_name"])
        self.assertEqual(len(result["periods"]), 4)

    def test_issued_line_with_two_time_zones(self):
        result = parse_nearshore_forecast(_fixture("mqt"), "LSZ240")
        self.assertEqual(result["issued"], "1101 AM EDT Sat Oct 10 2026 /1001 AM CDT Sat Oct 10 2026/")
        self.assertEqual(result["zone_name"], "Saxon Harbor WI to Black River MI")
        self.assertEqual(result["headlines"], ["SMALL CRAFT ADVISORY IN EFFECT THROUGH SUNDAY MORNING"])

    def test_every_zone_in_every_fixture_parses(self):
        for office in ("lot", "buf", "cle", "dlh", "dtx", "mqt"):
            text = _fixture(office)
            zones = [z for line in text.splitlines() if line[:3].isalpha() and line[2:3] == "Z"
                     for z in expand_ugc(line)]
            self.assertTrue(zones, office)
            for zone in zones:
                result = parse_nearshore_forecast(text, zone)
                self.assertTrue(result["periods"], f"{office} {zone}")
                self.assertIsNotNone(result["issued"], f"{office} {zone}")


# ---------------------------------------------------------------------------
# Coordinator and sensor (Home Assistant mocked)
# ---------------------------------------------------------------------------
_ha_coordinator = MagicMock()
_ha_entity = MagicMock()
_aiohttp = MagicMock()


class _UpdateFailed(Exception):
    pass


class _DataUpdateCoordinator:
    def __init__(self, hass, logger, name=None, update_interval=None):
        self.hass = hass
        self.name = name
        self.update_interval = update_interval


_ha_coordinator.DataUpdateCoordinator = _DataUpdateCoordinator
_ha_coordinator.UpdateFailed = _UpdateFailed
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_entity.DeviceInfo = dict
_aiohttp.ClientTimeout = lambda **kwargs: kwargs

_ha_sensor = MagicMock()
_ha_sensor.SensorEntity = type("SensorEntity", (), {})

_MOCK_MODULES = {
    "homeassistant": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.components": MagicMock(),
    "homeassistant.components.sensor": _ha_sensor,
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.weather": MagicMock(),
    "homeassistant.components.image": MagicMock(),
    "aiohttp": _aiohttp,
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


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _FakeResponse:
    def __init__(self, payload=None, error=None):
        self._payload = payload
        self._error = error

    def raise_for_status(self):
        if self._error is not None:
            raise self._error

    async def json(self, content_type=None):
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
    def __init__(self, result):
        self._result = result
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _FakeGet(self._result)


def _hours_ago(hours):
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")


def _product(text=None, issued=None):
    return {
        "id": "abc-123",
        "issuanceTime": _hours_ago(1) if issued is None else issued,
        "productText": _fixture() if text is None else text,
    }


def _with_session(session):
    return patch("noaa_it_all.coordinator.async_get_clientsession", return_value=session)


class TestMarineForecastCoordinator(unittest.TestCase):

    def _make(self, zone="LMZ741"):
        from noaa_it_all.coordinator import MarineForecastCoordinator
        return MarineForecastCoordinator(MagicMock(), "LOT", zone)

    def test_fetches_the_office_nsh_product_and_parses_the_zone(self):
        coordinator = self._make()
        product = _product()
        session = _FakeSession(_FakeResponse(product))
        with _with_session(session):
            data = _run(coordinator._async_update_data())

        url, kwargs = session.calls[0]
        self.assertEqual(
            url, "https://api.weather.gov/products/types/NSH/locations/LOT/latest"
        )
        self.assertIn("User-Agent", kwargs["headers"])
        self.assertEqual(len(data["forecast"]["periods"]), 4)
        self.assertEqual(data["product_id"], "abc-123")
        self.assertEqual(data["issuance_time"], product["issuanceTime"])
        self.assertEqual(data["source_url"], url)

    def test_a_forecast_over_a_day_old_raises_update_failed(self):
        """NWS keeps serving an office's last forecast for a week after it stops."""
        coordinator = self._make()
        with _with_session(_FakeSession(_FakeResponse(_product(issued=_hours_ago(25))))):
            with self.assertRaises(_UpdateFailed) as ctx:
                _run(coordinator._async_update_data())
        self.assertIn("LOT", str(ctx.exception))
        self.assertIn("24 hours", str(ctx.exception))

    def test_a_forecast_from_this_morning_is_current(self):
        coordinator = self._make()
        with _with_session(_FakeSession(_FakeResponse(_product(issued=_hours_ago(23))))):
            data = _run(coordinator._async_update_data())
        self.assertEqual(data["forecast"]["zone"], "LMZ741")

    def test_network_error_raises_update_failed(self):
        coordinator = self._make()
        with _with_session(_FakeSession(OSError("Network unreachable"))):
            with self.assertRaises(_UpdateFailed):
                _run(coordinator._async_update_data())

    def test_zone_missing_from_product_raises_update_failed_naming_it(self):
        coordinator = self._make("LMZ999")
        with _with_session(_FakeSession(_FakeResponse(_product()))):
            with self.assertRaises(_UpdateFailed) as ctx:
                _run(coordinator._async_update_data())
        self.assertIn("LMZ999", str(ctx.exception))
        self.assertIn("LOT", str(ctx.exception))

    def test_empty_product_text_raises_update_failed(self):
        coordinator = self._make()
        with _with_session(_FakeSession(_FakeResponse({"productText": ""}))):
            with self.assertRaises(_UpdateFailed):
                _run(coordinator._async_update_data())


class TestMarineForecastSensor(unittest.TestCase):

    def _make(self, data="fixture"):
        from noaa_it_all.sensors.surf import MarineForecastSensor
        coord = MagicMock()
        if data == "fixture":
            data = {
                "forecast": parse_nearshore_forecast(_fixture(), "LMZ741"),
                "product_id": "abc-123",
                "issuance_time": "2026-10-10T14:51:00+00:00",
                "source_url": "https://example.test/nsh",
            }
        coord.data = data
        return MarineForecastSensor(coord, "LOT", "LMZ741")

    def test_state_is_the_first_period_forecast(self):
        sensor = self._make()
        self.assertEqual(
            sensor.state,
            "South winds 15 to 20 kt becoming southeast. Partly cloudy. Waves 2 to 4 ft.",
        )
        self.assertEqual(sensor.extra_state_attributes["period"], "Rest Of Today")

    def test_long_forecast_is_shortened_at_a_word(self):
        """Home Assistant would make a state over 255 characters unknown."""
        words = "Northeast gales to 35 kt with occasional gusts to 45 kt."
        text = " ".join([words] * 6)
        sensor = self._make(data={"forecast": {"periods": [
            {"name": "Tonight", "detailed_forecast": text},
        ]}})
        state = sensor.state
        self.assertLessEqual(len(state), 255)
        self.assertTrue(state.endswith("…"))
        self.assertTrue(text.startswith(state[:-1]))
        self.assertIn(text[len(state) - 1], " .")
        self.assertEqual(sensor.extra_state_attributes["periods"][0]["detailed_forecast"], text)

    def test_period_without_text_has_no_state(self):
        sensor = self._make(data={"forecast": {"periods": [
            {"name": "Tonight", "detailed_forecast": ""},
        ]}})
        self.assertIsNone(sensor.state)

    def test_attributes_carry_every_period(self):
        attrs = self._make().extra_state_attributes
        self.assertEqual(attrs["period_count"], 4)
        self.assertEqual(attrs["periods"][3]["name"], "Sunday Night")
        self.assertIn("detailed_forecast", attrs["periods"][0])
        self.assertEqual(attrs["zone"], "LMZ741")
        self.assertEqual(attrs["zone_name"], "Wilmette Harbor to Northerly Island IL")
        self.assertEqual(attrs["issued"], "951 AM CDT Sat Oct 10 2026")
        self.assertEqual(attrs["product_id"], "abc-123")

    def test_identity(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Forecast")
        self.assertEqual(sensor._attr_unique_id, "noaa_LMZ741_marine_forecast")

    def test_grouped_under_its_zone_device(self):
        """Its own device, so the surf entry's device never holds it."""
        info = self._make().device_info
        self.assertEqual(info["name"], "NOAA LMZ741 Marine")
        self.assertEqual(info["identifiers"], {("noaa_it_all", "noaa_LMZ741_marine")})

    def test_no_data(self):
        sensor = self._make(data=None)
        self.assertIsNone(sensor.state)
        self.assertEqual(sensor.extra_state_attributes, {"periods": []})


class TestMarinePeriodSensor(unittest.TestCase):

    def _make(self, data="fixture"):
        from noaa_it_all.sensors.surf import MarinePeriodSensor
        coord = MagicMock()
        if data == "fixture":
            data = {"forecast": parse_nearshore_forecast(_fixture(), "LMZ741")}
        coord.data = data
        return MarinePeriodSensor(coord, "LOT", "LMZ741")

    def test_state_is_the_first_period_name(self):
        self.assertEqual(self._make().state, "Rest Of Today")

    def test_identity(self):
        sensor = self._make()
        self.assertEqual(sensor.name, "Period")
        self.assertEqual(sensor._attr_unique_id, "noaa_LMZ741_marine_period")

    def test_shares_the_forecast_device(self):
        from noaa_it_all.sensors.surf import MarineForecastSensor
        period = self._make()
        forecast = MarineForecastSensor(period.coordinator, "LOT", "LMZ741")
        self.assertEqual(period.device_info, forecast.device_info)

    def test_no_data(self):
        self.assertIsNone(self._make(data=None).state)
        self.assertIsNone(self._make(data={"forecast": {"periods": []}}).state)


# ---------------------------------------------------------------------------
# Marine hazards: the zone's NWS alerts
# ---------------------------------------------------------------------------
def _alerts(zone):
    import json
    with open(os.path.join(_FIXTURES, f"alerts_{zone}.json")) as f:
        return json.load(f)["features"]


def _cdt(stamp):
    return datetime.fromisoformat(stamp + "-05:00")


def _alert(event, onset="2026-10-14T00:00:00-05:00", ends="2026-10-16T00:00:00-05:00", **props):
    return {"properties": {
        "event": event, "status": "Actual", "messageType": "Alert", "severity": "Moderate",
        "onset": onset, "ends": ends, "headline": f"{event} issued", **props,
    }}


class TestClassifyMarineAlerts(unittest.TestCase):
    """Recorded LMZ741 alerts: a Small Craft Advisory from 4 PM to 10 AM the next day."""

    def test_issued_but_not_started_is_upcoming(self):
        result = classify_marine_alerts(_alerts("lmz741"), _cdt("2026-10-14T12:00:00"))
        self.assertIsNone(result["hazard"])
        self.assertEqual(result["hazards"], [])
        self.assertEqual(result["upcoming"][0]["event"], "Small Craft Advisory")
        self.assertEqual(
            result["upcoming"][0]["headline"],
            "SMALL CRAFT ADVISORY IN EFFECT FROM 4 PM THIS AFTERNOON TO 10 AM CDT THURSDAY",
        )

    def test_in_effect_after_its_onset(self):
        result = classify_marine_alerts(_alerts("lmz741"), _cdt("2026-10-14T17:00:00"))
        self.assertEqual(result["hazard"], "Small Craft Advisory")
        self.assertEqual(len(result["hazards"]), 1)
        self.assertEqual(result["hazards"][0]["onset"], "2026-10-14T16:00:00-05:00")
        self.assertEqual(result["hazards"][0]["ends"], "2026-10-15T10:00:00-05:00")
        self.assertEqual(result["upcoming"], [])

    def test_gone_once_it_ends(self):
        result = classify_marine_alerts(_alerts("lmz741"), _cdt("2026-10-15T10:00:00"))
        self.assertEqual(result, {"hazard": None, "hazards": [], "upcoming": [], "watches": []})

    def test_a_watch_is_never_the_hazard(self):
        result = classify_marine_alerts(_alerts("lmz849"), _cdt("2026-10-16T12:00:00"))
        self.assertIsNone(result["hazard"])
        self.assertEqual([w["event"] for w in result["watches"]], ["Gale Watch"])

    def test_most_severe_first(self):
        now = _cdt("2026-10-15T00:00:00")
        result = classify_marine_alerts([
            _alert("Small Craft Advisory"),
            _alert("Lakeshore Flood Warning"),
            _alert("Gale Warning"),
            _alert("Dense Fog Advisory"),
        ], now)
        self.assertEqual(result["hazard"], "Gale Warning")
        self.assertEqual(
            [h["event"] for h in result["hazards"]],
            ["Gale Warning", "Lakeshore Flood Warning", "Small Craft Advisory", "Dense Fog Advisory"],
        )

    def test_storm_outranks_gale_outranks_small_craft(self):
        now = _cdt("2026-10-15T00:00:00")
        for events, expected in (
            (["Small Craft Advisory", "Gale Warning"], "Gale Warning"),
            (["Gale Warning", "Storm Warning"], "Storm Warning"),
            (["Storm Warning", "Hurricane Force Wind Warning"], "Hurricane Force Wind Warning"),
        ):
            with self.subTest(events=events):
                result = classify_marine_alerts([_alert(e) for e in events], now)
                self.assertEqual(result["hazard"], expected)

    def test_cancellations_tests_and_statements_are_left_out(self):
        now = _cdt("2026-10-15T00:00:00")
        result = classify_marine_alerts([
            _alert("Gale Warning", messageType="Cancel"),
            _alert("Storm Warning", status="Test"),
            _alert("Marine Weather Statement"),
        ], now)
        self.assertEqual(result, {"hazard": None, "hazards": [], "upcoming": [], "watches": []})

    def test_falls_back_to_effective_and_expires(self):
        now = _cdt("2026-10-15T00:00:00")
        feature = _alert("Gale Warning", onset=None, ends=None,
                         effective="2026-10-14T00:00:00-05:00", expires="2026-10-14T12:00:00-05:00")
        self.assertIsNone(classify_marine_alerts([feature], now)["hazard"])

    def test_a_combined_headline_is_split_per_alert(self):
        """NWS gave both alerts one headline naming both hazards (LMZ741, 2026-10-14 evening)."""
        result = classify_marine_alerts(_alerts("lmz741_gale_watch"), _cdt("2026-10-14T20:00:00"))
        self.assertEqual(result["hazard"], "Small Craft Advisory")
        self.assertEqual(
            result["hazards"][0]["headline"], "SMALL CRAFT ADVISORY NOW IN EFFECT UNTIL 10 AM CDT THURSDAY"
        )
        self.assertEqual(
            result["watches"][0]["headline"],
            "GALE WATCH IN EFFECT FROM FRIDAY AFTERNOON THROUGH LATE FRIDAY NIGHT",
        )

    def test_a_combined_headline_without_this_event_uses_the_alert_headline(self):
        now = _cdt("2026-10-15T00:00:00")
        feature = _alert("Gale Warning", parameters={"NWSheadline": ["SMALL CRAFT ADVISORY... ...STORM WATCH"]})
        self.assertEqual(classify_marine_alerts([feature], now)["hazards"][0]["headline"], "Gale Warning issued")

    def test_without_a_headline_parameter_uses_the_headline(self):
        now = _cdt("2026-10-15T00:00:00")
        result = classify_marine_alerts([_alert("Gale Warning")], now)
        self.assertEqual(result["hazards"][0]["headline"], "Gale Warning issued")

    def test_a_replaced_watch_is_left_out(self):
        """NWS left the upgraded Gale Watch active as an Alert, VTEC UPG (LMZ046, 2026-10-16 early)."""
        result = classify_marine_alerts(_alerts("lmz046_replaced_watch"), _cdt("2026-10-15T23:30:00"))
        self.assertEqual(result["watches"], [])
        self.assertEqual(result["hazard"], "Small Craft Advisory")
        self.assertEqual([u["event"] for u in result["upcoming"]], ["Gale Warning"])

    def test_cancelled_and_upgraded_alerts_are_left_out_whatever_their_message_type(self):
        now = _cdt("2026-10-15T00:00:00")
        for action in ("CAN", "UPG"):
            with self.subTest(action=action):
                vtec = f"/O.{action}.KLOT.SC.Y.0061.261014T0500Z-261016T0500Z/"
                feature = _alert("Small Craft Advisory", messageType="Update", parameters={"VTEC": [vtec]})
                self.assertIsNone(classify_marine_alerts([feature], now)["hazard"])

    def test_an_expiring_alert_stays_until_its_end(self):
        """VTEC EXP says it will expire; until its end it is still in effect."""
        now = _cdt("2026-10-15T00:00:00")
        vtec = "/O.EXP.KLOT.SC.Y.0061.000000T0000Z-261015T0600Z/"
        feature = _alert("Small Craft Advisory", messageType="Update", parameters={"VTEC": [vtec]})
        self.assertEqual(classify_marine_alerts([feature], now)["hazard"], "Small Craft Advisory")


class TestMarineAlertsCoordinator(unittest.TestCase):

    def _make(self):
        from noaa_it_all.coordinator import MarineAlertsCoordinator
        return MarineAlertsCoordinator(MagicMock(), "LMZ741")

    def test_fetches_the_zone_alerts_and_classifies_them(self):
        features = _alerts("lmz741")
        session = _FakeSession(_FakeResponse({"features": features}))
        classified = {"hazard": None, "hazards": [], "upcoming": [], "watches": []}
        with _with_session(session), patch(
            "noaa_it_all.coordinator.classify_marine_alerts", return_value=dict(classified)
        ) as classify:
            data = _run(self._make()._async_update_data())
        url, kwargs = session.calls[0]
        self.assertEqual(url, "https://api.weather.gov/alerts/active?zone=LMZ741")
        self.assertIn("User-Agent", kwargs["headers"])
        self.assertIs(classify.call_args.args[0], features)
        self.assertEqual(data, {**classified, "source_url": url})

    def test_a_failed_fetch_raises_update_failed(self):
        with _with_session(_FakeSession(OSError("Network unreachable"))):
            with self.assertRaises(_UpdateFailed) as ctx:
                _run(self._make()._async_update_data())
        self.assertIn("LMZ741", str(ctx.exception))

    def test_an_answer_without_features_raises_update_failed(self):
        """No feature list is not the same as no alerts, so it must not read as None."""
        with _with_session(_FakeSession(_FakeResponse({"title": "error"}))):
            with self.assertRaises(_UpdateFailed):
                _run(self._make()._async_update_data())


class TestMarineHazardSensor(unittest.TestCase):

    def _make(self, data):
        from noaa_it_all.sensors.surf import MarineHazardSensor
        coord = MagicMock()
        coord.data = data
        return MarineHazardSensor(coord, "LOT", "LMZ741")

    def _data(self, now):
        return {**classify_marine_alerts(_alerts("lmz741"), now), "source_url": "https://example.test/a"}

    def test_state_is_the_hazard_in_effect(self):
        sensor = self._make(self._data(_cdt("2026-10-14T17:00:00")))
        self.assertEqual(sensor.state, "Small Craft Advisory")
        self.assertEqual(sensor.icon, "mdi:alert")
        attrs = sensor.extra_state_attributes
        self.assertEqual(attrs["hazard_count"], 1)
        self.assertEqual(attrs["hazards"][0]["event"], "Small Craft Advisory")
        self.assertEqual(attrs["zone"], "LMZ741")
        self.assertEqual(attrs["alerts_source"], "https://example.test/a")

    def test_state_is_none_text_with_nothing_in_effect(self):
        sensor = self._make(self._data(_cdt("2026-10-14T12:00:00")))
        self.assertEqual(sensor.state, "None")
        self.assertEqual(sensor.icon, "mdi:check-circle-outline")
        self.assertEqual(sensor.extra_state_attributes["upcoming"][0]["event"], "Small Craft Advisory")

    def test_no_data_is_unknown_not_none(self):
        """A failure never reads as safe: without data the state is unknown, not "None"."""
        sensor = self._make(None)
        self.assertIsNone(sensor.state)
        self.assertEqual(sensor.extra_state_attributes, {})

    def test_identity(self):
        sensor = self._make(None)
        self.assertEqual(sensor.name, "Hazard")
        self.assertEqual(sensor._attr_unique_id, "noaa_LMZ741_marine_hazard")
        self.assertEqual(sensor.device_info["name"], "NOAA LMZ741 Marine")


if __name__ == "__main__":
    unittest.main()
