"""The NDBC buoy behind each office's Surf Height.

A buoy that stops reporting, or one off the wrong coast, fails quietly: the
integration logs a warning on every poll and Surf Height falls back to the
forecast text. These tests run offline; test_buoy_stations_live.py asks NDBC
whether each station still reports.
"""

import re
import unittest

from const import OFFICE_BUOY_STATIONS, OFFICE_COORDINATES

# NDBC station IDs are five characters: digits for buoys, letters for C-MAN stations.
_STATION_ID = re.compile(r"^[0-9A-Z]{5}$")


class TestOfficeBuoyStations(unittest.TestCase):
    """Every office's buoy is a real NDBC station near that office."""

    def test_station_ids_are_ndbc_ids(self):
        for office, station in OFFICE_BUOY_STATIONS.items():
            with self.subTest(office=office):
                self.assertRegex(station, _STATION_ID)

    def test_every_office_has_coordinates(self):
        """The live check measures each buoy's distance from its office."""
        for office in OFFICE_BUOY_STATIONS:
            with self.subTest(office=office):
                self.assertIn(office, OFFICE_COORDINATES)

    def test_replaced_stations(self):
        """Stations that stopped reporting, or were off the wrong coast, in October 2026."""
        replaced = {
            # 46235 is Imperial Beach Nearshore, not Point Loma South, and stopped reporting. (#38)
            "SGX": "46232",
            # 42020 was recovered in May 2026.
            "CRP": "42092",
            # 42040 stopped reporting.
            "MOB": "42012",
            # 41047 is 350 NM ENE of Nassau, 900 km from Miami.
            "MFL": "41122",
        }
        for office, station in replaced.items():
            with self.subTest(office=office):
                self.assertEqual(OFFICE_BUOY_STATIONS[office], station)

    def test_brownsville_has_no_buoy(self):
        """42020 was recovered, and no buoy within 190 km of Brownsville reports waves."""
        self.assertNotIn("BRO", OFFICE_BUOY_STATIONS)


if __name__ == "__main__":
    unittest.main()
