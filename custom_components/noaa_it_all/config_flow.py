"""Config flow for NOAA Integration."""
import logging
import math

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_OFFICE_CODE,
    OFFICE_COORDINATES,
)

_LOGGER = logging.getLogger(__name__)

# NWS Forecast Offices that issue Surf Zone Forecasts (SRF)
NWS_OFFICES = {
    "AKQ": "Norfolk, VA",
    "APX": "Gaylord, MI",
    "BOX": "Boston, MA",
    "BRO": "Brownsville, TX",
    "CAR": "Caribou, ME",
    "CHS": "Charleston, SC",
    "CLE": "Cleveland, OH",
    "CRP": "Corpus Christi, TX",
    "DLH": "Duluth, MN",
    "DTX": "Detroit, MI",
    "EKA": "Eureka, CA",
    "GRB": "Green Bay, WI",
    "GRR": "Grand Rapids, MI",
    "GUM": "Guam",
    "GYX": "Portland, ME",
    "HFO": "Honolulu, HI",
    "ILM": "Wilmington, NC",
    "IWX": "Northern Indiana",
    "JAX": "Jacksonville, FL",
    "LOT": "Chicago, IL",
    "LOX": "Los Angeles, CA",
    "MFL": "Miami, FL",
    "MFR": "Medford, OR",
    "MHX": "Newport, NC",
    "MKX": "Milwaukee, WI",
    "MLB": "Melbourne, FL",
    "MOB": "Mobile, AL",
    "MQT": "Marquette, MI",
    "MTR": "San Francisco, CA",
    "OKX": "New York, NY",
    "PHI": "Philadelphia, PA",
    "PQR": "Portland, OR",
    "SGX": "San Diego, CA",
    "SJU": "San Juan, PR",
    "TAE": "Tallahassee, FL",
    "TBW": "Tampa, FL",
}

# Maximum distance (miles) used to filter "nearby" offices.
NEARBY_OFFICE_RADIUS_MILES = 50.0

# Earth radius in statute miles.
_EARTH_RADIUS_MILES = 3958.7613


def haversine_miles(lat1, lon1, lat2, lon2):
    """Return the great-circle distance in miles between two points."""
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    return 2.0 * _EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def find_nearby_offices(latitude, longitude, max_miles=NEARBY_OFFICE_RADIUS_MILES):
    """Return [(office_code, distance_miles), ...] sorted by distance ascending.

    When ``max_miles`` is None, all known offices are returned.
    """
    distances = []
    for code, (olat, olon) in OFFICE_COORDINATES.items():
        distances.append((code, haversine_miles(latitude, longitude, olat, olon)))
    distances.sort(key=lambda item: item[1])
    if max_miles is None:
        return distances
    return [item for item in distances if item[1] <= max_miles]


def _format_office_label(code, distance_miles):
    """Build a human-readable label for an office in the dropdown."""
    name = NWS_OFFICES.get(code, "Unknown")
    return f"{code} - {name} ({distance_miles:.1f} mi)"


def _build_office_options(latitude, longitude):
    """Return (options_dict, default_code, no_candidates_within_radius)."""
    candidates = find_nearby_offices(latitude, longitude)
    no_within_radius = not candidates
    if no_within_radius:
        # Fall back to the 5 nearest overall so the user still has a choice.
        candidates = find_nearby_offices(latitude, longitude, max_miles=None)[:5]
    options = {code: _format_office_label(code, dist) for code, dist in candidates}
    default_code = candidates[0][0] if candidates else None
    return options, default_code, no_within_radius


def _ha_home_coords(hass):
    """Return (lat, lon) from Home Assistant Home zone, or (None, None)."""
    if hass is None:
        return None, None
    config = getattr(hass, "config", None)
    if config is None:
        return None, None
    lat = getattr(config, "latitude", None)
    lon = getattr(config, "longitude", None)
    if not isinstance(lat, (int, float)) or not isinstance(lon, (int, float)):
        return None, None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        return None, None
    # Treat a literal 0,0 as "not configured" (Null Island default).
    if lat == 0 and lon == 0:
        return None, None
    return float(lat), float(lon)


class NOAAConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for NOAA Integration."""

    VERSION = 1

    def __init__(self):
        """Initialize transient state for the multi-step flow."""
        self._latitude = None
        self._longitude = None

    async def async_step_user(self, user_input=None):
        """Step 1: collect latitude and longitude (pre-filled from HA Home)."""
        errors = {}
        ha_lat, ha_lon = _ha_home_coords(getattr(self, "hass", None))

        if user_input is not None:
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if latitude is None or not -90 <= latitude <= 90:
                errors[CONF_LATITUDE] = "invalid_latitude"
            if longitude is None or not -180 <= longitude <= 180:
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                self._latitude = float(latitude)
                self._longitude = float(longitude)
                return await self.async_step_office()

        default_lat = ha_lat if ha_lat is not None else 0.0
        default_lon = ha_lon if ha_lon is not None else 0.0

        if ha_lat is not None:
            ha_location_text = f"{ha_lat:.4f}, {ha_lon:.4f}"
        else:
            ha_location_text = "not configured"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
            }),
            errors=errors,
            description_placeholders={"ha_location": ha_location_text},
        )

    async def async_step_office(self, user_input=None):
        """Step 2: choose the closest NWS forecast office."""
        options, default_code, no_within_radius = _build_office_options(
            self._latitude, self._longitude
        )

        if user_input is not None:
            office_code = user_input.get(CONF_OFFICE_CODE)
            if office_code not in NWS_OFFICES:
                # Defensive — should be enforced by the dropdown schema.
                return self.async_show_form(
                    step_id="office",
                    data_schema=vol.Schema({
                        vol.Required(
                            CONF_OFFICE_CODE, default=default_code
                        ): vol.In(options),
                    }),
                    errors={CONF_OFFICE_CODE: "invalid_office"},
                    description_placeholders=self._office_placeholders(no_within_radius),
                )

            office_name = NWS_OFFICES[office_code]
            lat_str = f"{self._latitude:.4f}".replace('.', '_').replace('-', 'n')
            lon_str = f"{self._longitude:.4f}".replace('.', '_').replace('-', 'n')
            await self.async_set_unique_id(f"noaa_{office_code}_{lat_str}_{lon_str}")
            self._abort_if_unique_id_configured()

            return self.async_create_entry(
                title=f"NOAA - {office_name}",
                data={
                    CONF_OFFICE_CODE: office_code,
                    CONF_LATITUDE: self._latitude,
                    CONF_LONGITUDE: self._longitude,
                },
            )

        return self.async_show_form(
            step_id="office",
            data_schema=vol.Schema({
                vol.Required(CONF_OFFICE_CODE, default=default_code): vol.In(options),
            }),
            description_placeholders=self._office_placeholders(no_within_radius),
        )

    def _office_placeholders(self, no_within_radius):
        """Build description placeholders for the office step."""
        return {
            "latitude": f"{self._latitude:.4f}",
            "longitude": f"{self._longitude:.4f}",
            "warning": (
                "No NWS forecast office was found within "
                f"{int(NEARBY_OFFICE_RADIUS_MILES)} miles of the selected location. "
                "Showing the nearest offices instead."
            ) if no_within_radius else "",
        }

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Create the options flow."""
        return NOAAOptionsFlow(config_entry)


class NOAAOptionsFlow(config_entries.OptionsFlow):
    """NOAA config flow options handler."""

    def __init__(self, config_entry):
        """Initialize NOAA options flow."""
        self.config_entry = config_entry
        self._latitude = None
        self._longitude = None

    async def async_step_init(self, user_input=None):
        """Step 1 of the options flow: latitude / longitude."""
        errors = {}
        ha_lat, ha_lon = _ha_home_coords(getattr(self, "hass", None))

        if user_input is not None:
            latitude = user_input.get(CONF_LATITUDE)
            longitude = user_input.get(CONF_LONGITUDE)

            if latitude is None or not -90 <= latitude <= 90:
                errors[CONF_LATITUDE] = "invalid_latitude"
            if longitude is None or not -180 <= longitude <= 180:
                errors[CONF_LONGITUDE] = "invalid_longitude"

            if not errors:
                self._latitude = float(latitude)
                self._longitude = float(longitude)
                return await self.async_step_office()

        # Prefer the previously configured value, then HA Home, then 0.0.
        existing_lat = self.config_entry.data.get(CONF_LATITUDE)
        existing_lon = self.config_entry.data.get(CONF_LONGITUDE)
        default_lat = (
            existing_lat if existing_lat is not None
            else ha_lat if ha_lat is not None
            else 0.0
        )
        default_lon = (
            existing_lon if existing_lon is not None
            else ha_lon if ha_lon is not None
            else 0.0
        )

        if ha_lat is not None:
            ha_location_text = f"{ha_lat:.4f}, {ha_lon:.4f}"
        else:
            ha_location_text = "not configured"

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_LATITUDE, default=default_lat): vol.Coerce(float),
                vol.Required(CONF_LONGITUDE, default=default_lon): vol.Coerce(float),
            }),
            errors=errors,
            description_placeholders={"ha_location": ha_location_text},
        )

    async def async_step_office(self, user_input=None):
        """Step 2 of the options flow: choose the NWS forecast office."""
        options, default_code, no_within_radius = _build_office_options(
            self._latitude, self._longitude
        )
        # Prefer the existing office_code if it's still a valid candidate.
        existing_code = self.config_entry.data.get(CONF_OFFICE_CODE)
        if existing_code in options:
            default_code = existing_code

        if user_input is not None:
            office_code = user_input.get(CONF_OFFICE_CODE)
            if office_code not in NWS_OFFICES:
                return self.async_show_form(
                    step_id="office",
                    data_schema=vol.Schema({
                        vol.Required(
                            CONF_OFFICE_CODE, default=default_code
                        ): vol.In(options),
                    }),
                    errors={CONF_OFFICE_CODE: "invalid_office"},
                    description_placeholders=self._office_placeholders(no_within_radius),
                )
            return self.async_create_entry(
                title="",
                data={
                    CONF_OFFICE_CODE: office_code,
                    CONF_LATITUDE: self._latitude,
                    CONF_LONGITUDE: self._longitude,
                },
            )

        return self.async_show_form(
            step_id="office",
            data_schema=vol.Schema({
                vol.Required(CONF_OFFICE_CODE, default=default_code): vol.In(options),
            }),
            description_placeholders=self._office_placeholders(no_within_radius),
        )

    def _office_placeholders(self, no_within_radius):
        """Build description placeholders for the office step."""
        return {
            "latitude": f"{self._latitude:.4f}",
            "longitude": f"{self._longitude:.4f}",
            "warning": (
                "No NWS forecast office was found within "
                f"{int(NEARBY_OFFICE_RADIUS_MILES)} miles of the selected location. "
                "Showing the nearest offices instead."
            ) if no_within_radius else "",
        }
