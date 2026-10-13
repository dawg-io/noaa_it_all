"""Tests to validate translations/en.json and strings.json are valid and consistent."""

import json
import os
import re
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

    def test_user_step_is_the_menu_of_entry_types(self):
        """Add entry starts by choosing weather, surf or hurricanes."""
        options = self.en["config"]["step"]["user"]["menu_options"]
        self.assertEqual({"location", "surf", "marine", "hurricane"}, set(options))

    def test_location_step_has_required_fields(self):
        location = self.en["config"]["step"]["location"]
        self.assertIn("title", location)
        self.assertIn("description", location)
        self.assertIn("data", location)

    def test_location_data_has_required_keys(self):
        data = self.en["config"]["step"]["location"]["data"]
        self.assertIn("latitude", data)
        self.assertIn("longitude", data)

    def test_every_step_and_abort_the_flow_uses_has_a_string(self):
        """A missing string shows the raw key in Home Assistant's dialogs."""
        with open(os.path.join(_COMPONENT, "config_flow.py")) as f:
            source = f.read()
        config_class, options_class = source.split("class NOAAOptionsFlow")
        for section, code in (("config", config_class), ("options", options_class)):
            for step in set(re.findall(r'step_id="(\w+)"', code)):
                with self.subTest(section=section, step=step):
                    self.assertIn(step, self.en[section]["step"])
        for reason in set(re.findall(r'(?:reason|error)="(\w+)"', config_class)):
            with self.subTest(abort=reason):
                self.assertIn(reason, self.en["config"]["abort"])

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

    def test_options_step_radar_present(self):
        self.assertIn("radar", self.en["options"]["step"])
        radar = self.en["options"]["step"]["radar"]
        self.assertIn("title", radar)
        self.assertIn("description", radar)
        self.assertIn("radar_loop_hours", radar["data"])

    def test_the_radar_description_fills_its_placeholder(self):
        """The step passes max_hours, so the text has to ask for it."""
        description = self.en["options"]["step"]["radar"]["description"]
        self.assertIn("{max_hours}", description)

    def test_options_error_has_radar_hours(self):
        self.assertIn("invalid_radar_hours", self.en["options"]["error"])


if __name__ == "__main__":
    unittest.main()
