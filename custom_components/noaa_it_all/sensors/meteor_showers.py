"""Meteor shower sensors for NOAA Integration.

Three sensors covering the space device's meteor forecast: what is active now, what is coming up,
and how good tonight's sky actually is. All three are thin projections over
``MeteorShowerCoordinator.data`` — every value, including local-time strings, is pre-computed in
``meteor.build_meteor_forecast`` so these classes stay simple property readers.
"""

import logging

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def space_device_info(office_code) -> DeviceInfo:
    """Return the shared NOAA Space device for an office.

    Mirrors ``_hurricane_device_info`` in ``sensors/hurricanes.py``. The existing space weather
    sensors each build this inline; new code shares one helper rather than adding more copies.
    """
    return DeviceInfo(
        identifiers={(DOMAIN, f"noaa_{office_code}_space")},
        name=f"NOAA {office_code} Space",
        manufacturer="NOAA",
    )


class _MeteorBaseSensor(CoordinatorEntity):
    """Shared plumbing for the meteor sensors.

    Uses ``_attr_has_entity_name = True`` so Home Assistant combines the device name with the
    local entity name, producing entity IDs like ``sensor.noaa_ilm_space_meteor_viewing_score``.
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
    def _best(self):
        """Return tonight's best shower entry, or ``None`` when nothing is active."""
        return self._forecast.get("best")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information to group this entity."""
        return space_device_info(self._office_code)


class MeteorShowerActivitySensor(_MeteorBaseSensor):
    """Which meteor shower is worth watching right now."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Meteor Shower Activity"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_meteor_shower_activity"

    @property
    def state(self):
        """Return the name of the best observable active shower, or ``None``."""
        best = self._best
        return best["name"] if best else "None"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:meteor"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        forecast = self._forecast
        active = forecast.get("active") or []
        attrs = {
            "office_code": self._office_code,
            "active_count": len(active),
            "solar_longitude": forecast.get("solar_longitude"),
            "night_of": forecast.get("night_of"),
        }

        best = self._best
        if best:
            attrs.update({
                "shower_code": best["code"],
                "zhr_now": best["zhr_now"],
                "zhr_max": best["zhr_max"],
                "peak_local": best["peak_local"],
                "days_until": best["days_until"],
                "is_peak_night": best["is_peak_night"],
                "radiant_altitude": best["radiant_altitude"],
                "constellation": best["constellation"],
                "parent_body": best["parent_body"],
                "velocity_kms": best["velocity_kms"],
                "variable": best["variable"],
            })

        # Trimmed per-shower list, kept small enough to stay well inside the recorder's
        # attribute size limits even when several showers overlap.
        attrs["active_showers"] = [
            {
                "code": shower["code"],
                "name": shower["name"],
                "zhr_now": shower["zhr_now"],
                "peak_local": shower["peak_local"],
                "radiant_altitude": shower["radiant_altitude"],
                "expected_per_hour": shower["expected_per_hour"],
            }
            for shower in active
        ]
        return attrs


class NextMeteorShowerSensor(_MeteorBaseSensor):
    """The next meteor shower to reach maximum."""

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Next Meteor Shower"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_next_meteor_shower"

    @property
    def _next(self):
        """Return the soonest upcoming shower, or ``None`` before the first refresh."""
        upcoming = self._forecast.get("upcoming") or []
        return upcoming[0] if upcoming else None

    @property
    def state(self):
        """Return the name of the next shower to peak."""
        nxt = self._next
        return nxt["name"] if nxt else None

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:calendar-star"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attrs = {"office_code": self._office_code}
        nxt = self._next
        if nxt:
            attrs.update({
                "code": nxt["code"],
                "peak_utc": nxt["peak_utc"],
                "peak_local": nxt["peak_local"],
                "days_until": nxt["days_until"],
                "zhr_max": nxt["zhr_max"],
                "constellation": nxt["constellation"],
            })
        # The full look-ahead list drives "what's coming up" dashboard cards.
        attrs["upcoming"] = self._forecast.get("upcoming") or []
        return attrs


class MeteorViewingScoreSensor(_MeteorBaseSensor):
    """How good tonight's sky geometry is for meteor watching, 0-100.

    The score deliberately measures *conditions* rather than shower strength: it is the fraction
    of the ideal rate an observer would achieve, so the shower's ZHR cancels out. A minor shower
    riding high under a new moon scores well. Shower strength is reported separately as
    ``expected_per_hour``.
    """

    @property
    def name(self):
        """Return the local name of the sensor."""
        return "Meteor Viewing Score"

    @property
    def unique_id(self):
        """Return a unique ID for this entity."""
        return f"noaa_{self._office_code}_meteor_viewing_score"

    @property
    def state(self):
        """Return the 0-100 viewing score for tonight's best shower."""
        best = self._best
        return best["viewing_score"] if best else 0

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "%"

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:star-shooting"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        forecast = self._forecast
        best = self._best

        if not best:
            return {
                "office_code": self._office_code,
                "rating": "Poor",
                "shower": None,
                "shower_code": None,
                "expected_per_hour": 0,
                "limiting_factor": "no active shower",
                "darkness": forecast.get("darkness"),
                "dark_window_start": forecast.get("dark_window_start"),
                "dark_window_end": forecast.get("dark_window_end"),
                "moon_illumination": forecast.get("moon_illumination"),
                "moon_altitude": forecast.get("moon_altitude"),
            }

        return {
            "office_code": self._office_code,
            "rating": best["rating"],
            "shower": best["name"],
            "shower_code": best["code"],
            "best_window_start": best["best_window_start"],
            "best_window_end": best["best_window_end"],
            "radiant_alt_at_best": best["radiant_altitude"],
            "max_radiant_altitude": best["max_radiant_altitude"],
            "radiant_never_rises": best["radiant_never_rises"],
            "moon_illumination": best["moon_illumination"],
            "moon_altitude": best["moon_altitude"],
            "darkness": forecast.get("darkness"),
            "limiting_magnitude": best["limiting_magnitude"],
            "expected_per_hour": best["expected_per_hour"],
            "limiting_factor": best["limiting_factor"],
            "dark_window_start": forecast.get("dark_window_start"),
            "dark_window_end": forecast.get("dark_window_end"),
            "dark_hours": forecast.get("dark_hours"),
        }
