"""Tests for the NOAA entity object_id normalization helper.

Covers the cases enumerated in the duplicate-prefix issue: corrupted
office-scoped prefixes are stripped, and valid global / office-only
entity IDs are left untouched.
"""

import os
import sys
import unittest


# ---------------------------------------------------------------------------
# Ensure the custom_components directory is on sys.path so that
# ``noaa_it_all`` resolves as a package.
# ---------------------------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PKG = os.path.join(_REPO, "custom_components", "noaa_it_all")
if _PKG not in sys.path:
    sys.path.insert(0, _PKG)


from entity_naming import (  # noqa: E402
    build_noaa_entity_object_id,
    normalize_noaa_entity_object_id,
)


class TestNormalizeNoaaEntityObjectId(unittest.TestCase):
    """Verify duplicated prefixes are stripped and valid IDs preserved."""

    # ---- duplicates that must be normalized -------------------------------

    def test_extended_forecast_duplicate_ilm(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_weather_noaa_ilm_extended_forecast",
                office_code="ilm",
            ),
            "noaa_ilm_weather_extended_forecast",
        )

    def test_extended_forecast_duplicate_sgx(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_sgx_weather_noaa_sgx_extended_forecast",
                office_code="sgx",
            ),
            "noaa_sgx_weather_extended_forecast",
        )

    def test_current_conditions_duplicate_lox(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_lox_weather_noaa_lox_current_conditions",
                office_code="lox",
            ),
            "noaa_lox_weather_current_conditions",
        )

    def test_surf_duplicate_ilm(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_surf_noaa_ilm_rip_current_risk",
                office_code="ilm",
            ),
            "noaa_ilm_surf_rip_current_risk",
        )

    def test_space_duplicate_dlh(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_dlh_space_noaa_dlh_aurora_visibility",
                office_code="dlh",
            ),
            "noaa_dlh_space_aurora_visibility",
        )

    # ---- valid IDs that must NOT change -----------------------------------

    def test_global_hurricane_unchanged(self):
        self.assertEqual(
            normalize_noaa_entity_object_id("noaa_weather_hurricane_activity"),
            "noaa_weather_hurricane_activity",
        )

    def test_global_space_unchanged(self):
        self.assertEqual(
            normalize_noaa_entity_object_id("noaa_space_planetary_k_index"),
            "noaa_space_planetary_k_index",
        )

    def test_office_only_unchanged(self):
        self.assertEqual(
            normalize_noaa_entity_object_id("noaa_ilm_temperature", office_code="ilm"),
            "noaa_ilm_temperature",
        )

    def test_office_humidity_unchanged(self):
        self.assertEqual(
            normalize_noaa_entity_object_id("noaa_ilm_humidity", office_code="ilm"),
            "noaa_ilm_humidity",
        )

    def test_binary_sensor_active_alerts_unchanged(self):
        self.assertEqual(
            normalize_noaa_entity_object_id("noaa_ilm_active_alerts", office_code="ilm"),
            "noaa_ilm_active_alerts",
        )

    def test_already_correct_weather_grouped_unchanged(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_weather_extended_forecast",
                office_code="ilm",
            ),
            "noaa_ilm_weather_extended_forecast",
        )

    # ---- behavior without an explicit office_code -------------------------

    def test_normalizes_without_office_code_argument(self):
        """The helper must auto-detect the duplicated office segment."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_weather_noaa_ilm_extended_forecast"
            ),
            "noaa_ilm_weather_extended_forecast",
        )
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_sgx_surf_noaa_sgx_rip_current_risk"
            ),
            "noaa_sgx_surf_rip_current_risk",
        )

    def test_case_insensitive_office_code(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_weather_noaa_ilm_extended_forecast",
                office_code="ILM",
            ),
            "noaa_ilm_weather_extended_forecast",
        )

    def test_uppercase_input_is_lowercased(self):
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "NOAA_ILM_WEATHER_NOAA_ILM_EXTENDED_FORECAST",
                office_code="ilm",
            ),
            "noaa_ilm_weather_extended_forecast",
        )

    # ---- pathological / edge cases ----------------------------------------

    def test_normalizes_multi_segment_office_without_office_code(self):
        """Auto-detect must work when the office code itself contains underscores."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_my_custom_weather_noaa_my_custom_extended_forecast"
            ),
            "noaa_my_custom_weather_extended_forecast",
        )

    def test_empty_string(self):
        self.assertEqual(normalize_noaa_entity_object_id(""), "")

    def test_does_not_strip_when_office_code_mismatches(self):
        """A mismatched office must not normalize an unrelated prefix."""
        self.assertEqual(
            normalize_noaa_entity_object_id(
                "noaa_ilm_weather_noaa_ilm_extended_forecast",
                office_code="sgx",
            ),
            "noaa_ilm_weather_noaa_ilm_extended_forecast",
        )


class TestBuildNoaaEntityObjectId(unittest.TestCase):
    """Verify the builder function creates correct object IDs."""

    def test_extended_forecast_ilm(self):
        self.assertEqual(
            build_noaa_entity_object_id("ILM", "weather", "extended_forecast"),
            "noaa_ilm_weather_extended_forecast",
        )

    def test_hourly_forecast_ilm(self):
        self.assertEqual(
            build_noaa_entity_object_id("ILM", "weather", "hourly_forecast"),
            "noaa_ilm_weather_hourly_forecast",
        )

    def test_extended_forecast_sgx(self):
        self.assertEqual(
            build_noaa_entity_object_id("SGX", "weather", "extended_forecast"),
            "noaa_sgx_weather_extended_forecast",
        )

    def test_rip_current_risk_sgx_surf(self):
        self.assertEqual(
            build_noaa_entity_object_id("SGX", "surf", "rip_current_risk"),
            "noaa_sgx_surf_rip_current_risk",
        )

    def test_case_insensitive(self):
        """Office code and group are lowercased."""
        self.assertEqual(
            build_noaa_entity_object_id("ILM", "WEATHER", "Extended_Forecast"),
            "noaa_ilm_weather_extended_forecast",
        )


if __name__ == "__main__":
    unittest.main()
