"""Live check that every office's NDBC buoy still reports wave height.

NDBC retires, moves and recovers buoys without notice, and the integration
only logs a warning when one stops. This asks NDBC directly, so it is skipped
unless NOAA_LIVE_TESTS=1 and pull requests never depend on NDBC being up.
The Buoy stations workflow runs it every week.
"""

import math
import os
import re
import unittest
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from const import NDBC_REALTIME_URL, OFFICE_BUOY_STATIONS, OFFICE_COORDINATES, USER_AGENT
from parsers import parse_ndbc_wave_height

_STATION_TABLE_URL = "https://www.ndbc.noaa.gov/data/stations/station_table.txt"
# The table's LOCATION column starts "32.517 N 117.425 W".
_LOCATION = re.compile(r"(\d+(?:\.\d+)?) ([NS]) (\d+(?:\.\d+)?) ([EW])")
_TIMEOUT = 30
# Buoys report waves at least hourly, so a day without one means the station has stopped.
_MAX_AGE = timedelta(hours=24)
# The farthest buoy is TAE's, 244 km from the office. 41047, which MFL mapped to until
# 0.9.1, is 907 km away in the Bahamas.
_MAX_DISTANCE_KM = 300


def _fetch(url):
    """Return the text at ``url``, or the error that stopped it."""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
            return response.read().decode("utf-8", errors="replace"), None
    except (urllib.error.URLError, TimeoutError) as err:
        return None, err


def _latest_wave_reading(text):
    """Return when the newest row with a wave height was taken, or None."""
    for line in text.splitlines():
        parts = line.split()
        if line.startswith("#") or len(parts) < 9 or parts[8] == "MM":
            continue
        try:
            return datetime(*map(int, parts[:5]), tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _station_positions(table):
    """Return each station's (lat, lon) from NDBC's pipe-separated station table."""
    positions = {}
    for line in table.splitlines():
        fields = line.split("|")
        if line.startswith("#") or len(fields) < 7:
            continue
        match = _LOCATION.match(fields[6].strip())
        if match:
            lat, ns, lon, ew = match.groups()
            positions[fields[0].strip().upper()] = (
                float(lat) * (1 if ns == "N" else -1),
                float(lon) * (1 if ew == "E" else -1),
            )
    return positions


def _distance_km(a, b):
    """Great-circle distance between two (lat, lon) points."""
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (math.sin((lat2 - lat1) / 2) ** 2
         + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 6371 * 2 * math.asin(math.sqrt(h))


@unittest.skipUnless(os.environ.get("NOAA_LIVE_TESTS") == "1", "set NOAA_LIVE_TESTS=1 to ask NDBC")
class TestBuoyStationsLive(unittest.TestCase):
    """Each station answers, reports a recent wave height, and sits near its office."""

    @classmethod
    def setUpClass(cls):
        cls.realtime = {
            station: _fetch(NDBC_REALTIME_URL.format(station=station))
            for station in set(OFFICE_BUOY_STATIONS.values())
        }
        table, cls.table_error = _fetch(_STATION_TABLE_URL)
        cls.positions = _station_positions(table or "")

    def _text(self, office, station):
        text, err = self.realtime[station]
        if err is not None:
            self.fail(f"{office}: {NDBC_REALTIME_URL.format(station=station)} failed: {err}")
        return text

    def test_station_answers(self):
        for office, station in OFFICE_BUOY_STATIONS.items():
            with self.subTest(office=office, station=station):
                self._text(office, station)

    def test_integration_reads_a_wave_height(self):
        for office, station in OFFICE_BUOY_STATIONS.items():
            with self.subTest(office=office, station=station):
                self.assertIsNotNone(
                    parse_ndbc_wave_height(self._text(office, station)),
                    f"{office}: {station} has no wave height",
                )

    def test_wave_height_is_recent(self):
        now = datetime.now(timezone.utc)
        for office, station in OFFICE_BUOY_STATIONS.items():
            with self.subTest(office=office, station=station):
                taken = _latest_wave_reading(self._text(office, station))
                self.assertIsNotNone(taken, f"{office}: {station} has no wave height")
                self.assertLess(now - taken, _MAX_AGE, f"{office}: {station}'s last wave height is from {taken}")

    def test_station_is_near_its_office(self):
        for office, station in OFFICE_BUOY_STATIONS.items():
            with self.subTest(office=office, station=station):
                if self.table_error is not None:
                    self.fail(f"{_STATION_TABLE_URL} failed: {self.table_error}")
                self.assertIn(station, self.positions, f"{office}: NDBC no longer lists {station}")
                distance = _distance_km(OFFICE_COORDINATES[office], self.positions[station])
                self.assertLess(distance, _MAX_DISTANCE_KM, f"{office}: {station} is {distance:.0f} km away")


if __name__ == "__main__":
    unittest.main()
