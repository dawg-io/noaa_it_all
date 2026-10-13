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

    def test_a_weather_entry_has_no_surf_or_hurricanes(self):
        hass, coordinators, _ = self._setup({**_VEF, "entry_type": "weather"})
        coordinators["SurfCoordinator"].assert_not_called()
        coordinators["HurricaneCoordinator"].assert_not_called()
        self.assertNotIn("surf_coordinator", self._data(hass))
        self.assertNotIn("hurricane_coordinator", self._data(hass))
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
        coordinators["SpaceWeatherCoordinator"].assert_not_called()
        coordinators["SurfCoordinator"].assert_not_called()
        self.assertEqual(
            hass.config_entries.async_forward_entry_setups.call_args.args[1], ["sensor"]
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


class TestMigrateEntry(unittest.TestCase):
    """Upgrading a version 1 entry into weather, surf and hurricane entries."""

    def _migrate(self, data, title="NOAA - Wilmington, NC", version=1, options=None, regs=None,
                 others=()):
        import noaa_it_all
        hass = _make_hass()
        entry = _make_entry(data, options)
        entry.version = version
        entry.title = title
        hass.config_entries.async_entries = MagicMock(return_value=[entry, *others])
        regs = regs or _Registries()
        with patch.object(noaa_it_all.dr, "async_get", return_value=regs):
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
        self.assertEqual(kwargs["version"], 2)
        self.assertEqual(self._added(hass), [
            {"entry_type": "surf", "office_code": "ILM"},
            {"entry_type": "hurricane"},
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

    def test_a_test_build_entry_with_no_surf_adds_only_hurricanes(self):
        hass, _ = self._migrate(
            {**_VEF, "surf_office_code": None}, title="NOAA - Las Vegas, NV",
        )
        self.assertEqual(self._added(hass), [{"entry_type": "hurricane"}])

    def test_only_the_first_entry_to_upgrade_adds_hurricanes(self):
        """A disabled old entry upgrades when enabled, maybe after hurricanes were deleted."""
        upgraded = MagicMock(entry_id="entry_2", version=2)
        hass, _ = self._migrate(dict(_ILM), others=[upgraded])
        self.assertEqual(self._added(hass), [{"entry_type": "surf", "office_code": "ILM"}])

    def test_an_entry_from_a_newer_release_is_refused(self):
        hass, result = self._migrate(dict(_ILM), version=3)
        self.assertFalse(result)
        hass.config_entries.async_update_entry.assert_not_called()

    def test_a_current_entry_is_left_alone(self):
        hass, result = self._migrate({**_ILM, "entry_type": "weather"}, version=2)
        self.assertTrue(result)
        hass.config_entries.async_update_entry.assert_not_called()
        hass.config_entries.flow.async_init.assert_not_called()


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
