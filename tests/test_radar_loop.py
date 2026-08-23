"""Tests for radar_loop.py: the frame store, the sampler and the GIF encoder.

Unlike the entity tests, nothing here mocks Home Assistant -- ``radar_loop``
deliberately imports none of it.  These run against a real temporary directory
and a real Pillow, which is the only way the encoder's palette handling can
actually be checked.
"""

import asyncio
import importlib
import os
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ``noaa_it_all/__init__.py`` imports Home Assistant, so importing the package
# the ordinary way here would mean mocking half of it -- exactly what keeping
# Home Assistant out of radar_loop was meant to avoid.  Instead, mount the same
# directory under a private package name and import the one submodule from
# there.  Its ``from .const import`` resolves against that name, const imports
# nothing but the standard library, and ``sys.modules["noaa_it_all"]`` is left
# alone for the test modules that do want the real package.
_PACKAGE = "_noaa_it_all_radar_loop"

if _PACKAGE not in sys.modules:
    _shim = types.ModuleType(_PACKAGE)
    _shim.__path__ = [os.path.join(_CC, "noaa_it_all")]
    sys.modules[_PACKAGE] = _shim

radar_loop = importlib.import_module(f"{_PACKAGE}.radar_loop")

PIL_AVAILABLE = radar_loop.PIL_AVAILABLE
RadarFrameStore = radar_loop.RadarFrameStore
assemble_gif = radar_loop.assemble_gif
frame_name = radar_loop.frame_name
parse_http_date = radar_loop.parse_http_date
select_frames = radar_loop.select_frames

if PIL_AVAILABLE:
    from PIL import Image


NOW = datetime(2026, 8, 23, 12, 0, 0, tzinfo=timezone.utc)

# NWS reflectivity is a fixed scale of roughly this many colours.
SCALE = [
    (4, 233, 231), (1, 159, 244), (3, 0, 244), (2, 253, 2), (1, 197, 1),
    (0, 142, 0), (253, 248, 2), (229, 188, 0), (253, 149, 0), (253, 0, 0),
    (212, 0, 0), (188, 0, 0), (248, 0, 253), (152, 84, 198),
]


def _run(coro):
    """Run a coroutine on a private loop, leaving the ambient one intact.

    Mirrors the helper in test_image.py: ``asyncio.run()`` clears the thread's
    current event loop on return, which breaks other test modules.
    """
    previous = None
    try:
        previous = asyncio.get_event_loop_policy().get_event_loop()
    except RuntimeError:
        pass
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(previous)


class _FakeHass:
    """Runs "executor" work inline; the store only needs the one method."""

    def __init__(self):
        self.calls = 0

    async def async_add_executor_job(self, func, *args):
        self.calls += 1
        return func(*args)


def _write_frame(path, colour=(253, 0, 0), size=(60, 40), empty=False):
    """Write a transparent, separately-palettised GIF, as RIDGE serves them.

    Index 0 is the transparent background and the echo colours follow, so each
    frame carries its own palette -- the arrangement that makes naively
    concatenating frames go wrong.
    """
    image = Image.new("P", size, 0)
    palette = [0, 0, 0] + list(colour) + [0, 0, 0] * 254
    image.putpalette(palette)
    if not empty:
        for x in range(size[0] // 6, size[0] // 6 * 5):
            for y in range(size[1] // 4, size[1] // 4 * 3):
                image.putpixel((x, y), 1)
    image.save(path, transparency=0)


class TestParseHttpDate(unittest.TestCase):
    """Last-Modified is the frame's identity, so parsing it must not throw."""

    def test_a_real_header_parses_to_utc(self):
        parsed = parse_http_date("Sun, 23 Aug 2026 11:54:00 GMT")
        self.assertEqual(datetime(2026, 8, 23, 11, 54, tzinfo=timezone.utc), parsed)

    def test_unparseable_input_is_none_rather_than_an_exception(self):
        for value in (None, "", "not a date", "Sun, 99 Xxx 2026", 17):
            with self.subTest(value=value):
                self.assertIsNone(parse_http_date(value))


class TestFrameStore(unittest.TestCase):
    """The file name is the index, so naming and dedup carry the weight."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.hass = _FakeHass()
        self.store = RadarFrameStore(self.hass, self._tmp.name, "KLTX")

    def _add(self, minutes_ago, data=b"gif-bytes"):
        return _run(self.store.async_add_frame(
            NOW - timedelta(minutes=minutes_ago), data
        ))

    def test_a_frame_is_written_under_its_timestamp(self):
        self.assertTrue(self._add(0))
        self.assertEqual(
            ["20260823T120000Z.gif"], os.listdir(self.store.path)
        )

    def test_the_same_scan_is_never_stored_twice(self):
        self.assertTrue(self._add(0, b"first"))
        self.assertFalse(self._add(0, b"second"))
        stored = os.path.join(self.store.path, "20260823T120000Z.gif")
        # The original must survive: re-fetching a scan we already hold is the
        # steady state, not a correction.
        self.assertEqual(b"first", open(stored, "rb").read())

    def test_a_successful_write_leaves_no_temporary_file(self):
        self._add(0)
        self.assertEqual(
            [], [n for n in os.listdir(self.store.path) if n.endswith(".tmp")]
        )

    def test_frames_come_back_oldest_first(self):
        for minutes in (30, 0, 60, 15):
            self._add(minutes)
        frames = _run(self.store.async_frames())
        self.assertEqual(sorted(t for t, _ in frames), [t for t, _ in frames])
        self.assertEqual(4, len(frames))

    def test_a_missing_directory_reads_as_empty(self):
        self.assertEqual([], _run(self.store.async_frames()))

    def test_pruning_drops_frames_outside_the_window(self):
        self._add(10)
        self._add(400)
        removed = _run(self.store.async_prune(timedelta(hours=1), NOW))
        self.assertEqual(1, removed)
        self.assertEqual(1, len(_run(self.store.async_frames())))

    def test_pruning_removes_names_it_cannot_date(self):
        self._add(0)
        os.makedirs(self.store.path, exist_ok=True)
        for junk in ("notes.txt", "20260823T120000Z.gif.tmp", "half-written"):
            open(os.path.join(self.store.path, junk), "w").close()
        _run(self.store.async_prune(timedelta(hours=1), NOW))
        self.assertEqual(["20260823T120000Z.gif"], os.listdir(self.store.path))

    def test_frames_dated_in_the_future_are_discarded(self):
        """A wrong clock must not produce frames that outlive every real one.

        Ageing works backwards from now, so a future-dated frame is never
        reached by the cutoff. Without an upper bound it would survive
        indefinitely while genuine frames aged out around it, and the loop
        would stick on a set that never updates.
        """
        self._add(10)
        self._add(-600)  # ten hours ahead of the clock
        removed = _run(self.store.async_prune(timedelta(hours=24), NOW))
        self.assertEqual(1, removed)
        remaining = _run(self.store.async_frames())
        self.assertEqual([NOW - timedelta(minutes=10)], [t for t, _ in remaining])

    def test_ordinary_clock_skew_is_tolerated(self):
        """NOAA's clock and ours need not agree to the second."""
        self._add(-5)
        _run(self.store.async_prune(timedelta(hours=24), NOW))
        self.assertEqual(1, len(_run(self.store.async_frames())))

    def test_the_file_cap_trims_the_oldest(self):
        original = radar_loop.RADAR_FRAME_MAX_FILES
        radar_loop.RADAR_FRAME_MAX_FILES = 5
        self.addCleanup(setattr, radar_loop, "RADAR_FRAME_MAX_FILES", original)
        for minutes in range(0, 80, 10):
            self._add(minutes)
        _run(self.store.async_prune(timedelta(hours=24), NOW))
        remaining = _run(self.store.async_frames())
        self.assertEqual(5, len(remaining))
        self.assertEqual(NOW, remaining[-1][0])

    def test_a_directory_that_cannot_be_created_reports_failure(self):
        """A disk that will not take the frame must not reach the dashboard.

        The blockage here is a plain file sitting where the frame directory
        needs to be, which fails identically whatever user the tests run as --
        unlike a chmod, which root ignores.
        """
        os.makedirs(os.path.dirname(self.store.path), exist_ok=True)
        with open(self.store.path, "w") as handle:
            handle.write("in the way")
        self.assertFalse(self._add(0))

    def test_removing_all_frames_clears_the_directory(self):
        self._add(0)
        _run(self.store.async_remove_all())
        self.assertFalse(os.path.exists(self.store.path))
        # Removing a store that was never written must not raise.
        _run(self.store.async_remove_all())

    def test_every_store_method_runs_off_the_event_loop(self):
        """Blocking file I/O in a coroutine stalls all of Home Assistant.

        Asserting on the call site rather than on reviewer discipline, the
        same way test_image.py guards state writes.
        """
        import ast
        import inspect

        blocking = {"listdir", "scandir", "unlink", "replace", "makedirs", "rmtree"}
        tree = ast.parse(inspect.getsource(radar_loop))
        offenders = set()
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef):
                continue
            for call in ast.walk(node):
                if isinstance(call, ast.Call):
                    func = call.func
                    if isinstance(func, ast.Name) and func.id == "open":
                        offenders.add(node.name)
                    if isinstance(func, ast.Attribute) and func.attr in blocking:
                        offenders.add(node.name)
        self.assertEqual(set(), offenders)


class TestSelectFrames(unittest.TestCase):
    """Sampling is by time, so a missed poll must not re-space the loop."""

    @staticmethod
    def _frames(count, step_minutes=10, end=NOW):
        return [
            (end - timedelta(minutes=step_minutes * i), f"/frames/{i}.gif")
            for i in range(count - 1, -1, -1)
        ]

    def test_a_short_buffer_is_used_whole(self):
        frames = self._frames(5)
        chosen = select_frames(
            frames, window=timedelta(hours=24), max_frames=72, now=NOW
        )
        self.assertEqual([p for _, p in frames], chosen)

    def test_a_full_buffer_is_thinned_to_the_cap(self):
        frames = self._frames(144)
        chosen = select_frames(
            frames, window=timedelta(hours=24), max_frames=72, now=NOW
        )
        self.assertEqual(72, len(chosen))

    def test_the_newest_frame_is_always_last(self):
        frames = self._frames(144)
        chosen = select_frames(
            frames, window=timedelta(hours=24), max_frames=72, now=NOW
        )
        self.assertEqual(frames[-1][1], chosen[-1])

    def test_a_gap_shortens_the_loop_rather_than_repeating_a_frame(self):
        """Exercises the sampler proper, so the buffer must exceed the cap.

        With 72 or fewer frames the function returns them wholesale and the
        step/tolerance logic -- the part that decides whether a gap gets filled
        with a frame from the wrong time -- never runs at all.
        """
        # Home Assistant was off for the middle eight hours of the window.
        frames = [
            (NOW - timedelta(minutes=5 * i), f"/frames/{i}.gif")
            for i in range(288)
            if not 8 * 60 <= 5 * i < 16 * 60
        ]
        self.assertGreater(len(frames), 72)
        chosen = select_frames(
            frames, window=timedelta(hours=24), max_frames=72, now=NOW
        )
        self.assertEqual(len(set(chosen)), len(chosen))
        # The gap is a third of the window, so a sampler that filled it with
        # the nearest available frame would still return the full 72.
        self.assertLess(len(chosen), 72)

    def test_an_empty_buffer_selects_nothing(self):
        self.assertEqual([], select_frames(
            [], window=timedelta(hours=24), max_frames=72, now=NOW
        ))

    def test_frames_outside_the_window_are_excluded(self):
        """A small buffer must not skip the window check.

        Pruning is what normally keeps the directory inside the window, and it
        can be behind -- a radar site stuck on one scan, or an entity that has
        just found an old directory on disk.  Handing those frames to the
        encoder would build a loop from the wrong day and then report it as
        covering the configured window.
        """
        stale = [
            (NOW - timedelta(days=5) + timedelta(minutes=10 * i), f"/old/{i}.gif")
            for i in range(10)
        ]
        self.assertEqual([], select_frames(
            stale, window=timedelta(hours=6), max_frames=72, now=NOW
        ))

    def test_a_mixed_buffer_keeps_only_the_frames_in_window(self):
        recent = self._frames(4, step_minutes=30)
        stale = [(NOW - timedelta(days=2), "/old/x.gif")]
        chosen = select_frames(
            stale + recent, window=timedelta(hours=6), max_frames=72, now=NOW
        )
        self.assertEqual([path for _, path in recent], chosen)

    def test_frames_dated_in_the_future_are_not_selected(self):
        frames = self._frames(4, step_minutes=10) + [
            (NOW + timedelta(hours=3), "/future/x.gif")
        ]
        chosen = select_frames(
            frames, window=timedelta(hours=6), max_frames=72, now=NOW
        )
        self.assertNotIn("/future/x.gif", chosen)


@unittest.skipUnless(PIL_AVAILABLE, "Pillow is required to assemble a GIF")
class TestAssembleGif(unittest.TestCase):
    """The encoder is where this feature is most likely to ship broken."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    def _frames(self, colours, size=(60, 40), empty=()):
        paths = []
        for index, colour in enumerate(colours):
            path = os.path.join(self._tmp.name, f"f{index:03d}.gif")
            _write_frame(path, colour, size=size, empty=index in empty)
            paths.append(path)
        return paths

    def _open(self, loop):
        """Write an assembled loop out and reopen it as an image."""
        out = os.path.join(self._tmp.name, "out.gif")
        with open(out, "wb") as handle:
            handle.write(loop.data)
        return Image.open(out)

    def test_the_result_names_the_frames_it_used(self):
        """Callers describe the loop from this, so it must be the truth."""
        paths = self._frames([(253, 0, 0), (2, 253, 2), (3, 0, 244)])
        broken = os.path.join(self._tmp.name, "broken.gif")
        with open(broken, "wb") as handle:
            handle.write(b"not a gif")
        loop = assemble_gif(paths + [broken])
        self.assertEqual(paths, list(loop.paths))

    def test_every_frame_keeps_its_own_colour(self):
        """The regression that matters.

        Left to itself the GIF writer adopts frame one's palette as the global
        table and remaps everything after it, so colours that appear later in
        the loop collapse to whatever frame one happened to contain.  On a real
        radar that means an overnight loop starts empty and the storm that
        arrives at noon is rendered as background.
        """
        colours = [(253, 0, 0), (2, 253, 2), (3, 0, 244)]
        result = self._open(assemble_gif(self._frames(colours)))
        self.assertEqual(3, result.n_frames)
        for index, expected in enumerate(colours):
            result.seek(index)
            actual = result.convert("RGB").getpixel((30, 20))
            with self.subTest(frame=index):
                self.assertLess(
                    max(abs(a - b) for a, b in zip(actual, expected)), 12,
                    f"frame {index} came back {actual}, expected {expected}",
                )

    def test_a_storm_arriving_after_an_empty_start_keeps_its_colours(self):
        """The palette must be sampled across the window, not taken from frame one."""
        colours = [(0, 0, 0)] * 8 + SCALE
        paths = self._frames(colours, size=(120, 90), empty=range(8))
        result = self._open(assemble_gif(paths))
        result.seek(result.n_frames - 1)
        final = result.convert("RGB")
        seen = {final.getpixel((x, 45)) for x in range(20, 100, 4)}
        seen.discard((0, 0, 0))
        self.assertTrue(seen, "the storm was flattened into the background")

    def test_the_loop_repeats_and_holds_on_the_newest_frame(self):
        paths = self._frames([(253, 0, 0), (2, 253, 2), (3, 0, 244)])
        loop = assemble_gif(paths, frame_ms=120, last_frame_ms=1500)
        result = self._open(loop)
        self.assertEqual(paths, list(loop.paths))
        durations = []
        for index in range(result.n_frames):
            result.seek(index)
            durations.append(result.info.get("duration"))
        self.assertEqual(0, result.info.get("loop"))  # 0 == forever
        self.assertEqual(1500, durations[-1])
        self.assertEqual([120] * (len(durations) - 1), durations[:-1])

    def test_identical_frames_merge_without_losing_playback_time(self):
        """Pillow collapses pixel-identical neighbours and sums their delays.

        A clear overnight radar is genuinely a still image, so this is free
        compression rather than a fault -- but the loop must still run for as
        long as it was asked to, and still end on the newest frame.
        """
        paths = self._frames([(0, 0, 0)] * 6 + [(253, 0, 0)], empty=range(6))
        result = self._open(assemble_gif(
            paths, frame_ms=100, last_frame_ms=900
        ))
        total = 0
        for index in range(result.n_frames):
            result.seek(index)
            total += result.info.get("duration")
        self.assertLess(result.n_frames, len(paths))
        self.assertEqual(100 * (len(paths) - 1) + 900, total)

    def test_too_few_frames_produce_nothing(self):
        self.assertIsNone(assemble_gif([]))
        self.assertIsNone(assemble_gif(self._frames([(253, 0, 0)])))

    def test_a_corrupt_frame_is_skipped_and_the_rest_still_assemble(self):
        paths = self._frames([(253, 0, 0), (2, 253, 2), (3, 0, 244)])
        with open(paths[1], "wb") as handle:
            handle.write(b"not a gif at all")
        with open(os.path.join(self._tmp.name, "empty.gif"), "wb"):
            pass
        paths.append(os.path.join(self._tmp.name, "empty.gif"))
        result = self._open(assemble_gif(paths))
        self.assertGreaterEqual(result.n_frames, 2)

    def test_an_oversized_loop_is_rebuilt_with_fewer_frames(self):
        paths = self._frames([c for c in SCALE], size=(120, 90))
        full = assemble_gif(paths)
        halved = assemble_gif(paths, max_bytes=len(full.data) - 1)
        self.assertIsNotNone(halved)
        self.assertLess(len(halved.data), len(full.data))
        # Thinning must count back from the newest frame, not forward from the
        # oldest: with an even frame count, every-other-from-the-front drops
        # the current scan and the hold lands on a stale one.
        self.assertIn(paths[-1], halved.paths)

    def test_a_loop_that_cannot_be_shrunk_enough_is_abandoned(self):
        paths = self._frames([c for c in SCALE], size=(120, 90))
        self.assertIsNone(assemble_gif(paths, max_bytes=1))

    def test_frames_of_differing_sizes_are_still_combined(self):
        """NOAA has changed product dimensions before; old frames still count.

        The newest frame sets the size. Taking it from the oldest would mean
        that after a product change every new full-resolution scan was scaled
        back down to the superseded dimensions for a whole window.
        """
        paths = self._frames([(253, 0, 0), (2, 253, 2)])
        odd = os.path.join(self._tmp.name, "odd.gif")
        _write_frame(odd, (3, 0, 244), size=(80, 60))
        paths.append(odd)
        result = self._open(assemble_gif(paths))
        self.assertEqual(3, result.n_frames)
        self.assertEqual((80, 60), result.size)


class TestAssembleWithoutPillow(unittest.TestCase):
    """Pillow ships with Home Assistant core, but must not be assumed."""

    def test_a_missing_pillow_degrades_instead_of_raising(self):
        original = radar_loop.PIL_AVAILABLE
        radar_loop.PIL_AVAILABLE = False
        self.addCleanup(setattr, radar_loop, "PIL_AVAILABLE", original)
        self.assertIsNone(assemble_gif(["/frames/a.gif", "/frames/b.gif"]))


class TestFrameName(unittest.TestCase):
    """Names sort chronologically because they are compared as strings."""

    def test_names_sort_in_time_order(self):
        times = [
            NOW - timedelta(minutes=90),
            NOW - timedelta(minutes=5),
            NOW - timedelta(hours=23),
        ]
        names = [frame_name(t) for t in times]
        self.assertEqual(
            [frame_name(t) for t in sorted(times)], sorted(names)
        )

    def test_a_naive_timestamp_is_treated_as_utc(self):
        self.assertEqual(
            frame_name(NOW), frame_name(NOW.replace(tzinfo=None))
        )


if __name__ == "__main__":
    unittest.main()
