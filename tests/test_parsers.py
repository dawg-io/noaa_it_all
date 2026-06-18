"""Unit tests for parsers.py — pure functions, no Home Assistant dependency."""

import unittest

from parsers import (
    celsius_to_fahrenheit,
    kmh_to_mph,
    pascals_to_inhg,
    meters_to_miles,
    degrees_to_cardinal,
    interpret_dst_value,
    rate_kp_index,
    calculate_aurora_visibility,
    calculate_aurora_duration,
    calculate_aurora_probability,
    get_visibility_class,
    get_required_kp,
    extract_storm_scale,
    extract_time_from_message,
    calculate_alert_duration,
    extract_impacts,
    get_severity_level,
    assess_location_risk,
    classify_hurricane_activity,
    parse_rip_current_risk,
    parse_surf_height,
    parse_water_temperature,
    parse_coops_water_temperature,
    parse_ndbc_wave_height,
    parse_nws_alert_features,
    format_forecast_text,
    format_forecast_periods,
    format_hourly_periods,
)

# Sample AURORA_KP_THRESHOLDS for testing (mirrors const.py)
AURORA_KP_THRESHOLDS = {
    "high_latitude": {"min_lat": 50.0, "kp_threshold": 3},
    "mid_latitude": {"min_lat": 40.0, "kp_threshold": 5},
    "low_latitude": {"min_lat": 30.0, "kp_threshold": 7},
    "very_low_latitude": {"min_lat": 0.0, "kp_threshold": 9},
}


# ---------------------------------------------------------------
# Unit conversion tests
# ---------------------------------------------------------------

class TestUnitConversions(unittest.TestCase):
    """Tests for unit conversion helpers."""

    def test_celsius_to_fahrenheit_basic(self):
        self.assertAlmostEqual(celsius_to_fahrenheit(0), 32.0)
        self.assertAlmostEqual(celsius_to_fahrenheit(100), 212.0)
        self.assertAlmostEqual(celsius_to_fahrenheit(-40), -40.0)

    def test_celsius_to_fahrenheit_none(self):
        self.assertIsNone(celsius_to_fahrenheit(None))

    def test_kmh_to_mph(self):
        self.assertAlmostEqual(kmh_to_mph(100), 62.1, places=1)
        self.assertIsNone(kmh_to_mph(None))

    def test_pascals_to_inhg(self):
        self.assertAlmostEqual(pascals_to_inhg(101325), 29.92, places=1)
        self.assertIsNone(pascals_to_inhg(None))

    def test_meters_to_miles(self):
        self.assertAlmostEqual(meters_to_miles(1609.34), 1.0, places=1)
        self.assertIsNone(meters_to_miles(None))

    def test_degrees_to_cardinal(self):
        self.assertEqual(degrees_to_cardinal(0), 'N')
        self.assertEqual(degrees_to_cardinal(90), 'E')
        self.assertEqual(degrees_to_cardinal(180), 'S')
        self.assertEqual(degrees_to_cardinal(270), 'W')
        self.assertEqual(degrees_to_cardinal(360), 'N')
        self.assertEqual(degrees_to_cardinal(45), 'NE')
        self.assertEqual(degrees_to_cardinal(225), 'SW')


# ---------------------------------------------------------------
# Space-weather interpretation tests
# ---------------------------------------------------------------

class TestSpaceWeatherInterpretation(unittest.TestCase):
    """Tests for space-weather parsing functions."""

    def test_interpret_dst_quiet(self):
        self.assertEqual(interpret_dst_value(0), 'No Storm (Quiet conditions)')
        self.assertEqual(interpret_dst_value(-10), 'No Storm (Quiet conditions)')

    def test_interpret_dst_minor(self):
        self.assertEqual(interpret_dst_value(-20), 'Minor Storm')
        self.assertEqual(interpret_dst_value(-30), 'Minor Storm')

    def test_interpret_dst_moderate(self):
        self.assertEqual(interpret_dst_value(-50), 'Moderate Storm')
        self.assertEqual(interpret_dst_value(-75), 'Moderate Storm')

    def test_interpret_dst_strong(self):
        self.assertEqual(interpret_dst_value(-100), 'Strong Storm')
        self.assertEqual(interpret_dst_value(-150), 'Strong Storm')

    def test_interpret_dst_severe(self):
        self.assertEqual(interpret_dst_value(-200), 'Severe Storm')
        self.assertEqual(interpret_dst_value(-250), 'Severe Storm')

    def test_interpret_dst_invalid(self):
        self.assertIn('Error', interpret_dst_value('invalid'))

    def test_rate_kp_index(self):
        self.assertEqual(rate_kp_index(0), 'low')
        self.assertEqual(rate_kp_index(1.5), 'low')
        self.assertEqual(rate_kp_index(2), 'moderate')
        self.assertEqual(rate_kp_index(4.9), 'moderate')
        self.assertEqual(rate_kp_index(5), 'high')
        self.assertEqual(rate_kp_index(9), 'high')
        self.assertEqual(rate_kp_index('unknown'), 'unknown')
        self.assertEqual(rate_kp_index(None), 'unknown')
        self.assertEqual(rate_kp_index('invalid'), 'unknown')


# ---------------------------------------------------------------
# Aurora tests
# ---------------------------------------------------------------

class TestAuroraHelpers(unittest.TestCase):
    """Tests for aurora calculation helpers."""

    def test_aurora_visibility_high_lat(self):
        self.assertTrue(calculate_aurora_visibility(3, 55.0, AURORA_KP_THRESHOLDS))
        self.assertFalse(calculate_aurora_visibility(2, 55.0, AURORA_KP_THRESHOLDS))

    def test_aurora_visibility_mid_lat(self):
        self.assertTrue(calculate_aurora_visibility(5, 45.0, AURORA_KP_THRESHOLDS))
        self.assertFalse(calculate_aurora_visibility(4, 45.0, AURORA_KP_THRESHOLDS))

    def test_aurora_visibility_low_lat(self):
        self.assertTrue(calculate_aurora_visibility(7, 35.0, AURORA_KP_THRESHOLDS))
        self.assertFalse(calculate_aurora_visibility(6, 35.0, AURORA_KP_THRESHOLDS))

    def test_aurora_duration_zero_kp(self):
        self.assertEqual(calculate_aurora_duration(0, 45.0), 0)

    def test_aurora_duration_moderate(self):
        duration = calculate_aurora_duration(5, 45.0)
        self.assertGreater(duration, 0)

    def test_aurora_duration_high_lat_bonus(self):
        low = calculate_aurora_duration(5, 30.0)
        high = calculate_aurora_duration(5, 55.0)
        self.assertGreater(high, low)

    def test_aurora_probability_low_kp(self):
        self.assertEqual(calculate_aurora_probability(0, 30.0), 0)

    def test_aurora_probability_high_kp_high_lat(self):
        prob = calculate_aurora_probability(7, 55.0)
        self.assertGreater(prob, 50)

    def test_visibility_class(self):
        self.assertEqual(get_visibility_class(80), "Excellent")
        self.assertEqual(get_visibility_class(60), "Good")
        self.assertEqual(get_visibility_class(40), "Fair")
        self.assertEqual(get_visibility_class(15), "Poor")
        self.assertEqual(get_visibility_class(5), "None")

    def test_required_kp(self):
        self.assertEqual(get_required_kp(55.0, AURORA_KP_THRESHOLDS), 3)
        self.assertEqual(get_required_kp(45.0, AURORA_KP_THRESHOLDS), 5)
        self.assertEqual(get_required_kp(35.0, AURORA_KP_THRESHOLDS), 7)
        self.assertEqual(get_required_kp(10.0, AURORA_KP_THRESHOLDS), 9)


# ---------------------------------------------------------------
# Solar radiation storm tests
# ---------------------------------------------------------------

class TestSolarRadiation(unittest.TestCase):
    """Tests for solar radiation storm parsing."""

    def test_extract_storm_scale_product_id(self):
        self.assertEqual(extract_storm_scale("any message", "S3_alert"), "S3")

    def test_extract_storm_scale_message(self):
        self.assertEqual(extract_storm_scale("SCALE S2 warning text", ""), "S2")

    def test_extract_storm_scale_keyword(self):
        self.assertEqual(extract_storm_scale("extreme radiation storm", ""), "S4")
        self.assertEqual(extract_storm_scale("strong solar event", ""), "S3")
        self.assertEqual(extract_storm_scale("moderate proton flux", ""), "S2")
        self.assertEqual(extract_storm_scale("minor radiation event", ""), "S1")

    def test_extract_storm_scale_unknown(self):
        self.assertEqual(extract_storm_scale("no relevant content", ""), "Unknown")

    def test_extract_time_found(self):
        msg = "Begin Time: 2025 Aug 10 1145 UTC\nEnd Time: 2025 Aug 10 1300 UTC"
        self.assertEqual(extract_time_from_message(msg, "begin time"), "2025 Aug 10 1145 UTC")
        self.assertEqual(extract_time_from_message(msg, "end time"), "2025 Aug 10 1300 UTC")

    def test_extract_time_not_found(self):
        self.assertIsNone(extract_time_from_message("no time here", "begin time"))

    def test_calculate_alert_duration_none(self):
        self.assertIsNone(calculate_alert_duration(None, None))
        self.assertIsNone(calculate_alert_duration("time", None))

    def test_extract_impacts(self):
        msg = "Satellite operations affected. Radio communication disrupted. GPS navigation degraded."
        impacts = extract_impacts(msg)
        self.assertIn('Satellite operations', impacts)
        self.assertIn('Radio communications', impacts)
        self.assertIn('Navigation systems', impacts)

    def test_extract_impacts_empty(self):
        self.assertEqual(extract_impacts("no impacts mentioned"), [])

    def test_severity_level(self):
        self.assertEqual(get_severity_level('S5'), 'Extreme')
        self.assertEqual(get_severity_level('S1'), 'Minor')
        self.assertEqual(get_severity_level('Unknown'), 'Unknown')
        self.assertEqual(get_severity_level('X'), 'Unknown')

    def test_assess_location_risk_no_alerts(self):
        self.assertEqual(assess_location_risk(45.0, []), 'Low')

    def test_assess_location_risk_high(self):
        alerts = [{'scale': 'S5'}]
        self.assertEqual(assess_location_risk(45.0, alerts), 'High')

    def test_assess_location_risk_moderate(self):
        alerts = [{'scale': 'S3'}]
        self.assertEqual(assess_location_risk(30.0, alerts), 'Moderate')


# ---------------------------------------------------------------
# Hurricane classification tests
# ---------------------------------------------------------------

class TestHurricaneClassification(unittest.TestCase):
    """Tests for hurricane activity classification."""

    def test_quiet(self):
        state, attrs = classify_hurricane_activity([], [])
        self.assertIn('Quiet', state)
        self.assertEqual(attrs['total_active_storms'], 0)

    def test_active_hurricane(self):
        storms = [{'classification': 'HU', 'name': 'Test'}]
        state, attrs = classify_hurricane_activity(storms, [])
        self.assertIn('High', state)
        self.assertEqual(attrs['hurricanes'], 1)

    def test_tropical_storm(self):
        storms = [{'classification': 'TS', 'name': 'Tropical'}]
        state, attrs = classify_hurricane_activity(storms, [])
        self.assertIn('Moderate', state)
        self.assertEqual(attrs['tropical_storms'], 1)

    def test_hurricane_warnings(self):
        features = [{'properties': {'event': 'Hurricane Warning'}}]
        state, attrs = classify_hurricane_activity([], features)
        self.assertIn('High', state)
        self.assertEqual(attrs['hurricane_warnings'], 1)


# ---------------------------------------------------------------
# Surf-zone parsing tests
# ---------------------------------------------------------------

class TestSurfParsing(unittest.TestCase):
    """Tests for surf-zone forecast parsing."""

    def test_rip_current_high(self):
        self.assertEqual(parse_rip_current_risk("high rip current risk expected"), "High")

    def test_rip_current_moderate(self):
        self.assertEqual(parse_rip_current_risk("moderate rip current risk"), "Moderate")

    def test_rip_current_low(self):
        self.assertEqual(parse_rip_current_risk("low rip current risk"), "Low")

    def test_rip_current_default(self):
        self.assertEqual(parse_rip_current_risk("no mention of anything"), "Low")

    def test_surf_height_range(self):
        self.assertEqual(parse_surf_height("surf height.............2 to 4 feet."), "2-4")

    def test_surf_height_single(self):
        self.assertEqual(parse_surf_height("surf height..........3 feet"), "3")

    def test_surf_height_none(self):
        self.assertIsNone(parse_surf_height("no surf data here"))

    def test_water_temp_mid(self):
        self.assertEqual(parse_water_temperature("water temperature...........in the mid 80s."), "83-87")

    def test_water_temp_upper(self):
        self.assertEqual(parse_water_temperature("water temperature in the upper 70s"), "75-79")

    def test_water_temp_lower(self):
        self.assertEqual(parse_water_temperature("water temperature in the lower 60s"), "60-64")

    def test_water_temp_around(self):
        self.assertEqual(parse_water_temperature("water temperature...........around 78"), "78")

    def test_water_temp_none(self):
        self.assertIsNone(parse_water_temperature("no temperature data"))


# ---------------------------------------------------------------
# CO-OPS / NDBC API parsing tests
# ---------------------------------------------------------------

class TestCoopsWaterTemperature(unittest.TestCase):
    """Tests for CO-OPS water temperature JSON parsing."""

    def test_valid_response(self):
        data = {
            "metadata": {"id": "8658163", "name": "Wrightsville Beach"},
            "data": [{"t": "2026-03-30 23:06", "v": "60.6", "f": "0,0,0"}],
        }
        self.assertEqual(parse_coops_water_temperature(data), 60.6)

    def test_multiple_records_uses_latest(self):
        data = {
            "data": [
                {"t": "2026-03-30 22:00", "v": "59.0", "f": "0,0,0"},
                {"t": "2026-03-30 23:00", "v": "61.2", "f": "0,0,0"},
            ],
        }
        self.assertEqual(parse_coops_water_temperature(data), 61.2)

    def test_empty_data_list(self):
        self.assertIsNone(parse_coops_water_temperature({"data": []}))

    def test_missing_data_key(self):
        self.assertIsNone(parse_coops_water_temperature({"error": "bad"}))

    def test_missing_value(self):
        data = {"data": [{"t": "2026-03-30 23:06", "v": "", "f": "0,0,0"}]}
        self.assertIsNone(parse_coops_water_temperature(data))

    def test_empty_dict_input(self):
        self.assertIsNone(parse_coops_water_temperature({}))


class TestNdbcWaveHeight(unittest.TestCase):
    """Tests for NDBC real-time wave height text parsing."""

    SAMPLE_TEXT = (
        "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD   "
        "PRES  ATMP  WTMP  DEWP  VIS PTDY  TIDE\n"
        "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT   "
        "hPa  degC  degC  degC  nmi  hPa    ft\n"
        "2026 03 31 02 30  MM   MM   MM   1.1     6   4.8 127     "
        "MM  16.8  15.7    MM   MM   MM    MM\n"
    )

    def test_valid_data(self):
        result = parse_ndbc_wave_height(self.SAMPLE_TEXT)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 3.6, places=1)

    def test_missing_wvht(self):
        text = (
            "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD\n"
            "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT\n"
            "2026 03 31 02 30  MM   MM   MM    MM     6   4.8 127\n"
        )
        self.assertIsNone(parse_ndbc_wave_height(text))

    def test_empty_text(self):
        self.assertIsNone(parse_ndbc_wave_height(""))

    def test_only_headers(self):
        text = "#YY  MM DD hh mm WVHT\n#yr  mo dy hr mn    m\n"
        self.assertIsNone(parse_ndbc_wave_height(text))

    def test_multiple_lines_first_missing_wvht(self):
        text = (
            "#YY  MM DD hh mm WDIR WSPD GST  WVHT   DPD   APD MWD\n"
            "#yr  mo dy hr mn degT m/s  m/s     m   sec   sec degT\n"
            "2026 03 31 02 30  MM   MM   MM    MM     6   4.8 127\n"
            "2026 03 31 02 00  90   10   12   1.0     7   5.0 090\n"
        )
        result = parse_ndbc_wave_height(text)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result, 3.3, places=1)


# ---------------------------------------------------------------
# NWS alert parsing tests
# ---------------------------------------------------------------

class TestNWSAlertParsing(unittest.TestCase):
    """Tests for NWS alert feature parsing."""

    def test_empty_features(self):
        alerts, summary = parse_nws_alert_features([])
        self.assertEqual(len(alerts), 0)
        self.assertEqual(summary['warnings'], 0)

    def test_actual_alert(self):
        features = [{
            'properties': {
                'status': 'Actual',
                'event': 'Tornado Warning',
                'severity': 'Extreme',
                'urgency': 'Immediate',
                'headline': 'Test',
                'areaDesc': 'Test Area',
                'description': 'Test description',
            }
        }]
        alerts, summary = parse_nws_alert_features(features)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(summary['warnings'], 1)
        self.assertEqual(summary['by_severity']['Extreme'], 1)

    def test_test_alert_excluded(self):
        features = [{
            'properties': {
                'status': 'Test',
                'event': 'Tornado Warning',
                'severity': 'Extreme',
                'urgency': 'Immediate',
            }
        }]
        alerts, summary = parse_nws_alert_features(features)
        self.assertEqual(len(alerts), 0)

    def test_watch_advisory_statement(self):
        features = [
            {'properties': {'status': 'Actual', 'event': 'Tornado Watch',
                            'severity': 'Moderate', 'urgency': 'Expected'}},
            {'properties': {'status': 'Actual', 'event': 'Wind Advisory',
                            'severity': 'Minor', 'urgency': 'Expected'}},
            {'properties': {'status': 'Actual', 'event': 'Special Weather Statement',
                            'severity': 'Minor', 'urgency': 'Future'}},
        ]
        alerts, summary = parse_nws_alert_features(features)
        self.assertEqual(len(alerts), 3)
        self.assertEqual(summary['watches'], 1)
        self.assertEqual(summary['advisories'], 1)
        self.assertEqual(summary['statements'], 1)


# ---------------------------------------------------------------
# Forecast formatting tests
# ---------------------------------------------------------------

class TestForecastFormatting(unittest.TestCase):
    """Tests for forecast formatting helpers."""

    def test_format_forecast_text(self):
        periods = [
            {'name': 'Tonight', 'detailedForecast': 'Clear skies'},
            {'name': 'Tomorrow', 'detailedForecast': 'Partly cloudy'},
        ]
        text = format_forecast_text(periods, max_periods=2)
        self.assertIn('Tonight: Clear skies', text)
        self.assertIn('Tomorrow: Partly cloudy', text)

    def test_format_forecast_text_limit(self):
        periods = [{'name': f'Day {i}', 'detailedForecast': 'Test'} for i in range(20)]
        text = format_forecast_text(periods, max_periods=3)
        self.assertEqual(text.count('Day'), 3)

    def test_format_forecast_periods(self):
        periods = [{'name': 'Tonight', 'temperature': 65, 'temperatureUnit': 'F',
                    'windSpeed': '5 mph', 'windDirection': 'NW',
                    'shortForecast': 'Clear', 'detailedForecast': 'Clear skies',
                    'startTime': '2025-01-01T00:00', 'isDaytime': False, 'icon': ''}]
        result = format_forecast_periods(periods)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['name'], 'Tonight')
        self.assertEqual(result[0]['temperature'], 65)

    def test_format_hourly_periods(self):
        periods = [{'startTime': '2025-01-01T00:00', 'temperature': 65,
                    'temperatureUnit': 'F', 'windSpeed': '5 mph', 'windDirection': 'NW',
                    'shortForecast': 'Clear', 'probabilityOfPrecipitation': {'value': 10},
                    'isDaytime': False, 'icon': ''}]
        result = format_hourly_periods(periods)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['precipitation_probability'], 10)

    def test_format_hourly_periods_numeric_precip(self):
        periods = [{'startTime': '2025-01-01T00:00', 'temperature': 65,
                    'probabilityOfPrecipitation': 25}]
        result = format_hourly_periods(periods)
        self.assertEqual(result[0]['precipitation_probability'], 25)


if __name__ == '__main__':
    unittest.main()
