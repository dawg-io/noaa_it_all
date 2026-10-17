"""Shared parsing and conversion utilities for NOAA Integration.

This module contains pure functions with no Home Assistant dependency,
making them independently unit-testable.
"""

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def pascals_to_hectopascals(pascals: Optional[float]) -> Optional[float]:
    """Return an NWS pressure in hPa, or None.

    NWS gives pascals to 2 decimals; the rounding only drops float noise. The
    observation sensors and the weather entity both use this, so they agree.
    """
    if pascals is None:
        return None
    return round(pascals / 100, 4)


def meters_to_kilometers(meters: Optional[float]) -> Optional[float]:
    """Return an NWS visibility in km, or None.

    NWS gives meters to 2 decimals; the rounding only drops float noise.
    """
    if meters is None:
        return None
    return round(meters / 1000, 5)


def degrees_to_cardinal(degrees: Union[int, float]) -> str:
    """Convert degrees to cardinal direction."""
    directions = ['N', 'NNE', 'NE', 'ENE', 'E', 'ESE', 'SE', 'SSE',
                  'S', 'SSW', 'SW', 'WSW', 'W', 'WNW', 'NW', 'NNW']
    idx = round(degrees / 22.5) % 16
    return directions[idx]


# ---------------------------------------------------------------------------
# Space-weather interpretation helpers
# ---------------------------------------------------------------------------

def interpret_dst_value(dst_value: Any) -> str:
    """Return a human-readable interpretation of a Dst index value."""
    if isinstance(dst_value, (int, float)):
        if dst_value > -20:
            return 'No Storm (Quiet conditions)'
        elif dst_value > -50:
            return 'Minor Storm'
        elif dst_value > -100:
            return 'Moderate Storm'
        elif dst_value > -200:
            return 'Strong Storm'
        else:
            return 'Severe Storm'
    return 'Error: Invalid Dst value'


def rate_kp_index(kp_value: Any) -> str:
    """Return 'low', 'moderate', or 'high' rating for a Kp index value."""
    if kp_value == 'unknown' or kp_value is None:
        return 'unknown'

    try:
        value = float(kp_value)
    except (TypeError, ValueError):
        return 'unknown'

    if value < 2:
        return 'low'
    elif 2 <= value < 5:
        return 'moderate'
    return 'high'


# ---------------------------------------------------------------------------
# Aurora helpers
# ---------------------------------------------------------------------------

def calculate_aurora_visibility(
    kp_index: float,
    magnetic_latitude: float,
    thresholds: Dict[str, Dict[str, float]],
) -> bool:
    """Return whether aurora is visible at *magnetic_latitude* given *kp_index*."""
    for _name, data in thresholds.items():
        if magnetic_latitude >= data["min_lat"]:
            return kp_index >= data["kp_threshold"]
    return False


def calculate_aurora_duration(kp_index: float, magnetic_latitude: float) -> float:
    """Estimate aurora duration in hours based on Kp and latitude."""
    if kp_index >= 7:
        duration = 4 + (kp_index - 7) * 2
    elif kp_index >= 5:
        duration = 2 + (kp_index - 5) * 1
    elif kp_index >= 3:
        duration = 1 + (kp_index - 3) * 0.5
    else:
        duration = 0

    if magnetic_latitude >= 50:
        duration *= 1.3
    elif magnetic_latitude >= 40:
        duration *= 1.1

    return round(duration, 1)


def calculate_aurora_probability(kp_index: float, magnetic_latitude: float) -> int:
    """Calculate aurora visibility probability (0-100) based on Kp and latitude."""
    if magnetic_latitude >= 55:
        if kp_index >= 3:
            probability = min(90, 30 + (kp_index - 3) * 15)
        else:
            probability = kp_index * 10
    elif magnetic_latitude >= 50:
        if kp_index >= 4:
            probability = min(80, 20 + (kp_index - 4) * 15)
        else:
            probability = max(0, (kp_index - 2) * 10)
    elif magnetic_latitude >= 40:
        if kp_index >= 5:
            probability = min(70, 15 + (kp_index - 5) * 15)
        else:
            probability = max(0, (kp_index - 4) * 8)
    elif magnetic_latitude >= 30:
        if kp_index >= 7:
            probability = min(50, 10 + (kp_index - 7) * 15)
        else:
            probability = max(0, (kp_index - 6) * 5)
    else:
        if kp_index >= 8:
            probability = min(30, (kp_index - 8) * 10)
        else:
            probability = 0

    return round(probability)


def get_visibility_class(probability: int) -> str:
    """Return visibility class label for a given probability percentage."""
    if probability >= 70:
        return "Excellent"
    elif probability >= 50:
        return "Good"
    elif probability >= 30:
        return "Fair"
    elif probability >= 10:
        return "Poor"
    return "None"


def get_required_kp(
    magnetic_latitude: float,
    thresholds: Dict[str, Dict[str, float]],
) -> int:
    """Return the minimum Kp index required for aurora visibility at a latitude."""
    for _name, data in thresholds.items():
        if magnetic_latitude >= data["min_lat"]:
            return data["kp_threshold"]
    return 9


# The length of a period in SWPC's Kp forecast.
_KP_FORECAST_PERIOD = timedelta(hours=3)


def next_aurora_period(
    forecast: Optional[List[Dict[str, Any]]],
    required_kp: float,
    now: datetime,
    dark: Optional[List[Tuple[datetime, datetime]]] = None,
) -> Optional[Dict[str, Any]]:
    """Return the first forecast Kp period after ``now`` that reaches ``required_kp`` while dark.

    ``forecast`` is SWPC's noaa-planetary-k-index-forecast.json: 3-hour
    periods, each ``observed``, ``estimated`` or ``predicted``. Estimated
    periods cover the rest of today and predicted ones the next two days, so
    both are forecasts. A period without a numeric Kp is skipped.

    ``dark``, when given, lists the ``(start, end)`` times it is dark enough
    to see aurora. A period then counts only for the part of it that is dark,
    and its time is the first dark moment in it: its start, or nightfall when
    that comes later in it. A period entirely in daylight doesn't count.

    A period whose time has come is left out: part of it is already measured,
    and the current Kp says more about it than its forecast. So a time, once
    given, stays until it arrives, even when it is nightfall in a period that
    has begun.

    Returns ``{"start": datetime, "kp": float}``, or None when no period does.
    """
    found = None
    for period in forecast or []:
        if not isinstance(period, dict) or period.get("observed") == "observed":
            continue
        kp = period.get("kp")
        if isinstance(kp, bool) or not isinstance(kp, (int, float)) or kp < required_kp:
            continue
        try:
            start = datetime.fromisoformat(period["time_tag"])
        except (KeyError, TypeError, ValueError):
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if dark is not None:
            start = _first_dark_moment(start, start + _KP_FORECAST_PERIOD, dark)
            if start is None:
                continue
        if start <= now:
            continue
        if found is None or start < found["start"]:
            found = {"start": start, "kp": kp}
    return found


def _first_dark_moment(
    start: datetime, end: datetime, dark: List[Tuple[datetime, datetime]]
) -> Optional[datetime]:
    """Return the first moment from ``start`` to ``end`` inside one of the ``dark`` windows, or None."""
    moments = [max(start, dark_start) for dark_start, dark_end in dark if dark_start < end and dark_end > start]
    return min(moments, default=None)


# ---------------------------------------------------------------------------
# Solar radiation storm helpers
# ---------------------------------------------------------------------------

# Solar radiation storms are the 10 MeV integral proton flux products: P11 to
# P14 for the S1 to S4 thresholds (10 to 10,000 pfu), each a warning (W), an
# alert (A) or a summary (S). P20 is the 100 MeV flux, which has no S-scale.
_RADIATION_STORM_PRODUCT = re.compile(r"P1\d[WAS]")
_MONTHS = {
    name: number for number, name in enumerate(
        ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1
    )
}
_SWPC_TIME = re.compile(r"(\d{4}) ([A-Z][a-z]{2}) (\d{2}) (\d{2})(\d{2}) UTC")


def _message_field(message: str, name: str) -> Optional[str]:
    """Return a field of an SWPC message, such as its Serial Number, or None."""
    match = re.search(rf"^{name}:[ \t]*(\S.*?)\s*$", message, re.MULTILINE)
    return match.group(1) if match else None


def _swpc_time(text: Optional[str]) -> Optional[datetime]:
    """Parse an SWPC message time, such as ``2026 Jan 19 2359 UTC``, whatever the locale."""
    match = _SWPC_TIME.fullmatch(text or "")
    if not match or match.group(2) not in _MONTHS:
        return None
    year, _, day, hour, minute = (int(g) if g.isdigit() else g for g in match.groups())
    try:
        return datetime(year, _MONTHS[match.group(2)], day, hour, minute, tzinfo=timezone.utc)
    except ValueError:
        return None


def _issue_time(alert: Dict[str, Any]) -> Optional[datetime]:
    """Return when an alerts.json product was issued, such as ``2026-01-19 18:19:10.037``."""
    try:
        return datetime.fromisoformat(alert["issue_datetime"]).replace(tzinfo=timezone.utc)
    except (KeyError, TypeError, ValueError):
        return None


def radiation_storm_products_in_effect(
    alerts: List[Dict[str, Any]], now: datetime
) -> List[Dict[str, Any]]:
    """Return the solar radiation storm products in alerts.json still in effect at ``now``.

    A warning is in effect until its Valid To or Now Valid Until time, unless
    an extended warning replaces it or it is cancelled. An alert is in effect
    until a summary for its threshold, issued after it, says the event ended
    after it began, or it is cancelled; of several for one threshold only the
    newest counts. Summaries and cancellations are records, never in effect.
    """
    products = []
    for alert in alerts:
        if not isinstance(alert, dict):
            continue
        product_id = alert.get("product_id") or ""
        if not _RADIATION_STORM_PRODUCT.fullmatch(product_id):
            continue
        message = alert.get("message") or ""
        products.append({
            "alert": alert,
            "id": product_id,
            "type": product_id[3],
            "serial": _message_field(message, "Serial Number"),
            "cancels": _message_field(message, "Cancel Serial Number"),
            "extends": _message_field(message, "Extension to Serial Number"),
            "issued": _issue_time(alert),
            "begin": _swpc_time(_message_field(message, "Begin Time")),
            "end": _swpc_time(_message_field(message, "End Time")),
            "until": _swpc_time(
                _message_field(message, "Now Valid Until") or _message_field(message, "Valid To")
            ),
        })

    cancelled = {(p["id"], p["cancels"]) for p in products if p["cancels"]}
    extended = {(p["id"], p["extends"]) for p in products if p["extends"]}
    current = [
        p for p in products
        if not p["cancels"] and (p["id"], p["serial"]) not in cancelled
    ]
    summaries = [p for p in current if p["type"] == "S"]

    def ended(alert):
        """Return True if a summary for the alert's threshold says its event is over."""
        for summary in summaries:
            if summary["id"][:3] != alert["id"][:3]:
                continue
            if alert["issued"] and summary["issued"] and summary["issued"] < alert["issued"]:
                continue
            if alert["begin"] and summary["end"] and summary["end"] < alert["begin"]:
                continue
            return True
        return False

    in_effect = []
    newest_alert = {}
    for p in current:
        if p["type"] == "W":
            if (p["id"], p["serial"]) not in extended and (p["until"] is None or now < p["until"]):
                in_effect.append(p)
        elif p["type"] == "A" and not ended(p):
            latest = newest_alert.get(p["id"])
            if latest is None or (p["issued"] or now) > (latest["issued"] or now):
                newest_alert[p["id"]] = p
    in_effect.extend(newest_alert.values())
    in_effect.sort(key=lambda p: p["issued"] or now, reverse=True)
    return [p["alert"] for p in in_effect]


def extract_storm_scale(message: str, product_id: str) -> str:
    """Extract S1-S5 storm scale from message or product ID."""
    stated = re.search(r"NOAA Scale:[ \t]*(S[1-5])\b", message)
    if stated:
        return stated.group(1)

    for scale in ['S5', 'S4', 'S3', 'S2', 'S1']:
        if product_id.startswith(scale):
            return scale

    message_upper = message.upper()
    for scale in ['S5', 'S4', 'S3', 'S2', 'S1']:
        if f'SCALE {scale}' in message_upper or f'{scale} (' in message_upper:
            return scale

    lower = message.lower()
    if any(kw in lower for kw in ['extreme', 'severe']):
        return 'S4'
    if any(kw in lower for kw in ['strong', 'major']):
        return 'S3'
    if 'moderate' in lower:
        return 'S2'
    if 'minor' in lower:
        return 'S1'

    return 'Unknown'


def extract_time_from_message(message: str, time_type: str) -> Optional[str]:
    """Extract time information from an alert message."""
    try:
        pattern = rf'{time_type}:\s*(\d{{4}}\s+\w{{3}}\s+\d{{1,2}}\s+\d{{4}}\s+UTC)'
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            return match.group(1)
    except Exception:
        pass
    return None


def calculate_alert_duration(begin_time: Optional[str], end_time: Optional[str]) -> Optional[str]:
    """Calculate duration between begin and end times."""
    if not begin_time or not end_time:
        return None
    try:
        return "TBD"
    except Exception:
        return None


def extract_impacts(message: str) -> List[str]:
    """Extract potential impacts from an alert message."""
    impacts: List[str] = []
    lower = message.lower()

    if 'satellite' in lower:
        impacts.append('Satellite operations')
    if 'radio' in lower or 'communication' in lower:
        impacts.append('Radio communications')
    if 'navigation' in lower or 'gps' in lower:
        impacts.append('Navigation systems')
    if 'radiation' in lower and ('hazard' in lower or 'risk' in lower):
        impacts.append('Radiation exposure risk')
    if 'polar' in lower:
        impacts.append('Polar region effects')

    return impacts


def get_severity_level(scale: str) -> str:
    """Return severity level string for a given storm scale."""
    severity_map = {
        'S5': 'Extreme',
        'S4': 'Severe',
        'S3': 'Strong',
        'S2': 'Moderate',
        'S1': 'Minor',
        'Unknown': 'Unknown',
    }
    return severity_map.get(scale, 'Unknown')


def assess_location_risk(
    magnetic_latitude: float,
    alerts: List[Dict[str, Any]],
) -> str:
    """Assess location-specific risk based on magnetic latitude and active alerts."""
    if not alerts:
        return 'Low'

    base_risk = 'Low'
    if magnetic_latitude >= 60.0:
        base_risk = 'High'
    elif magnetic_latitude >= 45.0:
        base_risk = 'Moderate'

    max_scale = 'S1'
    for alert in alerts:
        scale = alert.get('scale', 'S1')
        if scale in ['S4', 'S5']:
            return 'High'
        elif scale == 'S3':
            max_scale = 'S3'
        elif scale == 'S2' and max_scale not in ['S3', 'S4', 'S5']:
            max_scale = 'S2'

    if max_scale in ['S3', 'S4', 'S5'] and base_risk == 'Low':
        return 'Moderate'
    elif max_scale in ['S4', 'S5']:
        return 'High'

    return base_risk


# ---------------------------------------------------------------------------
# Hurricane classification helpers
# ---------------------------------------------------------------------------

def classify_hurricane_activity(
    active_storms: List[Dict[str, Any]],
    alert_features: List[Dict[str, Any]],
) -> Tuple[str, Dict[str, Any]]:
    """Classify hurricane activity and return (state_string, attributes_dict).

    Pure logic extracted from HurricaneActivitySensor.async_update.
    """
    hurricane_warnings = 0
    hurricane_watches = 0
    tropical_warnings = 0
    tropical_watches = 0

    for feature in alert_features:
        event = feature.get('properties', {}).get('event', '').lower()
        if 'hurricane warning' in event:
            hurricane_warnings += 1
        elif 'hurricane watch' in event:
            hurricane_watches += 1
        elif 'tropical storm warning' in event:
            tropical_warnings += 1
        elif 'tropical storm watch' in event:
            tropical_watches += 1

    hurricanes = 0
    tropical_storms = 0
    other_storms = 0
    storm_details: List[Dict[str, Any]] = []

    for storm in active_storms:
        classification = storm.get('classification', '').upper()
        storm_info = {
            'name': storm.get('name', 'Unknown'),
            'classification': classification,
            'intensity': storm.get('intensity', 'Unknown'),
            'pressure': storm.get('pressure', 'Unknown'),
            'latitude': storm.get('latitude', 'Unknown'),
            'longitude': storm.get('longitude', 'Unknown'),
            'movement_dir': storm.get('movementDir', 'Unknown'),
            'movement_speed': storm.get('movementSpeed', 'Unknown'),
            'last_update': storm.get('lastUpdate', 'Unknown'),
        }
        storm_details.append(storm_info)

        if classification in ['H1', 'H2', 'H3', 'H4', 'H5', 'HU']:
            hurricanes += 1
        elif classification in ['TS', 'TD']:
            tropical_storms += 1
        else:
            other_storms += 1

    total_storms = len(active_storms)

    if hurricane_warnings > 0 or hurricanes > 0:
        if hurricanes > 0:
            state = f'High - {hurricanes} Active Hurricane(s)'
        else:
            state = 'High - Hurricane Warnings Active'
    elif hurricane_watches > 0:
        state = 'Moderate - Hurricane Watches Active'
    elif tropical_warnings > 0 or tropical_storms > 0:
        if tropical_storms > 0:
            state = f'Moderate - {tropical_storms} Active Tropical Storm(s)'
        else:
            state = 'Moderate - Tropical Storm Warnings Active'
    elif tropical_watches > 0:
        state = 'Low - Tropical Storm Watches Active'
    elif other_storms > 0:
        state = f'Low - {other_storms} Other Storm System(s) Active'
    else:
        state = 'Quiet - No Active Storms or Alerts'

    attributes = {
        'total_active_storms': total_storms,
        'hurricanes': hurricanes,
        'tropical_storms': tropical_storms,
        'other_storms': other_storms,
        'hurricane_warnings': hurricane_warnings,
        'hurricane_watches': hurricane_watches,
        'tropical_warnings': tropical_warnings,
        'tropical_watches': tropical_watches,
        'total_alerts': len(alert_features),
        'storm_details': storm_details,
    }

    return state, attributes


# ---------------------------------------------------------------------------
# Surf-zone parsing helpers
# ---------------------------------------------------------------------------

def parse_rip_current_risk(forecast_text: str) -> str:
    """Parse rip current risk level from forecast text (case-insensitive)."""
    text = forecast_text.lower()
    if re.search(r"high\s+rip\s+current\s+risk|dangerous\s+rip\s+currents|"
                 r"rip\s+current\s+risk\s+is\s+high", text):
        return "High"
    if re.search(r"moderate\s+rip\s+current\s+risk|rip\s+current\s+risk\s+is\s+moderate", text):
        return "Moderate"
    if re.search(r"low\s+rip\s+current\s+risk|rip\s+current\s+risk\s+is\s+low", text):
        return "Low"
    return "Low"


def parse_surf_height(forecast_text: str) -> Optional[str]:
    """Parse surf height from forecast text (case-insensitive).

    Returns a string like ``"2-4"`` (range) or ``"3"`` (single), or *None*.
    """
    text = forecast_text.lower()
    height_patterns = [
        r"surf\s+height\.+(\d+)\s+to\s+(\d+)\s+feet",
        r"surf\s+height\s+(\d+)\s+to\s+(\d+)\s+feet",
        r"surf\s+height\.+(\d+)\s+feet",
        r"surf\s+height\s+(\d+)\s+feet",
        r"surf\s+height\s+(\d+)\s+to\s+(\d+)\s+feet",
        r"surf\s+(\d+)\s+to\s+(\d+)\s+feet",
    ]

    for pattern in height_patterns:
        match = re.search(pattern, text)
        if match:
            if len(match.groups()) == 2:
                return f"{int(match.group(1))}-{int(match.group(2))}"
            return match.group(1)
    return None


def parse_water_temperature(forecast_text: str) -> Optional[str]:
    """Parse water temperature from forecast text (case-insensitive).

    Returns a string like ``"85-89"`` (range) or ``"78"`` (single), or *None*.
    """
    text = forecast_text.lower()
    temp_patterns = [
        r"water\s+temperature\.+in\s+the\s+(upper|mid|lower)\s+(\d+)s",
        r"water\s+temperature\s+in\s+the\s+(upper|mid|lower)\s+(\d+)s",
        r"water\s+temperature\.+around\s+(\d+)",
        r"water\s+temperature\s+around\s+(\d+)",
        r"water\s+temperature\.+(\d+)\s*(?:degrees?|°?f?)",
        r"water\s+temp\.+(\d+)\s*(?:degrees?|°?f?)",
    ]

    for pattern in temp_patterns:
        match = re.search(pattern, text)
        if match:
            if "upper" in match.groups():
                base = int(match.groups()[-1])
                return f"{base + 5}-{base + 9}"
            elif "mid" in match.groups():
                base = int(match.groups()[-1])
                return f"{base + 3}-{base + 7}"
            elif "lower" in match.groups():
                base = int(match.groups()[-1])
                return f"{base}-{base + 4}"
            else:
                return match.groups()[-1]
    return None


# ---------------------------------------------------------------------------
# CO-OPS / NDBC API parsing helpers
# ---------------------------------------------------------------------------

def parse_coops_water_temperature(data: Dict[str, Any]) -> Optional[float]:
    """Extract water temperature in °F from a CO-OPS JSON response.

    Expects the structure returned by the CO-OPS ``datagetter`` API with
    ``units=english``.  Returns *None* when the response is missing or
    the value cannot be converted to a float.
    """
    try:
        records = data.get("data")
        if not records:
            return None
        value = records[-1].get("v")
        if value is None or value == "":
            return None
        value = float(value)
        # "NaN" or "inf" would parse; Home Assistant rejects them as a state.
        if not math.isfinite(value):
            return None
        return round(value, 1)
    except (TypeError, ValueError, IndexError, KeyError):
        return None


# Meters-to-feet conversion factor
_M_TO_FT = 3.28084


def parse_ndbc_wave_height(text: str) -> Optional[float]:
    """Extract significant wave height in feet from NDBC real-time text.

    The text is the standard meteorological data file
    (``/data/realtime2/{station}.txt``).  The first non-comment line
    after the two header rows is the most recent observation.

    Returns *None* when no valid reading is found or the value is ``MM``
    (missing).
    """
    for line in text.splitlines():
        if line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 9:
            continue
        wvht = parts[8]  # WVHT column (significant wave height in metres)
        if wvht == "MM":
            # Missing value for this observation; try the next line.
            continue
        try:
            height = float(wvht)
        except (ValueError, TypeError):
            # Invalid numeric value; try the next line.
            continue
        if not math.isfinite(height):
            # "nan" or "inf" parse as floats but are no reading either.
            continue
        return round(height * _M_TO_FT, 1)
    return None


def normalize_numeric(value) -> Optional[float]:
    """Normalize a parsed value to a numeric float.

    Handles direct numbers, numeric strings, and range strings like
    ``"2-4"`` or ``"85-89"`` (averaged).  Returns *None* when the value
    cannot be converted.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        if "-" in text:
            parts = text.split("-", 1)
            try:
                low = float(parts[0].strip())
                high = float(parts[1].strip())
                return round((low + high) / 2.0, 1)
            except (ValueError, TypeError):
                return None
        try:
            return float(text)
        except (ValueError, TypeError):
            return None
    return None


# ---------------------------------------------------------------------------
# NWS alert parsing helpers
# ---------------------------------------------------------------------------

def parse_nws_alert_features(features: List[Dict[str, Any]]) -> Tuple[
    List[Dict[str, Any]], Dict[str, Any]
]:
    """Parse NWS alert features and return (active_alerts, summary_dict).

    Only includes alerts with status == 'actual'.
    """
    active_alerts: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {
        'warnings': 0,
        'watches': 0,
        'advisories': 0,
        'statements': 0,
        'by_severity': {'Extreme': 0, 'Severe': 0, 'Moderate': 0, 'Minor': 0, 'Unknown': 0},
        'by_urgency': {'Immediate': 0, 'Expected': 0, 'Future': 0, 'Past': 0, 'Unknown': 0},
        'event_types': {},
    }

    for feature in features:
        props = feature.get('properties', {})
        status = props.get('status', '').lower()

        if status != 'actual':
            continue

        event = props.get('event', 'Unknown')
        severity = props.get('severity', 'Unknown')
        urgency = props.get('urgency', 'Unknown')

        instruction_raw = props.get('instruction')
        instruction = instruction_raw[:200] if instruction_raw else None

        alert_info = {
            'event': event,
            'headline': props.get('headline', 'No headline'),
            'severity': severity,
            'urgency': urgency,
            'certainty': props.get('certainty', 'Unknown'),
            'area': props.get('areaDesc', 'Unknown area'),
            'effective': props.get('effective', 'Unknown'),
            'onset': props.get('onset', 'Unknown'),
            'expires': props.get('expires', 'Unknown'),
            'ends': props.get('ends', 'Unknown'),
            'status': props.get('status', 'Unknown'),
            'message_type': props.get('messageType', 'Unknown'),
            'category': props.get('category', 'Unknown'),
            'sender': props.get('senderName', 'Unknown'),
            'instruction': instruction,
            'description': props.get('description', '')[:300],
        }
        active_alerts.append(alert_info)

        event_lower = event.lower()
        if 'warning' in event_lower:
            summary['warnings'] += 1
        elif 'watch' in event_lower:
            summary['watches'] += 1
        elif 'advisory' in event_lower:
            summary['advisories'] += 1
        elif 'statement' in event_lower:
            summary['statements'] += 1

        norm_severity = severity if severity in summary['by_severity'] else 'Unknown'
        norm_urgency = urgency if urgency in summary['by_urgency'] else 'Unknown'
        summary['by_severity'][norm_severity] += 1
        summary['by_urgency'][norm_urgency] += 1
        summary['event_types'][event] = summary['event_types'].get(event, 0) + 1

    return active_alerts, summary


# ---------------------------------------------------------------------------
# Forecast formatting helpers
# ---------------------------------------------------------------------------

def format_forecast_text(periods: List[Dict[str, Any]], max_periods: int = 14) -> str:
    """Format forecast periods into human-readable text."""
    lines = []
    for period in periods[:max_periods]:
        name = period.get('name', 'Unknown')
        detailed = period.get('detailedForecast', 'No details available')
        lines.append(f"{name}: {detailed}")
    return "\n\n".join(lines)


def format_forecast_periods(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format extended forecast periods for entity attributes."""
    formatted = []
    for period in periods:
        formatted.append({
            'name': period.get('name', 'Unknown'),
            'temperature': period.get('temperature'),
            'temperature_unit': period.get('temperatureUnit', 'F'),
            'wind_speed': period.get('windSpeed', 'Unknown'),
            'wind_direction': period.get('windDirection', 'Unknown'),
            'short_forecast': period.get('shortForecast', 'Unknown'),
            'detailed_forecast': period.get('detailedForecast', 'No details available'),
            'start_time': period.get('startTime', 'Unknown'),
            'is_daytime': period.get('isDaytime', False),
            'icon': period.get('icon', ''),
        })
    return formatted


def format_hourly_periods(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Format hourly forecast periods for entity attributes."""
    formatted = []
    for period in periods:
        precip_prob = period.get('probabilityOfPrecipitation')
        precip_value = 0
        if precip_prob and isinstance(precip_prob, dict):
            precip_value = precip_prob.get('value', 0)
        elif isinstance(precip_prob, (int, float)):
            precip_value = precip_prob

        formatted.append({
            'start_time': period.get('startTime', 'Unknown'),
            'temperature': period.get('temperature'),
            'temperature_unit': period.get('temperatureUnit', 'F'),
            'wind_speed': period.get('windSpeed', 'Unknown'),
            'wind_direction': period.get('windDirection', 'Unknown'),
            'short_forecast': period.get('shortForecast', 'Unknown'),
            'precipitation_probability': precip_value,
            'is_daytime': period.get('isDaytime', False),
            'icon': period.get('icon', ''),
        })
    return formatted


# ---------------------------------------------------------------------------
# Nearshore Marine Forecast (NSH) parsing helpers
# ---------------------------------------------------------------------------

_MARINE_ZONE_RE = re.compile(r"^[A-Z]{2}Z\d{3}$")
_UGC_START_RE = re.compile(r"^[A-Z]{2}[ZC]\d{3}")
_UGC_EXPIRY_RE = re.compile(r"-\d{6}-\s*$")
_UGC_TOKEN_RE = re.compile(r"^(?:([A-Z]{2}[ZC]))?(\d{3})(?:>(\d{3}))?$")
# When an NWS text product was issued, on a header line of its own:
# "235 PM EDT Tue Oct 13 2026", or "1000 AM ChST Wed Oct 14 2026" for Guam.
_ISSUED_TIME = r"\d{3,4}\s+[AP]M\s+\S+\s+[A-Za-z]{3}\s+[A-Za-z]{3}\s+\d{1,2}\s+\d{4}"
# Offices spanning two time zones append the second, e.g. "... 2026 /1001 AM CDT Sat Oct 10 2026/".
_NSH_ISSUED_RE = re.compile(rf"^{_ISSUED_TIME}(?:\s+/[^/]*/)?$")
_ISSUED_LINE_RE = re.compile(rf"^({_ISSUED_TIME})(?:\s+/[^/]*/)?[ \t]*$", re.MULTILINE)
_NSH_PERIOD_RE = re.compile(r"^\.([^.]+)\.\.\.(.*)$")


def find_issue_time(text: str) -> Optional[str]:
    """Return when an NWS text product was issued, from its header, or None."""
    match = _ISSUED_LINE_RE.search(text or "")
    return match.group(1) if match else None


def product_is_stale(issuance_time: Any, now: datetime, max_age_hours: float) -> bool:
    """Return True if an NWS product was issued more than ``max_age_hours`` before ``now``.

    A missing or unreadable issuance time is not stale: NWS always sends one,
    and a forecast is better shown than dropped over a format change.
    """
    if not isinstance(issuance_time, str):
        return False
    try:
        issued = datetime.fromisoformat(issuance_time)
    except ValueError:
        return False
    if issued.tzinfo is None:
        return False
    return now - issued > timedelta(hours=max_age_hours)


def normalize_marine_zone(value: Any) -> Optional[str]:
    """Return an upper-case NWS zone ID such as ``LMZ741``, or None if invalid."""
    if not isinstance(value, str):
        return None
    zone = value.strip().upper()
    return zone if _MARINE_ZONE_RE.match(zone) else None


def expand_ugc(ugc: str) -> List[str]:
    """Expand a UGC header such as ``LMZ740>742-102115-`` into zone IDs.

    The trailing six-digit group is the product expiry time and is ignored.
    A range (``740>742``) is inclusive, and a bare three-digit number reuses
    the most recent state/type prefix, e.g. ``LMZ740>742-744-`` is 740-742
    plus 744.
    """
    zones: List[str] = []
    prefix = ""
    for token in ugc.replace("\n", "").split("-"):
        token = token.strip()
        if not token or re.fullmatch(r"\d{6}", token):
            continue
        match = _UGC_TOKEN_RE.match(token)
        if not match:
            continue
        if match.group(1):
            prefix = match.group(1)
        if not prefix:
            continue
        start = int(match.group(2))
        end = int(match.group(3)) if match.group(3) else start
        zones.extend(f"{prefix}{n:03d}" for n in range(start, end + 1))
    return zones


def parse_nearshore_forecast(text: str, zone: str) -> Optional[Dict[str, Any]]:
    """Parse the block of an NSH product that covers ``zone``.

    Returns None when the text has no block for the zone. Otherwise returns
    a dict with ``zone``, ``zone_name`` (None if the names cannot be matched
    to the zone list), ``zone_names``, ``issued``, ``headlines`` and
    ``periods`` (a list of ``{"name", "detailed_forecast"}`` in forecast
    order, wrapped lines joined into one string).
    """
    zone = (zone or "").strip().upper()
    if not text or not zone:
        return None

    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if not _UGC_START_RE.match(lines[i].strip()):
            i += 1
            continue

        # The UGC header may wrap over several lines; it ends at the line
        # carrying the six-digit expiry group.
        ugc_lines: List[str] = []
        found_end = False
        while i < len(lines):
            ugc_lines.append(lines[i].strip())
            found_end = bool(_UGC_EXPIRY_RE.search(lines[i]))
            i += 1
            if found_end:
                break
        body: List[str] = []
        while i < len(lines) and lines[i].strip() != "$$":
            body.append(lines[i])
            i += 1
        if not found_end:
            continue
        zones = expand_ugc("".join(ugc_lines))
        if zone not in zones:
            continue
        return _parse_nsh_block(zone, zones, body)
    return None


def _parse_nsh_block(zone: str, zones: List[str], body: List[str]) -> Dict[str, Any]:
    """Parse one NSH block body (everything between the UGC header and ``$$``)."""
    name_lines: List[str] = []
    issued = None
    headlines: List[str] = []
    headline_parts: Optional[List[str]] = None
    periods: List[Dict[str, str]] = []
    current: Optional[Dict[str, Any]] = None

    for raw in body:
        line = raw.strip()
        if not line:
            continue
        period = _NSH_PERIOD_RE.match(line)
        if period:
            current = {"label": period.group(1).strip(), "parts": [period.group(2).strip()]}
            periods.append(current)
            headline_parts = None
            continue
        if current is not None:
            current["parts"].append(line)
            continue
        if issued is None:
            if _NSH_ISSUED_RE.match(line):
                issued = line
            else:
                name_lines.append(line)
            continue
        # Headlines such as "...SMALL CRAFT ADVISORY IN EFFECT..." often wrap
        # over several lines; collect from the opening to the closing "...".
        if headline_parts is None:
            if not line.startswith("..."):
                continue
            headline_parts = [line[3:]]
        else:
            headline_parts.append(line)
        if headline_parts[-1].endswith("..."):
            headline_parts[-1] = headline_parts[-1][:-3]
            headlines.append(re.sub(r"\s+", " ", " ".join(headline_parts)).strip())
            headline_parts = None

    # Zone names end with "-" and may wrap mid-name, so join with a space.
    # A single zone's name is taken whole, since names can contain hyphens
    # ("Chequamegon Bay-Bayfield to Oak Point WI").
    joined = " ".join(name_lines)
    if len(zones) == 1:
        names = [joined.strip().rstrip("-").strip()] if joined.strip() else []
    else:
        names = [n.strip() for n in joined.split("-") if n.strip()]
    if len(names) == len(zones):
        zone_name = names[zones.index(zone)]
    elif len(names) == 1:
        # One name shared by every zone in the group (e.g. LEZ040-041).
        zone_name = names[0]
    else:
        zone_name = None

    return {
        "zone": zone,
        "zone_name": zone_name,
        "zone_names": names,
        "issued": issued,
        "headlines": headlines,
        "periods": [
            {
                "name": p["label"].title(),
                "detailed_forecast": re.sub(r"\s+", " ", " ".join(p["parts"])).strip(),
            }
            for p in periods
        ],
    }


# ---------------------------------------------------------------------------
# Marine hazards (NWS active alerts for one marine zone)
# ---------------------------------------------------------------------------

# Most severe first. Events not listed rank after the listed warnings (an
# unknown warning) or after the listed advisories (an unknown advisory).
MARINE_HAZARD_ORDER = (
    "Hurricane Warning",
    "Hurricane Force Wind Warning",
    "Storm Warning",
    "Tropical Storm Warning",
    "Special Marine Warning",
    "Gale Warning",
    "Hazardous Seas Warning",
    "Heavy Freezing Spray Warning",
    "Small Craft Advisory",
    "Brisk Wind Advisory",
    "Freezing Spray Advisory",
    "Dense Fog Advisory",
    "Dense Smoke Advisory",
    "Low Water Advisory",
)
_NWS_SEVERITY_ORDER = ("Extreme", "Severe", "Moderate", "Minor")


def _alert_time(value: Any) -> Optional[datetime]:
    """Return an alert timestamp as an aware datetime, or None."""
    if not isinstance(value, str):
        return None
    try:
        when = datetime.fromisoformat(value)
    except ValueError:
        return None
    return when if when.tzinfo is not None else None


def _alert_headline(props: Dict[str, Any], event: str) -> Optional[str]:
    """Return NWS's headline for this alert's own event.

    An NWS message covering several hazards gives every alert in it the same
    combined headline, such as "SMALL CRAFT ADVISORY NOW IN EFFECT UNTIL 10 AM
    CDT THURSDAY... ...GALE WATCH IN EFFECT FROM FRIDAY AFTERNOON", so the part
    naming this event is picked out. Without one, the alert's own headline
    ("Gale Watch issued October 14 at ...") is used.
    """
    for text in (props.get("parameters") or {}).get("NWSheadline") or []:
        if not isinstance(text, str):
            continue
        for part in re.split(r"\.\.\.\s*\.\.\.", text):
            part = re.sub(r"\s+", " ", part).strip(" .")
            if part.upper().startswith(event.upper()):
                return part
    return props.get("headline")


def _alert_replaced(props: Dict[str, Any]) -> bool:
    """Return True when the alert's VTEC says it was cancelled (CAN) or upgraded (UPG).

    NWS does not always send these as Cancel messages: an upgraded Gale Watch
    can stay in the active alerts as an Alert, headlined "The Gale Watch has
    been replaced", until the warning that replaced it ends.
    """
    for vtec in (props.get("parameters") or {}).get("VTEC") or []:
        if isinstance(vtec, str) and re.match(r"/[OTEX]\.(CAN|UPG)\.", vtec):
            return True
    return False


def _marine_hazard_rank(item: Dict[str, Any]) -> Tuple[float, int, str]:
    event = item["event"]
    if event in MARINE_HAZARD_ORDER:
        rank = MARINE_HAZARD_ORDER.index(event)
    elif event.endswith("Warning"):
        rank = MARINE_HAZARD_ORDER.index("Small Craft Advisory") - 0.5
    else:
        rank = len(MARINE_HAZARD_ORDER)
    severity = item.get("severity")
    sev = _NWS_SEVERITY_ORDER.index(severity) if severity in _NWS_SEVERITY_ORDER else len(_NWS_SEVERITY_ORDER)
    return (rank, sev, item.get("onset") or "")


def classify_marine_alerts(features: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """Sort a marine zone's active NWS alerts into hazards, upcoming and watches.

    ``hazards`` are the warnings and advisories in effect at ``now`` and
    ``upcoming`` the ones issued that start later, both most severe first;
    ``watches`` are watches. ``hazard`` is the most severe hazard's event, or
    None when nothing is in effect. Statements, cancellations, tests and
    alerts that have ended are left out.
    """
    hazards: List[Dict[str, Any]] = []
    upcoming: List[Dict[str, Any]] = []
    watches: List[Dict[str, Any]] = []
    for feature in features or []:
        props = feature.get("properties") or {}
        event = props.get("event")
        if not isinstance(event, str) or (props.get("status") or "").lower() != "actual":
            continue
        if (props.get("messageType") or "").lower() == "cancel" or _alert_replaced(props):
            continue
        start = _alert_time(props.get("onset")) or _alert_time(props.get("effective"))
        end = _alert_time(props.get("ends")) or _alert_time(props.get("expires"))
        if end is not None and end <= now:
            continue
        item = {
            "event": event,
            "headline": _alert_headline(props, event),
            "onset": start.isoformat() if start else None,
            "ends": end.isoformat() if end else None,
            "severity": props.get("severity"),
        }
        if event.endswith("Watch"):
            watches.append(item)
        elif event.endswith(("Warning", "Advisory")):
            (upcoming if start is not None and start > now else hazards).append(item)
    hazards.sort(key=_marine_hazard_rank)
    upcoming.sort(key=_marine_hazard_rank)
    watches.sort(key=lambda item: item.get("onset") or "")
    return {
        "hazard": hazards[0]["event"] if hazards else None,
        "hazards": hazards,
        "upcoming": upcoming,
        "watches": watches,
    }
