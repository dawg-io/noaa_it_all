# Changelog

All notable changes to NOAA It All for Home Assistant will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.1] - Current

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
