"""Tests to validate manifest.json and hacs.json metadata correctness."""

import json
import os
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_COMPONENT = os.path.join(_REPO, "custom_components", "noaa_it_all")


class TestManifest(unittest.TestCase):
    """Validate manifest.json structure and content."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_COMPONENT, "manifest.json")) as f:
            cls.manifest = json.load(f)

    def test_is_valid_json(self):
        self.assertIsInstance(self.manifest, dict)

    def test_domain(self):
        self.assertEqual(self.manifest["domain"], "noaa_it_all")

    def test_name(self):
        self.assertIn("name", self.manifest)
        self.assertTrue(len(self.manifest["name"]) > 0)

    def test_codeowners(self):
        self.assertIn("codeowners", self.manifest)
        self.assertIsInstance(self.manifest["codeowners"], list)
        self.assertTrue(len(self.manifest["codeowners"]) > 0)

    def test_config_flow_enabled(self):
        self.assertTrue(self.manifest.get("config_flow"))

    def test_documentation_url(self):
        # NOTE: documentation and issue_tracker must point to the primary
        # dawg-io/noaa_it_all repository, NOT this dev fork.
        doc = self.manifest.get("documentation", "")
        self.assertIn("github.com/dawg-io/noaa_it_all", doc)

    def test_issue_tracker_url(self):
        # NOTE: Must point to dawg-io/noaa_it_all, not the dev repo.
        tracker = self.manifest.get("issue_tracker", "")
        self.assertIn("github.com/dawg-io/noaa_it_all", tracker)
        self.assertTrue(tracker.endswith("/issues"))

    def test_documentation_url_not_dev_repo(self):
        """Safeguard: manifest URLs must NOT point to the dev fork."""
        doc = self.manifest.get("documentation", "")
        self.assertNotIn("dev-noaa_it_all", doc,
                         "documentation URL must point to dawg-io/noaa_it_all, not the dev repo")

    def test_issue_tracker_not_dev_repo(self):
        """Safeguard: issue_tracker must NOT point to the dev fork."""
        tracker = self.manifest.get("issue_tracker", "")
        self.assertNotIn("dev-noaa_it_all", tracker,
                         "issue_tracker URL must point to dawg-io/noaa_it_all, not the dev repo")

    def test_iot_class(self):
        self.assertEqual(self.manifest["iot_class"], "cloud_polling")

    def test_version_present(self):
        self.assertIn("version", self.manifest)
        parts = self.manifest["version"].split(".")
        self.assertTrue(len(parts) >= 2, "Version should be semver")

    def test_requirements(self):
        self.assertIn("requirements", self.manifest)
        self.assertIsInstance(self.manifest["requirements"], list)


class TestHacsJson(unittest.TestCase):
    """Validate hacs.json structure and content."""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_REPO, "hacs.json")) as f:
            cls.hacs = json.load(f)

    def test_is_valid_json(self):
        self.assertIsInstance(self.hacs, dict)

    def test_name_present(self):
        self.assertIn("name", self.hacs)
        self.assertTrue(len(self.hacs["name"]) > 0)

    def test_render_readme(self):
        self.assertTrue(self.hacs.get("render_readme"))

    def test_homeassistant_minimum_version(self):
        self.assertIn("homeassistant", self.hacs)

    def test_country(self):
        self.assertEqual(self.hacs.get("country"), "US")


if __name__ == "__main__":
    unittest.main()
