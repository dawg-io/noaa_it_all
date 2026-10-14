"""Check that the README and the pages under docs/ link to things that exist.

The documentation is split across README.md and docs/*.md, so a moved section
or a renamed heading leaves a dead link behind. These tests resolve every
relative link and image the way GitHub does, including #anchors.
"""

import os
import re
import unittest

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DOCS = os.path.join(_REPO, "docs")
_IMAGES = os.path.join(_DOCS, "images")

_FENCE = re.compile(r"^\s*(```|~~~).*?^\s*\1", re.DOTALL | re.MULTILINE)
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_MD_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^\s)>]+)")
_HTML_SRC = re.compile(r"<(?:img|a)\b[^>]*?\s(?:src|href)=[\"']([^\"']+)[\"']", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)


def _doc_paths():
    return [os.path.join(_REPO, "README.md")] + sorted(
        os.path.join(_DOCS, name) for name in os.listdir(_DOCS) if name.endswith(".md"))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _slugs(markdown):
    """The anchors GitHub generates for the headings in some markdown."""
    seen = {}
    slugs = set()
    for _, text in _HEADING.findall(_FENCE.sub("", markdown)):
        text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text).replace("`", "").replace("*", "")
        slug = re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        slugs.add(slug if count == 0 else f"{slug}-{count}")
    return slugs


def _targets(path):
    """Relative link and image targets in a markdown file, outside code."""
    body = _INLINE_CODE.sub("", _FENCE.sub("", _read(path)))
    found = _MD_LINK.findall(body) + _HTML_SRC.findall(body)
    return [t for t in found if "://" not in t and not t.startswith("mailto:")]


class TestDocLinks(unittest.TestCase):
    """Every relative link and image in the docs resolves."""

    def test_docs_found(self):
        names = {os.path.basename(p) for p in _doc_paths()}
        for name in ("README.md", "configuration.md", "entities.md", "automations.md", "dashboards.md"):
            self.assertIn(name, names)

    def test_relative_targets_exist(self):
        for path in _doc_paths():
            for target in _targets(path):
                file_part = target.split("#", 1)[0]
                if not file_part:
                    continue
                resolved = os.path.normpath(os.path.join(os.path.dirname(path), file_part))
                with self.subTest(doc=os.path.relpath(path, _REPO), target=target):
                    self.assertTrue(resolved.startswith(_REPO + os.sep), "points outside the repository")
                    self.assertTrue(os.path.exists(resolved), "target does not exist")

    def test_anchors_exist(self):
        for path in _doc_paths():
            for target in _targets(path):
                if "#" not in target:
                    continue
                file_part, anchor = target.split("#", 1)
                linked = os.path.normpath(os.path.join(os.path.dirname(path), file_part)) if file_part else path
                if not linked.endswith(".md") or not os.path.exists(linked):
                    continue
                with self.subTest(doc=os.path.relpath(path, _REPO), target=target):
                    self.assertIn(anchor, _slugs(_read(linked)), "no heading has this anchor")

    def test_every_image_is_used(self):
        used = set()
        for path in _doc_paths():
            for target in _targets(path):
                used.add(os.path.normpath(os.path.join(os.path.dirname(path), target.split("#", 1)[0])))
        for name in sorted(os.listdir(_IMAGES)):
            with self.subTest(image=name):
                self.assertIn(os.path.join(_IMAGES, name), used, "image is not referenced by any doc")


class TestSiteLinks(unittest.TestCase):
    """Links to the documentation site point at pages that exist in docs/.

    README.md and info.md link to the GitHub Pages site built from docs/
    (website/), so renaming a page or a heading there would break them.
    """

    _SITE = "https://dawg-io.github.io/noaa_it_all/"

    def test_site_links_resolve(self):
        found = 0
        for name in ("README.md", "info.md"):
            body = _INLINE_CODE.sub("", _FENCE.sub("", _read(os.path.join(_REPO, name))))
            for target in _MD_LINK.findall(body):
                if not target.startswith(self._SITE):
                    continue
                found += 1
                path, _, anchor = target[len(self._SITE):].partition("#")
                page = os.path.join(_DOCS, (path.strip("/") or "README") + ".md")
                with self.subTest(doc=name, target=target):
                    self.assertTrue(os.path.isfile(page), "no such page in docs/")
                    if anchor:
                        self.assertIn(anchor, _slugs(_read(page)), "no heading has this anchor")
        self.assertTrue(found, "no links to the documentation site found -- extraction is broken")


class TestSlugs(unittest.TestCase):
    """The slug function matches GitHub for the heading shapes the docs use."""

    def test_shapes(self):
        self.assertEqual(_slugs("## Troubleshooting & FAQ"), {"troubleshooting--faq"})
        self.assertEqual(_slugs("## Upgrading from 0.9.x"), {"upgrading-from-09x"})
        self.assertEqual(_slugs("## 📍 NOAA {OFFICE} Weather"), {"-noaa-office-weather"})
        self.assertEqual(_slugs('## "icon not available" in HACS'), {"icon-not-available-in-hacs"})
        self.assertEqual(_slugs("## FAQ\n## FAQ"), {"faq", "faq-1"})
        self.assertEqual(_slugs("```\n# a comment\n```\n## Real"), {"real"})


if __name__ == "__main__":
    unittest.main()
