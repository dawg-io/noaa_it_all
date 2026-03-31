"""Shared parsing and conversion utilities for NOAA Integration.

This module contains pure functions with no Home Assistant dependency,
making them independently unit-testable.
"""

import re
from typing import Any, Dict, List, Optional, Tuple, Union


# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------

def celsius_to_fahrenheit(celsius: Optional[float]) -> Optional[float]:
    """Convert Celsius to Fahrenheit."""
    if celsius is None:
        return None
    return round((celsius * 9 / 5) + 32, 1)


def kmh_to_mph(kmh: Optional[float]) -> Optional[float]:
    """Convert km/h to mph."""
    if kmh is None:
        return None
    return round(kmh * 0.621371, 1)


def pascals_to_inhg(pascals: Optional[float]) -> Optional[float]:
    """Convert Pascals to inches of mercury."""
    if pascals is None:
        return None
    return round(pascals * 0.00029530, 2)


def meters_to_miles(meters: Optional[float]) -> Optional[float]:
    """Convert meters to miles."""
    if meters is None:
        return None
    return round(meters * 0.000621371, 1)


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


# ---------------------------------------------------------------------------
# Solar radiation storm helpers
# ---------------------------------------------------------------------------

def extract_storm_scale(message: str, product_id: str) -> str:
    """Extract S1-S5 storm scale from message or product ID."""
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
        return round(float(value), 1)
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
            return round(float(wvht) * _M_TO_FT, 1)
        except (ValueError, TypeError):
            # Invalid numeric value; try the next line.
            continue
    return None


def normalize_numeric(value) -> float | None:
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
