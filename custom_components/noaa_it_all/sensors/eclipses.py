"""Eclipse sensors for NOAA Integration.

Three sensors over ``EclipseCoordinator.data``: what is coming, how much of it you will actually
see, and how worthwhile that is. Like the meteor sensors these are thin projections -- every
value including the local time strings is pre-computed in ``eclipse.build_eclipse_forecast`` --
so these classes stay simple property readers.

The distinction that runs through all three is between the eclipse and *your* eclipse. A total
solar eclipse is total along a strip a couple of hundred kilometres wide and partial across a
continent, so the type these sensors report is always the one this observer gets, with the
headline classification kept alongside it as ``global_type``.
"""

import logging

from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import ECLIPSE_UPCOMING_MIN_COVERAGE
from .meteor_showers import space_device_info

_LOGGER = logging.getLogger(__name__)


class _EclipseBaseSensor(CoordinatorEntity):
    """Shared plumbing for the eclipse sensors.

    Uses ``_attr_has_entity_name = True`` so Home Assistant combines the device name with the
    local entity name, producing entity IDs like ``sensor.noaa_ilm_space_next_eclipse``.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator, office_code):
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._office_code = office_code

    @property
    def _forecast(self):
        """Return the coordinator payload, or an empty dict before the first refresh."""
        return self.coordinator.data or {}

    @property
    def _headline(self):
        """Return the eclipse these sensors describe, or ``None`` when there is none.

        An eclipse under way outranks the next one: during the ninety seconds of totality the
        interesting question is not what happens in 2029.
        """
        forecast = self._forecast
        return forecast.get("current") or forecast.get("next")

    @property
    def device_info(self):
        """Return device information to group this entity."""
        return space_device_info(self._office_code)


class NextEclipseSensor(_EclipseBaseSensor):
    """The next eclipse visible from here, named as this observer will see it."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Next Eclipse"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_next_eclipse"

    @property
    def state(self):
        """Return the name of the next visible eclipse, or ``None``."""
        headline = self._headline
        return headline["name"] if headline else "None"

    @property
    def icon(self):
        """Return the icon."""
        headline = self._headline
        if headline and headline["kind"] == "lunar":
            return "mdi:moon-waning-crescent"
        return "mdi:weather-sunny-off"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        forecast = self._forecast
        attrs = {
            "office_code": self._office_code,
            "upcoming": forecast.get("upcoming") or [],
            "catalog_last_year": forecast.get("catalog_last_year"),
            "catalog_exhausted": forecast.get("catalog_exhausted", False),
        }

        # Which solar eclipse is next *anywhere* is worth saying even when none of it reaches
        # here, because otherwise a user who has just seen one on the news is told the next
        # solar eclipse is in 2041.
        global_next = forecast.get("next_solar_global")
        if global_next:
            attrs["next_solar_anywhere"] = global_next["name"]
            attrs["next_solar_anywhere_date"] = global_next["date"]
            attrs["next_solar_anywhere_days"] = global_next["days_until"]

        headline = self._headline
        if headline:
            attrs.update({
                "kind": headline["kind"],
                "eclipse_type": headline["type"],
                "global_type": headline["global_type"],
                "date": headline["date"],
                "in_progress": headline["in_progress"],
                "days_until": headline["days_until"],
                "starts_local": headline["start_local"],
                "maximum_local": headline["max_local"],
                "ends_local": headline["end_local"],
                "disc_covered": headline["disc_covered"],
                "viewing_score": headline["viewing_score"],
                "rating": headline["rating"],
                "altitude_when_visible": headline["altitude_when_visible"],
                "look_towards": headline["direction_when_visible"],
                "eye_protection_required": headline["eye_protection_required"],
            })
        return attrs


class EclipseCoverageSensor(_EclipseBaseSensor):
    """How much of the Sun or Moon you will actually see covered, as a percentage.

    This is the "will I get 29% or all of it" number. It is the fraction of the disc's **area**
    that is hidden, not of its diameter -- eclipse magnitude, the figure usually quoted, is the
    diameter fraction, and the two are far apart: magnitude 0.5 is only 39% covered. Magnitude is
    kept as an attribute for anyone comparing against a published table.

    The state is what is covered at the best moment the body is actually **above your horizon**,
    which is not always the greatest eclipse: where the Sun sets mid-eclipse the peak happens
    underground. ``peak_disc_covered`` reports the geometric maximum for comparison.
    """

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Eclipse Coverage"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_eclipse_coverage"

    @property
    def state(self):
        """Return the percentage of the disc covered at the best visible moment."""
        headline = self._headline
        return headline["disc_covered"] if headline else 0

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:circle-slice-4"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        headline = self._headline
        if not headline:
            return {
                "office_code": self._office_code,
                "eclipse": None,
                "visible": False,
                "peak_disc_covered": 0,
                "magnitude": 0,
            }

        attrs = {
            "office_code": self._office_code,
            "eclipse": headline["name"],
            "kind": headline["kind"],
            "eclipse_type": headline["type"],
            "global_type": headline["global_type"],
            "visible": headline["visible"],
            "not_visible_reason": headline["not_visible_reason"],
            "peak_disc_covered": headline["peak_disc_covered"],
            "magnitude": headline["magnitude"],
            "gamma": headline["gamma"],
            "visible_fraction": headline["visible_fraction"],
            "in_progress_at_rise": headline["in_progress_at_rise"],
            "in_progress_at_set": headline["in_progress_at_set"],
            "starts_local": headline["start_local"],
            "maximum_local": headline["max_local"],
            "ends_local": headline["end_local"],
            "duration_seconds": headline["duration_s"],
        }
        if headline["kind"] == "lunar":
            attrs["umbral_magnitude"] = headline["umbral_magnitude"]
            attrs["penumbral_magnitude"] = headline["penumbral_magnitude"]
        return attrs


class EclipseViewingScoreSensor(_EclipseBaseSensor):
    """How worthwhile the next eclipse is from here, 0-100.

    Unlike the meteor viewing score this deliberately does *not* factor out the strength of the
    event. It cannot: whether the Moon covers a tenth of the Sun or all of it is the single most
    important thing about a solar eclipse, so a score that measured only conditions would rate an
    imperceptible nibble under a clear sky as highly as totality.

    Like the meteor score it accounts for altitude and, for lunar eclipses, sky darkness -- and
    like it, it knows nothing about cloud. Pair it with
    ``sensor.noaa_{office}_weather_cloud_cover`` if you want that.
    """

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Eclipse Viewing Score"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_eclipse_viewing_score"

    @property
    def state(self):
        """Return the 0-100 viewing score for the next visible eclipse."""
        headline = self._headline
        return headline["viewing_score"] if headline else 0

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:telescope"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        headline = self._headline
        if not headline:
            return {
                "office_code": self._office_code,
                "rating": "Poor",
                "eclipse": None,
                "limiting_factor": "no eclipse due",
                "worthwhile_threshold": ECLIPSE_UPCOMING_MIN_COVERAGE,
            }

        return {
            "office_code": self._office_code,
            "rating": headline["rating"],
            "eclipse": headline["name"],
            "kind": headline["kind"],
            "eclipse_type": headline["type"],
            "limiting_factor": headline["limiting_factor"],
            "disc_covered": headline["disc_covered"],
            # The geometry at the moment worth watching, which is where people should be
            # looking -- not the geometry at greatest eclipse, which for a body that sets partway
            # through is a point below the horizon.
            "altitude_when_visible": headline["altitude_when_visible"],
            "azimuth_when_visible": headline["azimuth_when_visible"],
            "look_towards": headline["direction_when_visible"],
            "altitude_at_maximum": headline["altitude_at_max"],
            "watch_from_local": headline["visible_start_local"],
            "watch_until_local": headline["visible_end_local"],
            "totality_starts_local": headline["central_start_local"],
            "totality_ends_local": headline["central_end_local"],
            "totality_seconds": headline["central_duration_s"],
            "eye_protection_required": headline["eye_protection_required"],
            "safe_without_filter": headline["safe_unfiltered"],
            "eye_safety": headline["eye_safety"],
            "worthwhile_threshold": ECLIPSE_UPCOMING_MIN_COVERAGE,
        }


class NextEclipseTimeSensor(_EclipseBaseSensor):
    """When the next eclipse becomes watchable from here, as a timestamp.

    The companion to Next Eclipse, which names the event: this one dates it. Its state is the
    moment the eclipse has begun **and** the Sun or Moon is above your horizon -- for an eclipse
    already under way at moonrise that is moonrise, not first contact -- so it answers "when do I
    go outside" rather than "when does the geometry start".

    Home Assistant renders a timestamp natively, so a card shows "in 3 days" or "8:29 PM" without
    a template, and a time trigger can fire off this entity directly. That is the point of it: the
    same instant was always available as an attribute of Next Eclipse, but only as a string that
    every automation had to convert by hand.

    Like its siblings it reads the current eclipse in preference to the next one, so mid-event it
    reports when *this* one became watchable and reads as "started twenty minutes ago" -- which is
    the useful thing to say while somebody is outside looking at it.

    **On the device class.** This returns an ISO-8601 string and declares ``device_class`` as the
    bare string ``"timestamp"``, rather than inheriting ``SensorEntity`` and returning a
    ``datetime``. The latter is the textbook approach and is deliberately not used here: no sensor
    in this integration inherits ``SensorEntity``, ``device_class`` is a plain string everywhere it
    already appears (see ``weather_observations.py``), and adding a second base class to the
    coordinator entity is what produced a metaclass conflict against the test suite's mocks when
    it was last tried. An ISO-8601 string with an offset is what the frontend's timestamp renderer
    and the ``time`` trigger parse, so the behaviour is identical for every use this has. What it
    gives up is recorder statistics and core-side validation, neither of which means anything for
    a value that changes a handful of times a year. Promoting it later is a contained change.
    """

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Next Eclipse Time"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_next_eclipse_time"

    @property
    def device_class(self):
        """Return the device class."""
        return "timestamp"

    @property
    def state(self):
        """Return when the eclipse becomes watchable, ISO-8601, or ``None``.

        ``None`` rather than a placeholder: a timestamp sensor has to be a real instant or
        nothing at all, and Home Assistant renders nothing as "unknown", which is the honest
        reading when no eclipse is due. The sibling coverage sensor returns 0 in the same
        situation, which is right for a percentage and would be meaningless here.
        """
        headline = self._headline
        if not headline:
            return None
        return headline["visible_start_utc"]

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:clock-start"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        headline = self._headline
        if not headline:
            return {
                "office_code": self._office_code,
                "eclipse": None,
                "date": None,
            }

        return {
            "office_code": self._office_code,
            "eclipse": headline["name"],
            "kind": headline["kind"],
            "eclipse_type": headline["type"],
            "date": headline["date"],
            "watch_until_utc": headline["visible_end_utc"],
            "watch_from_local": headline["visible_start_local"],
            "watch_until_local": headline["visible_end_local"],
            "maximum_local": headline["max_local"],
            "totality_starts_local": headline["central_start_local"],
            "totality_ends_local": headline["central_end_local"],
            "totality_seconds": headline["central_duration_s"],
            "days_until": headline["days_until"],
            "in_progress": headline["in_progress"],
            "disc_covered": headline["disc_covered"],
            "viewing_score": headline["viewing_score"],
            "rating": headline["rating"],
            "look_towards": headline["direction_when_visible"],
            "eye_protection_required": headline["eye_protection_required"],
        }
