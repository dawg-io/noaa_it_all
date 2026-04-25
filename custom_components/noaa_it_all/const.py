"""Constants for NOAA Integration."""

DOMAIN = "noaa_it_all"

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

# Default values
DEFAULT_SCAN_INTERVAL = 10  # minutes
REQUEST_TIMEOUT = 30  # seconds
USER_AGENT = "HomeAssistant/NOAA-Integration"

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
