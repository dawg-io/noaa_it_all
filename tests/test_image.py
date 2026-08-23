"""Tests for image.py entity properties using mocked HA modules."""

import asyncio
import logging
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CC = os.path.join(_REPO, "custom_components")

if _CC not in sys.path:
    sys.path.insert(0, _CC)

# ---------------------------------------------------------------------------
# Mock Home Assistant modules
# ---------------------------------------------------------------------------
_ha_image = MagicMock()
_ha_entity = MagicMock()
_ha_coordinator = MagicMock()
_ha_event = MagicMock()
_ha_util = MagicMock()
_ha_util_dt = MagicMock()
_aiohttp = MagicMock()


class _FakeImageEntity:
    """Stand-in for homeassistant.components.image.ImageEntity.

    Only the parts image.py builds on are modelled, but ``entity_picture``
    mirrors upstream exactly -- returning None until ``image_last_updated``
    is set -- because that semantic is what the fallback in
    ``NoaaImageEntity.entity_picture`` exists to work around.
    """

    _attr_content_type = "image/jpeg"
    _attr_image_last_updated = None
    _attr_should_poll = False
    entity_id = None

    def __init__(self, hass):
        self.hass = hass
        self._on_remove = []

    @property
    def image_last_updated(self):
        return self._attr_image_last_updated

    @property
    def content_type(self):
        return self._attr_content_type

    @property
    def entity_picture(self):
        if self.image_last_updated is None:
            return None
        return f"/api/image_proxy/{self.entity_id}?token=stub"

    async def async_added_to_hass(self):
        """No-op; the real one wires up access tokens."""

    def async_on_remove(self, func):
        self._on_remove.append(func)

    def async_write_ha_state(self):
        """No-op; tests replace this when they want to observe writes."""


_ha_image.ImageEntity = _FakeImageEntity

_ha_entity.DeviceInfo = dict
_ha_util_dt.utcnow = lambda: datetime.now(timezone.utc)
_ha_util.dt = _ha_util_dt


# ``aiohttp`` is mocked wholesale, so its exception classes are MagicMocks and
# cannot be used in an ``except`` clause. Substitute real ones.
class _ClientError(Exception):
    """Stand-in for aiohttp.ClientError."""


class _ClientOSError(_ClientError, OSError):
    """Stand-in for aiohttp.ClientOSError."""


class _ClientConnectorError(_ClientOSError):
    """Stand-in for aiohttp.ClientConnectorError."""


class _ServerDisconnectedError(_ClientError):
    """Stand-in for aiohttp.ServerDisconnectedError."""


class _ServerTimeoutError(_ClientError, asyncio.TimeoutError):
    """Stand-in for aiohttp.ServerTimeoutError."""


_aiohttp.ClientError = _ClientError
_aiohttp.ClientOSError = _ClientOSError
_aiohttp.ClientConnectorError = _ClientConnectorError
_aiohttp.ServerDisconnectedError = _ServerDisconnectedError
_aiohttp.ServerTimeoutError = _ServerTimeoutError
_aiohttp.ClientTimeout = lambda **kwargs: kwargs
_ha_coordinator.CoordinatorEntity = type("CoordinatorEntity", (), {
    "__init__": lambda self, coordinator: setattr(self, "coordinator", coordinator),
})
_ha_coordinator.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {})

_MOCK_MODULES = {
    # Home Assistant modules
    "homeassistant": MagicMock(),
    "homeassistant.components": MagicMock(),
    "homeassistant.components.image": _ha_image,
    "homeassistant.components.binary_sensor": MagicMock(),
    "homeassistant.components.weather": MagicMock(),
    "homeassistant.config_entries": MagicMock(),
    "homeassistant.core": MagicMock(),
    "homeassistant.const": MagicMock(),
    "homeassistant.helpers": MagicMock(),
    "homeassistant.helpers.aiohttp_client": MagicMock(),
    "homeassistant.helpers.entity": _ha_entity,
    "homeassistant.helpers.entity_platform": MagicMock(),
    "homeassistant.helpers.event": _ha_event,
    "homeassistant.helpers.update_coordinator": _ha_coordinator,
    "homeassistant.util": _ha_util,
    "homeassistant.util.dt": _ha_util_dt,
    "aiohttp": _aiohttp,
    # Block noaa_it_all internal modules that have Python 3.10+ type syntax
    # (|  union annotations in parsers.py) or heavy HA runtime dependencies,
    # so importing noaa_it_all.image doesn't pull in the full coordinator stack.
    "noaa_it_all.coordinator": MagicMock(),
    "noaa_it_all.parsers": MagicMock(),
    "noaa_it_all.sensors": MagicMock(),
    "noaa_it_all.sensors.hurricanes": MagicMock(),
}

_patcher = None


def setUpModule():
    global _patcher
    _patcher = patch.dict(sys.modules, _MOCK_MODULES)
    _patcher.start()


def tearDownModule():
    if _patcher is not None:
        _patcher.stop()


OFFICE = "SGX"
HASS = MagicMock()


def _run(coro):
    """Run a coroutine on a private loop, leaving the ambient one intact.

    ``asyncio.run()`` clears the thread's current event loop when it returns,
    which breaks other test modules that reach for ``get_event_loop()``.
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


class TestGeoelectricFieldImageEntity(unittest.TestCase):
    """Tests for GeoelectricFieldImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import GeoelectricFieldImageEntity
        return GeoelectricFieldImageEntity(HASS, OFFICE)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Geoelectric Field Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, f"noaa_{OFFICE}_geoelectric_image")

    def test_upstream_url(self):
        entity = self._make()
        self.assertTrue(entity._image_url.startswith("https://"))
        self.assertIn("geoelectric", entity._image_url)

    def test_cache_bust_contains_timestamp(self):
        entity = self._make()
        self.assertIn("?t=", entity._image_url)

    def test_content_type_is_png(self):
        entity = self._make()
        self.assertEqual(entity.content_type, "image/png")

    def test_device_info(self):
        entity = self._make()
        info = entity.device_info
        self.assertIn("identifiers", info)
        self.assertIn("manufacturer", info)


class TestAuroraForecastImageEntity(unittest.TestCase):
    """Tests for AuroraForecastImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import AuroraForecastImageEntity
        return AuroraForecastImageEntity(HASS, OFFICE)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Aurora Forecast Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, f"noaa_{OFFICE}_aurora_image")

    def test_upstream_url(self):
        entity = self._make()
        self.assertTrue(entity._image_url.startswith("https://"))
        self.assertIn("ovation", entity._image_url)

    def test_cache_bust_contains_timestamp(self):
        entity = self._make()
        self.assertIn("?t=", entity._image_url)

    def test_content_type_is_jpeg(self):
        entity = self._make()
        self.assertEqual(entity.content_type, "image/jpeg")

    def test_device_info(self):
        entity = self._make()
        info = entity.device_info
        self.assertIn("identifiers", info)
        self.assertIn("manufacturer", info)


class TestHurricaneOutlookImageEntity(unittest.TestCase):
    """Tests for HurricaneOutlookImageEntity properties."""

    def _make(self):
        from noaa_it_all.image import HurricaneOutlookImageEntity
        return HurricaneOutlookImageEntity(HASS)

    def test_name(self):
        # Local name only; HA prepends "NOAA Hurricane" to form the full name.
        entity = self._make()
        self.assertEqual(entity.name, "Outlook Image")

    def test_unique_id(self):
        entity = self._make()
        self.assertEqual(entity.unique_id, "noaa_hurricane_outlook_image")

    def test_has_entity_name(self):
        from noaa_it_all.image import HurricaneOutlookImageEntity
        self.assertTrue(HurricaneOutlookImageEntity._attr_has_entity_name)

    def test_device_info_uses_hurricane_device(self):
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        entity = self._make()
        info = entity.device_info
        self.assertIn((DOMAIN, HURRICANE_DEVICE_ID), info["identifiers"])


class TestRadarBaseReflectivityImageEntity(unittest.TestCase):
    """Tests for RadarBaseReflectivityImageEntity properties."""

    def _make(self, office="SGX", radar_site="KNKX"):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        return RadarBaseReflectivityImageEntity(HASS, office, radar_site)

    def test_name(self):
        # Local name only; HA prepends the office weather device name.
        entity = self._make()
        self.assertEqual(entity.name, "Radar Base Reflectivity")

    def test_unique_id_sgx(self):
        entity = self._make(office="SGX")
        self.assertEqual(entity.unique_id, "noaa_sgx_weather_radar_base_reflectivity")

    def test_unique_id_ilm(self):
        entity = self._make(office="ILM", radar_site="KLTX")
        self.assertEqual(entity.unique_id, "noaa_ilm_weather_radar_base_reflectivity")

    def test_unique_id_lowercase(self):
        # Office code must be lowercased in the unique_id regardless of input case.
        entity = self._make(office="SGX")
        self.assertNotIn("SGX", entity.unique_id)
        self.assertIn("sgx", entity.unique_id)

    def test_has_entity_name(self):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        self.assertTrue(RadarBaseReflectivityImageEntity._attr_has_entity_name)

    def test_upstream_url_contains_radar_site(self):
        entity = self._make(radar_site="KNKX")
        self.assertIn("KNKX", entity._image_url)

    def test_content_type_is_gif(self):
        entity = self._make(radar_site="KNKX")
        self.assertEqual(entity.content_type, "image/gif")

    def test_device_info_uses_office_weather_device(self):
        from noaa_it_all.const import DOMAIN
        entity = self._make(office="SGX")
        info = entity.device_info
        self.assertIn((DOMAIN, "noaa_SGX_weather"), info["identifiers"])

    def test_device_name(self):
        entity = self._make(office="ILM", radar_site="KLTX")
        self.assertEqual(entity.device_info["name"], "NOAA ILM Weather")


class TestRadarLoopImageEntity(unittest.TestCase):
    """Tests for RadarLoopImageEntity properties."""

    def _make(self, office="SGX", radar_site="KNKX"):
        from noaa_it_all.image import RadarLoopImageEntity
        return RadarLoopImageEntity(HASS, office, radar_site)

    def test_name(self):
        entity = self._make()
        self.assertEqual(entity.name, "Radar Loop")

    def test_unique_id_sgx(self):
        entity = self._make(office="SGX")
        self.assertEqual(entity.unique_id, "noaa_sgx_weather_radar_loop")

    def test_unique_id_ilm(self):
        entity = self._make(office="ILM", radar_site="KLTX")
        self.assertEqual(entity.unique_id, "noaa_ilm_weather_radar_loop")

    def test_has_entity_name(self):
        from noaa_it_all.image import RadarLoopImageEntity
        self.assertTrue(RadarLoopImageEntity._attr_has_entity_name)


class TestGOESImageEntities(unittest.TestCase):
    """Tests for GOES satellite image entity properties."""

    def test_goes_airmass_unique_id(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        entity = GOESAirMassImageEntity(HASS)
        self.assertEqual(entity.unique_id, "noaa_hurricane_goes_air_mass")

    def test_goes_airmass_name(self):
        # Local name only; HA prepends "NOAA Hurricane".
        from noaa_it_all.image import GOESAirMassImageEntity
        entity = GOESAirMassImageEntity(HASS)
        self.assertEqual(entity.name, "GOES Air Mass")

    def test_goes_airmass_has_entity_name(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        self.assertTrue(GOESAirMassImageEntity._attr_has_entity_name)

    def test_goes_airmass_device_info_uses_hurricane_device(self):
        from noaa_it_all.image import GOESAirMassImageEntity
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        entity = GOESAirMassImageEntity(HASS)
        self.assertIn((DOMAIN, HURRICANE_DEVICE_ID), entity.device_info["identifiers"])

    def test_goes_geocolor_unique_id(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        entity = GOESGeoColorImageEntity(HASS)
        self.assertEqual(entity.unique_id, "noaa_hurricane_goes_geocolor")

    def test_goes_geocolor_name(self):
        # Local name only; HA prepends "NOAA Hurricane".
        from noaa_it_all.image import GOESGeoColorImageEntity
        entity = GOESGeoColorImageEntity(HASS)
        self.assertEqual(entity.name, "GOES Geocolor")

    def test_goes_geocolor_has_entity_name(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        self.assertTrue(GOESGeoColorImageEntity._attr_has_entity_name)

    def test_goes_geocolor_device_info_uses_hurricane_device(self):
        from noaa_it_all.image import GOESGeoColorImageEntity
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        entity = GOESGeoColorImageEntity(HASS)
        self.assertIn((DOMAIN, HURRICANE_DEVICE_ID), entity.device_info["identifiers"])


class TestTwoOfficeSetup(unittest.TestCase):
    """Verify entity structure when two NWS offices (ILM and SGX) are configured.

    These tests exercise entity properties directly — the async_setup_entry
    deduplication logic is tested separately in integration tests.  Here we
    confirm that:
      - Hurricane entities always attach to the shared NOAA Hurricane device.
      - Radar entities attach to their respective office weather device.
      - Unique-IDs are distinct across offices and do not collide with the
        global hurricane entity IDs.
    """

    def _make_hurricane_entities(self):
        from noaa_it_all.image import (
            HurricaneOutlookImageEntity,
            GOESAirMassImageEntity,
            GOESGeoColorImageEntity,
        )
        return [
            HurricaneOutlookImageEntity(HASS),
            GOESAirMassImageEntity(HASS),
            GOESGeoColorImageEntity(HASS),
        ]

    def _make_radar_entity(self, office, radar_site):
        from noaa_it_all.image import RadarBaseReflectivityImageEntity
        return RadarBaseReflectivityImageEntity(HASS, office, radar_site)

    # ------------------------------------------------------------------
    # Hurricane entities are global — created once regardless of offices
    # ------------------------------------------------------------------

    def test_hurricane_entities_unique_ids_are_global(self):
        """Hurricane entity unique_ids must not contain an office code."""
        entities = self._make_hurricane_entities()
        for entity in entities:
            self.assertNotIn("ilm", entity.unique_id)
            self.assertNotIn("sgx", entity.unique_id)

    def test_hurricane_entities_attach_to_hurricane_device(self):
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        for entity in self._make_hurricane_entities():
            self.assertIn(
                (DOMAIN, HURRICANE_DEVICE_ID),
                entity.device_info["identifiers"],
                msg=f"{entity.__class__.__name__} must use the NOAA Hurricane device",
            )

    def test_hurricane_entity_ids_are_stable(self):
        """Hurricane unique_ids are constant — not per-office."""
        entities = self._make_hurricane_entities()
        self.assertEqual(entities[0].unique_id, "noaa_hurricane_outlook_image")
        self.assertEqual(entities[1].unique_id, "noaa_hurricane_goes_air_mass")
        self.assertEqual(entities[2].unique_id, "noaa_hurricane_goes_geocolor")

    # ------------------------------------------------------------------
    # Radar entities are per-office
    # ------------------------------------------------------------------

    def test_radar_unique_ids_differ_per_office(self):
        ilm_radar = self._make_radar_entity("ILM", "KLTX")
        sgx_radar = self._make_radar_entity("SGX", "KNKX")
        self.assertNotEqual(ilm_radar.unique_id, sgx_radar.unique_id)

    def test_ilm_radar_unique_id(self):
        entity = self._make_radar_entity("ILM", "KLTX")
        self.assertEqual(entity.unique_id, "noaa_ilm_weather_radar_base_reflectivity")

    def test_sgx_radar_unique_id(self):
        entity = self._make_radar_entity("SGX", "KNKX")
        self.assertEqual(entity.unique_id, "noaa_sgx_weather_radar_base_reflectivity")

    def test_ilm_radar_attaches_to_ilm_weather_device(self):
        from noaa_it_all.const import DOMAIN
        entity = self._make_radar_entity("ILM", "KLTX")
        self.assertIn((DOMAIN, "noaa_ILM_weather"), entity.device_info["identifiers"])
        self.assertEqual(entity.device_info["name"], "NOAA ILM Weather")

    def test_sgx_radar_attaches_to_sgx_weather_device(self):
        from noaa_it_all.const import DOMAIN
        entity = self._make_radar_entity("SGX", "KNKX")
        self.assertIn((DOMAIN, "noaa_SGX_weather"), entity.device_info["identifiers"])
        self.assertEqual(entity.device_info["name"], "NOAA SGX Weather")

    def test_radar_entities_do_not_use_hurricane_device(self):
        from noaa_it_all.const import DOMAIN, HURRICANE_DEVICE_ID
        for office, site in [("ILM", "KLTX"), ("SGX", "KNKX")]:
            entity = self._make_radar_entity(office, site)
            self.assertNotIn(
                (DOMAIN, HURRICANE_DEVICE_ID),
                entity.device_info["identifiers"],
                msg=f"Radar entity for {office} must NOT use the hurricane device",
            )

    # ------------------------------------------------------------------
    # No forbidden entity ID patterns
    # ------------------------------------------------------------------

    def test_no_noaa_weather_prefix_in_hurricane_unique_ids(self):
        for entity in self._make_hurricane_entities():
            self.assertFalse(
                entity.unique_id.startswith("noaa_weather_"),
                msg=f"{entity.unique_id} must not start with noaa_weather_",
            )

    def test_no_office_suffix_in_radar_unique_id(self):
        """Old pattern was noaa_{office}_radar_base_reflectivity (no 'weather')."""
        for office, site in [("ILM", "KLTX"), ("SGX", "KNKX")]:
            entity = self._make_radar_entity(office, site)
            # New pattern must contain 'weather' between office and radar name
            self.assertIn("weather", entity.unique_id)
            # Old pattern ended with the office code — ensure it now ends with
            # the entity slug, not the office code
            self.assertFalse(
                entity.unique_id.endswith(f"_{office.lower()}"),
                msg=f"{entity.unique_id} must not end with the office code",
            )

    def test_all_hurricane_entity_names_are_local_only(self):
        """With has_entity_name=True the name must be the local part only."""
        entities = self._make_hurricane_entities()
        local_names = {e.name for e in entities}
        for name in local_names:
            self.assertNotIn("NOAA Hurricane", name,
                             msg=f"Name '{name}' must be local-only, not include device name")
            self.assertNotIn("NOAA Satellite", name,
                             msg=f"Name '{name}' must not include legacy 'NOAA Satellite' prefix")

    def test_radar_entity_name_is_local_only(self):
        """Radar entity name must not embed the office code or device prefix."""
        entity = self._make_radar_entity("ILM", "KLTX")
        self.assertEqual(entity.name, "Radar Base Reflectivity")
        self.assertNotIn("ILM", entity.name)
        self.assertNotIn("NOAA Weather", entity.name)


PNG = b"\x89PNG\r\n\x1a\nfirst-frame"


class _FakeResponse:
    """Minimal stand-in for an aiohttp response."""

    def __init__(self, status=200, content_type="image/png", body=PNG, headers=None):
        self.status = status
        self.headers = {"content-type": content_type}
        if headers:
            self.headers.update(headers)
        self._body = body

    async def read(self):
        return self._body


class _FakeGet:
    """Async context manager returned by _FakeSession.get()."""

    def __init__(self, result):
        self._result = result

    async def __aenter__(self):
        if isinstance(self._result, BaseException):
            raise self._result
        return self._result

    async def __aexit__(self, *exc_info):
        return False


class _FakeSession:
    """Session that yields the given responses (or raises the given errors)."""

    def __init__(self, *results):
        self._results = list(results)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        result = self._results.pop(0) if len(self._results) > 1 else self._results[0]
        return _FakeGet(result)


def _refresh(entity, *results):
    """Run one background refresh against a session yielding ``results``."""
    session = _FakeSession(*results)
    with patch("noaa_it_all.image.async_get_clientsession", return_value=session):
        _run(entity._async_scheduled_refresh())
    return session


def _make_entity():
    from noaa_it_all.image import GeoelectricFieldImageEntity
    entity = GeoelectricFieldImageEntity(HASS, OFFICE)
    entity.entity_id = "image.noaa_sgx_space_geoelectric_field_image"
    entity.async_write_ha_state = MagicMock()
    return entity


class TestImageCacheSurvivesFailures(unittest.TestCase):
    """The point of the whole exercise.

    A transient upstream failure -- the DNS timeouts and "network
    unreachable" errors seen in the wild against
    ``services.swpc.noaa.gov`` -- used to make ``async_image()`` return
    ``b""``.  Home Assistant treats empty bytes as an error and turns them
    into an HTTP 500, so one blip replaced a perfectly good picture with a
    broken tile.  The last good frame is now kept and re-served instead.
    """

    def _seeded(self):
        """Return an entity with one frame already cached."""
        entity = _make_entity()
        _refresh(entity, _FakeResponse())
        self.assertEqual(_run(entity.async_image()), PNG)
        return entity

    def test_successful_fetch_caches_bytes_and_stamps_the_time(self):
        entity = self._seeded()
        self.assertIsNotNone(entity.image_last_updated)
        entity.async_write_ha_state.assert_called_once()

    def test_response_content_type_is_adopted(self):
        entity = _make_entity()
        _refresh(entity, _FakeResponse(content_type="image/gif; charset=binary"))
        self.assertEqual(entity.content_type, "image/gif")

    def test_async_image_does_no_io(self):
        entity = self._seeded()
        with patch("noaa_it_all.image.async_get_clientsession") as session:
            self.assertEqual(_run(entity.async_image()), PNG)
        session.assert_not_called()

    def _assert_cache_survives(self, failure):
        entity = self._seeded()
        stamp = entity.image_last_updated
        entity.async_write_ha_state.reset_mock()

        _refresh(entity, failure)

        self.assertEqual(_run(entity.async_image()), PNG)
        self.assertEqual(entity.image_last_updated, stamp)
        entity.async_write_ha_state.assert_not_called()

    def test_connection_error_keeps_the_previous_image(self):
        self._assert_cache_survives(
            _ClientConnectorError("Cannot connect to host services.swpc.noaa.gov:443")
        )

    def test_timeout_keeps_the_previous_image(self):
        # A ClientTimeout expiry raises asyncio.TimeoutError, which is not an
        # aiohttp.ClientError -- it used to be logged as "Unexpected error".
        self._assert_cache_survives(asyncio.TimeoutError())

    def test_server_disconnect_keeps_the_previous_image(self):
        self._assert_cache_survives(_ServerDisconnectedError())

    def test_http_error_keeps_the_previous_image(self):
        self._assert_cache_survives(_FakeResponse(status=503))

    def test_non_image_content_type_keeps_the_previous_image(self):
        self._assert_cache_survives(
            _FakeResponse(content_type="text/html", body=b"<html>oops</html>")
        )

    def test_empty_body_keeps_the_previous_image(self):
        self._assert_cache_survives(_FakeResponse(body=b""))

    def test_oversized_body_keeps_the_previous_image(self):
        from noaa_it_all.const import IMAGE_MAX_BYTES
        self._assert_cache_survives(_FakeResponse(body=b"x" * (IMAGE_MAX_BYTES + 1)))

    def test_first_ever_failure_returns_none_not_empty_bytes(self):
        # Empty bytes are falsy to Home Assistant's _async_get_image(), which
        # turns them into an HTTP 500; None is the documented "no image".
        entity = _make_entity()
        _refresh(entity, _ClientConnectorError("boom"))
        self.assertIsNone(_run(entity.async_image()))

    def test_unchanged_bytes_do_not_advance_the_timestamp(self):
        entity = self._seeded()
        stamp = entity.image_last_updated
        entity.async_write_ha_state.reset_mock()

        _refresh(entity, _FakeResponse())

        self.assertEqual(entity.image_last_updated, stamp)
        entity.async_write_ha_state.assert_not_called()

    def test_changed_bytes_advance_the_timestamp_and_write_state(self):
        entity = self._seeded()
        stamp = entity.image_last_updated
        entity.async_write_ha_state.reset_mock()

        _refresh(entity, _FakeResponse(body=PNG + b"-second"))

        self.assertEqual(_run(entity.async_image()), PNG + b"-second")
        self.assertNotEqual(entity.image_last_updated, stamp)
        entity.async_write_ha_state.assert_called_once()

    def test_not_modified_keeps_the_cache_without_rewriting_state(self):
        entity = self._seeded()
        stamp = entity.image_last_updated
        entity.async_write_ha_state.reset_mock()

        _refresh(entity, _FakeResponse(status=304, body=b""))

        self.assertEqual(_run(entity.async_image()), PNG)
        self.assertEqual(entity.image_last_updated, stamp)
        entity.async_write_ha_state.assert_not_called()


class TestImageRequestHeaders(unittest.TestCase):
    """Requests identify the integration and revalidate what is cached."""

    def test_user_agent_is_sent(self):
        from noaa_it_all.const import USER_AGENT
        entity = _make_entity()
        session = _refresh(entity, _FakeResponse())
        self.assertEqual(session.calls[0][1]["headers"]["User-Agent"], USER_AGENT)

    def test_no_conditional_headers_before_anything_is_cached(self):
        entity = _make_entity()
        session = _refresh(entity, _FakeResponse(headers={"etag": '"abc"'}))
        self.assertNotIn("If-None-Match", session.calls[0][1]["headers"])

    def test_etag_is_replayed_on_the_next_refresh(self):
        entity = _make_entity()
        _refresh(entity, _FakeResponse(headers={"etag": '"abc"'}))
        session = _refresh(entity, _FakeResponse(status=304, body=b""))
        self.assertEqual(session.calls[0][1]["headers"]["If-None-Match"], '"abc"')

    def test_last_modified_is_replayed_when_there_is_no_etag(self):
        stamp = "Sat, 23 Aug 2026 11:00:00 GMT"
        entity = _make_entity()
        _refresh(entity, _FakeResponse(headers={"last-modified": stamp}))
        session = _refresh(entity, _FakeResponse(status=304, body=b""))
        self.assertEqual(
            session.calls[0][1]["headers"]["If-Modified-Since"], stamp
        )


class TestImageFailureLogging(unittest.TestCase):
    """A blip must not be an ERROR; a sustained outage must not be silent."""

    def _fail(self, entity, times):
        levels = []
        with patch("noaa_it_all.image._LOGGER") as logger:
            logger.log.side_effect = lambda level, *a, **k: levels.append(level)
            for _ in range(times):
                _refresh(entity, _ClientConnectorError("network unreachable"))
        return levels

    def _seeded(self):
        entity = _make_entity()
        _refresh(entity, _FakeResponse())
        return entity

    def test_a_blip_with_a_cached_image_is_only_debug(self):
        levels = self._fail(self._seeded(), 2)
        self.assertEqual(levels, [logging.DEBUG, logging.DEBUG])

    def test_a_short_outage_warns_once(self):
        from noaa_it_all.const import IMAGE_FAILURE_WARN_AFTER
        levels = self._fail(self._seeded(), IMAGE_FAILURE_WARN_AFTER)
        self.assertEqual(levels[-1], logging.WARNING)
        self.assertNotIn(logging.ERROR, levels)

    def test_a_sustained_outage_escalates_to_error(self):
        from noaa_it_all.const import IMAGE_FAILURE_ERROR_AFTER
        levels = self._fail(self._seeded(), IMAGE_FAILURE_ERROR_AFTER)
        self.assertEqual(levels[-1], logging.ERROR)
        self.assertEqual(levels.count(logging.ERROR), 1)

    def test_a_blank_card_warns_immediately(self):
        # With nothing cached the user really is looking at an empty card, so
        # staying at debug would hide a genuine problem.
        levels = self._fail(_make_entity(), 1)
        self.assertEqual(levels, [logging.WARNING])

    def test_a_wrong_url_always_warns(self):
        entity = self._seeded()
        with patch("noaa_it_all.image._LOGGER") as logger:
            levels = []
            logger.log.side_effect = lambda level, *a, **k: levels.append(level)
            _refresh(entity, _FakeResponse(status=404))
        self.assertEqual(levels, [logging.WARNING])

    def test_recovery_logs_info_and_resets_the_counter(self):
        from noaa_it_all.const import IMAGE_FAILURE_WARN_AFTER
        entity = self._seeded()
        self._fail(entity, IMAGE_FAILURE_WARN_AFTER)

        with patch("noaa_it_all.image._LOGGER") as logger:
            _refresh(entity, _FakeResponse(body=PNG + b"-new"))
            logger.info.assert_called_once()

        self.assertEqual(entity._failure_count, 0)


class TestEntityPicture(unittest.TestCase):
    """Pictures are served through Home Assistant, with an upstream fallback."""

    def test_falls_back_to_the_upstream_url_before_the_first_fetch(self):
        # image_last_updated is None until a fetch succeeds, and the base
        # class returns None for the picture then.  Pointing at NOAA in that
        # window means a restart during a Home Assistant-side DNS outage
        # still renders, because the browser's own network may be fine.
        entity = _make_entity()
        self.assertEqual(entity.entity_picture, entity._image_url)
        self.assertIn("?t=", entity.entity_picture)

    def test_uses_the_ha_proxy_once_an_image_has_been_fetched(self):
        entity = _make_entity()
        _refresh(entity, _FakeResponse())
        self.assertTrue(entity.entity_picture.startswith("/api/image_proxy/"))
        self.assertNotIn("services.swpc.noaa.gov", entity.entity_picture)


class TestRefreshScheduling(unittest.TestCase):
    """The fetch happens on a timer, never on the setup or request path."""

    def _added(self):
        entity = _make_entity()
        with patch("noaa_it_all.image.async_track_time_interval") as interval, \
                patch("noaa_it_all.image.async_call_later") as later:
            _run(entity.async_added_to_hass())
        return entity, interval, later

    def test_a_recurring_refresh_is_registered(self):
        from noaa_it_all.image import SCAN_INTERVAL
        entity, interval, _ = self._added()
        interval.assert_called_once()
        self.assertEqual(interval.call_args[0][2], SCAN_INTERVAL)
        self.assertEqual(
            interval.call_args[0][1], entity._async_scheduled_refresh
        )

    def test_the_first_fetch_is_scheduled_rather_than_awaited(self):
        # Awaiting it here would put a NOAA round trip on the config entry
        # setup path -- during exactly the outages this guards against.
        _, _, later = self._added()
        later.assert_called_once()
        self.assertEqual(later.call_args[0][1], 0)

    def test_both_timers_are_cancelled_when_the_entity_is_removed(self):
        entity, interval, later = self._added()
        self.assertEqual(
            entity._on_remove, [interval.return_value, later.return_value]
        )


class TestNoStateWriteBeforeAdd(unittest.TestCase):
    """Regression tests for the startup ``NoEntitySpecifiedError`` errors.

    Home Assistant does not assign ``entity_id`` until the entity is added,
    and ``async_write_ha_state()`` raises ``NoEntitySpecifiedError`` before
    that point -- which used to produce one error line per image entity on
    every startup (commit c7ed6e6).  The background refresher now legitimately
    writes state, so instead of banning the call outright these tests pin down
    *where* it may happen and prove the guard holds.
    """

    def _all_entities(self):
        from noaa_it_all.image import (
            AuroraForecastImageEntity,
            GOESAirMassImageEntity,
            GOESGeoColorImageEntity,
            GeoelectricFieldImageEntity,
            HurricaneOutlookImageEntity,
            RadarBaseReflectivityImageEntity,
            RadarLoopImageEntity,
        )
        return [
            GeoelectricFieldImageEntity(HASS, OFFICE),
            AuroraForecastImageEntity(HASS, OFFICE),
            HurricaneOutlookImageEntity(HASS),
            RadarBaseReflectivityImageEntity(HASS, OFFICE, "KNKX"),
            RadarLoopImageEntity(HASS, OFFICE, "KNKX"),
            GOESAirMassImageEntity(HASS),
            GOESGeoColorImageEntity(HASS),
        ]

    def test_constructing_an_entity_never_writes_state(self):
        def _raise(*args, **kwargs):
            raise AssertionError("state written before the entity was added")

        with patch.object(_FakeImageEntity, "async_write_ha_state", _raise):
            self._all_entities()

    def test_a_refresh_that_lands_before_the_add_is_a_no_op(self):
        """Entities are created before Home Assistant assigns an entity_id."""
        class _NoEntitySpecifiedError(Exception):
            pass

        for entity in self._all_entities():
            with self.subTest(entity=entity.__class__.__name__):
                self.assertIsNone(entity.entity_id)
                entity.async_write_ha_state = MagicMock(
                    side_effect=_NoEntitySpecifiedError("No entity id specified")
                )
                _refresh(entity, _FakeResponse())
                entity.async_write_ha_state.assert_not_called()
                self.assertEqual(_run(entity.async_image()), PNG)

    def test_state_is_only_written_from_the_guarded_helper(self):
        """Replaces the old module-wide ban on the ``async_write_ha_state`` string.

        The ban's real intent was "no state write on a path Home Assistant can
        reach before ``entity_id`` is assigned".  Asserting on the call site
        keeps that intent while allowing the background refresher to publish.
        """
        import ast
        import inspect

        from noaa_it_all import image as image_module

        allowed = {"_write_state_if_added"}
        tree = ast.parse(inspect.getsource(image_module))
        offenders = set()
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name in allowed:
                continue
            for call in ast.walk(node):
                if (isinstance(call, ast.Attribute)
                        and call.attr == "async_write_ha_state"):
                    offenders.add(node.name)
        self.assertEqual(set(), offenders)

    def test_the_upstream_url_is_refreshed_on_every_fetch(self):
        for entity in self._all_entities():
            with self.subTest(entity=entity.__class__.__name__):
                entity._image_url = "https://example.invalid/stale.png"
                _refresh(entity, _FakeResponse())
                self.assertNotEqual(
                    entity._image_url, "https://example.invalid/stale.png"
                )
                self.assertIn("?t=", entity._image_url)


class TestContentTypes(unittest.TestCase):
    """Home Assistant defaults every image to JPEG; five of seven are not."""

    def test_declared_content_types_match_the_upstream_formats(self):
        from noaa_it_all.image import (
            AuroraForecastImageEntity,
            GOESAirMassImageEntity,
            GOESGeoColorImageEntity,
            GeoelectricFieldImageEntity,
            HurricaneOutlookImageEntity,
            RadarBaseReflectivityImageEntity,
            RadarLoopImageEntity,
        )
        expected = [
            (GeoelectricFieldImageEntity(HASS, OFFICE), "image/png"),
            (AuroraForecastImageEntity(HASS, OFFICE), "image/jpeg"),
            (HurricaneOutlookImageEntity(HASS), "image/png"),
            (RadarBaseReflectivityImageEntity(HASS, OFFICE, "KNKX"), "image/gif"),
            (RadarLoopImageEntity(HASS, OFFICE, "KNKX"), "image/gif"),
            (GOESAirMassImageEntity(HASS), "image/jpeg"),
            (GOESGeoColorImageEntity(HASS), "image/jpeg"),
        ]
        for entity, content_type in expected:
            with self.subTest(entity=entity.__class__.__name__):
                self.assertEqual(entity.content_type, content_type)

    def test_log_labels_are_distinct(self):
        from noaa_it_all.image import (
            AuroraForecastImageEntity,
            GOESAirMassImageEntity,
            GOESGeoColorImageEntity,
            GeoelectricFieldImageEntity,
            HurricaneOutlookImageEntity,
            RadarBaseReflectivityImageEntity,
            RadarLoopImageEntity,
        )
        labels = [
            GeoelectricFieldImageEntity(HASS, OFFICE)._log_label,
            AuroraForecastImageEntity(HASS, OFFICE)._log_label,
            HurricaneOutlookImageEntity(HASS)._log_label,
            RadarBaseReflectivityImageEntity(HASS, OFFICE, "KNKX")._log_label,
            RadarLoopImageEntity(HASS, OFFICE, "KNKX")._log_label,
            GOESAirMassImageEntity(HASS)._log_label,
            GOESGeoColorImageEntity(HASS)._log_label,
        ]
        self.assertEqual(len(labels), len(set(labels)))


if __name__ == "__main__":
    unittest.main()


GIF = b"GIF89a-fake-frame"


def _loop_of(data, paths=("/frames/a.gif", "/frames/b.gif")):
    """Build the RadarLoop that assemble_gif would return."""
    from noaa_it_all.radar_loop import RadarLoop
    return RadarLoop(data, list(paths))


class _RecordingStore:
    """Stands in for RadarFrameStore, recording what the entity asks of it."""

    def __init__(self, frames=(), accept=True):
        self.frames = list(frames)
        self.accept = accept
        self.added = []
        self.pruned = []

    async def async_add_frame(self, timestamp, data):
        self.added.append((timestamp, data))
        if not self.accept:
            return False
        path = f"/frames/{timestamp:%Y%m%dT%H%M%SZ}.gif"
        if any(existing == path for _, existing in self.frames):
            return False
        self.frames.append((timestamp, path))
        return True

    async def async_frames(self):
        return list(self.frames)

    async def async_prune(self, window, now):
        self.pruned.append((window, now))
        return 0


def _local_loop_entity(frames=(), accept=True, loop_hours=24):
    """A radar loop entity in local mode with its store swapped for a fake."""
    from noaa_it_all.image import RadarLoopImageEntity

    hass = MagicMock()
    hass.config.path = MagicMock(return_value="/config/noaa_it_all/radar_frames")

    async def _executor(func, *args):
        """Run the encoder inline; the real one hands it to a worker thread."""
        return func(*args)

    hass.async_add_executor_job = _executor
    entity = RadarLoopImageEntity(hass, OFFICE, "KNKX", loop_hours=loop_hours)
    entity._store = _RecordingStore(frames, accept=accept)
    entity.entity_id = "image.noaa_sgx_weather_radar_loop"
    entity.async_write_ha_state = MagicMock()
    return entity


def _stored(count, start_minutes_ago=240):
    """A buffer of ``count`` frames, oldest first.

    Timestamps are derived from the real clock rather than a fixed date: the
    code under test prunes and samples against ``dt_util.utcnow()``, so any
    hard-coded date would silently stop being inside the window once enough
    real time had passed, and the suite would start failing on a calendar day
    rather than on a code change.
    """
    from noaa_it_all import image as image_module

    now = image_module.dt_util.utcnow()
    return [
        (
            now - timedelta(minutes=start_minutes_ago - index * 10),
            f"/frames/stored-{index}.gif",
        )
        for index in range(count)
    ]


class TestRadarLoopUpstreamMode(unittest.TestCase):
    """With the option off, nothing about the entity may have changed."""

    def test_it_fetches_noaas_own_loop(self):
        from noaa_it_all.image import RadarLoopImageEntity
        entity = RadarLoopImageEntity(HASS, OFFICE, "KNKX")
        self.assertIn("_loop.gif", entity._base_url())

    def test_it_writes_nothing_to_disk(self):
        from noaa_it_all.image import RadarLoopImageEntity
        hass = MagicMock()
        entity = RadarLoopImageEntity(HASS, OFFICE, "KNKX")
        self.assertIsNone(entity._store)
        hass.config.path.assert_not_called()

    def test_it_reports_upstream_mode(self):
        from noaa_it_all.image import RadarLoopImageEntity
        entity = RadarLoopImageEntity(HASS, OFFICE, "KNKX")
        self.assertEqual("upstream", entity.extra_state_attributes["loop_mode"])

    def test_it_still_caches_through_a_failure(self):
        from noaa_it_all.image import RadarLoopImageEntity
        entity = RadarLoopImageEntity(HASS, OFFICE, "KNKX")
        entity.entity_id = "image.noaa_sgx_weather_radar_loop"
        entity.async_write_ha_state = MagicMock()
        _refresh(entity, _FakeResponse(content_type="image/gif", body=GIF))
        self.assertEqual(GIF, _run(entity.async_image()))
        _refresh(entity, _FakeResponse(status=503))
        self.assertEqual(GIF, _run(entity.async_image()))


class TestRadarLoopLocalMode(unittest.TestCase):
    """Collecting frames and assembling them into a longer animation."""

    def test_it_fetches_single_scans_rather_than_the_loop(self):
        entity = _local_loop_entity()
        self.assertIn("_0.gif", entity._base_url())

    def test_a_fetched_scan_is_stored_under_its_published_time(self):
        entity = _local_loop_entity(frames=_stored(10))
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"LOOP")):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        timestamp, data = entity._store.added[0]
        self.assertEqual(GIF, data)
        self.assertEqual(
            datetime(2026, 8, 23, 11, 54, tzinfo=timezone.utc), timestamp
        )

    def test_the_assembled_loop_is_what_gets_served(self):
        entity = _local_loop_entity(frames=_stored(10))
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"ASSEMBLED")):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        self.assertEqual(b"ASSEMBLED", _run(entity.async_image()))
        self.assertEqual("local", entity.extra_state_attributes["loop_mode"])

    def test_a_scan_already_held_is_not_reassembled(self):
        entity = _local_loop_entity(frames=_stored(10))
        headers = {"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"}
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"ASSEMBLED")) as build:
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF, headers=headers))
            self.assertEqual(1, build.call_count)
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF, headers=headers))
            self.assertEqual(1, build.call_count)

    def test_storing_a_frame_prunes_the_window(self):
        entity = _local_loop_entity(frames=_stored(10))
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"LOOP")):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        self.assertEqual(timedelta(hours=24), entity._store.pruned[0][0])

    def test_a_missing_last_modified_still_yields_a_frame(self):
        entity = _local_loop_entity(frames=_stored(10))
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"LOOP")):
            _refresh(entity, _FakeResponse(content_type="image/gif", body=GIF))
        self.assertEqual(1, len(entity._store.added))

    def test_a_thin_buffer_falls_back_to_noaas_loop(self):
        entity = _local_loop_entity(frames=_stored(2))
        session = _refresh(entity, _FakeResponse(
            content_type="image/gif", body=GIF,
            headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
        ))
        self.assertTrue(any("_loop.gif" in url for url, _ in session.calls))
        self.assertEqual("upstream", entity.extra_state_attributes["loop_mode"])

    def test_a_failed_assembly_falls_back_to_noaas_loop(self):
        entity = _local_loop_entity(frames=_stored(10))
        with patch("noaa_it_all.image.assemble_gif", return_value=None):
            session = _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        self.assertTrue(any("_loop.gif" in url for url, _ in session.calls))

    def test_a_disk_that_refuses_the_frame_still_shows_a_loop(self):
        entity = _local_loop_entity(frames=_stored(10), accept=False)
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"LOOP")):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        self.assertEqual(b"LOOP", _run(entity.async_image()))

    def test_the_reported_window_matches_the_frames_used(self):
        frames = _stored(10)
        used = [path for _, path in frames[2:8]]
        entity = _local_loop_entity(frames=frames)
        with patch("noaa_it_all.image.assemble_gif",
                   return_value=_loop_of(b"LOOP", used)):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        attributes = entity.extra_state_attributes
        self.assertEqual(6, attributes["frame_count"])
        self.assertEqual(frames[2][0].isoformat(), attributes["window_start"])
        self.assertEqual(frames[7][0].isoformat(), attributes["window_end"])

    def test_the_reported_count_is_what_the_encoder_used_not_what_it_was_given(self):
        """Frames shed to fit the size limit must not be counted as shown.

        These attributes exist so a loop quietly shorter than configured is
        visible; counting the frames offered rather than the frames encoded
        would hide precisely that case.
        """
        frames = _stored(10)
        entity = _local_loop_entity(frames=frames)
        # The encoder kept three of the ten it was handed.
        with patch("noaa_it_all.image.assemble_gif",
                   return_value=_loop_of(
                       b"LOOP", [path for _, path in frames[7:]])):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        self.assertEqual(3, entity.extra_state_attributes["frame_count"])


class TestRadarLoopValidatorsAreScopedToTheirResource(unittest.TestCase):
    """This entity fetches two URLs through one set of cached validators.

    Offering the single frame's ETag back when asking for the animation is
    asking the wrong question about the wrong file, and a server that answered
    304 to it would hand back a still image as the loop.
    """

    HEADERS = {
        "last-modified": "Sun, 23 Aug 2026 11:54:00 GMT",
        "etag": '"frame-etag"',
    }

    LOOP_HEADERS = {"etag": '"loop-etag"'}

    @staticmethod
    def _sent_to(session, needle):
        """Return the conditional headers sent to the matching request."""
        for url, kwargs in session.calls:
            if needle in url:
                headers = kwargs.get("headers", {})
                return {
                    key: value for key, value in headers.items()
                    if key in ("If-None-Match", "If-Modified-Since")
                }
        raise AssertionError(f"no request was made to {needle}")

    def _seed_both_resources(self, entity):
        """Fetch the frame and the fallback loop once each, caching both."""
        _refresh(
            entity,
            _FakeResponse(
                content_type="image/gif", body=GIF, headers=self.HEADERS),
            _FakeResponse(
                content_type="image/gif", body=b"GIF89a-loop",
                headers=self.LOOP_HEADERS),
        )

    def test_each_resource_is_revalidated_with_its_own_validator(self):
        """Not merely "never the wrong one" -- each must still get the right one.

        Scoping validators by resource is only half the job: if the two
        resources shared one slot, each fetch would evict the other's and
        neither could ever revalidate, so the fallback loop would be
        re-downloaded in full on every refresh for as long as the buffer was
        filling.
        """
        entity = _local_loop_entity(frames=_stored(2))
        self._seed_both_resources(entity)
        session = _refresh(
            entity,
            _FakeResponse(
                content_type="image/gif", body=b"GIF89a-newer",
                headers={
                    "last-modified": "Sun, 23 Aug 2026 12:04:00 GMT",
                    "etag": '"newer-frame-etag"',
                },
            ),
            _FakeResponse(
                content_type="image/gif", body=b"GIF89a-loop",
                headers=self.LOOP_HEADERS),
        )
        self.assertEqual(
            {"If-None-Match": '"frame-etag"'}, self._sent_to(session, "_0.gif")
        )
        self.assertEqual(
            {"If-None-Match": '"loop-etag"'}, self._sent_to(session, "_loop.gif")
        )

    def test_neither_resource_is_offered_the_others_validator(self):
        entity = _local_loop_entity(frames=_stored(2))
        self._seed_both_resources(entity)
        session = _refresh(
            entity,
            _FakeResponse(
                content_type="image/gif", body=b"GIF89a-newer",
                headers={"last-modified": "Sun, 23 Aug 2026 12:04:00 GMT",
                         "etag": '"newer-frame-etag"'},
            ),
            _FakeResponse(
                content_type="image/gif", body=b"GIF89a-loop",
                headers=self.LOOP_HEADERS),
        )
        self.assertNotIn(
            '"loop-etag"', self._sent_to(session, "_0.gif").values()
        )
        self.assertNotIn(
            '"frame-etag"', self._sent_to(session, "_loop.gif").values()
        )

    def test_the_fallback_loop_is_cache_busted_like_every_other_url(self):
        """It was before this PR, and a CDN will happily serve a stale copy."""
        entity = _local_loop_entity(frames=_stored(2))
        session = _refresh(
            entity,
            _FakeResponse(
                content_type="image/gif", body=GIF, headers=self.HEADERS),
            _FakeResponse(content_type="image/gif", body=b"GIF89a-loop"),
        )
        loop_url = next(url for url, _ in session.calls if "_loop.gif" in url)
        self.assertIn("?t=", loop_url)

    def test_a_single_url_entity_still_revalidates(self):
        """Scoping validators must not switch conditional requests off."""
        entity = _make_entity()
        _refresh(entity, _FakeResponse(headers={"etag": '"png-etag"'}))
        session = _refresh(entity, _FakeResponse())
        url, kwargs = session.calls[0]
        self.assertEqual('"png-etag"', kwargs["headers"]["If-None-Match"])


class TestRadarLoopLocalModeSurvivesFailures(unittest.TestCase):
    """The invariant the whole image module exists to hold, in local mode.

    A refresh that fails must leave the displayed animation exactly as it
    was -- the local loop adds a fetch, a disk and an encoder to the list of
    things that can fail, and none of them may blank the card.
    """

    def _seeded(self):
        entity = _local_loop_entity(frames=_stored(10))
        with patch("noaa_it_all.image.assemble_gif", return_value=_loop_of(b"GOOD-LOOP")):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        self.assertEqual(b"GOOD-LOOP", _run(entity.async_image()))
        entity.async_write_ha_state.reset_mock()
        return entity

    def _assert_survives(self, result, build=b"GOOD-LOOP"):
        entity = self._seeded()
        stamp = entity.image_last_updated
        with patch("noaa_it_all.image.assemble_gif",
                   return_value=_loop_of(build) if build else None):
            _refresh(entity, result)
        self.assertEqual(b"GOOD-LOOP", _run(entity.async_image()))
        self.assertEqual(stamp, entity.image_last_updated)
        entity.async_write_ha_state.assert_not_called()

    def test_a_server_error_leaves_the_loop_alone(self):
        self._assert_survives(_FakeResponse(status=503))

    def test_a_network_error_leaves_the_loop_alone(self):
        self._assert_survives(asyncio.TimeoutError())

    def test_an_empty_body_leaves_the_loop_alone(self):
        self._assert_survives(_FakeResponse(content_type="image/gif", body=b""))

    def test_a_non_image_response_leaves_the_loop_alone(self):
        self._assert_survives(
            _FakeResponse(content_type="text/html", body=b"<html>no</html>")
        )

    def test_an_encoder_that_gives_up_leaves_the_loop_alone(self):
        """Assembly returning None must not blank the card either.

        The fallback fetch of NOAA's own loop fails here too, so there is
        nothing at all to fall back to -- the previous animation has to stand.
        """
        entity = self._seeded()
        stamp = entity.image_last_updated
        with patch("noaa_it_all.image.assemble_gif", return_value=None):
            _refresh(
                entity,
                _FakeResponse(
                    content_type="image/gif", body=b"NEW-FRAME",
                    headers={"last-modified": "Sun, 23 Aug 2026 12:04:00 GMT"},
                ),
                _FakeResponse(status=503),
            )
        self.assertEqual(b"GOOD-LOOP", _run(entity.async_image()))
        self.assertEqual(stamp, entity.image_last_updated)


class TestRadarLoopHoursOption(unittest.TestCase):
    """Reading the option off the config entry."""

    @staticmethod
    def _entry(value):
        entry = MagicMock()
        entry.data = {"office_code": OFFICE}
        entry.options = {} if value is None else {"radar_loop_hours": value}
        return entry

    def test_a_saved_value_is_used(self):
        from noaa_it_all.image import radar_loop_hours
        self.assertEqual(6, radar_loop_hours(self._entry(6)))

    def test_the_default_is_a_full_day(self):
        from noaa_it_all.image import radar_loop_hours
        self.assertEqual(24, radar_loop_hours(self._entry(None)))

    def test_zero_is_honoured_as_the_opt_out(self):
        from noaa_it_all.image import radar_loop_hours
        self.assertEqual(0, radar_loop_hours(self._entry(0)))

    def test_out_of_range_values_are_clamped(self):
        from noaa_it_all.image import radar_loop_hours
        self.assertEqual(24, radar_loop_hours(self._entry(999)))
        self.assertEqual(0, radar_loop_hours(self._entry(-5)))

    def test_an_unusable_value_falls_back_to_the_default(self):
        from noaa_it_all.image import radar_loop_hours
        self.assertEqual(24, radar_loop_hours(self._entry("lots")))


try:
    from PIL import Image as _PILImage
    _PIL = True
except ImportError:  # pragma: no cover - Pillow ships with Home Assistant core
    _PIL = False


def _nexrad_frame(index, size=(240, 200)):
    """A transparent, separately-palettised GIF with a drifting echo."""
    from io import BytesIO

    scale = [
        (4, 233, 231), (1, 159, 244), (3, 0, 244), (2, 253, 2),
        (1, 197, 1), (0, 142, 0), (253, 248, 2), (253, 0, 0),
    ]
    image = _PILImage.new("P", size, 0)
    palette = [0, 0, 0]
    for colour in scale:
        palette += list(colour)
    palette += [0, 0, 0] * (256 - 1 - len(scale))
    image.putpalette(palette)
    origin = (index * 9) % (size[0] - 60)
    for x in range(origin, origin + 60):
        for y in range(size[1] // 4, size[1] // 4 * 3):
            image.putpixel((x, y), 1 + ((x + y) // 9) % len(scale))
    buffer = BytesIO()
    image.save(buffer, format="GIF", transparency=0)
    return buffer.getvalue()


@unittest.skipUnless(_PIL, "Pillow is required to assemble a GIF")
class TestRadarLoopEndToEnd(unittest.TestCase):
    """The whole path, with a real directory and a real encoder.

    Every other test in this file swaps the store or the encoder for a fake,
    which leaves the wiring between them unexercised -- and that wiring is
    where a 24-hour loop either works or quietly serves NOAA's 50 minutes
    forever.
    """

    def _entity(self, directory):
        from noaa_it_all.image import RadarLoopImageEntity

        hass = MagicMock()
        hass.config.path = MagicMock(return_value=directory)

        async def _executor(func, *args):
            return func(*args)

        hass.async_add_executor_job = _executor
        entity = RadarLoopImageEntity(hass, OFFICE, "KLTX", loop_hours=24)
        entity.entity_id = "image.noaa_sgx_weather_radar_loop"
        entity.async_write_ha_state = MagicMock()
        return entity

    @staticmethod
    def _start(polls):
        """The publication time of the first frame in a run of ``polls``.

        Anchored to the real clock, not to a fixed date. The code under test
        prunes and samples against ``dt_util.utcnow()``, so frames pinned to a
        calendar date drop out of the window as soon as enough real time
        passes -- which would make this suite start failing on a date rather
        than on a change. Truncated to whole seconds because that is the
        resolution both the HTTP date header and the frame filename carry.
        """
        from noaa_it_all import image as image_module

        now = image_module.dt_util.utcnow().replace(microsecond=0)
        return now - timedelta(minutes=10 * polls)

    def _poll(self, entity, index, start):
        """One refresh, with NOAA's loop queued behind it as the fallback."""
        published = (start + timedelta(minutes=10 * index)).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        )
        return _refresh(
            entity,
            _FakeResponse(
                content_type="image/gif",
                body=_nexrad_frame(index),
                headers={"last-modified": published},
            ),
            _FakeResponse(content_type="image/gif", body=b"GIF89a-noaa-loop"),
        )

    def test_the_loop_grows_from_noaas_into_a_locally_built_animation(self):
        with tempfile.TemporaryDirectory() as directory:
            entity = self._entity(directory)
            start = self._start(12)

            # Too thin to improve on NOAA: its own loop is what gets served.
            self._poll(entity, 0, start)
            self.assertEqual("upstream", entity.extra_state_attributes["loop_mode"])
            self.assertEqual(b"GIF89a-noaa-loop", _run(entity.async_image()))

            for index in range(1, 12):
                self._poll(entity, index, start)

            attributes = entity.extra_state_attributes
            self.assertEqual("local", attributes["loop_mode"])
            self.assertEqual(12, attributes["frame_count"])
            self.assertEqual(
                start.isoformat(), attributes["window_start"]
            )

            served = _run(entity.async_image())
            self.assertEqual("image/gif", entity.content_type)
            with tempfile.NamedTemporaryFile(suffix=".gif") as handle:
                handle.write(served)
                handle.flush()
                animation = _PILImage.open(handle.name)
                # A drifting echo means no two frames are identical, so none of
                # them are merged away.
                self.assertEqual(12, animation.n_frames)
                self.assertEqual(0, animation.info.get("loop"))

            stored = os.listdir(os.path.join(directory, "KLTX"))
            self.assertEqual(12, len(stored))
            self.assertTrue(all(name.endswith(".gif") for name in stored))

    def test_frames_collected_before_a_restart_are_still_there_after_it(self):
        """The whole feature rests on this: a restart must not start over."""
        with tempfile.TemporaryDirectory() as directory:
            start = self._start(9)
            first = self._entity(directory)
            for index in range(8):
                self._poll(first, index, start)
            self.assertEqual("local", first.extra_state_attributes["loop_mode"])

            # A new entity over the same directory stands in for the restart.
            second = self._entity(directory)
            self._poll(second, 8, start)
            attributes = second.extra_state_attributes
            self.assertEqual("local", attributes["loop_mode"])
            self.assertEqual(9, attributes["frame_count"])
            self.assertEqual(start.isoformat(), attributes["window_start"])


class TestRadarLoopPruning(unittest.TestCase):
    """Pruning has to keep up with the window even when nothing new arrives."""

    def test_pruning_runs_even_when_the_scan_has_not_changed(self):
        """A radar site stuck on one scan must not let the window stretch.

        Maintenance windows and outages hold one Last-Modified for hours. If
        pruning only ran when a frame was stored, nothing would age out for the
        whole outage and the loop would quietly cover more than it claims.
        """
        entity = _local_loop_entity(frames=_stored(10))
        headers = {"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"}
        with patch("noaa_it_all.image.assemble_gif",
                   return_value=_loop_of(b"LOOP")):
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF, headers=headers))
            first = len(entity._store.pruned)
            _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF, headers=headers))
        self.assertGreater(len(entity._store.pruned), first)


class TestRadarLoopMinimumFrames(unittest.TestCase):
    """The floor has to apply to what ships, not to what is on disk."""

    def test_a_sparse_window_falls_back_even_with_frames_on_disk(self):
        """The floor has to be judged on the sampled frames, not the directory.

        Here the store holds 84 frames -- comfortably over the floor -- but all
        bar four are older than the window, so the loop that would actually
        ship is four frames long. That is fewer than NOAA's ten, which is
        precisely what RADAR_LOOP_MIN_FRAMES exists to prevent, and it is
        enough frames that the encoder would happily build it.
        """
        from noaa_it_all import image as image_module

        now = image_module.dt_util.utcnow()
        recent = [
            (now - timedelta(minutes=15 * index), f"/frames/recent-{index}.gif")
            for index in range(4)
        ][::-1]
        ancient = [
            (now - timedelta(days=3, minutes=10 * index), f"/frames/old-{index}.gif")
            for index in range(80)
        ][::-1]
        entity = _local_loop_entity(frames=ancient + recent)
        self.assertGreaterEqual(len(entity._store.frames), 84)

        with patch("noaa_it_all.image.assemble_gif",
                   return_value=_loop_of(b"LOOP")) as build:
            session = _refresh(entity, _FakeResponse(
                content_type="image/gif", body=GIF,
                headers={"last-modified": "Sun, 23 Aug 2026 11:54:00 GMT"},
            ))
        build.assert_not_called()
        self.assertTrue(any("_loop.gif" in url for url, _ in session.calls))
        self.assertEqual("upstream", entity.extra_state_attributes["loop_mode"])


class TestRadarFrameHousekeeping(unittest.TestCase):
    """Frames for a site nothing collects any more must not be orphaned."""

    def _hass(self, entries, present):
        hass = MagicMock()
        hass.config.path = MagicMock(return_value="/config/radar_frames")
        hass.config_entries.async_entries = MagicMock(return_value=entries)

        async def _executor(func, *args):
            return list(present)

        hass.async_add_executor_job = _executor
        return hass

    @staticmethod
    def _entry(office, hours):
        entry = MagicMock()
        entry.data = {"office_code": office}
        entry.options = {"radar_loop_hours": hours}
        return entry

    def _run_cleanup(self, hass, keep):
        from noaa_it_all import image as image_module

        removed = []

        class _Store:
            def __init__(self, _hass, _base, site):
                self.site = site

            async def async_remove_all(self):
                removed.append(self.site)

        with patch.object(image_module, "RadarFrameStore", _Store):
            _run(image_module.async_discard_unused_radar_frames(hass, keep=keep))
        return removed

    def test_the_site_in_use_is_kept(self):
        hass = self._hass([self._entry("ILM", 24)], ["KLTX"])
        self.assertEqual([], self._run_cleanup(hass, keep="KLTX"))

    def test_a_site_switched_away_from_is_removed(self):
        """Changing office leaves the old site's frames with no owner."""
        hass = self._hass([self._entry("SGX", 24)], ["KLTX", "KNKX"])
        self.assertEqual(["KLTX"], self._run_cleanup(hass, keep="KNKX"))

    def test_turning_the_loop_off_reclaims_the_disk(self):
        """The options screen promises 0 hours will "store nothing"."""
        hass = self._hass([self._entry("ILM", 0)], ["KLTX"])
        self.assertEqual(["KLTX"], self._run_cleanup(hass, keep=None))

    def test_a_site_another_entry_still_uses_is_kept(self):
        hass = self._hass(
            [self._entry("ILM", 0), self._entry("SGX", 24)], ["KLTX", "KNKX"]
        )
        self.assertEqual(["KLTX"], self._run_cleanup(hass, keep=None))
