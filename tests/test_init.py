"""Tests for async_setup_entry — merged config and the options update listener.

Covers the runtime half of dawg-io/noaa_it_all#21: coordinators must be built
from the saved options rather than the initial setup data, and changing an
option must reload the entry so those coordinators are rebuilt (they capture
office_code / latitude / longitude at construction and cannot be re-pointed).
"""

import ast
import asyncio
import contextlib
import os
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

# ---------------------------------------------------------------------------
# Ensure the custom_components directory is on sys.path
# ---------------------------------------------------------------------------
_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")
if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_config_entries = MagicMock()
_ha_core = MagicMock()
_ha_coordinator = MagicMock()

# Coordinators subclass DataUpdateCoordinator at import time, so it has to be a
# real class rather than a MagicMock.
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})

_ha_homeassistant = MagicMock()
_ha_homeassistant.config_entries = _ha_config_entries
_ha_homeassistant.core = _ha_core

_MOCK_MODULES = {
    "homeassistant": _ha_homeassistant,
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.entity": MagicMock(),
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.discovery": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.config_entries": _ha_config_entries,
    "homeassistant.core": _ha_core,
    "aiohttp": MagicMock(),
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


# Every coordinator class bound into the noaa_it_all package namespace by
# ``from .coordinator import (...)``.
_COORDINATOR_NAMES = (
    "SpaceWeatherCoordinator",
    "HurricaneCoordinator",
    "NWSAlertsCoordinator",
    "ObservationsCoordinator",
    "SurfCoordinator",
    "MarineForecastCoordinator",
    "MarineAlertsCoordinator",
    "ForecastCoordinator",
    "CloudCoverCoordinator",
    "RadarTimestampCoordinator",
    "ForecastDiscussionCoordinator",
    "MeteorShowerCoordinator",
    "EclipseCoordinator",
)

# Wilmington, NC — the ILM forecast office.
_ILM = {"office_code": "ILM", "latitude": 34.2257, "longitude": -77.9447}
# San Diego, CA — the SGX forecast office.
_SGX = {"office_code": "SGX", "latitude": 32.7157, "longitude": -117.1611}


def _run(coro):
    """Run a coroutine synchronously for unittest."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@contextlib.contextmanager
def _patched_coordinators():
    """Replace every coordinator class with an awaitable-refresh stub."""
    with contextlib.ExitStack() as stack:
        patched = {}
        for name in _COORDINATOR_NAMES:
            cls = stack.enter_context(patch(f"noaa_it_all.{name}"))
            cls.return_value.async_refresh = AsyncMock(return_value=None)
            patched[name] = cls
        yield patched


def _make_hass():
    """Create a fake Home Assistant object with a real hass.data dict."""
    hass = MagicMock()
    hass.data = {}
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=None)
    hass.config_entries.async_reload = AsyncMock(return_value=None)
    return hass


def _make_entry(data, options=None):
    """Create a fake ConfigEntry with real data / options mappings."""
    entry = MagicMock()
    entry.entry_id = "entry_1"
    entry.data = dict(data)
    entry.options = {} if options is None else dict(options)
    entry.add_update_listener = MagicMock(return_value="unsubscribe")
    entry.async_on_unload = MagicMock()
    return entry


def _setup(entry):
    """Run async_setup_entry against a fresh hass with stubbed coordinators."""
    import noaa_it_all

    hass = _make_hass()
    with _patched_coordinators() as coordinators:
        result = _run(noaa_it_all.async_setup_entry(hass, entry))
    return hass, result, coordinators


class TestSetupEntryUsesSavedOptions(unittest.TestCase):
    """Coordinators and stored config must reflect config_entry.options."""

    def _entry_data(self, hass):
        from noaa_it_all.const import DOMAIN
        return hass.data[DOMAIN]["entry_1"]

    def test_setup_returns_true_and_stores_entry_data(self):
        from noaa_it_all.const import DOMAIN

        hass, result, _ = _setup(_make_entry(_SGX))
        self.assertTrue(result)
        self.assertIn("entry_1", hass.data[DOMAIN])

    def test_stored_config_is_the_merged_mapping(self):
        hass, _, _ = _setup(_make_entry(_SGX, _ILM))
        self.assertEqual(self._entry_data(hass)["config"], _ILM)

    def test_stored_config_falls_back_to_data(self):
        hass, _, _ = _setup(_make_entry(_SGX))
        self.assertEqual(self._entry_data(hass)["config"], _SGX)

    def test_location_coordinators_get_the_option_coordinates(self):
        _, _, coordinators = _setup(_make_entry(_SGX, _ILM))
        coordinators["ObservationsCoordinator"].assert_called_once()
        args = coordinators["ObservationsCoordinator"].call_args.args
        self.assertEqual(args[1], "ILM")
        self.assertAlmostEqual(args[2], 34.2257)
        self.assertAlmostEqual(args[3], -77.9447)

    def test_alerts_coordinator_gets_the_option_coordinates(self):
        _, _, coordinators = _setup(_make_entry(_SGX, _ILM))
        args = coordinators["NWSAlertsCoordinator"].call_args.args
        self.assertAlmostEqual(args[1], 34.2257)
        self.assertAlmostEqual(args[2], -77.9447)

    def test_office_coordinators_get_the_option_office(self):
        _, _, coordinators = _setup(_make_entry(_SGX, _ILM))
        self.assertEqual(
            coordinators["ForecastDiscussionCoordinator"].call_args.args[1], "ILM"
        )

    def test_partial_options_only_override_what_they_carry(self):
        """Changing only the coordinates keeps the office from setup data."""
        entry = _make_entry(_SGX, {"latitude": 34.2257, "longitude": -77.9447})
        hass, _, coordinators = _setup(entry)
        self.assertEqual(self._entry_data(hass)["config"]["office_code"], "SGX")
        args = coordinators["ForecastCoordinator"].call_args.args
        self.assertEqual(args[1], "SGX")
        self.assertAlmostEqual(args[2], 34.2257)

    def test_location_coordinators_skipped_without_coordinates(self):
        _, _, coordinators = _setup(_make_entry({"office_code": "ILM"}))
        coordinators["NWSAlertsCoordinator"].assert_not_called()
        coordinators["ObservationsCoordinator"].assert_not_called()
        coordinators["MeteorShowerCoordinator"].assert_not_called()
        coordinators["EclipseCoordinator"].assert_not_called()


class TestOptionsUpdateListener(unittest.TestCase):
    """An options change has to reload the entry to take effect."""

    def test_update_listener_registered_once(self):
        entry = _make_entry(_SGX)
        _setup(entry)
        entry.add_update_listener.assert_called_once()

    def test_update_listener_is_unregistered_on_unload(self):
        entry = _make_entry(_SGX)
        _setup(entry)
        entry.async_on_unload.assert_any_call("unsubscribe")

    def test_registered_listener_reloads_the_entry(self):
        import noaa_it_all

        entry = _make_entry(_SGX)
        _setup(entry)
        listener = entry.add_update_listener.call_args.args[0]
        self.assertIs(listener, noaa_it_all._async_update_listener)

        hass = _make_hass()
        _run(listener(hass, entry))
        hass.config_entries.async_reload.assert_awaited_once_with("entry_1")


if __name__ == "__main__":
    unittest.main()


class TestRemoveEntryCleansUpRadarFrames(unittest.TestCase):
    """Uninstalling should not leave a day of radar behind.

    The frames live in the configuration directory, so anything left there
    rides along in every backup from then on.
    """

    @staticmethod
    def _entry(entry_id, office):
        entry = MagicMock()
        entry.entry_id = entry_id
        entry.data = {"office_code": office}
        entry.options = {}
        return entry

    @staticmethod
    def _hass(entries):
        hass = MagicMock()
        hass.config.path = MagicMock(return_value="/config/noaa_it_all/radar_frames")
        hass.config_entries.async_entries = MagicMock(return_value=entries)
        return hass

    def _remove(self, hass, entry):
        import noaa_it_all

        removed = []

        class _Store:
            def __init__(self, _hass, _base, site):
                self.site = site

            async def async_remove_all(self):
                removed.append(self.site)

        with patch.object(noaa_it_all, "RadarFrameStore", _Store):
            _run(noaa_it_all.async_remove_entry(hass, entry))
        return removed

    def test_the_sites_frames_are_deleted(self):
        entry = self._entry("entry_1", "ILM")
        removed = self._remove(self._hass([entry]), entry)
        self.assertEqual(["KLTX"], removed)

    def test_frames_shared_with_another_entry_are_kept(self):
        entry = self._entry("entry_1", "ILM")
        other = self._entry("entry_2", "ILM")
        removed = self._remove(self._hass([entry, other]), entry)
        self.assertEqual([], removed)

    def test_an_office_without_a_radar_site_is_a_no_op(self):
        entry = self._entry("entry_1", "ZZZ")
        removed = self._remove(self._hass([entry]), entry)
        self.assertEqual([], removed)


class TestConfigSchema(unittest.TestCase):
    """hassfest warns when an integration with async_setup or setup has no CONFIG_SCHEMA.

    The check reads __init__.py's module-level assignments, as this test does.
    YAML setup was removed (the sensor and image platforms have no
    async_setup_platform), so the schema is config_entry_only_config_schema,
    which tells anyone with "noaa_it_all:" in YAML to remove it.
    """

    def setUp(self):
        with open(os.path.join(_CC, "noaa_it_all", "__init__.py"), encoding="utf-8") as f:
            self.module = ast.parse(f.read())

    def _config_schema_value(self):
        for node in self.module.body:
            if isinstance(node, ast.Assign) and any(
                getattr(target, "id", None) == "CONFIG_SCHEMA" for target in node.targets
            ):
                return node.value
        return None

    def test_config_schema_is_defined(self):
        self.assertIsNotNone(self._config_schema_value(),
                             "__init__.py defines async_setup, so hassfest requires CONFIG_SCHEMA")

    def test_config_schema_rejects_yaml_setup(self):
        value = self._config_schema_value()
        self.assertIsInstance(value, ast.Call)
        self.assertEqual("config_entry_only_config_schema", getattr(value.func, "attr", None))
        self.assertEqual(["DOMAIN"], [getattr(arg, "id", None) for arg in value.args])


# Las Vegas: the VEF office issues no Surf Zone Forecast.
_VEF = {
    "office_code": "VEF", "radar_site": "KESX",
    "latitude": 36.1699, "longitude": -115.1398,
}


class TestEntryTypesSetUp(unittest.TestCase):
    """Each kind of entry builds only its own coordinators and platforms."""

    def _data(self, hass):
        from noaa_it_all.const import DOMAIN
        return hass.data[DOMAIN]["entry_1"]

    def _setup(self, data):
        import noaa_it_all
        with patch.object(noaa_it_all, "_async_adopt_entities") as adopt:
            hass, result, coordinators = _setup(_make_entry(data))
        self.assertTrue(result)
        return hass, coordinators, adopt

    def test_a_weather_entry_has_no_surf_hurricanes_or_space(self):
        hass, coordinators, _ = self._setup({**_VEF, "entry_type": "weather"})
        for name in (
            "SurfCoordinator", "HurricaneCoordinator", "SpaceWeatherCoordinator",
            "MeteorShowerCoordinator", "EclipseCoordinator",
        ):
            coordinators[name].assert_not_called()
        for key in (
            "surf_coordinator", "hurricane_coordinator", "space_weather_coordinator",
            "meteor_coordinator", "eclipse_coordinator",
        ):
            self.assertNotIn(key, self._data(hass))
        hass.config_entries.async_forward_entry_setups.assert_awaited_once_with(
            hass.config_entries.async_forward_entry_setups.call_args.args[0],
            ["sensor", "image", "binary_sensor", "weather"],
        )

    def test_the_stored_radar_site_is_used(self):
        _, coordinators, _ = self._setup({**_VEF, "entry_type": "weather"})
        self.assertEqual(
            coordinators["RadarTimestampCoordinator"].call_args.args[1:], ("VEF", "KESX")
        )

    def test_a_surf_entry_has_only_its_office_surf(self):
        hass, coordinators, adopt = self._setup({"entry_type": "surf", "office_code": "ILM"})
        args = coordinators["SurfCoordinator"].call_args.args
        self.assertEqual(args[1:], ("ILM", "8658163", "41110"))
        coordinators["SpaceWeatherCoordinator"].assert_not_called()
        coordinators["HurricaneCoordinator"].assert_not_called()
        self.assertIs(self._data(hass)["surf_coordinator"], coordinators["SurfCoordinator"].return_value)
        self.assertEqual(
            hass.config_entries.async_forward_entry_setups.call_args.args[1],
            ["sensor", "binary_sensor"],
        )
        # Takes over its device and any of the four surf entities it finds.
        _, _, device_key, entities = adopt.call_args.args
        self.assertEqual(device_key, "noaa_ILM_surf")
        self.assertEqual(len(entities), 4)
        # ILM has a tide station and a buoy, so it creates all four.
        self.assertEqual(len(self._data(hass)["surf_entities"]), 4)

    def test_a_new_surf_entry_creates_only_what_its_office_has_data_for(self):
        from noaa_it_all.offices import RIP_CURRENT_RISK, UNSAFE_TO_SWIM
        hass, _, _ = self._setup({"entry_type": "surf", "office_code": "LOT"})
        self.assertEqual(self._data(hass)["surf_entities"], [RIP_CURRENT_RISK, UNSAFE_TO_SWIM])

    def test_a_surf_entity_carried_over_from_0_7_is_kept(self):
        """MFR has no tide station but read water temperature from its forecast."""
        import noaa_it_all
        from noaa_it_all.offices import WATER_TEMPERATURE
        regs = _Registries()
        regs.add_entity("sensor.noaa_mfr_surf_water_temperature", "sensor",
                        "noaa_MFR_water_temperature", "entry_1", None)
        with patch.object(noaa_it_all.er, "async_get", return_value=regs):
            hass, _, _ = self._setup({"entry_type": "surf", "office_code": "MFR"})
        self.assertIn(WATER_TEMPERATURE, self._data(hass)["surf_entities"])

    def test_the_hurricane_entry_has_only_hurricanes(self):
        hass, coordinators, adopt = self._setup({"entry_type": "hurricane"})
        coordinators["HurricaneCoordinator"].assert_called_once()
        coordinators["SurfCoordinator"].assert_not_called()
        coordinators["SpaceWeatherCoordinator"].assert_not_called()
        self.assertEqual(
            hass.config_entries.async_forward_entry_setups.call_args.args[1],
            ["sensor", "image"],
        )
        _, _, device_key, entities = adopt.call_args.args
        self.assertEqual(device_key, "noaa_hurricane")
        self.assertEqual(len(entities), 6)

    def test_a_marine_entry_has_only_its_zone_forecast(self):
        hass, coordinators, _ = self._setup(
            {"entry_type": "marine", "marine_zone": "LMZ741", "office_code": "LOT"}
        )
        self.assertEqual(
            coordinators["MarineForecastCoordinator"].call_args.args[1:], ("LOT", "LMZ741")
        )
        self.assertEqual(coordinators["MarineAlertsCoordinator"].call_args.args[1:], ("LMZ741",))
        coordinators["SpaceWeatherCoordinator"].assert_not_called()
        coordinators["SurfCoordinator"].assert_not_called()
        self.assertEqual(
            hass.config_entries.async_forward_entry_setups.call_args.args[1], ["sensor"]
        )

    def test_a_space_entry_has_space_weather_meteors_and_eclipses(self):
        hass, coordinators, adopt = self._setup({**_ILM, "entry_type": "space"})
        coordinators["SpaceWeatherCoordinator"].assert_called_once()
        for name in ("MeteorShowerCoordinator", "EclipseCoordinator"):
            self.assertEqual(
                coordinators[name].call_args.args[1:], ("ILM", 34.2257, -77.9447)
            )
        for name in (
            "ObservationsCoordinator", "ForecastCoordinator", "NWSAlertsCoordinator",
            "RadarTimestampCoordinator", "ForecastDiscussionCoordinator", "SurfCoordinator",
        ):
            coordinators[name].assert_not_called()
        self.assertEqual(
            set(self._data(hass)),
            {"config", "space_weather_coordinator", "meteor_coordinator", "eclipse_coordinator"},
        )
        self.assertEqual(
            hass.config_entries.async_forward_entry_setups.call_args.args[1],
            ["sensor", "binary_sensor", "image"],
        )
        # Takes over its office's Space device and all twenty of its entities,
        # under the unique IDs they had in the weather entry.
        _, _, device_key, entities = adopt.call_args.args
        self.assertEqual(device_key, "noaa_ILM_space")
        self.assertEqual(len(entities), 20)
        self.assertIn(("sensor", "noaa_ILM_planetary_k_index"), entities)
        self.assertIn(("binary_sensor", "noaa_ILM_eclipse_coming_up"), entities)
        self.assertIn(("image", "noaa_ILM_aurora_image"), entities)

    def test_unload_uses_the_space_platforms(self):
        import noaa_it_all
        from noaa_it_all.const import DOMAIN
        hass = _make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        entry = _make_entry({**_ILM, "entry_type": "space"})
        hass.data[DOMAIN] = {"entry_1": {}}
        self.assertTrue(_run(noaa_it_all.async_unload_entry(hass, entry)))
        self.assertEqual(
            hass.config_entries.async_unload_platforms.call_args.args[1],
            ["sensor", "binary_sensor", "image"],
        )

    def test_a_failed_takeover_does_not_stop_setup(self):
        import noaa_it_all
        with patch.object(
            noaa_it_all, "_async_adopt_entities", side_effect=RuntimeError("registry")
        ):
            _, result, coordinators = _setup(_make_entry({"entry_type": "hurricane"}))
        self.assertTrue(result)
        coordinators["HurricaneCoordinator"].assert_called_once()

    def test_unload_uses_the_entry_type_platforms(self):
        import noaa_it_all
        from noaa_it_all.const import DOMAIN
        hass = _make_hass()
        hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)
        entry = _make_entry({"entry_type": "surf", "office_code": "ILM"})
        hass.data[DOMAIN] = {"entry_1": {}}
        self.assertTrue(_run(noaa_it_all.async_unload_entry(hass, entry)))
        self.assertEqual(
            hass.config_entries.async_unload_platforms.call_args.args[1],
            ["sensor", "binary_sensor"],
        )

    def test_removing_an_inland_entry_deletes_its_stored_radar_site(self):
        entry = MagicMock()
        entry.entry_id = "entry_1"
        entry.data = dict(_VEF)
        entry.options = {}
        removed = TestRemoveEntryCleansUpRadarFrames()._remove(
            TestRemoveEntryCleansUpRadarFrames._hass([entry]), entry
        )
        self.assertEqual(["KESX"], removed)

    def test_removing_a_surf_entry_leaves_radar_frames_alone(self):
        entry = MagicMock()
        entry.entry_id = "entry_1"
        entry.data = {"entry_type": "surf", "office_code": "ILM"}
        entry.options = {}
        removed = TestRemoveEntryCleansUpRadarFrames()._remove(
            TestRemoveEntryCleansUpRadarFrames._hass([entry]), entry
        )
        self.assertEqual([], removed)


class _Device:
    def __init__(self, device_id, config_entries, disabled_by=None):
        self.id = device_id
        self.config_entries = set(config_entries)
        self.disabled_by = disabled_by


class _Registries:
    """Device and entity registries that behave like Home Assistant's.

    Taking an entry off a device deletes the device's entities that still
    belong to that entry, and taking off its last entry deletes the device.
    That is what makes the order of a takeover matter, so the fakes do it too.
    """

    def __init__(self):
        self.devices = {}          # identifier -> _Device
        self.entities = {}         # entity_id -> SimpleNamespace
        self.calls = []

    # -- device registry
    def async_get_device(self, identifiers):
        (identifier,) = identifiers
        return self.devices.get(identifier[1])

    def async_update_device(self, device_id, add_config_entry_id=None,
                            remove_config_entry_id=None, **changes):
        key, device = next((k, d) for k, d in self.devices.items() if d.id == device_id)
        if "disabled_by" in changes:
            self.calls.append(("device_disabled_by", changes["disabled_by"]))
            device.disabled_by = changes["disabled_by"]
        if add_config_entry_id:
            self.calls.append(("add", add_config_entry_id))
            device.config_entries = device.config_entries | {add_config_entry_id}
        if remove_config_entry_id:
            self.calls.append(("remove", remove_config_entry_id))
            device.config_entries = device.config_entries - {remove_config_entry_id}
            for entity_id, ent in list(self.entities.items()):
                if ent.device_id == device_id and ent.config_entry_id == remove_config_entry_id:
                    del self.entities[entity_id]
            if not device.config_entries:
                del self.devices[key]

    # -- entity registry
    def add_entity(self, entity_id, platform, unique_id, config_entry_id, device_id,
                   disabled_by=None):
        from types import SimpleNamespace
        self.entities[entity_id] = SimpleNamespace(
            entity_id=entity_id, domain=platform, unique_id=unique_id,
            config_entry_id=config_entry_id, device_id=device_id, disabled_by=disabled_by,
        )

    def async_get_entity_id(self, domain, platform, unique_id):
        return next(
            (e.entity_id for e in self.entities.values()
             if e.domain == domain and e.unique_id == unique_id),
            None,
        )

    def async_get(self, entity_id):
        return self.entities.get(entity_id)

    def async_update_entity(self, entity_id, **changes):
        self.calls.append(("move", entity_id))
        for key, value in changes.items():
            setattr(self.entities[entity_id], key, value)

    def async_remove(self, entity_id):
        self.calls.append(("delete", entity_id))
        del self.entities[entity_id]


class TestAdoptEntities(unittest.TestCase):
    """A surf or hurricane entry takes over the entities a weather entry had."""

    def _adopt(self, regs, entry_id, *args):
        import noaa_it_all
        entry = MagicMock()
        entry.entry_id = entry_id
        with patch.object(noaa_it_all.dr, "async_get", return_value=regs), \
                patch.object(noaa_it_all.er, "async_get", return_value=regs):
            noaa_it_all._async_adopt_entities(MagicMock(), entry, *args)

    def _wilmington(self, disabled_by=None):
        """A weather entry from before 0.8.0 with ILM's surf device and entities."""
        regs = _Registries()
        regs.devices["noaa_ILM_surf"] = _Device("dev_surf", {"weather_1"}, disabled_by)
        for platform, suffix in (
            ("sensor", "rip_current_risk"), ("binary_sensor", "unsafe_to_swim"),
            ("sensor", "water_temperature"), ("sensor", "surf_height"),
        ):
            regs.add_entity(
                f"{platform}.noaa_ilm_surf_{suffix}", platform,
                f"noaa_ILM_{suffix}", "weather_1", "dev_surf", disabled_by,
            )
        return regs

    def _keep(self, office, suffixes):
        platforms = {"unsafe_to_swim": "binary_sensor"}
        return [(platforms.get(s, "sensor"), f"noaa_{office}_{s}") for s in suffixes]

    def test_moves_the_entities_and_device_keeping_their_ids(self):
        regs = self._wilmington()
        keep = self._keep("ILM", ["rip_current_risk", "unsafe_to_swim",
                                  "water_temperature", "surf_height"])
        self._adopt(regs, "surf_1", "noaa_ILM_surf", keep)
        self.assertEqual(
            sorted(regs.entities),
            ["binary_sensor.noaa_ilm_surf_unsafe_to_swim",
             "sensor.noaa_ilm_surf_rip_current_risk",
             "sensor.noaa_ilm_surf_surf_height",
             "sensor.noaa_ilm_surf_water_temperature"],
        )
        self.assertEqual({e.config_entry_id for e in regs.entities.values()}, {"surf_1"})
        self.assertEqual(regs.devices["noaa_ILM_surf"].config_entries, {"surf_1"})
        # The old entry lets go of the device last; any earlier deletes the entities.
        self.assertEqual(regs.calls[0], ("add", "surf_1"))
        self.assertEqual(regs.calls[-1], ("remove", "weather_1"))

    def test_keeps_every_surf_entity(self):
        """The surf entry passes all four, so an upgrade deletes none of them."""
        import noaa_it_all
        regs = self._wilmington()
        self._adopt(regs, "surf_1", "noaa_ILM_surf", [
            (platform, f"noaa_ILM_{suffix}")
            for platform, suffix in noaa_it_all.ALL_SURF_ENTITIES
        ])
        self.assertEqual(len(regs.entities), 4)
        self.assertEqual({e.config_entry_id for e in regs.entities.values()}, {"surf_1"})

    def test_clears_disabled_by_a_disabled_old_entry(self):
        """HA only clears it when the entity's own entry is enabled; this one is."""
        import noaa_it_all
        regs = self._wilmington(disabled_by=noaa_it_all.er.RegistryEntryDisabler.CONFIG_ENTRY)
        regs.devices["noaa_ILM_surf"].disabled_by = noaa_it_all.dr.DeviceEntryDisabler.CONFIG_ENTRY
        self._adopt(regs, "surf_1", "noaa_ILM_surf", self._keep("ILM", ["rip_current_risk"]))
        self.assertIsNone(regs.devices["noaa_ILM_surf"].disabled_by)
        self.assertIsNone(regs.entities["sensor.noaa_ilm_surf_rip_current_risk"].disabled_by)

    def test_leaves_a_user_choice_to_disable_alone(self):
        import noaa_it_all
        regs = self._wilmington(disabled_by=noaa_it_all.er.RegistryEntryDisabler.USER)
        self._adopt(regs, "surf_1", "noaa_ILM_surf", self._keep("ILM", ["rip_current_risk"]))
        self.assertIs(
            regs.entities["sensor.noaa_ilm_surf_rip_current_risk"].disabled_by,
            noaa_it_all.er.RegistryEntryDisabler.USER,
        )

    def test_a_second_run_changes_nothing(self):
        regs = self._wilmington()
        keep = self._keep("ILM", ["rip_current_risk"])
        self._adopt(regs, "surf_1", "noaa_ILM_surf", keep)
        regs.calls.clear()
        self._adopt(regs, "surf_1", "noaa_ILM_surf", keep)
        self.assertEqual(regs.calls, [])

    def test_nothing_to_take_over_is_fine(self):
        regs = _Registries()
        self._adopt(regs, "hurricane_1", "noaa_hurricane", [("sensor", "noaa_hurricane_alerts")])
        self.assertEqual(regs.calls, [])


class _OwnedDevice:
    """A device as Home Assistant 2026.8 and later keep it: one config entry."""

    def __init__(self, device_id, config_entry_id, disabled_by=None):
        self.id = device_id
        self.config_entry_id = config_entry_id
        self.disabled_by = disabled_by

    @property
    def config_entries(self):
        raise AssertionError("DeviceEntry.config_entries is deprecated (#76)")


class _SingleOwnerRegistries(_Registries):
    """Registries as in Home Assistant 2026.8 and later, where a device has one entry.

    Two entries can each have a device with the same identifier. Looking one up
    by identifier alone and adding or removing a device's entries are
    deprecated, to be removed in 2027.8, so those calls fail here. As in
    Home Assistant's device_registry._async_update_device and
    entity_registry.async_device_modified: moving a device to another entry
    deletes its entities still with the old entry and clears a disable that
    came from it, and removing a device deletes its own entities and unlinks
    the rest.
    """

    def __init__(self):
        super().__init__()
        self.devices = {}          # (identifier, config entry) -> _OwnedDevice

    def add_device(self, key, device_id, config_entry_id, disabled_by=None):
        self.devices[(key, config_entry_id)] = _OwnedDevice(device_id, config_entry_id, disabled_by)

    def _find(self, device_id):
        return next((k, d) for k, d in self.devices.items() if d.id == device_id)

    # -- device registry
    def async_get_device(self, identifiers):
        raise AssertionError("async_get_device is deprecated (#76)")

    def async_get_device_by_identifier(self, identifier, config_entry_id):
        return self.devices.get((identifier[1], config_entry_id))

    def async_get_devices(self, *, identifiers=None, connections=None, config_entry_id=None):
        keys = {identifier[1] for identifier in identifiers or ()}
        return [
            device for (key, owner), device in self.devices.items()
            if key in keys and config_entry_id in (None, owner)
        ]

    def async_update_device(self, device_id, new_config_entry_id=None, **changes):
        if {"add_config_entry_id", "remove_config_entry_id"} & set(changes):
            raise AssertionError("add/remove_config_entry_id are deprecated (#76)")
        (key, owner), device = self._find(device_id)
        if "disabled_by" in changes:
            self.calls.append(("device_disabled_by", changes["disabled_by"]))
            device.disabled_by = changes["disabled_by"]
        if new_config_entry_id:
            self.calls.append(("move_device", new_config_entry_id))
            for entity_id, ent in list(self.entities.items()):
                if ent.device_id == device_id and ent.config_entry_id == owner:
                    del self.entities[entity_id]
            del self.devices[(key, owner)]
            device.config_entry_id = new_config_entry_id
            # The new entry is enabled; HA clears a disable that came from the old one.
            if device.disabled_by is not None and device.disabled_by == _CONFIG_ENTRY_DISABLED():
                device.disabled_by = None
            self.devices[(key, new_config_entry_id)] = device

    def async_remove_device(self, device_id):
        self.calls.append(("remove_device", device_id))
        (key, owner), _ = self._find(device_id)
        del self.devices[(key, owner)]
        for entity_id, ent in list(self.entities.items()):
            if ent.device_id == device_id:
                if ent.config_entry_id == owner:
                    del self.entities[entity_id]
                else:
                    ent.device_id = None


def _CONFIG_ENTRY_DISABLED():
    import noaa_it_all
    return noaa_it_all.dr.DeviceEntryDisabler.CONFIG_ENTRY


class TestAdoptEntitiesSingleOwnerDevices(TestAdoptEntities):
    """#76: the same takeover in Home Assistant 2026.8 and later, without deprecated calls."""

    def _wilmington(self, disabled_by=None):
        regs = _SingleOwnerRegistries()
        regs.add_device("noaa_ILM_surf", "dev_surf", "weather_1", disabled_by)
        for platform, suffix in (
            ("sensor", "rip_current_risk"), ("binary_sensor", "unsafe_to_swim"),
            ("sensor", "water_temperature"), ("sensor", "surf_height"),
        ):
            regs.add_entity(
                f"{platform}.noaa_ilm_surf_{suffix}", platform,
                f"noaa_ILM_{suffix}", "weather_1", "dev_surf", disabled_by,
            )
        return regs

    def test_moves_the_entities_and_device_keeping_their_ids(self):
        regs = self._wilmington()
        keep = self._keep("ILM", ["rip_current_risk", "unsafe_to_swim",
                                  "water_temperature", "surf_height"])
        self._adopt(regs, "surf_1", "noaa_ILM_surf", keep)
        self.assertEqual(
            sorted((e.entity_id, e.unique_id) for e in regs.entities.values()),
            [("binary_sensor.noaa_ilm_surf_unsafe_to_swim", "noaa_ILM_unsafe_to_swim"),
             ("sensor.noaa_ilm_surf_rip_current_risk", "noaa_ILM_rip_current_risk"),
             ("sensor.noaa_ilm_surf_surf_height", "noaa_ILM_surf_height"),
             ("sensor.noaa_ilm_surf_water_temperature", "noaa_ILM_water_temperature")],
        )
        self.assertEqual({e.config_entry_id for e in regs.entities.values()}, {"surf_1"})
        self.assertEqual({e.device_id for e in regs.entities.values()}, {"dev_surf"})
        self.assertEqual(list(regs.devices), [("noaa_ILM_surf", "surf_1")])
        # The device moves last; any earlier deletes the entities.
        self.assertEqual(regs.calls[-1], ("move_device", "surf_1"))

    def test_clears_disabled_by_a_disabled_old_entry(self):
        """The entities' flag is cleared here; moving the device clears the device's."""
        import noaa_it_all
        regs = self._wilmington(disabled_by=noaa_it_all.er.RegistryEntryDisabler.CONFIG_ENTRY)
        regs.devices[("noaa_ILM_surf", "weather_1")].disabled_by = _CONFIG_ENTRY_DISABLED()
        self._adopt(regs, "surf_1", "noaa_ILM_surf", self._keep("ILM", ["rip_current_risk"]))
        self.assertIsNone(regs.entities["sensor.noaa_ilm_surf_rip_current_risk"].disabled_by)
        self.assertIn(("move_device", "surf_1"), regs.calls)
        # Passing disabled_by=None on a move is inconsistent in 2026.9 and later.
        self.assertNotIn("device_disabled_by", [call[0] for call in regs.calls])

    def test_a_split_device_moves_the_one_with_the_entities(self):
        """Home Assistant split a device two entries shared into one per entry."""
        regs = _SingleOwnerRegistries()
        regs.add_device("noaa_ILM_space", "dev_w1", "weather_1")
        regs.add_device("noaa_ILM_space", "dev_w2", "weather_2")
        regs.add_entity("sensor.noaa_ilm_space_planetary_k_index", "sensor",
                        "noaa_ILM_planetary_k_index", "weather_2", "dev_w2")
        self._adopt(regs, "space_1", "noaa_ILM_space",
                    [("sensor", "noaa_ILM_planetary_k_index")])
        self.assertEqual(regs.devices[("noaa_ILM_space", "space_1")].id, "dev_w2")
        entity = regs.entities["sensor.noaa_ilm_space_planetary_k_index"]
        self.assertEqual((entity.config_entry_id, entity.device_id), ("space_1", "dev_w2"))
        # The other split is the other entry's; nothing of the user's is deleted.
        self.assertEqual(regs.devices[("noaa_ILM_space", "weather_1")].id, "dev_w1")

    def test_a_split_device_moves_the_one_with_entities_already_moved(self):
        """A takeover cut short moved the entities but not their device."""
        regs = _SingleOwnerRegistries()
        regs.add_device("noaa_ILM_space", "dev_w1", "weather_1")
        regs.add_device("noaa_ILM_space", "dev_w2", "weather_2")
        regs.add_entity("sensor.noaa_ilm_space_planetary_k_index", "sensor",
                        "noaa_ILM_planetary_k_index", "space_1", "dev_w2")
        self._adopt(regs, "space_1", "noaa_ILM_space",
                    [("sensor", "noaa_ILM_planetary_k_index")])
        self.assertEqual(regs.devices[("noaa_ILM_space", "space_1")].id, "dev_w2")

    def test_an_entry_with_its_own_device_takes_the_entities_and_leaves_the_old_device(self):
        """The entry's own device gets the entities at setup; the old one keeps what the user set."""
        regs = _SingleOwnerRegistries()
        regs.add_device("noaa_ILM_space", "dev_space", "space_1")
        regs.add_device("noaa_ILM_space", "dev_old", "weather_1")
        regs.add_entity("sensor.noaa_ilm_space_planetary_k_index", "sensor",
                        "noaa_ILM_planetary_k_index", "weather_1", "dev_old")
        self._adopt(regs, "space_1", "noaa_ILM_space",
                    [("sensor", "noaa_ILM_planetary_k_index")])
        entity = regs.entities["sensor.noaa_ilm_space_planetary_k_index"]
        self.assertEqual(entity.config_entry_id, "space_1")
        self.assertEqual(sorted(regs.devices), [("noaa_ILM_space", "space_1"),
                                                ("noaa_ILM_space", "weather_1")])
        self.assertEqual([call for call in regs.calls if call[0] != "move"], [])

    def test_nothing_to_take_over_is_fine(self):
        regs = _SingleOwnerRegistries()
        self._adopt(regs, "hurricane_1", "noaa_hurricane", [("sensor", "noaa_hurricane_alerts")])
        self.assertEqual(regs.calls, [])


# The Space entry an upgraded Wilmington weather entry adds.
_ILM_SPACE = {
    "entry_type": "space", "office_code": "ILM",
    "latitude": 34.2257, "longitude": -77.9447, "place": "Wilmington, NC",
}


class TestMigrateEntry(unittest.TestCase):
    """Upgrading a version 1 entry into weather, surf, hurricane and Space entries."""

    def _migrate(self, data, title="NOAA - Wilmington, NC", version=1, options=None, regs=None,
                 others=()):
        import noaa_it_all
        hass = _make_hass()
        entry = _make_entry(data, options)
        entry.version = version
        entry.title = title
        hass.config_entries.async_entries = MagicMock(return_value=[entry, *others])
        by_id = {e.entry_id: e for e in (entry, *others)}
        hass.config_entries.async_get_entry = by_id.get
        regs = regs or _Registries()
        with patch.object(noaa_it_all.dr, "async_get", return_value=regs), \
                patch.object(noaa_it_all.er, "async_get", return_value=regs):
            result = _run(noaa_it_all.async_migrate_entry(hass, entry))
        return hass, result

    def _added(self, hass):
        return [c.kwargs["data"] for c in hass.config_entries.flow.async_init.call_args_list]

    def test_a_coastal_entry_becomes_weather_with_its_surf_and_hurricanes(self):
        hass, result = self._migrate(dict(_ILM), options={"radar_loop_hours": 6})
        self.assertTrue(result)
        kwargs = hass.config_entries.async_update_entry.call_args.kwargs
        self.assertEqual(kwargs["data"], {**_ILM, "entry_type": "weather"})
        self.assertEqual(kwargs["options"], {"radar_loop_hours": 6})
        self.assertEqual(kwargs["title"], "NOAA Weather - Wilmington, NC")
        self.assertEqual(kwargs["version"], 3)
        self.assertEqual(self._added(hass), [
            {"entry_type": "surf", "office_code": "ILM"},
            {"entry_type": "hurricane"},
            _ILM_SPACE,
        ])

    def test_the_office_in_options_decides_the_surf_office(self):
        hass, _ = self._migrate(dict(_SGX), options=dict(_ILM))
        self.assertIn({"entry_type": "surf", "office_code": "ILM"}, self._added(hass))

    def test_a_renamed_entry_keeps_its_name(self):
        hass, _ = self._migrate(dict(_ILM), title="Beach house")
        self.assertEqual(
            hass.config_entries.async_update_entry.call_args.kwargs["title"], "Beach house"
        )

    def test_a_test_build_entry_moves_to_its_chosen_surf_office(self):
        """0.8.0 test builds saved a surf office on the weather entry."""
        regs = _Registries()
        regs.devices["noaa_VEF_surf"] = _Device("dev_vef", {"entry_1"})
        regs.add_entity("sensor.noaa_vef_surf_rip_current_risk", "sensor",
                        "noaa_VEF_rip_current_risk", "entry_1", "dev_vef")
        hass, _ = self._migrate(
            {**_VEF, "surf_office_code": "SGX"}, title="NOAA - Las Vegas, NV", regs=regs,
        )
        data = hass.config_entries.async_update_entry.call_args.kwargs["data"]
        self.assertNotIn("surf_office_code", data)
        self.assertIn({"entry_type": "surf", "office_code": "SGX"}, self._added(hass))
        # Its VEF-named surf device held SGX data; nothing can take it over.
        self.assertEqual(regs.devices, {})
        self.assertEqual(regs.entities, {})

    def test_a_test_build_entry_drops_its_surf_device_without_deprecated_calls(self):
        """#76: the same on Home Assistant 2026.8 and later."""
        regs = _SingleOwnerRegistries()
        regs.add_device("noaa_VEF_surf", "dev_vef", "entry_1")
        regs.add_device("noaa_VEF_surf", "dev_other", "entry_2")
        regs.add_entity("sensor.noaa_vef_surf_rip_current_risk", "sensor",
                        "noaa_VEF_rip_current_risk", "entry_1", "dev_vef")
        self._migrate({**_VEF, "surf_office_code": "SGX"}, title="NOAA - Las Vegas, NV", regs=regs)
        # Only this entry's device goes.
        self.assertEqual(list(regs.devices), [("noaa_VEF_surf", "entry_2")])
        self.assertEqual(regs.entities, {})

    def test_a_test_build_entry_with_no_surf_adds_only_hurricanes(self):
        hass, _ = self._migrate(
            {**_VEF, "surf_office_code": None}, title="NOAA - Las Vegas, NV",
        )
        self.assertEqual(self._added(hass), [{"entry_type": "hurricane"}, {
            "entry_type": "space", "office_code": "VEF",
            "latitude": 36.1699, "longitude": -115.1398, "place": "Las Vegas, NV",
        }])

    def test_only_the_first_entry_to_upgrade_adds_hurricanes(self):
        """A disabled old entry upgrades when enabled, maybe after hurricanes were deleted."""
        upgraded = MagicMock(entry_id="entry_2", version=2)
        hass, _ = self._migrate(dict(_ILM), others=[upgraded])
        self.assertEqual(
            self._added(hass), [{"entry_type": "surf", "office_code": "ILM"}, _ILM_SPACE]
        )

    def test_an_entry_from_a_newer_release_is_refused(self):
        hass, result = self._migrate(dict(_ILM), version=4)
        self.assertFalse(result)
        hass.config_entries.async_update_entry.assert_not_called()

    def test_a_current_entry_is_left_alone(self):
        hass, result = self._migrate({**_ILM, "entry_type": "weather"}, version=3)
        self.assertTrue(result)
        hass.config_entries.async_update_entry.assert_not_called()
        hass.config_entries.flow.async_init.assert_not_called()


class TestMigrateSpace(unittest.TestCase):
    """Upgrading a version 2 weather entry moves its Space into a Space entry."""

    _migrate = TestMigrateEntry._migrate
    _added = TestMigrateEntry._added

    def _upgrade(self, data, title="NOAA Weather - Wilmington, NC", options=None, **kwargs):
        hass, result = self._migrate(data, title=title, version=2, options=options, **kwargs)
        self.assertTrue(result)
        return hass

    @staticmethod
    def _other(entry_id, data, version, title="NOAA Weather - Wilmington, NC"):
        other = MagicMock(entry_id=entry_id, version=version, title=title)
        other.data, other.options = data, {}
        return other

    def test_a_weather_entry_adds_its_office_space_entry(self):
        hass = self._upgrade({**_ILM, "entry_type": "weather"})
        self.assertEqual(self._added(hass), [_ILM_SPACE])
        # Only the version changes: the weather entry keeps its data and title.
        hass.config_entries.async_update_entry.assert_called_once_with(
            hass.config_entries.async_update_entry.call_args.args[0], version=3
        )

    def test_the_space_entry_is_at_the_location_in_effect(self):
        """A location changed with Configure is in the options."""
        hass = self._upgrade(
            {**_SGX, "entry_type": "weather"},
            title="NOAA Weather - San Diego, CA", options=dict(_ILM),
        )
        # The title still names the office it was set up with, so the Space
        # entry is named after its own office instead.
        self.assertEqual(self._added(hass), [{**_ILM_SPACE, "place": None}])

    def test_an_inland_office_takes_its_place_from_the_title(self):
        hass = self._upgrade({**_VEF, "entry_type": "weather"}, title="NOAA Weather - Las Vegas, NV")
        self.assertEqual(self._added(hass)[0]["place"], "Las Vegas, NV")

    def test_a_renamed_entry_leaves_the_name_to_the_office(self):
        hass = self._upgrade({**_VEF, "entry_type": "weather"}, title="Vegas")
        self.assertIsNone(self._added(hass)[0]["place"])

    def test_an_office_changed_with_configure_takes_no_name_from_the_title(self):
        hass = self._upgrade(
            {**_VEF, "entry_type": "weather"}, title="NOAA Weather - Las Vegas, NV",
            options={"office_code": "LKN", "latitude": 40.83, "longitude": -115.76},
        )
        added = self._added(hass)[0]
        self.assertEqual(added["office_code"], "LKN")
        self.assertIsNone(added["place"])

    def test_no_space_entry_once_another_entry_in_the_office_has_upgraded(self):
        """A Space entry deleted after the upgrade stays deleted when another is enabled."""
        upgraded = self._other("entry_2", {**_ILM, "entry_type": "weather"}, version=3)
        hass = self._upgrade({**_ILM, "entry_type": "weather"}, others=[upgraded])
        self.assertEqual(self._added(hass), [])
        hass.config_entries.async_update_entry.assert_called_once()

    def test_an_upgraded_entry_in_another_office_does_not_count(self):
        upgraded = self._other("entry_2", {**_VEF, "entry_type": "weather"}, version=3)
        hass = self._upgrade({**_ILM, "entry_type": "weather"}, others=[upgraded])
        self.assertEqual(self._added(hass), [_ILM_SPACE])

    def test_the_space_entry_goes_where_its_entities_were(self):
        """The entry that set up first had the office's Space entities, and their history."""
        beach = {"office_code": "ILM", "latitude": 33.6891, "longitude": -78.8867,
                 "entry_type": "weather"}
        owner = self._other("entry_2", beach, version=2)
        regs = _Registries()
        regs.add_entity("sensor.noaa_ilm_space_planetary_k_index", "sensor",
                        "noaa_ILM_planetary_k_index", "entry_2", "dev_space")
        hass = self._upgrade({**_ILM, "entry_type": "weather"}, others=[owner], regs=regs)
        self.assertEqual(self._added(hass), [
            {**_ILM_SPACE, "latitude": 33.6891, "longitude": -78.8867},
        ])

    def test_its_own_space_entities_keep_its_own_location(self):
        regs = _Registries()
        regs.add_entity("sensor.noaa_ilm_space_planetary_k_index", "sensor",
                        "noaa_ILM_planetary_k_index", "entry_1", "dev_space")
        hass = self._upgrade({**_ILM, "entry_type": "weather"}, regs=regs)
        self.assertEqual(self._added(hass), [_ILM_SPACE])

    def test_an_entry_saved_without_a_location_uses_its_office(self):
        hass = self._upgrade({"office_code": "ILM", "entry_type": "weather"})
        from noaa_it_all.const import OFFICE_COORDINATES
        lat, lon = OFFICE_COORDINATES["ILM"]
        added = self._added(hass)[0]
        self.assertEqual((added["latitude"], added["longitude"]), (lat, lon))

    def test_without_any_location_no_space_entry_is_added(self):
        with self.assertLogs("noaa_it_all", level="WARNING"):
            hass = self._upgrade({"office_code": "VEF", "entry_type": "weather"})
        self.assertEqual(self._added(hass), [])
        hass.config_entries.async_update_entry.assert_called_once()

    def test_other_entries_only_change_version(self):
        for data in (
            {"entry_type": "surf", "office_code": "ILM"},
            {"entry_type": "marine", "office_code": "LOT", "marine_zone": "LMZ741"},
            {"entry_type": "hurricane"},
        ):
            with self.subTest(data=data):
                hass = self._upgrade(data, title="NOAA")
                self.assertEqual(self._added(hass), [])
                self.assertEqual(
                    hass.config_entries.async_update_entry.call_args.kwargs, {"version": 3}
                )


class TestOfficeHelpers(unittest.TestCase):
    """offices.py: what an entry's office does not cover in the tables."""

    def test_surf_office(self):
        from noaa_it_all.offices import surf_office
        self.assertEqual(surf_office({"office_code": "ILM"}), "ILM")
        self.assertIsNone(surf_office({"office_code": "VEF"}))
        self.assertEqual(surf_office({"office_code": "VEF", "surf_office_code": "SGX"}), "SGX")
        self.assertIsNone(surf_office({"office_code": "ILM", "surf_office_code": None}))

    def test_radar_site(self):
        from noaa_it_all.offices import radar_site
        self.assertEqual(radar_site({"office_code": "ILM"}), "KLTX")
        self.assertEqual(radar_site({"office_code": "ILM", "radar_site": None}), "KLTX")
        self.assertEqual(radar_site(_VEF), "KESX")
        self.assertIsNone(radar_site({"office_code": "VEF"}))
        self.assertIsNone(radar_site({"entry_type": "surf", "office_code": "ILM"}))
        self.assertIsNone(radar_site({"entry_type": "hurricane"}))

    def test_entry_types(self):
        from noaa_it_all.offices import (
            entry_type, is_hurricane_entry, is_surf_entry, is_weather_entry,
        )
        self.assertEqual(entry_type({"office_code": "ILM"}), "weather")
        self.assertTrue(is_weather_entry({"office_code": "ILM"}))
        self.assertTrue(is_surf_entry({"entry_type": "surf"}))
        self.assertTrue(is_hurricane_entry({"entry_type": "hurricane"}))
        self.assertFalse(is_weather_entry({"entry_type": "surf"}))

    def test_surf_entities_follow_the_stations(self):
        from noaa_it_all.offices import (
            RIP_CURRENT_RISK, SURF_HEIGHT, UNSAFE_TO_SWIM, WATER_TEMPERATURE, surf_entities,
        )
        self.assertEqual(
            surf_entities("ILM"),
            [RIP_CURRENT_RISK, UNSAFE_TO_SWIM, WATER_TEMPERATURE, SURF_HEIGHT],
        )
        self.assertEqual(surf_entities("DLH"), [RIP_CURRENT_RISK, UNSAFE_TO_SWIM, WATER_TEMPERATURE])
        self.assertEqual(surf_entities("APX"), [RIP_CURRENT_RISK, UNSAFE_TO_SWIM])

    def test_a_stored_radar_site_that_is_not_a_site_is_ignored(self):
        """It names a directory that removing the entry deletes."""
        from noaa_it_all.offices import radar_site
        for stored in ("../..", "/config", "KESX/..", "kesx", 42):
            with self.subTest(stored=stored):
                self.assertIsNone(radar_site({"office_code": "VEF", "radar_site": stored}))
                self.assertEqual(
                    radar_site({"office_code": "ILM", "radar_site": stored}), "KLTX"
                )

    def test_every_table_radar_site_is_well_formed(self):
        from noaa_it_all.const import OFFICE_RADAR_SITES
        from noaa_it_all.offices import is_radar_site
        for office, site in OFFICE_RADAR_SITES.items():
            self.assertTrue(is_radar_site(site), f"{office}: {site}")

    def test_magnetic_latitude_uses_the_table_for_a_listed_office(self):
        from noaa_it_all.offices import magnetic_latitude
        self.assertEqual(magnetic_latitude("DLH", 36.0, -115.0), 56.8)

    def test_magnetic_latitude_is_estimated_for_an_inland_office(self):
        from noaa_it_all.offices import magnetic_latitude
        # Las Vegas sits near 43 degrees geomagnetic, well north of its
        # geographic latitude, and nowhere near the equator.
        self.assertAlmostEqual(magnetic_latitude("VEF", 36.1699, -115.1398), 42.7, delta=0.5)

    def test_magnetic_latitude_without_a_location_uses_the_default(self):
        from noaa_it_all.offices import magnetic_latitude
        self.assertEqual(magnetic_latitude("VEF"), 0.0)
        self.assertEqual(magnetic_latitude("VEF", default=45.0), 45.0)
