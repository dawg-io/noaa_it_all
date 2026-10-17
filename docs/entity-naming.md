# Entity Naming Conventions

Understanding entity naming helps you quickly identify and use sensors in automations and dashboards.

Home Assistant builds each entity ID from the **device name** and the entity's own **name**:
`NOAA ILM Weather` + `Temperature` becomes `sensor.noaa_ilm_weather_temperature`, so office-scoped
entities follow `{entity_type}.noaa_{office}_{weather|surf|space}_{name}`. The six
hurricane entities have no office code, because their device has none, and the marine entities
use the zone instead — see [Exceptions to the pattern](#exceptions-to-the-pattern) below.

**Every example in these docs uses the `ILM` office.** To adapt one to your own location,
replace `ilm` with your office code in lower case — and leave the entities listed under
[Exceptions to the pattern](#exceptions-to-the-pattern) alone, because they carry no office code.

## Naming Patterns by Device

| Device | Device Name Pattern | Example Entity ID |
|--------|--------------------|--------------------|
| NOAA Hurricane | `NOAA Hurricane` (global — no office code) | `sensor.noaa_hurricane_activity` |
| NOAA {OFFICE} Weather | `NOAA {OFFICE} Weather` | `sensor.noaa_ilm_weather_visibility` |
| NOAA {OFFICE} Space | `NOAA {OFFICE} Space` | `sensor.noaa_ilm_space_planetary_k_index` |
| NOAA {OFFICE} Surf | `NOAA {OFFICE} Surf` | `sensor.noaa_ilm_surf_rip_current_risk` |
| NOAA {ZONE} Marine | `NOAA {ZONE} Marine` (marine zone, not office) | `sensor.noaa_lmz741_marine_forecast` |

**Examples:**
- `sensor.noaa_ilm_weather_temperature` — Temperature for Wilmington (ILM office)
- `binary_sensor.noaa_ilm_surf_unsafe_to_swim` — Rip current safety for Wilmington
- `sensor.noaa_hurricane_activity` — Global hurricane activity (NOAA Hurricane device)
- `image.noaa_hurricane_outlook_image` — Atlantic hurricane outlook image (NOAA Hurricane device)
- `image.noaa_hurricane_pacific_outlook_image` — East Pacific hurricane outlook image (NOAA Hurricane device)
- `image.noaa_ilm_weather_radar_base_reflectivity` — Radar base reflectivity for Wilmington (ILM)
- `image.noaa_ilm_weather_radar_loop` — Radar loop for Wilmington (ILM)

## Exceptions to the pattern

These six entity IDs do **not** contain an office code, because they live on the shared,
office-independent `NOAA Hurricane` device. When you copy an example and swap the office code,
skip these — substituting into them produces an entity that does not exist:

| Entity ID | Why |
|---|---|
| `sensor.noaa_hurricane_alerts` | Global NHC data, on the shared `NOAA Hurricane` device |
| `sensor.noaa_hurricane_activity` | Global NHC data, on the shared `NOAA Hurricane` device |
| `image.noaa_hurricane_outlook_image` | Global NHC data, on the shared `NOAA Hurricane` device |
| `image.noaa_hurricane_pacific_outlook_image` | Global NHC data, on the shared `NOAA Hurricane` device |
| `image.noaa_hurricane_goes_air_mass` | Global GOES imagery, on the shared `NOAA Hurricane` device |
| `image.noaa_hurricane_goes_geocolor` | Global GOES imagery, on the shared `NOAA Hurricane` device |

The marine entities use the marine zone where the others use the office:
`sensor.noaa_{zone}_marine_period`, `sensor.noaa_{zone}_marine_forecast` and
`sensor.noaa_{zone}_marine_hazard`, e.g. `sensor.noaa_lmz741_marine_forecast` for `LMZ741`.

Two further IDs are easy to get wrong even though they do follow the rule:

- `sensor.noaa_{office}_surf_surf_height` — the word "surf" appears **twice**: once for the
  `NOAA {OFFICE} Surf` device and once for the "Surf Height" entity name.
- `weather.noaa_{office}_weather` — a single `weather`, not a doubled `_weather_weather`; this
  entity does not set `has_entity_name`, so its ID comes from its own name alone.

## Office Code Usage
- **Office-specific entities**: Include the office code in the device name (e.g., `NOAA ILM Weather`)
- **Global hurricane entities**: Always under `NOAA Hurricane` — never duplicated per office
- **Replace office code**: If you change the NWS office under **Configure**, the entities are
  created again with the new office code in their IDs, and the previous office's entities are left
  behind as unavailable for you to delete under **Settings → Devices & services → Entities**.
  Update any automations and cards that use the old IDs.

## Entity Types
- **sensor.**: Numeric or text state (temperature, humidity, alert count, etc.)
- **binary_sensor.**: On/Off or True/False state (unsafe conditions, active alerts)
- **image.**: Visual data (radar, satellite, forecast images)
- **weather.**: The weather entity, for the Weather Forecast card and `weather.get_forecasts`

## Best Practices

1. **Use Device Views**: Access entities by device (Settings → Devices & services → NOAA It All) for organized browsing
2. **Create Groups**: Use Home Assistant groups to combine related entities across device boundaries (see [Grouping entities across devices](devices.md#grouping-entities-across-devices))
3. **Label Your Location**: In automations, use friendly names in messages (e.g., "Wilmington" instead of "ILM")
4. **Check Availability**: Sensors return `unknown` or `None` when data is unavailable - use conditions to verify state
5. **Binary Sensors for Triggers**: Use binary sensors (`on`/`off`) for automation triggers instead of checking sensor values
6. **Access Attributes**: Many sensors include detailed information in attributes (e.g., full alert text, forecast periods)

## Customizing Entity Properties

The easiest way to rename an entity or change its icon is in its settings: click the entity, then
the ⚙️ icon. To do it in YAML instead, add `customize` to `configuration.yaml` and restart:

```yaml
# configuration.yaml
homeassistant:
  customize:
    sensor.noaa_ilm_weather_temperature:
      friendly_name: "Wilmington Temperature"
      icon: mdi:thermometer
    binary_sensor.noaa_ilm_surf_unsafe_to_swim:
      friendly_name: "Beach Safety"
      icon: mdi:swim
    sensor.noaa_ilm_space_planetary_k_index:
      friendly_name: "Geomagnetic Activity"
      icon: mdi:earth
```

## Quick Reference: Common Entity Patterns

| Data Type | Entity Pattern | Example |
|-----------|---------------|---------|
| Weather Observation | `sensor.noaa_{office}_weather_{metric}` | `sensor.noaa_ilm_weather_temperature` |
| Weather Alert Binary | `binary_sensor.noaa_{office}_weather_{alert_type}_alert` | `binary_sensor.noaa_ilm_weather_severe_weather_alert` |
| Surf Conditions | `sensor.noaa_{office}_surf_{metric}` | `sensor.noaa_ilm_surf_rip_current_risk` |
| Surf Binary | `binary_sensor.noaa_{office}_surf_{name}` | `binary_sensor.noaa_ilm_surf_unsafe_to_swim` |
| Space Weather | `sensor.noaa_{office}_space_{metric}` | `sensor.noaa_ilm_space_aurora_next_time` |
| Meteor Showers | `sensor.noaa_{office}_space_{metric}` | `sensor.noaa_ilm_space_meteor_viewing_score` |
| Meteor Shower Binary | `binary_sensor.noaa_{office}_space_meteor_shower_active` | `binary_sensor.noaa_ilm_space_meteor_shower_active` |
| Eclipses | `sensor.noaa_{office}_space_eclipse_{metric}` | `sensor.noaa_ilm_space_eclipse_coverage` |
| Eclipse Timing | `sensor.noaa_{office}_space_next_eclipse_time` | `sensor.noaa_ilm_space_next_eclipse_time` |
| Eclipse Binary | `binary_sensor.noaa_{office}_space_eclipse_{name}` | `binary_sensor.noaa_ilm_space_eclipse_visible_now` |
| Forecast / Discussion | `sensor.noaa_{office}_weather_{name}` | `sensor.noaa_ilm_weather_extended_forecast` |
| Weather Entity | `weather.noaa_{office}_weather` | `weather.noaa_ilm_weather` |
| Hurricane (global) | `sensor.noaa_hurricane_{metric}` | `sensor.noaa_hurricane_activity` |
| Hurricane Images (global) | `image.noaa_hurricane_{name}` | `image.noaa_hurricane_outlook_image` |
| Space Images | `image.noaa_{office}_space_{name}` | `image.noaa_ilm_space_aurora_forecast_image` |
| Radar Image | `image.noaa_{office}_weather_radar_{name}` | `image.noaa_ilm_weather_radar_base_reflectivity` |
| Marine Forecast | `sensor.noaa_{zone}_marine_{name}` | `sensor.noaa_lmz741_marine_forecast` |

## Migration: Old Entity IDs

If you are upgrading from a previous version, the following image entity IDs have changed:

| Old Entity ID | New Entity ID |
|---------------|---------------|
| `image.noaa_weather_hurricane_outlook_image` | `image.noaa_hurricane_outlook_image` |
| `image.noaa_weather_noaa_satellite_goes_air_mass` | `image.noaa_hurricane_goes_air_mass` |
| `image.noaa_weather_noaa_satellite_goes_geocolor` | `image.noaa_hurricane_goes_geocolor` |
| `image.noaa_weather_radar_base_reflectivity_{office}` | `image.noaa_{office}_weather_radar_base_reflectivity` |

The underlying unique IDs for GOES Air Mass and GOES Geocolor have also changed, so Home Assistant will register them as new entities. To clean up stale entries, go to **Settings → Devices & services → Entities**, filter by "unavailable", and remove the old image entities. Update any automations or dashboard cards that reference the old entity IDs.

### Binary sensor names (0.5.0)

Before 0.5.0 the binary sensors set a full name that already contained `NOAA {office}`, which Home Assistant then prefixed with the device name again. The result was a doubled entity ID and friendly name:

| Before 0.5.0 | From 0.5.0 |
|---|---|
| `binary_sensor.noaa_{office}_surf_noaa_{office}_unsafe_to_swim` | `binary_sensor.noaa_{office}_surf_unsafe_to_swim` |
| `binary_sensor.noaa_{office}_weather_noaa_{office}_severe_weather_alert` | `binary_sensor.noaa_{office}_weather_severe_weather_alert` |
| `binary_sensor.noaa_{office}_weather_noaa_{office}_flood_winter_alert` | `binary_sensor.noaa_{office}_weather_flood_winter_alert` |
| `binary_sensor.noaa_{office}_weather_noaa_{office}_heat_air_quality_alert` | `binary_sensor.noaa_{office}_weather_heat_air_quality_alert` |
| `binary_sensor.noaa_{office}_weather_noaa_{office}_active_alerts` | `binary_sensor.noaa_{office}_weather_active_alerts` |

**Existing installations keep their current entity IDs and nothing breaks.** The `unique_id` values are unchanged, so Home Assistant's entity registry holds on to whatever ID it already assigned — your automations and dashboard cards keep working untouched. What does change is the displayed friendly name, which loses the stutter (for example "NOAA ILM Surf NOAA ILM Unsafe to Swim" becomes "NOAA ILM Surf Unsafe to Swim").

Only fresh installations get the shorter entity IDs. If you would like an existing installation to match, rename the entities yourself in **Settings → Devices & services → Entities**, then update any automations that reference the old IDs.
