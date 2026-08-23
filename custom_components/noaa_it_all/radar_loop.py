"""Accumulate NEXRAD frames locally and assemble them into a long radar loop.

NOAA publishes a ready-made animation at ``{SITE}_loop.gif``, but it is fixed
at ten frames covering roughly fifty minutes, and the server keeps only those
ten frames.  A longer loop therefore cannot be downloaded; it has to be built
from frames collected over time.  This module owns that: a small on-disk ring
of single-scan GIFs per radar site, a sampler that picks evenly spaced frames
out of it, and a Pillow encoder that stitches them into one animation.

Nothing here imports Home Assistant.  ``hass`` is passed in solely to borrow
its executor, which keeps the file and image work off the event loop -- and
keeps this module testable against a real directory and a real Pillow without
any of the module mocking the entity tests need.
"""

from __future__ import annotations

import io
import logging
import os
import shutil
from collections import namedtuple
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from .const import (
    RADAR_FRAME_FUTURE_SLACK_MINUTES,
    RADAR_FRAME_MAX_FILES,
    RADAR_LOOP_BACKGROUND,
    RADAR_LOOP_FRAME_MS,
    RADAR_LOOP_LAST_FRAME_MS,
    RADAR_LOOP_MAX_BYTES,
)

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:  # pragma: no cover - Pillow ships with Home Assistant core
    Image = None
    PIL_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

# What ``assemble_gif`` hands back: the encoded animation, and the frames it
# actually used.  The caller needs the second part to describe the loop
# honestly -- a frame dropped as unreadable, or shed to get under the size
# limit, is not in the animation and must not be counted as though it were.
RadarLoop = namedtuple("RadarLoop", "data paths")

# Sorts lexicographically in the same order it sorts chronologically, which is
# what lets the directory listing double as the index.
_NAME_FORMAT = "%Y%m%dT%H%M%SZ"
_SUFFIX = ".gif"
_TEMP_SUFFIX = ".tmp"


def parse_http_date(value):
    """Return an aware UTC datetime for an HTTP date header, or None.

    Used on ``Last-Modified``, which for the radar endpoint is the time NOAA
    published the scan.  Anything unparseable is None rather than an exception:
    a header NOAA changed the shape of must not take the loop down.
    """
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (AttributeError, TypeError, ValueError):
        # AttributeError covers a non-string slipping through: the header is
        # whatever the response handed us, and none of this is worth an
        # exception that would take the radar loop down.
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def frame_name(timestamp: datetime) -> str:
    """Return the on-disk file name for a frame captured at ``timestamp``."""
    if timestamp.tzinfo is not None:
        timestamp = timestamp.astimezone(timezone.utc)
    return f"{timestamp.strftime(_NAME_FORMAT)}{_SUFFIX}"


def _parse_frame_name(name: str):
    """Return the timestamp encoded in a frame file name, or None."""
    if not name.endswith(_SUFFIX):
        return None
    try:
        parsed = datetime.strptime(name[: -len(_SUFFIX)], _NAME_FORMAT)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


class RadarFrameStore:
    """A per-radar-site directory of single-scan GIFs, keyed by scan time.

    The file name *is* the index -- there is no sidecar manifest to drift out
    of step with the directory, and no whole-buffer rewrite on every poll.  A
    frame that is already on disk is never rewritten, which is what makes
    "have we seen this scan?" a cheap existence check rather than a comparison.
    """

    def __init__(self, hass, base_dir: str, radar_site: str) -> None:
        """Store the paths; no I/O happens until a method is awaited."""
        self._hass = hass
        self._radar_site = radar_site
        self._dir = os.path.join(base_dir, radar_site)

    @property
    def path(self) -> str:
        """Return the directory this store writes frames to."""
        return self._dir

    # -- Reading ---------------------------------------------------------

    async def async_frames(self):
        """Return [(timestamp, path), ...] for stored frames, oldest first.

        Only names and times cross back to the caller.  Frame bytes are read
        once, inside the encoder, so a full window never sits in memory.
        """
        return await self._hass.async_add_executor_job(self._frames)

    def _frames(self):
        """List and sort the frame directory (executor side)."""
        try:
            entries = os.listdir(self._dir)
        except FileNotFoundError:
            return []
        except OSError as err:
            _LOGGER.warning(
                "Could not list the radar frame directory for %s: %s",
                self._radar_site, err,
            )
            return []

        frames = []
        for name in entries:
            timestamp = _parse_frame_name(name)
            if timestamp is not None:
                frames.append((timestamp, os.path.join(self._dir, name)))
        frames.sort(key=lambda item: item[0])
        return frames

    # -- Writing ---------------------------------------------------------

    async def async_add_frame(self, timestamp: datetime, data: bytes) -> bool:
        """Store one scan, returning True only if it was genuinely new.

        False covers both "we already had this scan" and "the disk would not
        take it".  Neither is an error the dashboard should ever notice.
        """
        return await self._hass.async_add_executor_job(
            self._add_frame, timestamp, data
        )

    def _add_frame(self, timestamp: datetime, data: bytes) -> bool:
        """Write a frame atomically, skipping one we already hold."""
        target = os.path.join(self._dir, frame_name(timestamp))
        if os.path.exists(target):
            return False
        temporary = f"{target}{_TEMP_SUFFIX}"
        try:
            os.makedirs(self._dir, exist_ok=True)
            with open(temporary, "wb") as handle:
                handle.write(data)
            # Rename rather than write in place: a crash or a full disk part
            # way through must not leave a truncated frame behind, because the
            # name is all the encoder has to go on.
            os.replace(temporary, target)
        except OSError as err:
            _LOGGER.warning(
                "Could not store a radar frame for %s: %s", self._radar_site, err
            )
            self._unlink(temporary)
            return False
        return True

    # -- Pruning ---------------------------------------------------------

    async def async_prune(self, window: timedelta, now: datetime) -> int:
        """Drop frames outside ``window`` and return how many were removed."""
        return await self._hass.async_add_executor_job(self._prune, window, now)

    def _prune(self, window: timedelta, now: datetime) -> int:
        """Delete expired frames, junk names and abandoned temp files."""
        try:
            entries = os.listdir(self._dir)
        except FileNotFoundError:
            return 0
        except OSError as err:
            _LOGGER.warning(
                "Could not prune radar frames for %s: %s", self._radar_site, err
            )
            return 0

        cutoff = now - window
        # A frame dated in the future is the product of a wrong clock -- either
        # ours when it was written, or NOAA's Last-Modified.  Ageing cannot
        # reach it, so without an upper bound it would outlive every real frame
        # and hold the loop on a set that never updates.  A little slack
        # absorbs ordinary clock skew.
        horizon = now + timedelta(minutes=RADAR_FRAME_FUTURE_SLACK_MINUTES)
        removed = 0
        keep = []
        for name in entries:
            path = os.path.join(self._dir, name)
            timestamp = _parse_frame_name(name)
            # Anything that is not a frame we can date -- an abandoned .tmp, a
            # file someone dropped in by hand -- is not useful and cannot be
            # aged out later, so it goes now.
            if timestamp is None or timestamp < cutoff or timestamp > horizon:
                removed += self._unlink(path)
                continue
            keep.append((timestamp, path))

        # Backstop against a directory growing without bound for any reason the
        # window did not catch.  Frames are now known to be inside it, so
        # trimming the oldest is the right end.
        if len(keep) > RADAR_FRAME_MAX_FILES:
            keep.sort(key=lambda item: item[0])
            for _, path in keep[: len(keep) - RADAR_FRAME_MAX_FILES]:
                removed += self._unlink(path)
        return removed

    async def async_discard(self, path: str) -> None:
        """Delete a single frame that turned out to be unreadable."""
        await self._hass.async_add_executor_job(self._unlink, path)

    async def async_remove_all(self) -> None:
        """Delete this site's frame directory, for entry removal."""
        await self._hass.async_add_executor_job(self._remove_all)

    def _remove_all(self) -> None:
        """Remove the site directory and everything under it."""
        try:
            shutil.rmtree(self._dir)
        except FileNotFoundError:
            return
        except OSError as err:
            _LOGGER.warning(
                "Could not remove stored radar frames for %s: %s",
                self._radar_site, err,
            )

    @staticmethod
    def _unlink(path: str) -> int:
        """Delete one file, returning 1 if it went away."""
        try:
            os.unlink(path)
        except FileNotFoundError:
            return 0
        except OSError as err:
            _LOGGER.debug("Could not remove %s: %s", path, err)
            return 0
        return 1


def select_frames(frames, *, window: timedelta, max_frames: int, now: datetime):
    """Pick up to ``max_frames`` evenly spaced frames, oldest first.

    Sampling is by *time*, not by position in the list: walk backwards from
    ``now`` in fixed steps and take the nearest frame to each step.  Decimating
    every Nth item instead would re-space the whole loop whenever a poll was
    missed, and again whenever the configured duration changed.

    The newest frame is always the step-zero target, so the animation always
    ends on the current scan.
    """
    if not frames or max_frames < 1:
        return []

    # Filter by the window first.  Skipping straight to "few enough frames,
    # take them all" would put frames from outside the requested window into
    # the loop whenever pruning had not caught up -- and then report them as
    # the window it covers.
    cutoff = now - window
    inside = [item for item in frames if cutoff <= item[0] <= now]
    if not inside:
        return []
    if len(inside) <= max_frames:
        return [path for _, path in inside]
    frames = inside

    step = window / max_frames
    tolerance = step / 2
    chosen = {}
    for index in range(max_frames):
        target = now - step * index
        best = min(frames, key=lambda item: abs(item[0] - target))
        # A gap in the buffer shortens the loop rather than filling it with a
        # frame from the wrong time.
        if abs(best[0] - target) <= tolerance:
            chosen[best[0]] = best[1]
    return [chosen[timestamp] for timestamp in sorted(chosen)]


def _load_frame(path: str, size, background):
    """Return one frame as an opaque RGB image, or None if it is unusable.

    Converting via RGBA applies that frame's own palette and turns its
    transparency index into real alpha, which is what makes frames with
    different palettes comparable.  Compositing onto a solid colour then drops
    transparency entirely, so the encoder never has to reconcile a transparency
    index across frames -- the failure that turns a radar loop psychedelic.
    """
    try:
        with Image.open(path) as source:
            frame = source.convert("RGBA")
    except (OSError, ValueError) as err:
        _LOGGER.debug("Skipping unreadable radar frame %s: %s", path, err)
        return None
    if size is not None and frame.size != size:
        # NOAA has changed product dimensions before.  Older frames are still
        # worth showing, so scale rather than discard.
        frame = frame.resize(size)
    backdrop = Image.new("RGBA", frame.size, tuple(background) + (255,))
    return Image.alpha_composite(backdrop, frame).convert("RGB")


def _probe(path):
    """Return a frame's dimensions without decoding it, or None if unreadable.

    ``Image.open`` only reads the header, so this costs a stat and a few bytes
    per frame -- cheap enough to run over the whole window before committing to
    decoding any of it.
    """
    try:
        with Image.open(path) as source:
            return source.size
    except (OSError, ValueError) as err:
        _LOGGER.debug("Skipping unreadable radar frame %s: %s", path, err)
        return None


def _master_palette(paths, size, background, samples=8):
    """Build one palette that covers the whole animation.

    Deriving the palette from the first frame alone looks reasonable and is
    badly wrong: an overnight loop starts on an empty radar, so frame one
    contains nothing but background, and every echo that appears later gets
    mapped to the nearest colour that frame happened to contain -- black.  The
    storm silently disappears.  Sampling across the window instead means the
    palette has seen the loop's colours before it has to encode them.
    """
    picked = paths
    if len(paths) > samples:
        step = (len(paths) - 1) / (samples - 1)
        picked = [paths[round(index * step)] for index in range(samples)]

    loaded = [
        frame for frame in (_load_frame(path, size, background) for path in picked)
        if frame is not None
    ]
    if not loaded:
        return None

    width, height = loaded[0].size
    montage = Image.new("RGB", (width, height * len(loaded)))
    for index, frame in enumerate(loaded):
        montage.paste(frame, (0, index * height))
    return montage.quantize(
        colors=255, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
    )


def _encode(paths, *, frame_ms, last_frame_ms, background):
    """Encode the given frame paths into one animated GIF."""
    # Establish the frame list from headers alone first.  The durations list
    # has to match the frames actually written, so the set of frames has to be
    # settled before encoding starts rather than discovered during it.
    usable = [path for path in paths if _probe(path) is not None]

    # The newest frame sets the dimensions everything else is scaled to.  Using
    # the oldest instead would mean that after NOAA changed a product's size,
    # every new full-resolution scan was squeezed back down to the old one for
    # a whole window -- degrading the frames that matter to preserve the ones
    # about to age out.
    size = None
    while usable:
        size = _probe(usable[-1])
        if size is not None:
            break
        usable.pop()

    first = None
    while usable:
        first = _load_frame(usable[0], size, background)
        if first is not None:
            break
        # Header parsed but the pixels did not: drop it and take the next.
        usable.pop(0)
    if first is None or size is None or len(usable) < 2:
        return None

    # One palette for the whole animation.  Left to itself the GIF writer takes
    # frame one's palette as the global table and then remaps every later frame
    # against it, which is exactly how a radar loop ends up cycling through
    # colours it never contained.
    master = _master_palette(usable, size, background)
    if master is None:
        return None

    lead = first.quantize(palette=master, dither=Image.Dither.NONE)

    def _quantized(path_list):
        """Yield frames one at a time so the whole window is never resident."""
        previous = lead
        for path in path_list:
            frame = _load_frame(path, size, background)
            if frame is None:
                # Repeat the previous frame rather than yielding nothing: the
                # durations below are already fixed, so a short yield would
                # slide the hold off the newest frame.  A corrupt frame reads
                # as a momentary freeze instead.
                yield previous
                continue
            previous = frame.quantize(palette=master, dither=Image.Dither.NONE)
            yield previous

    # Pillow drops a frame that is pixel-identical to the one before it and
    # adds its duration to that frame instead, so the encoded animation can
    # legitimately contain fewer frames than there are paths -- a clear
    # overnight radar collapses to one long still.  Total playback time is
    # preserved, and the hold still lands on the newest frame, so this is left
    # alone: it is free compression on exactly the frames worth nothing.
    durations = [frame_ms] * (len(usable) - 1) + [last_frame_ms]
    buffer = io.BytesIO()
    lead.save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=_quantized(usable[1:]),
        duration=durations,
        loop=0,
        # Every frame is opaque and covers the one before it, so there is
        # nothing to restore between frames.
        disposal=1,
        # Pillow's optimiser re-derives a palette per frame, undoing the shared
        # table above for no useful gain once the table is already minimal.
        optimize=False,
    )
    return RadarLoop(buffer.getvalue(), usable)


def assemble_gif(
    paths,
    *,
    frame_ms: int = RADAR_LOOP_FRAME_MS,
    last_frame_ms: int = RADAR_LOOP_LAST_FRAME_MS,
    max_bytes: int = RADAR_LOOP_MAX_BYTES,
    background=RADAR_LOOP_BACKGROUND,
):
    """Return a :class:`RadarLoop`, or None if one cannot be made.

    The result carries the frames actually encoded as well as the bytes, so the
    caller can describe the animation truthfully rather than assuming it got
    everything it asked for.

    Synchronous and CPU-bound -- callers run it in an executor.  Every failure
    is None rather than an exception, because the caller's response to "no loop
    this time" is to keep showing the previous one.
    """
    if not PIL_AVAILABLE:
        _LOGGER.debug("Pillow is unavailable, so no local radar loop was built")
        return None
    if len(paths) < 2:
        return None

    try:
        result = _encode(
            paths,
            frame_ms=frame_ms,
            last_frame_ms=last_frame_ms,
            background=background,
        )
        if result is None:
            return None
        if len(result.data) > max_bytes:
            # Rather than push something absurd through the image proxy, halve
            # the frame count and try once more.  Sampling every other frame
            # keeps the window the same length and only coarsens it.
            #
            # Counted back from the end, not forward from the start: with an
            # even number of frames, every other one from the front excludes
            # the last, which would leave the animation ending -- and holding
            # -- on a scan that is not the current one.
            thinned = paths[::-2][::-1]
            _LOGGER.warning(
                "The radar loop came to %d bytes over the %d byte limit; "
                "rebuilding it with %d of %d frames",
                len(result.data), max_bytes, len(thinned), len(paths),
            )
            result = _encode(
                thinned,
                frame_ms=frame_ms,
                last_frame_ms=last_frame_ms,
                background=background,
            )
            if result is None:
                return None
            if len(result.data) > max_bytes:
                _LOGGER.warning(
                    "The radar loop is still %d bytes; falling back to NOAA's "
                    "own loop", len(result.data),
                )
                return None
    except Exception as err:  # noqa: BLE001 - a bad frame must not break the entity
        _LOGGER.warning("Could not assemble the radar loop: %s", err)
        return None

    _LOGGER.debug(
        "Assembled a %d frame radar loop (%d bytes)",
        len(result.paths), len(result.data),
    )
    return result
