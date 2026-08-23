# Changelog

All notable changes to NOAA It All for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.2] - Current

### Fixed
- **Image entities no longer log an error on every startup.** `image.py` sets up its entities with
  `async_add_entities(entities, True)`, so Home Assistant calls `async_update()` *before* adding
  each entity — and `entity_id` is not assigned until after the add. The explicit
  `self.async_write_ha_state()` inside every image `async_update()` therefore raised
  `NoEntitySpecifiedError` on that first call, which the surrounding `except Exception` turned into
  `Error during <image> update: No entity id specified for entity ...` — one line per image entity,
  every startup. All seven writes are removed. Home Assistant writes the state itself exactly once,
  in `add_to_platform_finish()` after the entity is added, so the explicit call was redundant then
  and fatal before then. `update_before_add=True` is kept, so the image URL is resolved as the
  entity is set up rather than left empty.
- **Documentation entity IDs now match the entities the integration actually creates.** Every
  `sensor.`/`binary_sensor.`/`image.`/`weather.` reference in `README.md`, `CONFIGURATION.md` and
  `info.md` was checked against the 45 entity IDs produced by instantiating the real entity classes.
  128 references were wrong — most were missing the device-group segment
  (`sensor.noaa_ilm_temperature` instead of `sensor.noaa_ilm_weather_temperature`), had a phantom
  one (`sensor.noaa_weather_hurricane_activity` instead of `sensor.noaa_hurricane_activity`), or
  used a renamed metric (`kp_index` instead of `planetary_k_index`). All examples now use one
  office code (`ilm`) throughout, so adapting one means changing that single token.
- **The documented naming rule is now the rule the code follows.** `README.md` claimed "All
  entities use `_attr_has_entity_name = True`"; three do not. The device table listed a
  `NOAA Surf` device that does not exist (it is `NOAA {OFFICE} Surf`) and omitted `NOAA Hurricane`;
  `CONFIGURATION.md`'s pattern omitted the device-group segment entirely. Both documents now carry
  an **Exceptions to the pattern** table listing the five entity IDs that contain no office code,
  so a find-and-replace does not corrupt them. The rule itself is stated correctly: Home Assistant
  prepends the device name whether or not an entity sets `has_entity_name` — that flag only decides
  whether a redundant device-name prefix is stripped off the entity's own name first
  (`entity_registry._async_get_full_entity_name`).
- **Broken copy/paste examples fixed.** `state_attr()` calls naming attributes that do not exist
  (`total_alerts`, `alert_types`, `office`, `issued_time`, `product_link`) now use the real keys
  (`alert_count`, `alerts`, `office_code`, `issue_time`); the aurora automation's `condition: sun`
  with both `after: sunset` and `before: sunrise` — unsatisfiable at every instant, so it never
  fired — is now a `sun.sun` state condition; wind direction reads its `cardinal_direction`
  attribute rather than the state, which is degrees; and `notify.mobile_app` is written
  `notify.mobile_app_your_phone`, since the bare service is never registered.
- **Update frequency and legacy YAML corrected.** The docs claimed a 5-minute refresh; coordinators
  run at `DEFAULT_SCAN_INTERVAL = 10` minutes, and meteor sensors at 30. Legacy YAML was documented
  as providing "global sensors only" — it creates no entities at all and logs an error, which the
  docs now say.

### Notes
- The geoelectric and aurora images are `image.noaa_{office}_space_geoelectric_field_image` and
  `image.noaa_{office}_space_aurora_forecast_image`. An earlier revision of this release documented
  them without the device prefix, on the mistaken belief that omitting `_attr_has_entity_name`
  suppressed it. It does not — the device name is always prepended.
- An image entity **disabled in the entity registry** is never added, so the pre-add update was the
  only update it ever ran — the error repeated on every update instead of firing once at startup.
  That is how this surfaced.
- The remaining `async_write_ha_state()` in `weather.py` is intentional and unaffected: it is the
  forecast-coordinator listener, registered in `async_added_to_hass()`, so it can only fire after
  `entity_id` is assigned, and there is no platform-side write behind it.
- **Image entities are not polled.** Home Assistant's `ImageEntity` sets `_attr_should_poll = False`
  upstream, and `entity_platform` only arms a polling timer when some entity reports `should_poll`.
  So `async_update()` runs exactly once and the module-level `SCAN_INTERVAL` in `image.py` has no
  effect — the cache-busting `?t=` suffix is fixed for the lifetime of the config entry, and each
  image entity's state stays `unknown` because `_attr_image_last_updated` is never set. This is
  pre-existing behaviour, unchanged by this release, and is tracked as a follow-up.
- `tests/test_image.py` now runs `async_update()` on all seven image entities with an
  `async_write_ha_state` that raises, asserting nothing is logged as an error and that the image URL
  is still populated, plus a source-level guard so a new image entity cannot reintroduce the
  pattern.

## [0.5.1]

### Fixed
- **The Configure screen no longer fails with a 500.** `NOAAOptionsFlow.__init__` assigned
  `self.config_entry`, but Home Assistant made `OptionsFlow.config_entry` a read-only property that
  the framework populates itself, so opening options raised
  `AttributeError: property 'config_entry' of 'NOAAOptionsFlow' object has no setter`. The options
  flow now takes no constructor argument and reads the entry through the inherited property.
- **Saved options are now actually used.** The options flow writes to `config_entry.options`, but
  every runtime read used `config_entry.data`, so changing the location saved without error and
  then had no effect on any entity. `__init__.py`, `sensor.py`, `binary_sensor.py`, `weather.py`
  and `image.py` now resolve their configuration through the new
  `entry_config.resolve_entry_config()` helper, which lets saved options override the values
  entered at initial setup and falls back to those values per key.
- **Changing the location takes effect without restarting Home Assistant.** Nothing reloaded the
  config entry when its options changed, and the coordinators capture the office code and
  coordinates at construction with no way to re-point them — so even a correct read still needed a
  restart. The entry now registers an update listener that reloads it, rebuilding the coordinators
  against the new location.
- The options form pre-fills from the location currently in effect rather than from the original
  setup values, so reopening Configure after a save no longer shows stale coordinates.

### Notes
- Changing the **forecast office** rewrites entity IDs, which are derived from the office code, so
  the previous office's entities are left behind for manual cleanup. The config entry's title and
  `unique_id` also still reflect the office and coordinates chosen at initial setup, because
  options are stored separately from entry data. Migrating this flow to Home Assistant's
  `async_step_reconfigure` would address both and is tracked separately.
- The test suite's fake `OptionsFlow` now exposes `config_entry` as a getter-only property,
  matching real Home Assistant. The previous permissive stub is why CI stayed green on a crash that
  reproduced on every supported install.

Reported by @JoeOster in [dawg-io/noaa_it_all#21](https://github.com/dawg-io/noaa_it_all/issues/21).

## [0.5.0]

### Added
- **Meteor shower alerts and viewing forecast**, in the `NOAA Space` device group:
  - `binary_sensor.noaa_{office}_space_meteor_shower_active` — turns on only when a shower is
    genuinely worth going outside for, gated on both a real predicted rate (>=5/hour) and usable
    sky conditions (score >=25) so it stays off most nights rather than sitting permanently on
    (about 50 nights a year measured from Wilmington NC, clustered around the major showers)
  - `sensor.noaa_{office}_space_meteor_shower_activity` — the shower most worth watching now
  - `sensor.noaa_{office}_space_next_meteor_shower` — next shower to peak, with an `upcoming`
    attribute listing the next five for dashboard cards
  - `sensor.noaa_{office}_space_meteor_viewing_score` — 0-100 sky-conditions score with the best
    viewing window, expected meteors/hour, moon state and the limiting factor
- Bundled catalog of 29 meteor showers (`meteor_catalog.py`) keyed by **solar longitude** rather
  than by date, sourced from the IMO Meteor Shower Calendar and the IAU Meteor Data Center.
- `astro.py` and `meteor.py`: standard-library positional astronomy and the meteor rate model,
  with no Home Assistant dependency, verified against Meeus worked examples 7.a, 12.a, 13.b,
  25.a, 47.a and 48.a.

### Notes
- **This feature makes no network requests.** NOAA publishes no meteor shower data — the NWS
  alert taxonomy covers terrestrial hazards and the Space Weather Prediction Center covers
  geomagnetic activity, not meteors — and no live feed is needed, because Earth crosses the same
  debris streams at the same point in its orbit every year. Peak times are computed locally from
  each shower's stored solar longitude, so the catalog never needs a date update.
- Computed peak times are accurate to about **±11 minutes**, far finer than the hours-wide spread
  of real shower maxima and than the precision to which published maxima are themselves quoted.
- The viewing score measures **sky conditions, not shower strength** — the shower's ZHR cancels
  out of the relation, so a minor shower riding high under a new moon scores well while the
  Perseids behind a full moon score badly. Shower strength is reported as `expected_per_hour`.
- The score accounts for radiant altitude, moonlight and astronomical darkness. It does **not**
  account for cloud cover; pair it with the existing Cloud Cover sensor if you want that.
- No new dependencies: `requirements` remains `aiohttp` and `voluptuous`.

### Fixed
- **Binary sensors no longer repeat the device name.** All five existing binary sensors set a
  full `_attr_name` containing `NOAA {office}` while also carrying a device, so Home Assistant
  prefixed the device name a second time — producing
  `binary_sensor.noaa_ilm_surf_noaa_ilm_unsafe_to_swim` and the friendly name
  "NOAA ILM Surf NOAA ILM Unsafe to Swim". They now use `_attr_has_entity_name = True` with a
  local-only name, matching every sensor in the integration. Found by running the integration on
  a live Home Assistant instance.
  - **Existing installations are unaffected in any way that breaks automations.** The `unique_id`
    values are unchanged, so the entity registry keeps the entity IDs it already assigned. Only
    the displayed friendly name changes. Fresh installations get the shorter IDs
    (`binary_sensor.noaa_{office}_surf_unsafe_to_swim`); see the migration table in the README.
- Corrected the binary sensor entity IDs throughout README.md and CONFIGURATION.md. They
  previously documented IDs such as `binary_sensor.noaa_ilm_unsafe_to_swim`, which Home Assistant
  never actually produced.

### Changed
- Meteor shower entities refresh every 30 minutes rather than the integration default of 10,
  since nothing is fetched and the best-of-night result is stable for hours.

## [0.3.13] - Previous

### Added
- Dedicated `NOAA Hurricane` device that groups all global hurricane / NHC entities (Hurricane Alerts, Hurricane Activity, Hurricane Outlook Image, GOES Air Mass, GOES GeoColor) into a single device, independent of any configured NWS office.
- Location-specific aurora visibility predictions with timing and duration
- Solar Radiation Storm alerts with S1-S5 classification and location-specific risk assessment
- Forecast Discussion sensor (AFD product) with meteorologist-written technical analysis
- Cloud Cover sensor from NWS gridpoint data
- Radar Timestamp sensor for tracking radar image freshness
- Feels Like (apparent temperature) sensor with wind chill / heat index
- Comprehensive NWS Active Alerts sensor with severity and urgency breakdowns

### Improved
- Weather observations now fetched from nearest station using coordinates (weather.gov API)
- Device grouping organises all entities under NOAA Space, NOAA Weather, NOAA Surf, NOAA Hurricane, and NOAA Weather [OFFICE]

### Breaking Changes
- Hurricane sensors and hurricane image entities are no longer duplicated per configured NWS office. Their `unique_id` values changed from `noaa_{office}_hurricane_*` / `noaa_{office}_goes_*` to global IDs (`noaa_hurricane_alerts`, `noaa_hurricane_activity`, `noaa_hurricane_outlook_image`, `noaa_goes_airmass_image`, `noaa_goes_geocolor_image`). Existing entity registry entries from previous versions will become orphaned and may need to be deleted; the new entities will be created automatically under the `NOAA Hurricane` device.

## [1.0.20]

### Breaking Changes
- **Latitude and Longitude are now required fields** in Config Flow setup
- Weather data now fetched from nearest observation station to configured coordinates
- Users must reconfigure the integration to provide coordinates

### Added
- Config Flow UI setup with NWS office selector and coordinate inputs
- Location-specific weather observations from nearest NWS station
- Binary sensors for Severe Weather, Flood/Winter, Heat/Air Quality, and Active Alerts

## [1.0.0]

### Added
- Initial release
- Planetary K-Index sensor
- Geomagnetic Storm measurements
- Hurricane alerts and activity sensors
- Geomagnetic field and aurora forecast image entities
- Legacy YAML configuration support
