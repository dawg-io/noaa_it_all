"""Meteor shower catalog for NOAA Integration.

Every shower is keyed by **solar longitude** — the angular position of Earth in its orbit —
rather than by a calendar date. Earth crosses each debris stream at the same solar longitude
every year, so the catalog never needs a date edit: :func:`astro.next_solar_longitude_after`
converts a stored solar longitude into the actual peak instant for whatever year is asked about.
That is why this file is correct in 2026 and still correct in 2050.

Parameters are taken from the IMO Meteor Shower Calendar working list of visual meteor showers
and the IAU Meteor Data Center shower database. Activity windows were converted from the
published activity dates to solar longitude, and every ``sol_lon_max`` here has been verified to
reproduce its published maximum date to within a day (see ``tests/test_meteor_catalog.py``).

Two deliberate simplifications, both well inside the accuracy of the sky-brightness model that
consumes this data:

* **Radiant drift is not modelled.** Radiants migrate roughly 0.5-1 deg per day across the
  activity period; the stored ``ra``/``dec`` are the peak-night positions. Away from peak this
  shifts the radiant altitude by a degree or two, moving the viewing score by a point or so.
* **ZHR is the ordinary-year figure.** Showers marked ``"variable": True`` produce rare, poorly
  predictable outbursts (the Draconids have gone from a handful per hour to storm levels).
  Nothing here attempts to predict those.

Like ``astro.py`` and ``meteor.py``, this module is standard library only with no relative
imports, so tests can load it directly.

Field reference:

==================  =============================================================
``code``            IAU three-letter shower code
``name``            Common name
``sol_lon_max``     Solar longitude of maximum, degrees (J2000)
``sol_lon_start``   Solar longitude at which activity begins
``sol_lon_end``     Solar longitude at which activity ends
``ra`` / ``dec``    Radiant position at maximum, degrees (J2000)
``zhr``             Zenithal hourly rate at maximum, meteors/hour
``r``               Population index (higher means relatively more faint meteors)
``v_geo``           Geocentric velocity, km/s
``constellation``   Constellation containing the radiant
``parent``          Parent body, or ``None`` where unidentified
``variable``        ``True`` for showers with unpredictable outburst behaviour
``b``               Activity-profile slope; ``None`` means derive it from the window
==================  =============================================================

About ``b``
-----------

The activity profile is ``ZHR = ZHR_max * 10 ** (-b * |delta_solar_longitude|)``, so ``b``
controls how sharply activity falls away from maximum. It matters more than it looks: the
Quadrantids are at half maximum for roughly fourteen *hours*, while the Taurids run for weeks,
and no single default describes both.

Values here come from the IMO Meteor Shower Calendar working list (originally Jenniskens 1994,
*Meteor stream activity*). Where a shower has no sourced value, ``b`` is ``None`` and
:func:`meteor.activity_slope` derives one from the activity window instead. That derivation is a
fallback, not an equal alternative: an activity window describes where a shower is detectable at
all, which is far wider than its peak, so a derived slope always comes out too shallow. The
remaining showers on the fallback are minor ones whose peak rates are low enough that the
difference does not change what an observer would do.
"""

from __future__ import annotations

from typing import Any, Dict, List

#: Fields every catalog entry must define.
REQUIRED_FIELDS = (
    "code", "name", "sol_lon_max", "sol_lon_start", "sol_lon_end",
    "ra", "dec", "zhr", "r", "v_geo", "constellation", "parent", "variable", "b",
)

METEOR_SHOWERS: List[Dict[str, Any]] = [
    {
        "code": "QUA", "name": "Quadrantids",
        "sol_lon_max": 283.15, "sol_lon_start": 276.25, "sol_lon_end": 291.78,
        "ra": 230.0, "dec": 49.0,
        "zhr": 110, "r": 2.1, "v_geo": 41,
        "constellation": "Bootes", "parent": "(196256) 2003 EH1",
        "variable": False, "b": 2.2,
    },
    {
        "code": "GNO", "name": "Gamma Normids",
        "sol_lon_max": 354.0, "sol_lon_start": 336.39, "sol_lon_end": 7.33,
        "ra": 239.0, "dec": -50.0,
        "zhr": 6, "r": 2.4, "v_geo": 56,
        "constellation": "Norma", "parent": None,
        "variable": False, "b": None,
    },
    {
        "code": "LYR", "name": "Lyrids",
        "sol_lon_max": 32.32, "sol_lon_start": 24.07, "sol_lon_end": 39.68,
        "ra": 271.0, "dec": 34.0,
        "zhr": 18, "r": 2.1, "v_geo": 49,
        "constellation": "Lyra", "parent": "C/1861 G1 Thatcher",
        "variable": False, "b": 0.22,
    },
    {
        "code": "PPU", "name": "Pi Puppids",
        "sol_lon_max": 33.5, "sol_lon_start": 25.05, "sol_lon_end": 37.74,
        "ra": 110.0, "dec": -45.0,
        "zhr": 5, "r": 2.0, "v_geo": 18,
        "constellation": "Puppis", "parent": "26P/Grigg-Skjellerup",
        "variable": True, "b": None,
    },
    {
        "code": "ETA", "name": "Eta Aquariids",
        "sol_lon_max": 45.5, "sol_lon_start": 28.96, "sol_lon_end": 66.71,
        "ra": 338.0, "dec": -1.0,
        "zhr": 50, "r": 2.4, "v_geo": 66,
        "constellation": "Aquarius", "parent": "1P/Halley",
        "variable": False, "b": 0.08,
    },
    {
        "code": "ELY", "name": "Eta Lyrids",
        "sol_lon_max": 48.0, "sol_lon_start": 42.59, "sol_lon_end": 53.23,
        "ra": 287.0, "dec": 44.0,
        "zhr": 3, "r": 3.0, "v_geo": 43,
        "constellation": "Lyra", "parent": "C/1983 H1 IRAS-Araki-Alcock",
        "variable": False, "b": None,
    },
    {
        "code": "JBO", "name": "June Bootids",
        "sol_lon_max": 95.7, "sol_lon_start": 90.62, "sol_lon_end": 100.16,
        "ra": 224.0, "dec": 48.0,
        "zhr": 2, "r": 2.2, "v_geo": 18,
        "constellation": "Bootes", "parent": "7P/Pons-Winnecke",
        "variable": True, "b": None,
    },
    {
        "code": "PAU", "name": "Piscis Austrinids",
        "sol_lon_max": 125.0, "sol_lon_start": 112.56, "sol_lon_end": 137.41,
        "ra": 341.0, "dec": -30.0,
        "zhr": 5, "r": 3.2, "v_geo": 35,
        "constellation": "Piscis Austrinus", "parent": None,
        "variable": False, "b": None,
    },
    {
        "code": "CAP", "name": "Alpha Capricornids",
        "sol_lon_max": 127.0, "sol_lon_start": 101.11, "sol_lon_end": 142.21,
        "ra": 307.0, "dec": -10.0,
        "zhr": 5, "r": 2.5, "v_geo": 23,
        "constellation": "Capricornus", "parent": "169P/NEAT",
        "variable": False, "b": 0.056,
    },
    {
        "code": "SDA", "name": "Southern Delta Aquariids",
        "sol_lon_max": 127.0, "sol_lon_start": 109.69, "sol_lon_end": 149.90,
        "ra": 340.0, "dec": -16.0,
        "zhr": 25, "r": 3.2, "v_geo": 41,
        "constellation": "Aquarius", "parent": "96P/Machholz",
        "variable": False, "b": 0.091,
    },
    {
        "code": "PER", "name": "Perseids",
        "sol_lon_max": 140.0, "sol_lon_start": 114.46, "sol_lon_end": 150.87,
        "ra": 48.0, "dec": 58.0,
        "zhr": 100, "r": 2.2, "v_geo": 59,
        "constellation": "Perseus", "parent": "109P/Swift-Tuttle",
        "variable": False, "b": 0.2,
    },
    {
        "code": "KCG", "name": "Kappa Cygnids",
        "sol_lon_max": 145.0, "sol_lon_start": 130.70, "sol_lon_end": 151.83,
        "ra": 286.0, "dec": 59.0,
        "zhr": 3, "r": 3.0, "v_geo": 25,
        "constellation": "Cygnus", "parent": None,
        "variable": False, "b": 0.068,
    },
    {
        "code": "AUR", "name": "Aurigids",
        "sol_lon_max": 158.6, "sol_lon_start": 154.73, "sol_lon_end": 162.47,
        "ra": 91.0, "dec": 39.0,
        "zhr": 6, "r": 2.6, "v_geo": 66,
        "constellation": "Auriga", "parent": "C/1911 N1 Kiess",
        "variable": True, "b": 0.19,
    },
    {
        "code": "SPE", "name": "September Epsilon Perseids",
        "sol_lon_max": 166.7, "sol_lon_start": 162.47, "sol_lon_end": 178.04,
        "ra": 48.0, "dec": 40.0,
        "zhr": 5, "r": 3.0, "v_geo": 64,
        "constellation": "Perseus", "parent": None,
        "variable": False, "b": 0.19,
    },
    {
        "code": "DRA", "name": "Draconids",
        "sol_lon_max": 195.4, "sol_lon_start": 192.76, "sol_lon_end": 196.71,
        "ra": 262.0, "dec": 54.0,
        "zhr": 5, "r": 2.6, "v_geo": 20,
        "constellation": "Draco", "parent": "21P/Giacobini-Zinner",
        "variable": True, "b": 2.5,
    },
    {
        "code": "STA", "name": "Southern Taurids",
        "sol_lon_max": 197.0, "sol_lon_start": 167.32, "sol_lon_end": 237.67,
        "ra": 32.0, "dec": 9.0,
        "zhr": 5, "r": 2.3, "v_geo": 27,
        "constellation": "Taurus", "parent": "2P/Encke",
        "variable": False, "b": 0.026,
    },
    {
        "code": "ORI", "name": "Orionids",
        "sol_lon_max": 208.0, "sol_lon_start": 188.82, "sol_lon_end": 224.59,
        "ra": 95.0, "dec": 16.0,
        "zhr": 20, "r": 2.5, "v_geo": 66,
        "constellation": "Orion", "parent": "1P/Halley",
        "variable": False, "b": 0.12,
    },
    {
        "code": "LMI", "name": "Leonis Minorids",
        "sol_lon_max": 211.0, "sol_lon_start": 205.62, "sol_lon_end": 213.58,
        "ra": 162.0, "dec": 37.0,
        "zhr": 2, "r": 3.0, "v_geo": 62,
        "constellation": "Leo Minor", "parent": "C/1739 K1",
        "variable": False, "b": None,
    },
    {
        "code": "NTA", "name": "Northern Taurids",
        "sol_lon_max": 230.0, "sol_lon_start": 206.62, "sol_lon_end": 257.93,
        "ra": 58.0, "dec": 22.0,
        "zhr": 5, "r": 2.3, "v_geo": 29,
        "constellation": "Taurus", "parent": "2P/Encke",
        "variable": False, "b": 0.026,
    },
    {
        "code": "LEO", "name": "Leonids",
        "sol_lon_max": 235.27, "sol_lon_start": 223.59, "sol_lon_end": 247.78,
        "ra": 152.0, "dec": 22.0,
        "zhr": 15, "r": 2.5, "v_geo": 71,
        "constellation": "Leo", "parent": "55P/Tempel-Tuttle",
        "variable": True, "b": 0.55,
    },
    {
        "code": "AMO", "name": "Alpha Monocerotids",
        "sol_lon_max": 239.32, "sol_lon_start": 232.63, "sol_lon_end": 242.72,
        "ra": 117.0, "dec": 1.0,
        "zhr": 3, "r": 2.4, "v_geo": 65,
        "constellation": "Monoceros", "parent": None,
        "variable": True, "b": 2.5,
    },
    {
        "code": "PHO", "name": "Phoenicids",
        "sol_lon_max": 250.0, "sol_lon_start": 245.76, "sol_lon_end": 256.91,
        "ra": 18.0, "dec": -53.0,
        "zhr": 3, "r": 2.8, "v_geo": 18,
        "constellation": "Phoenix", "parent": "289P/Blanpain",
        "variable": True, "b": None,
    },
    {
        "code": "AND", "name": "Andromedids",
        "sol_lon_max": 251.0, "sol_lon_start": 242.72, "sol_lon_end": 253.87,
        "ra": 25.0, "dec": 31.0,
        "zhr": 3, "r": 3.0, "v_geo": 17,
        "constellation": "Andromeda", "parent": "3D/Biela",
        "variable": True, "b": None,
    },
    {
        "code": "PUP", "name": "Puppid-Velids",
        "sol_lon_max": 255.0, "sol_lon_start": 248.79, "sol_lon_end": 263.01,
        "ra": 123.0, "dec": -45.0,
        "zhr": 10, "r": 2.9, "v_geo": 40,
        "constellation": "Puppis", "parent": None,
        "variable": False, "b": 0.034,
    },
    {
        "code": "MON", "name": "December Monocerotids",
        "sol_lon_max": 257.0, "sol_lon_start": 244.74, "sol_lon_end": 268.10,
        "ra": 100.0, "dec": 8.0,
        "zhr": 3, "r": 3.0, "v_geo": 41,
        "constellation": "Monoceros", "parent": "C/1917 F1 Mellish",
        "variable": False, "b": 0.25,
    },
    {
        "code": "HYD", "name": "Sigma Hydrids",
        "sol_lon_max": 257.0, "sol_lon_start": 250.82, "sol_lon_end": 268.10,
        "ra": 127.0, "dec": 2.0,
        "zhr": 7, "r": 3.0, "v_geo": 58,
        "constellation": "Hydra", "parent": None,
        "variable": False, "b": None,
    },
    {
        "code": "GEM", "name": "Geminids",
        "sol_lon_max": 262.2, "sol_lon_start": 251.84, "sol_lon_end": 265.04,
        "ra": 112.0, "dec": 33.0,
        "zhr": 150, "r": 2.6, "v_geo": 35,
        "constellation": "Gemini", "parent": "(3200) Phaethon",
        "variable": False, "b": 0.39,
    },
    {
        "code": "COM", "name": "Comae Berenicids",
        "sol_lon_max": 264.0, "sol_lon_start": 259.96, "sol_lon_end": 302.98,
        "ra": 175.0, "dec": 18.0,
        "zhr": 3, "r": 3.0, "v_geo": 65,
        "constellation": "Coma Berenices", "parent": None,
        "variable": False, "b": 0.18,
    },
    {
        "code": "URS", "name": "Ursids",
        "sol_lon_max": 270.7, "sol_lon_start": 265.04, "sol_lon_end": 274.21,
        "ra": 217.0, "dec": 76.0,
        "zhr": 10, "r": 3.0, "v_geo": 33,
        "constellation": "Ursa Minor", "parent": "8P/Tuttle",
        "variable": True, "b": 0.9,
    },
]
