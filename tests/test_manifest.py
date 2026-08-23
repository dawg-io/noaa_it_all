"""Tests to validate manifest.json and hacs.json metadata correctness."""

import json
import os
import re
import struct
import sys
import unittest
import zlib

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


class TestUserAgent(unittest.TestCase):
    """The User-Agent must stay truthful about who is calling NOAA.

    api.weather.gov requires a User-Agent and asks that it be unique to the
    application, with a website or email so they can get in touch rather than
    just blocking traffic they cannot attribute. These tests exist because the
    string used to be ``HomeAssistant/NOAA-Integration``: generic, contactless,
    unversioned, and implying Home Assistant core rather than a third-party
    custom integration.
    """

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_COMPONENT, "manifest.json")) as f:
            cls.manifest = json.load(f)
        # Imported by path rather than as ``noaa_it_all.const``, which would
        # pull in the package __init__ and with it the Home Assistant runtime.
        sys.path.insert(0, _COMPONENT)
        try:
            import const
        finally:
            sys.path.remove(_COMPONENT)
        cls.user_agent = const.USER_AGENT

    def test_identifies_the_integration_by_domain(self):
        self.assertTrue(
            self.user_agent.startswith(f"{self.manifest['domain']}/"),
            f"User-Agent should lead with the integration domain: {self.user_agent}",
        )

    def test_version_matches_the_manifest(self):
        """A stale version here would misreport which release is calling."""
        self.assertIn(
            f"{self.manifest['domain']}/{self.manifest['version']}",
            self.user_agent,
            "User-Agent version is out of step with manifest.json",
        )

    def test_version_is_read_from_the_manifest_not_hardcoded(self):
        """Bumping a release must not require remembering a second place.

        ``test_version_matches_the_manifest`` cannot catch a regression here on
        its own: the moment someone pastes the current version back in as a
        literal it still passes, right up until the next bump. So assert the
        string is actually interpolated.
        """
        with open(os.path.join(_COMPONENT, "const.py"), encoding="utf-8") as f:
            assignment = next(
                line for line in f if line.startswith("USER_AGENT")
            )
        self.assertNotRegex(
            assignment,
            r"\d+\.\d+",
            f"User-Agent must build its version from the manifest: {assignment.strip()}",
        )
        self.assertIn("VERSION", assignment)

    def test_manifest_reader_returns_the_real_manifest(self):
        """The reader behind VERSION/DOCUMENTATION_URL must actually work."""
        sys.path.insert(0, _COMPONENT)
        try:
            import const
        finally:
            sys.path.remove(_COMPONENT)
        self.assertEqual(const._manifest(), self.manifest)

    def test_carries_contact_information(self):
        """NOAA asks for a website or email so they can make contact."""
        self.assertIn(self.manifest["documentation"], self.user_agent)

    def test_documentation_url_is_read_from_the_manifest_not_hardcoded(self):
        with open(os.path.join(_COMPONENT, "const.py"), encoding="utf-8") as f:
            assignment = next(
                line for line in f if line.startswith("USER_AGENT")
            )
        self.assertNotIn("https://", assignment)
        self.assertIn("DOCUMENTATION_URL", assignment)

    def test_does_not_point_at_the_dev_repo(self):
        self.assertNotIn("dev-noaa_it_all", self.user_agent)

    def test_does_not_claim_to_be_home_assistant_core(self):
        self.assertFalse(
            self.user_agent.startswith("HomeAssistant"),
            "This is a custom integration, not Home Assistant core",
        )


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


# ---------------------------------------------------------------------------
# Helpers for PNG introspection (no third-party dependencies required)
# ---------------------------------------------------------------------------

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_dimensions(path):
    """Return (width, height, bit_depth, color_type, interlace) for a PNG."""
    with open(path, "rb") as fh:
        sig = fh.read(8)
        assert sig == _PNG_SIG, f"{path} is not a valid PNG"
        length = struct.unpack(">I", fh.read(4))[0]
        fh.read(4)  # chunk type (IHDR)
        ihdr = fh.read(length)
    w = struct.unpack(">I", ihdr[0:4])[0]
    h = struct.unpack(">I", ihdr[4:8])[0]
    return w, h, ihdr[8], ihdr[9], ihdr[12]


def _png_corner_alphas(path, width, height):
    """Return the alpha values at all four corners of an RGBA PNG."""
    with open(path, "rb") as fh:
        data = fh.read()
    offset = 8
    idat = b""
    while offset < len(data):
        length = struct.unpack(">I", data[offset:offset + 4])[0]
        ctype = data[offset + 4:offset + 8]
        if ctype == b"IDAT":
            idat += data[offset + 8:offset + 8 + length]
        offset += 12 + length
    raw = zlib.decompress(idat)
    channels = 4
    stride = width * channels

    def _alpha(row_raw, x):
        filter_type = row_raw[0]
        row = bytearray(row_raw[1:1 + stride])
        if filter_type == 1:
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                row[i] = (row[i] + left) & 0xFF
        elif filter_type == 2:
            pass  # treat prior row as zeros for first row
        return row[x * channels + 3]

    first_row = raw[0:1 + stride]
    last_row_start = (height - 1) * (1 + stride)
    last_row = raw[last_row_start:last_row_start + 1 + stride]
    return (
        _alpha(first_row, 0),
        _alpha(first_row, width - 1),
        _alpha(last_row, 0),
        _alpha(last_row, width - 1),
    )


# Expected brand asset dimensions (matches HA brand review guidelines)
_BRAND_ASSETS = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "logo.png": (768, 256),
    "logo@2x.png": (1536, 512),
}


class TestBrandAssets(unittest.TestCase):
    """Validate brand/ directory assets meet HA / HACS requirements."""

    _BRAND_DIR = os.path.join(_COMPONENT, "brand")

    def test_brand_directory_exists(self):
        self.assertTrue(
            os.path.isdir(self._BRAND_DIR),
            f"brand/ directory missing at {self._BRAND_DIR}",
        )

    def test_required_files_present(self):
        for filename in _BRAND_ASSETS:
            self.assertTrue(
                os.path.isfile(os.path.join(self._BRAND_DIR, filename)),
                f"brand/{filename} is missing",
            )

    def test_dimensions_and_format(self):
        """Icons must be square; logos must be wider than tall."""
        for filename, (exp_w, exp_h) in _BRAND_ASSETS.items():
            path = os.path.join(self._BRAND_DIR, filename)
            w, h, bit_depth, color_type, interlace = _png_dimensions(path)
            self.assertEqual((w, h), (exp_w, exp_h), f"brand/{filename}: unexpected size")
            self.assertEqual(bit_depth, 8, f"brand/{filename}: must be 8-bit")
            self.assertEqual(color_type, 6, f"brand/{filename}: must be RGBA (color_type 6)")
            self.assertEqual(interlace, 0, f"brand/{filename}: must be non-interlaced")
            if "logo" in filename:
                self.assertGreater(w, h, f"brand/{filename}: logo must be wider than tall")
                shortest = min(w, h)
                if "@2x" in filename:
                    self.assertGreaterEqual(shortest, 256,
                                            f"brand/{filename}: @2x logo shortest side < 256")
                    self.assertLessEqual(shortest, 512,
                                         f"brand/{filename}: @2x logo shortest side > 512")
                else:
                    self.assertGreaterEqual(shortest, 128,
                                            f"brand/{filename}: logo shortest side < 128")
                    self.assertLessEqual(shortest, 256,
                                         f"brand/{filename}: logo shortest side > 256")

    def test_corners_are_transparent(self):
        """All four corners of every brand asset must be fully transparent."""
        for filename, (exp_w, exp_h) in _BRAND_ASSETS.items():
            path = os.path.join(self._BRAND_DIR, filename)
            corners = _png_corner_alphas(path, exp_w, exp_h)
            for alpha in corners:
                self.assertEqual(
                    alpha, 0,
                    f"brand/{filename}: corner pixel is not transparent (alpha={alpha})",
                )

    def test_root_icon_exists(self):
        """icon.png at the repository root is the README header image source.

        It is NOT read by HACS or Home Assistant for any store or UI display.
        Those come from custom_components/noaa_it_all/brand/ (inside HA) and from
        the home-assistant/brands CDN (the HACS store list).
        """
        root_icon = os.path.join(_REPO, "icon.png")
        self.assertTrue(os.path.isfile(root_icon), "icon.png missing from repository root")
        w, h, _, _, _ = _png_dimensions(root_icon)
        self.assertEqual((w, h), (256, 256), "root icon.png must be 256x256")


class TestReadmeImages(unittest.TestCase):
    """Guard against image URLs that render as a broken image.

    A github.com/<owner>/<repo>/blob/... URL serves an HTML *page*, not an image,
    so it shows as broken on GitHub and on the HACS repository page (hacs.json sets
    render_readme, so HACS renders this same markdown).
    """

    _FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.DOTALL | re.MULTILINE)
    _HTML_IMG = re.compile(r"<img[^>]*?\ssrc=[\"']([^\"']+)[\"']", re.IGNORECASE)
    _MD_IMG = re.compile(r"!\[[^\]]*\]\(\s*([^\s)]+)")

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(_REPO, "README.md"), encoding="utf-8") as f:
            body = f.read()
        # Drop fenced code blocks first: the Lovelace card examples contain
        # <img src="{{ ... }}"> templates that are documentation, not real images.
        body = cls._FENCE.sub("", body)
        cls.urls = cls._HTML_IMG.findall(body) + cls._MD_IMG.findall(body)

    def test_images_found(self):
        """Sanity check that the extraction actually matched something."""
        self.assertTrue(self.urls, "no image URLs found in README.md -- extraction is broken")

    def test_no_github_blob_image_urls(self):
        for url in self.urls:
            if "github.com" in url and "/blob/" in url:
                self.fail(
                    f"README.md image URL serves an HTML page, not an image: {url}\n"
                    "Use https://raw.githubusercontent.com/<owner>/<repo>/<branch>/<path> instead."
                )


if __name__ == "__main__":
    unittest.main()
