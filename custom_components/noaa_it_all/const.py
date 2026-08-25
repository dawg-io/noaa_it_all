"""Constants for NOAA Integration."""

import json
from pathlib import Path

DOMAIN = "noaa_it_all"


def _manifest() -> dict:
    """Return the parsed ``manifest.json`` sitting next to this file.

    Read here so the version and documentation URL have exactly one home and
    a release bump does not have to be remembered in two places. Home
    Assistant imports custom integration modules in an executor thread, and
    this is a single small local file, so the read does not block the event
    loop.
    """
    try:
        with open(Path(__file__).parent / "manifest.json", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        # A broken manifest means Home Assistant will not load the
        # integration at all; fall back to sentinels rather than raising an
        # obscure error while merely importing constants.
        return {}


_MANIFEST = _manifest()

VERSION = _MANIFEST.get("version") or "0.0.0"
DOCUMENTATION_URL = (
    _MANIFEST.get("documentation") or "https://github.com/dawg-io/noaa_it_all"
)

# Global (non office-specific) device identifiers.
# Hurricane data comes from the National Hurricane Center and is global,
# not tied to any single NWS forecast office, so all hurricane entities
# are grouped under a single dedicated device.
HURRICANE_DEVICE_ID = "noaa_hurricane"
HURRICANE_DEVICE_NAME = "NOAA Hurricane"

# Key used in hass.data[DOMAIN] to track whether the global hurricane
# entities have already been added by an earlier config entry, so they
# are not duplicated when multiple offices are configured. The value
# stored is the ``entry_id`` of the *owning* config entry (not just a
# boolean), so that if the owner is unloaded while other entries
# remain we can detect ownership transfer and re-create the entities.
HURRICANE_SENSORS_ADDED_KEY = "_hurricane_sensors_added"
HURRICANE_IMAGES_ADDED_KEY = "_hurricane_images_added"

# Key for the single shared HurricaneCoordinator. Hurricane data is
# global (NHC) so all config entries share one coordinator instead of
# each entry creating its own and triggering redundant API calls.
HURRICANE_COORDINATOR_KEY = "_hurricane_coordinator"

# Configuration keys
CONF_OFFICE_CODE = "office_code"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_RADAR_LOOP_HOURS = "radar_loop_hours"

# Default values
DEFAULT_SCAN_INTERVAL = 10  # minutes
REQUEST_TIMEOUT = 30  # seconds
# Identifies this integration to NOAA. api.weather.gov requires a User-Agent
# and asks that it be unique to the application, with a website or email so
# they can make contact instead of simply blocking traffic they cannot place.
# The version is part of the string so an old release can be told apart from a
# fixed one -- built from manifest.json so bumping the release is enough.
# To add a contact address later, put it in the parenthesised part alongside
# the URL: f"... (+{DOCUMENTATION_URL}, you@example.com)".
USER_AGENT = f"{DOMAIN}/{VERSION} (+{DOCUMENTATION_URL})"

# Image entities keep the last successfully fetched frame and re-fetch on a
# background timer, so a transient upstream failure leaves the previous
# picture on screen.  These thresholds keep the log quiet while that is
# happening: a blip stays at debug level, a short outage warns once, and only
# a sustained outage is reported as an error (and then only periodically).
IMAGE_FAILURE_WARN_AFTER = 3   # consecutive failed refreshes (~30 min)
IMAGE_FAILURE_ERROR_AFTER = 6  # consecutive failed refreshes (~1 hour)

# Images are fetched in the background rather than while serving an HTTP
# request, so this is independent of REQUEST_TIMEOUT (which belongs to the
# coordinators) and of Home Assistant's own 10s image-proxy budget.
IMAGE_FETCH_TIMEOUT = 20  # seconds
IMAGE_MAX_BYTES = 20 * 1024 * 1024  # refuse absurd payloads rather than cache them

# -------------------------------------------------------------------
# Radar loop
# -------------------------------------------------------------------
# NOAA publishes a ready-made radar animation, but it is fixed at ten frames
# covering roughly fifty minutes, which is long enough to see that it is
# raining and too short to see where the rain came from.  NOAA also keeps only
# those ten frames on the server, so a longer loop cannot be downloaded -- it
# has to be accumulated here, one frame per refresh, and assembled locally.
#
# The window is measured in hours and 0 means "serve NOAA's own loop
# unchanged", which is both the escape hatch and the behaviour every release
# before this one had.
DEFAULT_RADAR_LOOP_HOURS = 24
RADAR_LOOP_MAX_HOURS = 24

# The assembled animation is re-downloaded by every open dashboard each time it
# changes, so frame count is a bandwidth and memory decision, not a fidelity
# one.  Seventy-two frames spreads a 24-hour window over 20-minute steps: storm
# motion stays legible, the GIF lands around 1-2 MB, and a cycle plays in about
# ten seconds, which is roughly as long as anyone watches a loop.  Shorter
# windows get proportionally finer steps from the same cap -- a six-hour loop
# works out at one frame per five minutes, i.e. every scan NOAA publishes.
RADAR_LOOP_MAX_FRAMES = 72
RADAR_LOOP_MIN_FRAMES = 6  # below this the local loop is worse than NOAA's
RADAR_LOOP_FRAME_MS = 120  # browsers clamp anything under ~20ms
RADAR_LOOP_LAST_FRAME_MS = 1500  # hold on "now" so the loop reads as a loop
RADAR_LOOP_MAX_BYTES = 8 * 1024 * 1024

# Frames are composited onto an opaque background before being combined.  The
# source frames are transparent overlays with a palette each, and reconciling
# per-frame transparency across differing palettes is the single most reliable
# way to produce a psychedelic radar loop.  Compositing removes the problem.
RADAR_LOOP_BACKGROUND = (0, 0, 0)

# Frames live in <config>/noaa_it_all/radar_frames/<SITE>/.  Every polled frame
# inside the window is kept, not just the ones the current window displays, so
# that changing the duration re-samples from real history instead of starting
# over.  That is ~144 files, a few MB, per radar site.
RADAR_FRAME_DIR = "radar_frames"
RADAR_FRAME_MAX_FILES = 200  # backstop against a directory growing unbounded
# A frame dated beyond now + this is the product of a wrong clock rather than a
# scan we have not reached yet.  Ageing never reaches such a frame, so it is
# discarded outright; the slack absorbs ordinary skew between us and NOAA.
RADAR_FRAME_FUTURE_SLACK_MINUTES = 60

# API endpoints
NWS_SRF_URL = "https://forecast.weather.gov/product.php?site={office}&issuedby={office}&product=SRF&format=TXT"
NWS_API_BASE = "https://api.weather.gov"
NWS_POINTS_URL = "https://api.weather.gov/points/{lat},{lon}"
NWS_OBSERVATIONS_URL = "https://api.weather.gov/stations/{station}/observations/latest"
NWS_RADAR_BASE_URL = "https://radar.weather.gov/ridge/standard/{radar}_0.gif"
NWS_RADAR_LOOP_URL = "https://radar.weather.gov/ridge/standard/{radar}_loop.gif"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?point={lat},{lon}"
NWS_ALERTS_ZONE_URL = "https://api.weather.gov/alerts/active?zone={zone}"
NWS_GRIDPOINT_URL = "https://api.weather.gov/gridpoints/{office}/{gridX},{gridY}"
NWS_AFD_URL = "https://forecast.weather.gov/product.php?site={office}&issuedby={office}&product=AFD&format=TXT"

# NOAA CO-OPS API for water temperature (Tides and Currents)
COOPS_WATER_TEMP_URL = (
    "https://api.tidesandcurrents.noaa.gov/api/prod/datagetter"
    "?station={station}&product=water_temperature&units=english"
    "&time_zone=lst_ldt&format=json&date=latest&application=HomeAssistant"
)

# NDBC real-time buoy data for wave height
NDBC_REALTIME_URL = "https://www.ndbc.noaa.gov/data/realtime2/{station}.txt"

# NWS office to observation station mapping
# Each office uses the primary weather observation station in their area
OFFICE_STATION_IDS = {
    "AKQ": "KORF",  # Norfolk International Airport
    "APX": "KGLS",  # Gaylord
    "BOX": "KBOS",  # Boston Logan Airport
    "BRO": "KBRO",  # Brownsville South Padre Island
    "CAR": "KCAR",  # Caribou Municipal Airport
    "CHS": "KCHS",  # Charleston International Airport
    "CLE": "KCLE",  # Cleveland Hopkins International Airport
    "CRP": "KCRP",  # Corpus Christi International Airport
    "DLH": "KDLH",  # Duluth International Airport
    "DTX": "KDTW",  # Detroit Metro Airport
    "EKA": "KACV",  # Arcata-Eureka Airport
    "GRB": "KGRB",  # Green Bay Austin Straubel Airport
    "GRR": "KGRR",  # Gerald R. Ford Airport
    "GUM": "PGUM",  # Guam International Airport
    "GYX": "KPWM",  # Portland International Jetport
    "HFO": "PHNL",  # Honolulu International Airport
    "ILM": "KILM",  # Wilmington International Airport
    "IWX": "KSBN",  # South Bend International Airport
    "JAX": "KJAX",  # Jacksonville International Airport
    "LOT": "KORD",  # Chicago O'Hare International Airport
    "LOX": "KLAX",  # Los Angeles International Airport
    "MFL": "KMIA",  # Miami International Airport
    "MFR": "KMFR",  # Rogue Valley International-Medford Airport
    "MHX": "KMRH",  # Michael J. Smith Field
    "MKX": "KMKE",  # Milwaukee Mitchell International Airport
    "MLB": "KMLB",  # Melbourne Orlando International Airport
    "MOB": "KMOB",  # Mobile Regional Airport
    "MQT": "KSAW",  # Sawyer International Airport
    "MTR": "KSFO",  # San Francisco International Airport
    "OKX": "KJFK",  # John F. Kennedy International Airport
    "PHI": "KPHL",  # Philadelphia International Airport
    "PQR": "KPDX",  # Portland International Airport
    "SGX": "KSAN",  # San Diego International Airport
    "SJU": "TJSJ",  # Luis Muñoz Marín International Airport
    "TAE": "KTLH",  # Tallahassee International Airport
    "TBW": "KTPA",  # Tampa International Airport
}

# NWS office to CO-OPS tide station mapping (water temperature)
# Station IDs from https://tidesandcurrents.noaa.gov
OFFICE_TIDE_STATIONS = {
    "AKQ": "8638610",   # Sewells Point, VA
    "BOX": "8443970",   # Boston, MA
    "BRO": "8779770",   # Port Isabel, TX
    "CAR": "8413320",   # Bar Harbor, ME
    "CHS": "8665530",   # Charleston, SC
    "CLE": "9063063",   # Cleveland, OH
    "CRP": "8775870",   # Bob Hall Pier, TX
    "DLH": "9099064",   # Duluth, MN
    "EKA": "9418767",   # North Spit, CA
    "GRB": "9087068",   # Sturgeon Bay, WI
    "GUM": "1630000",   # Apra Harbor, Guam
    "GYX": "8418150",   # Portland, ME
    "HFO": "1612340",   # Honolulu, HI
    "ILM": "8658163",   # Wrightsville Beach, NC
    "JAX": "8720218",   # Mayport, FL
    "LOX": "9410660",   # Los Angeles, CA
    "MFL": "8723214",   # Virginia Key, FL
    "MHX": "8656483",   # Beaufort, NC
    "MKX": "9087044",   # Milwaukee, WI
    "MLB": "8721604",   # Trident Pier, FL
    "MOB": "8737048",   # Mobile State Docks, AL
    "MQT": "9099018",   # Marquette, MI
    "MTR": "9414290",   # San Francisco, CA
    "OKX": "8518750",   # The Battery, NY
    "PHI": "8545240",   # Philadelphia, PA
    "PQR": "9439040",   # Astoria, OR
    "SGX": "9410170",   # San Diego, CA
    "SJU": "9755371",   # San Juan, PR
    "TAE": "8728690",   # Apalachicola, FL
    "TBW": "8726520",   # St. Petersburg, FL
}

# NWS office to NDBC buoy station mapping (wave height)
# Station IDs from https://www.ndbc.noaa.gov
OFFICE_BUOY_STATIONS = {
    "AKQ": "44014",   # Virginia Beach, VA
    "BOX": "44013",   # Boston 16 NM east of Boston, MA
    "BRO": "42020",   # Corpus Christi area
    "CHS": "41004",   # EDISTO - 41 NM southeast of Charleston, SC
    "CRP": "42020",   # Corpus Christi, TX
    "EKA": "46022",   # Eel River, CA
    "GYX": "44007",   # Portland, ME
    "HFO": "51202",   # Waimea Bay, HI
    "ILM": "41110",   # Wrightsville Beach Nearshore, NC
    "JAX": "41112",   # St. Augustine, FL
    "LOX": "46222",   # San Pedro, CA
    "MFL": "41047",   # Canaveral East, FL
    "MHX": "41159",   # Cape Lookout Nearshore, NC
    "MLB": "41113",   # Cape Canaveral Nearshore, FL
    "MOB": "42040",   # Mobile South, AL
    "MTR": "46026",   # San Francisco, CA
    "OKX": "44025",   # Long Island, NY
    "PQR": "46029",   # Columbia River Bar, OR
    "SGX": "46235",   # Point Loma South, CA
    "SJU": "41053",   # San Juan, PR
    "TAE": "42039",   # Pensacola, FL
    "TBW": "42036",   # West Tampa, FL
}

# NWS office to radar site mapping
# Each office maps to the primary NEXRAD radar station covering their area
OFFICE_RADAR_SITES = {
    "AKQ": "KAKQ",  # Norfolk/Richmond - Wakefield, VA
    "APX": "KAPX",  # Gaylord, MI
    "BOX": "KBOX",  # Boston, MA - Taunton
    "BRO": "KBRO",  # Brownsville, TX
    "CAR": "KCBW",  # Caribou, ME - Houlton
    "CHS": "KCLX",  # Charleston, SC - Grays
    "CLE": "KCLE",  # Cleveland, OH
    "CRP": "KCRP",  # Corpus Christi, TX
    "DLH": "KDLH",  # Duluth, MN
    "DTX": "KDTX",  # Detroit, MI - White Lake
    "EKA": "KBHX",  # Eureka, CA - Blue Canyon
    "GRB": "KGRB",  # Green Bay, WI
    "GRR": "KGRR",  # Grand Rapids, MI
    "GUM": "PGUA",  # Guam - Barrigada
    "GYX": "KGYX",  # Portland, ME - Gray
    "HFO": "PHKI",  # Honolulu, HI - South Shore
    "ILM": "KLTX",  # Wilmington, NC - Shallotte
    "IWX": "KIWX",  # Northern Indiana - North Webster
    "JAX": "KJAX",  # Jacksonville, FL
    "LOT": "KLOT",  # Chicago, IL - Romeoville
    "LOX": "KSOX",  # Los Angeles, CA - Santa Ana Mountains
    "MFL": "KAMX",  # Miami, FL
    "MFR": "KMAX",  # Medford, OR
    "MHX": "KMHX",  # Newport/Morehead City, NC
    "MKX": "KMKX",  # Milwaukee, WI - Dousman
    "MLB": "KMLB",  # Melbourne, FL
    "MOB": "KMOB",  # Mobile, AL
    "MQT": "KMQT",  # Marquette, MI
    "MTR": "KMUX",  # San Francisco, CA - Mt. Umunhum
    "OKX": "KOKX",  # New York, NY - Upton
    "PHI": "KDIX",  # Philadelphia, PA - Mt. Holly, NJ
    "PQR": "KRTX",  # Portland, OR
    "SGX": "KNKX",  # San Diego, CA
    "SJU": "TJUA",  # San Juan, PR - Cayey
    "TAE": "KTLH",  # Tallahassee, FL
    "TBW": "KTBW",  # Tampa, FL - Ruskin
}

# NWS forecast office approximate geographic coordinates (lat, lon).
# Used by the config flow to suggest the closest office to the user's
# Home Assistant Home zone via a haversine distance calculation.
OFFICE_COORDINATES = {
    "AKQ": (36.9840, -77.0072),    # Wakefield, VA (Norfolk/Richmond)
    "APX": (44.9075, -84.7197),    # Gaylord, MI
    "BOX": (41.9559, -71.1314),    # Taunton, MA (Boston)
    "BRO": (25.9140, -97.4220),    # Brownsville, TX
    "CAR": (46.8714, -68.0142),    # Caribou, ME
    "CHS": (32.8986, -80.0408),    # Charleston, SC
    "CLE": (41.4117, -81.8497),    # Cleveland, OH
    "CRP": (27.7700, -97.5067),    # Corpus Christi, TX
    "DLH": (46.8369, -92.1833),    # Duluth, MN
    "DTX": (42.6997, -83.4716),    # White Lake, MI (Detroit)
    "EKA": (40.9789, -124.1085),   # Eureka, CA
    "GRB": (44.4983, -88.1114),    # Green Bay, WI
    "GRR": (42.8939, -85.5447),    # Grand Rapids, MI
    "GUM": (13.4828, 144.7997),    # Guam
    "GYX": (43.8915, -70.2569),    # Gray, ME (Portland)
    "HFO": (21.3245, -158.0250),   # Honolulu, HI
    "ILM": (34.2675, -77.9011),    # Wilmington, NC
    "IWX": (41.3589, -85.7000),    # North Webster, IN (Northern Indiana)
    "JAX": (30.4842, -81.7019),    # Jacksonville, FL
    "LOT": (41.6042, -88.0842),    # Romeoville, IL (Chicago)
    "LOX": (34.2475, -119.1842),   # Oxnard, CA (Los Angeles)
    "MFL": (25.7547, -80.3839),    # Miami, FL
    "MFR": (42.3650, -122.8722),   # Medford, OR
    "MHX": (34.7758, -76.8783),    # Newport/Morehead City, NC
    "MKX": (42.9669, -88.5506),    # Sullivan, WI (Milwaukee)
    "MLB": (28.1131, -80.6539),    # Melbourne, FL
    "MOB": (30.6797, -88.2400),    # Mobile, AL
    "MQT": (46.5311, -87.5489),    # Negaunee, MI (Marquette)
    "MTR": (36.5950, -121.8480),   # Monterey, CA (San Francisco)
    "OKX": (40.8656, -72.8639),    # Upton, NY (New York)
    "PHI": (39.9942, -74.8336),    # Mount Holly, NJ (Philadelphia)
    "PQR": (45.5503, -122.5667),   # Portland, OR
    "SGX": (32.8331, -117.2756),   # San Diego, CA
    "SJU": (18.4314, -66.0042),    # San Juan, PR
    "TAE": (30.4072, -84.3500),    # Tallahassee, FL
    "TBW": (27.7053, -82.4014),    # Ruskin, FL (Tampa Bay)
}

# Aurora visibility mapping - approximate magnetic latitudes for NWS offices
OFFICE_MAGNETIC_LATITUDES = {
    "AKQ": 40.2,  # Norfolk, VA
    "APX": 51.8,  # Gaylord, MI
    "BOX": 42.1,  # Boston, MA
    "BRO": 25.9,  # Brownsville, TX
    "CAR": 56.7,  # Caribou, ME
    "CHS": 32.8,  # Charleston, SC
    "CLE": 46.4,  # Cleveland, OH
    "CRP": 27.8,  # Corpus Christi, TX
    "DLH": 56.8,  # Duluth, MN
    "DTX": 47.6,  # Detroit, MI
    "EKA": 50.5,  # Eureka, CA
    "GRB": 49.5,  # Green Bay, WI
    "GRR": 47.9,  # Grand Rapids, MI
    "GUM": 3.3,   # Guam
    "GYX": 43.7,  # Portland, ME
    "HFO": 11.4,  # Honolulu, HI
    "ILM": 34.2,  # Wilmington, NC
    "IWX": 46.8,  # Northern Indiana
    "JAX": 30.3,  # Jacksonville, FL
    "LOT": 47.8,  # Chicago, IL
    "LOX": 34.1,  # Los Angeles, CA
    "MFL": 25.8,  # Miami, FL
    "MFR": 49.3,  # Medford, OR
    "MHX": 34.8,  # Newport, NC
    "MKX": 48.2,  # Milwaukee, WI
    "MLB": 28.1,  # Melbourne, FL
    "MOB": 30.7,  # Mobile, AL
    "MQT": 55.2,  # Marquette, MI
    "MTR": 46.2,  # San Francisco, CA
    "OKX": 40.8,  # New York, NY
    "PHI": 39.9,  # Philadelphia, PA
    "PQR": 55.4,  # Portland, OR
    "SGX": 32.7,  # San Diego, CA
    "SJU": 18.4,  # San Juan, PR
    "TAE": 30.4,  # Tallahassee, FL
    "TBW": 27.8,  # Tampa, FL
}

# Aurora visibility thresholds based on Kp index and magnetic latitude
AURORA_KP_THRESHOLDS = {
    # Kp levels needed for aurora visibility at different magnetic latitudes
    "high_latitude": {"min_lat": 50.0, "kp_threshold": 3},    # Northern US/Canada border
    "mid_latitude": {"min_lat": 40.0, "kp_threshold": 5},     # Northern US states
    "low_latitude": {"min_lat": 30.0, "kp_threshold": 7},     # Southern US states
    "very_low_latitude": {"min_lat": 0.0, "kp_threshold": 9},  # Extreme events only
}

# Solar Radiation Storm scale and impact information
SOLAR_RADIATION_STORM_SCALES = {
    "S1": {
        "name": "Minor",
        "description": "Biological: None. Satellite operations: None. "
                       "Other systems: Minor impact on HF radio in polar regions."
    },
    "S2": {
        "name": "Moderate",
        "description": "Biological: Passengers and crew in high-altitude flights at high latitudes may be "
                       "exposed to radiation risk. Satellite operations: Infrequent single-event upsets possible. "
                       "Other systems: Small effects on HF propagation through polar regions and navigation at "
                       "polar cap locations possibly affected."
    },
    "S3": {
        "name": "Strong",
        "description": "Biological: Radiation hazard avoidance recommended for astronauts on EVA; passengers "
                       "and crew in high-altitude flights at high latitudes may be exposed to radiation risk. "
                       "Satellite operations: Single-event upsets, noise in imaging systems, and slight reduction "
                       "of efficiency in solar panel are likely. Other systems: Degraded HF radio propagation "
                       "through polar regions and navigation position errors likely."
    },
    "S4": {
        "name": "Severe",
        "description": "Biological: Unavoidable radiation hazard to astronauts on EVA; passengers and crew "
                       "in high-altitude flights at high latitudes may be exposed to radiation risk. "
                       "Satellite operations: Memory device problems and noise on imaging systems; star-tracker "
                       "problems may cause orientation problems, and solar panel efficiency can be degraded. "
                       "Other systems: Blackout of HF radio communications through polar regions and increased "
                       "navigation errors over several days are likely."
    },
    "S5": {
        "name": "Extreme",
        "description": "Biological: Unavoidable high radiation hazard to astronauts on EVA "
                       "(extra-vehicular activity); passengers and crew in high-altitude flights at high "
                       "latitudes may be exposed to radiation risk. Satellite operations: Memory device problems "
                       "and noise on imaging systems; star-tracker problems may cause orientation problems, and "
                       "solar panel efficiency can be degraded. Other systems: Complete blackout of HF "
                       "(high frequency) communications possible through polar regions, and navigation may be "
                       "degraded for days."
    }
}

# Meteor shower forecast tuning.
#
# Unlike every other data domain here, meteor showers need no feed: Earth crosses the same debris
# streams at the same solar longitude every year, so the bundled catalog in meteor_catalog.py is
# computed locally rather than polled. NOAA/NWS publish no meteor data of any kind — their alert
# taxonomy is terrestrial hazards, and SWPC covers geomagnetic activity, not meteors.

# How often to recompute the forecast, in minutes. Longer than DEFAULT_SCAN_INTERVAL because
# nothing is being fetched and the best-of-night result is stable for hours.
METEOR_SCAN_INTERVAL = 30

# How many upcoming showers to expose for dashboard cards.
METEOR_UPCOMING_COUNT = 5

# Thresholds for the "meteor shower active" binary sensor. With ~30 showers catalogued something
# is technically active most nights, so a bare activity flag would sit permanently on and be
# useless as an automation trigger. Requiring a real predicted rate keeps it meaningful.
METEOR_ACTIVE_MIN_RATE = 5      # predicted meteors/hour at the best moment of the night
METEOR_ACTIVE_MIN_SCORE = 25    # viewing score out of 100

# Eclipse forecast tuning.
#
# Solar eclipses are the one thing here that needs bundled data rather than a feed or a formula:
# see eclipse_catalog.py. Lunar eclipses need neither and are computed outright. NOAA publishes
# no eclipse products at all -- eclipses are NASA's beat, and NASA publishes them as documents.

# How often to recompute, in minutes, when the next eclipse is still a long way off. Longer than
# DEFAULT_SCAN_INTERVAL because nothing is fetched and the answer changes only by a countdown.
ECLIPSE_SCAN_INTERVAL = 60

# ...and how often once one is close or under way. A meteor shower lasts all night, so a slow
# poll costs nothing; totality lasts two minutes. Polling every hour would let "go outside now"
# fire after the event had finished, so the coordinator tightens its own interval as an eclipse
# approaches. This cannot be solved in the entities: Home Assistant only re-reads their state
# when the coordinator publishes an update, so a property that checked the clock itself would
# simply never fire.
ECLIPSE_APPROACH_SCAN_INTERVAL = 5
ECLIPSE_ACTIVE_SCAN_INTERVAL = 1

# How close counts as "approaching", in hours before first contact.
ECLIPSE_APPROACH_WINDOW_HOURS = 6

# How many eclipses to expose for dashboard cards.
ECLIPSE_UPCOMING_COUNT = 5

# How many catalogued solar eclipses to work through looking for ones visible from here. From a
# fixed site only about one in three produces any obscuration at all, so the scan has to look
# past the misses -- but it does not have to look past all of them, and each one costs real work.
ECLIPSE_MAX_CATALOG_SCAN = 24

# Penumbral lunar eclipses are real, catalogued, and invisible to almost everybody: the Moon
# passes through the faint outer shadow and dims by an amount most observers cannot detect.
# They are computed and reported, but excluded from "what's next" so they cannot displace a
# genuine eclipse in the headline.
ECLIPSE_INCLUDE_PENUMBRAL = False

# Thresholds for the two eclipse binary sensors. Unlike the meteor equivalents these are not
# fighting a permanently-on flag -- eclipses are rare -- they are here to stop a 3% nibble at
# the Sun, which nobody would notice without a filter, from being announced as an event.
ECLIPSE_VISIBLE_MIN_COVERAGE = 10    # % of the disc covered at the best visible moment
ECLIPSE_VISIBLE_LEAD_MINUTES = 60    # turn on this long before first contact
ECLIPSE_UPCOMING_DAYS = 14           # how far ahead "coming up" looks
ECLIPSE_UPCOMING_MIN_COVERAGE = 25   # % -- worth a calendar entry, not just a glance

# Solar Radiation Storm alert keywords for filtering NOAA alerts
SOLAR_RADIATION_KEYWORDS = [
    "solar radiation",
    "radiation storm",
    "proton event",
    "proton flux",
    "solar proton",
    "Type IV",
    "coronal mass ejection",
    "solar particle"
]
