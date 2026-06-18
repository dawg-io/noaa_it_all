"""Tests to validate translations/en.json and strings.json are valid and consistent."""

import json
import os
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMPONENT = os.path.join(_REPO, "custom_components", "noaa_it_all")


class TestTranslationsExist(unittest.TestCase):
    """Ensure translations/en.json exists and mirrors strings.json."""

    def test_en_json_exists(self):
        path = os.path.join(_COMPONENT, "translations", "en.json")
        self.assertTrue(os.path.isfile(path), "translations/en.json is missing")

    def test_strings_json_exists(self):
        path = os.path.join(_COMPONENT, "strings.json")
        self.assertTrue(os.path.isfile(path), "strings.json is missing")


class TestTranslationsValid(unittest.TestCase):
    """Validate that translations/en.json is well-formed and complete."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_COMPONENT, "translations", "en.json")) as f:
            cls.en = json.load(f)
        with open(os.path.join(_COMPONENT, "strings.json")) as f:
            cls.strings = json.load(f)

    def test_en_json_is_valid_json(self):
        self.assertIsInstance(self.en, dict)

    def test_strings_json_is_valid_json(self):
        self.assertIsInstance(self.strings, dict)

    def test_en_matches_strings(self):
        """translations/en.json should mirror strings.json."""
        self.assertEqual(self.en, self.strings)

    def test_config_section_present(self):
        self.assertIn("config", self.en)

    def test_config_step_user_present(self):
        self.assertIn("step", self.en["config"])
        self.assertIn("user", self.en["config"]["step"])

    def test_user_step_has_required_fields(self):
        user = self.en["config"]["step"]["user"]
        self.assertIn("title", user)
        self.assertIn("description", user)
        self.assertIn("data", user)

    def test_user_data_has_required_keys(self):
        data = self.en["config"]["step"]["user"]["data"]
        self.assertIn("latitude", data)
        self.assertIn("longitude", data)

    def test_office_step_present(self):
        self.assertIn("office", self.en["config"]["step"])
        office = self.en["config"]["step"]["office"]
        self.assertIn("title", office)
        self.assertIn("description", office)
        self.assertIn("data", office)
        self.assertIn("office_code", office["data"])

    def test_error_section_present(self):
        self.assertIn("error", self.en["config"])

    def test_error_has_latitude_and_longitude(self):
        errors = self.en["config"]["error"]
        self.assertIn("invalid_latitude", errors)
        self.assertIn("invalid_longitude", errors)

    def test_abort_section_present(self):
        self.assertIn("abort", self.en["config"])
        self.assertIn("already_configured", self.en["config"]["abort"])

    def test_options_section_present(self):
        self.assertIn("options", self.en)

    def test_options_step_init_present(self):
        self.assertIn("step", self.en["options"])
        self.assertIn("init", self.en["options"]["step"])


if __name__ == "__main__":
    unittest.main()
