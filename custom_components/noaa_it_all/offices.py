"""What kind of entry this is, and where its office's data comes from.

A weather entry names the NWS forecast office for its location; a surf entry
names one coastal office that issues Surf Zone Forecasts, and a Space entry the
office its location is in. The tables in const.py cover only those coastal
offices, so anything they do not cover for an inland office is stored on the
entry at setup or estimated.
"""

import math
import re

from .const import (
    CONF_ENTRY_TYPE,
    ENTRY_TYPE_HURRICANE,
    ENTRY_TYPE_MARINE,
    ENTRY_TYPE_SPACE,
    ENTRY_TYPE_WEATHER,
    CONF_OFFICE_CODE,
    CONF_RADAR_SITE,
    CONF_SURF_OFFICE_CODE,
    ENTRY_TYPE_SURF,
    GEOMAGNETIC_POLE_LAT,
    GEOMAGNETIC_POLE_LON,
    OFFICE_BUOY_STATIONS,
    OFFICE_COORDINATES,
    OFFICE_MAGNETIC_LATITUDES,
    OFFICE_RADAR_SITES,
    OFFICE_TIDE_STATIONS,
)

# The surf entities, as (platform, unique ID suffix). Their unique IDs are
# noaa_<office>_<suffix>, from the days surf lived in the weather entry, so an
# upgraded entry's entities keep their IDs and history in the surf entry.
RIP_CURRENT_RISK = ("sensor", "rip_current_risk")
UNSAFE_TO_SWIM = ("binary_sensor", "unsafe_to_swim")
WATER_TEMPERATURE = ("sensor", "water_temperature")
SURF_HEIGHT = ("sensor", "surf_height")
ALL_SURF_ENTITIES = (RIP_CURRENT_RISK, UNSAFE_TO_SWIM, WATER_TEMPERATURE, SURF_HEIGHT)

# The Space entities, as (platform, unique ID suffix). Their unique IDs are
# noaa_<office>_<suffix>, from the days Space lived in the weather entry, so an
# upgraded entry's entities keep their IDs and history in the Space entry.
SPACE_ENTITIES = (
    ("sensor", "geomagnetic_storm"),
    ("sensor", "geomagnetic_storm_interpretation"),
    ("sensor", "planetary_k_index"),
    ("sensor", "planetary_k_index_rating"),
    ("sensor", "aurora_next_time"),
    ("sensor", "aurora_duration"),
    ("sensor", "aurora_visibility_probability"),
    ("sensor", "solar_radiation_storm_alerts"),
    ("sensor", "meteor_shower_activity"),
    ("sensor", "next_meteor_shower"),
    ("sensor", "meteor_viewing_score"),
    ("sensor", "next_eclipse"),
    ("sensor", "next_eclipse_time"),
    ("sensor", "eclipse_coverage"),
    ("sensor", "eclipse_viewing_score"),
    ("binary_sensor", "meteor_shower_active"),
    ("binary_sensor", "eclipse_visible_now"),
    ("binary_sensor", "eclipse_coming_up"),
    ("image", "geoelectric_image"),
    ("image", "aurora_image"),
)

# The hurricane entry's entities, as (platform, unique ID). The same IDs they
# had when the first weather entry hosted them, so they keep their history.
HURRICANE_ENTITIES = (
    ("sensor", "noaa_hurricane_alerts"),
    ("sensor", "noaa_hurricane_activity"),
    ("image", "noaa_hurricane_outlook_image"),
    ("image", "noaa_hurricane_pacific_outlook_image"),
    ("image", "noaa_hurricane_goes_air_mass"),
    ("image", "noaa_hurricane_goes_geocolor"),
)


# A NEXRAD or TDWR site identifier, e.g. KESX. The site names a directory of
# stored radar frames, which is deleted with the entry, so anything else (a
# path such as "../..") is refused rather than joined onto the frames folder.
_RADAR_SITE = re.compile(r"[A-Z]{4}")


def is_radar_site(value):
    """Return True if ``value`` is a well-formed radar site identifier."""
    return isinstance(value, str) and _RADAR_SITE.fullmatch(value) is not None


def entry_type(conf):
    """Return what an entry is: weather, surf, marine, space or hurricane."""
    return conf.get(CONF_ENTRY_TYPE, ENTRY_TYPE_WEATHER)


def is_surf_entry(conf):
    """Return True for a surf entry."""
    return entry_type(conf) == ENTRY_TYPE_SURF


def is_hurricane_entry(conf):
    """Return True for the hurricane entry."""
    return entry_type(conf) == ENTRY_TYPE_HURRICANE


def is_marine_entry(conf):
    """Return True for a marine entry: one zone's nearshore marine forecast."""
    return entry_type(conf) == ENTRY_TYPE_MARINE


def is_weather_entry(conf):
    """Return True for a weather entry: a location's forecast, alerts and radar."""
    return entry_type(conf) == ENTRY_TYPE_WEATHER


def is_space_entry(conf):
    """Return True for a Space entry: space weather, aurora, meteors and eclipses."""
    return entry_type(conf) == ENTRY_TYPE_SPACE


def surf_entities(office):
    """Return the surf entities a surf entry for ``office`` creates.

    Rip current risk always comes from the forecast. Water temperature needs a
    tide station and surf height a buoy, and an office without one would only
    ever show unknown, so it does not get that entity.
    """
    entities = [RIP_CURRENT_RISK, UNSAFE_TO_SWIM]
    if office in OFFICE_TIDE_STATIONS:
        entities.append(WATER_TEMPERATURE)
    if office in OFFICE_BUOY_STATIONS:
        entities.append(SURF_HEIGHT)
    return entities


def surf_office(conf):
    """Return the surf office a weather entry from before 0.8.0 used, or None.

    Only read when migrating. A 0.8.0 test build saved the choice; an older
    entry always used its own office, which was always a coastal one.
    """
    if CONF_SURF_OFFICE_CODE in conf:
        return conf[CONF_SURF_OFFICE_CODE]
    office = conf.get(CONF_OFFICE_CODE)
    return office if office in OFFICE_COORDINATES else None


def radar_site(conf):
    """Return the NEXRAD site for the entry's radar images, or None."""
    if not is_weather_entry(conf):
        return None
    stored = conf.get(CONF_RADAR_SITE)
    if is_radar_site(stored):
        return stored
    return OFFICE_RADAR_SITES.get(conf.get(CONF_OFFICE_CODE))


def geomagnetic_latitude(latitude, longitude):
    """Return the dipole geomagnetic latitude in degrees of a point."""
    phi = math.radians(latitude)
    pole_phi = math.radians(GEOMAGNETIC_POLE_LAT)
    dlon = math.radians(longitude - GEOMAGNETIC_POLE_LON)
    return math.degrees(math.asin(
        math.sin(phi) * math.sin(pole_phi)
        + math.cos(phi) * math.cos(pole_phi) * math.cos(dlon)
    ))


def magnetic_latitude(office_code, latitude=None, longitude=None, default=0.0):
    """Return the magnetic latitude the aurora sensors judge visibility by.

    The table covers the coastal offices. Any other office is estimated from
    the configured location, so an inland office does not read as the equator.
    """
    if office_code in OFFICE_MAGNETIC_LATITUDES:
        return OFFICE_MAGNETIC_LATITUDES[office_code]
    if latitude is None or longitude is None:
        return default
    return round(geomagnetic_latitude(latitude, longitude), 1)
