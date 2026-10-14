# NOAA It All - Configuration Guide

This guide provides detailed configuration examples for NOAA It All, including entity setup, device grouping, dashboard cards, and automation patterns.

## Table of Contents
1. [Installation Methods](#installation-methods)
2. [Options](#options)
3. [Entity Configuration](#entity-configuration)
4. [Device Grouping](#device-grouping)
5. [Dashboard Card Examples](#dashboard-card-examples)
6. [Automation Examples](#automation-examples)
7. [Script Examples](#script-examples)

## Installation Methods

### Config Flow
Setup is done in the UI, and the integration has five kinds of entry: weather for a location, surf
forecast for a coast, nearshore marine forecast for a Great Lakes zone, Space (space weather,
aurora, meteor showers and eclipses) and hurricanes and satellite images. The
[README](README.md#configuration) walks through each with screenshots.

**Steps for a location:**
1. Navigate to **Settings** → **Devices & services** → **Add integration**
2. Search for "NOAA It All" and choose **Weather for a location**
3. Enter your **Latitude** and **Longitude** (e.g., 34.2104, -77.8868), pre-filled from your Home zone
4. Select your NWS Forecast Office. The office NWS names for your location is pre-selected (e.g., ILM for Wilmington)
5. Choose a surf forecast office, or **No surf data**
6. Choose Space for the office, or **No space data**
7. Click Submit, then **Skip and finish** or assign the device to an area

The surf office becomes its own `NOAA Surf` entry, and Space a `NOAA Space` entry for the forecast
office, at this location. Each office has one Space entry, which other locations in it share. Add
more beaches, marine zones, Space for another office, or the hurricane entry later with **Add
entry** on the NOAA It All page.

**Example Configuration Data:**
```yaml
# A weather entry, as stored internally by Home Assistant
entry_type: "weather"
office_code: "ILM"
radar_site: "KLTX"
latitude: 34.2104
longitude: -77.8868

# A Space entry
entry_type: "space"
office_code: "ILM"
latitude: 34.2104
longitude: -77.8868
```

### Legacy YAML Configuration

> **Removed.** YAML configuration is no longer supported and creates **no entities**. If
> `noaa_it_all:` is present in `configuration.yaml`, the integration logs an error and sets nothing
> up. Remove the block and add the integration through **Settings → Devices & services → Add
> Integration → NOAA It All**.

## Options

**Settings** → **Devices & services** → **NOAA It All** → **Configure** (the gear on a
`NOAA Weather` entry). The flow walks through latitude and longitude, then the forecast office,
then the radar loop. Saving reloads the entry so the new values take effect immediately. Surf,
marine, Space and hurricane entries have no options: add or delete them instead. A Space entry
doesn't move with the weather entry.

| Option | Default | Notes |
|---|---|---|
| Latitude / Longitude | Home Assistant's Home location | Used for observations, forecasts, alerts and cloud cover |
| NWS Forecast Office | The office NWS names for those coordinates | Determines the entity IDs, radar site and forecast discussion |
| Hours of radar history | `24` | Length of the Radar Loop animation, `0`–`24` |

### Hours of radar history

NOAA's own radar animation is fixed at about 50 minutes, and only its ten most recent frames exist
on the server — there is no longer version to download. To show more than that, the integration
saves one frame each time it refreshes and assembles the animation itself.

```yaml
# Stored in the config entry's options
office_code: "ILM"
latitude: 34.2104
longitude: -77.8868
radar_loop_hours: 24
```

- **`0`** — serve NOAA's own ~50 minute loop unchanged and store nothing on disk. This is how the
  integration behaved before version 0.6.0.
- **`1`–`24`** — build the loop locally over that window.

What to expect when it is on:

- **The loop fills in over time.** It starts at whatever history has been collected and reaches
  full length after that many hours of uptime. Until there are at least six frames, the card falls
  back to NOAA's own loop rather than showing a near-still image.
- **Frames persist across restarts**, under `<config>/noaa_it_all/radar_frames/<RADAR_SITE>/`, one
  small GIF per scan. Expect a few megabytes per radar site. Frames outside the window are deleted
  on every refresh. The directory is removed when you delete the integration, when you switch the
  entry to a different forecast office, or when you set this option back to `0` — unless another
  configured office is still building a loop from the same radar site.
- **Frame spacing follows the window.** The animation is capped at 72 frames and plays through in
  about ten seconds, so a 24-hour loop steps every 20 minutes while a 6-hour loop keeps roughly one
  frame per radar scan.
- **The file is larger than NOAA's**, and every open dashboard re-downloads it whenever it changes.
  On a wall tablet on a mobile connection, prefer a shorter window.

While the buffer is still filling, each refresh makes two requests instead of one — the latest
frame, plus NOAA's loop to display in the meantime. That stops once enough frames have been
collected.

The entity exposes what it is actually doing as attributes:

| Attribute | Meaning |
|---|---|
| `loop_mode` | `local` when showing an animation built here, `upstream` when showing NOAA's |
| `loop_hours` | The configured window |
| `frame_count` | Frames in the animation currently being served |
| `window_start` / `window_end` | Times of its oldest and newest frames |

```yaml
# Alert when the radar loop quietly falls back to NOAA's short animation
template:
  - binary_sensor:
      - name: "Radar loop degraded"
        state: >
          {{ state_attr('image.noaa_ilm_weather_radar_loop', 'loop_mode') == 'upstream' }}
```

## Entity Configuration

### Understanding Entity IDs
All NOAA It All entities follow consistent naming patterns:

**Pattern:**
```
{entity_type}.noaa_{office}_{weather|surf|space}_{sensor_name}
```

The middle segment is the **device group**, and it is always present on office-scoped entities.
Globally-scoped entities use `{entity_type}.noaa_hurricane_{sensor_name}` instead, with no office
code, and marine entities use the marine zone: `sensor.noaa_{zone}_marine_{sensor_name}`. See
[Exceptions to the pattern](#exceptions-to-the-pattern).

**Every example in this guide uses the `ILM` office.** To adapt one, replace `ilm` with your own
office code in lower case, leaving the exceptions below untouched.

**Examples:**
- `sensor.noaa_ilm_weather_temperature` - Temperature for the Wilmington (ILM) office
- `binary_sensor.noaa_ilm_surf_unsafe_to_swim` - Rip current safety sensor
- `sensor.noaa_ilm_space_planetary_k_index` - Space weather sensor
- `image.noaa_ilm_weather_radar_base_reflectivity` - Radar image for the office

### Exceptions to the pattern

These six entity IDs contain **no office code** — they live on the shared, office-independent
`NOAA Hurricane` device. Do not substitute into them:

| Entity ID | Why |
|---|---|
| `sensor.noaa_hurricane_alerts` | Global NHC data on the shared `NOAA Hurricane` device |
| `sensor.noaa_hurricane_activity` | Global NHC data on the shared `NOAA Hurricane` device |
| `image.noaa_hurricane_outlook_image` | Global NHC imagery (Atlantic) |
| `image.noaa_hurricane_pacific_outlook_image` | Global NHC imagery (East Pacific) |
| `image.noaa_hurricane_goes_air_mass` | Global GOES imagery |
| `image.noaa_hurricane_goes_geocolor` | Global GOES imagery |

The two marine entities use the zone, not an office: `sensor.noaa_{zone}_marine_period` and
`sensor.noaa_{zone}_marine_forecast` (e.g. `sensor.noaa_lmz741_marine_forecast`).

And two that follow the rule but read oddly:

- `sensor.noaa_{office}_surf_surf_height` — "surf" twice: device group, then entity name.
- `weather.noaa_{office}_weather` — a single `weather`, not `_weather_weather`.

### Customizing Entity Properties

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

## Device Grouping

NOAA It All organizes entities into five kinds of device, one for each kind of entry: `NOAA
Weather`, `NOAA Space`, `NOAA Surf`, `NOAA Marine` and `NOAA Hurricane`.

### 1. NOAA {OFFICE} Weather (Observations, Forecasts, Alerts & Radar)
Entities for your configured location, in the `NOAA Weather` entry.

**Entities in this group:**
- `weather.noaa_{office}_weather`
- `sensor.noaa_{office}_weather_temperature`
- `sensor.noaa_{office}_weather_humidity`
- `sensor.noaa_{office}_weather_wind_speed`
- `sensor.noaa_{office}_weather_wind_direction`
- `sensor.noaa_{office}_weather_barometric_pressure`
- `sensor.noaa_{office}_weather_dewpoint`
- `sensor.noaa_{office}_weather_visibility`
- `sensor.noaa_{office}_weather_sky_conditions`
- `sensor.noaa_{office}_weather_feels_like`
- `sensor.noaa_{office}_weather_cloud_cover`
- `sensor.noaa_{office}_weather_extended_forecast`
- `sensor.noaa_{office}_weather_hourly_forecast`
- `sensor.noaa_{office}_weather_forecast_discussion`
- `sensor.noaa_{office}_weather_active_nws_alerts`
- `sensor.noaa_{office}_weather_radar_timestamp`
- `binary_sensor.noaa_{office}_weather_severe_weather_alert`
- `binary_sensor.noaa_{office}_weather_flood_winter_alert`
- `binary_sensor.noaa_{office}_weather_heat_air_quality_alert`
- `binary_sensor.noaa_{office}_weather_active_alerts`
- `image.noaa_{office}_weather_radar_base_reflectivity`
- `image.noaa_{office}_weather_radar_loop`

### 2. NOAA {OFFICE} Space (Space Weather, Meteor Showers & Eclipses)
Entities that monitor space weather conditions worldwide, plus the aurora, meteor shower and
eclipse forecasts for the entry's location, in the office's `NOAA Space` entry. With more than one
Space entry, the space weather entities show the same values in each: the Kp index and its
rating, the geomagnetic storm and its interpretation, the solar radiation storm alerts and the two
images.

**Entities in this group:**
- `sensor.noaa_{office}_space_planetary_k_index`
- `sensor.noaa_{office}_space_planetary_k_index_rating`
- `sensor.noaa_{office}_space_geomagnetic_storm`
- `sensor.noaa_{office}_space_geomagnetic_storm_interpretation`
- `sensor.noaa_{office}_space_aurora_next_time`
- `sensor.noaa_{office}_space_aurora_duration`
- `sensor.noaa_{office}_space_aurora_visibility_probability`
- `sensor.noaa_{office}_space_solar_radiation_storm_alerts`
- `sensor.noaa_{office}_space_meteor_shower_activity`
- `sensor.noaa_{office}_space_next_meteor_shower`
- `sensor.noaa_{office}_space_meteor_viewing_score`
- `binary_sensor.noaa_{office}_space_meteor_shower_active`
- `sensor.noaa_{office}_space_next_eclipse`
- `sensor.noaa_{office}_space_next_eclipse_time`
- `sensor.noaa_{office}_space_eclipse_coverage`
- `sensor.noaa_{office}_space_eclipse_viewing_score`
- `binary_sensor.noaa_{office}_space_eclipse_visible_now`
- `binary_sensor.noaa_{office}_space_eclipse_coming_up`
- `image.noaa_{office}_space_geoelectric_field_image`
- `image.noaa_{office}_space_aurora_forecast_image`

> Meteor shower entities require latitude/longitude because the radiant's
> altitude — the single biggest factor in how many meteors you see — depends on where you are.
> They are computed locally from a bundled catalog and make no network requests.

> Eclipse entities require latitude/longitude for a stronger reason still: a solar eclipse is a
> shadow a couple of hundred kilometres wide, so two towns an hour apart can get totality and
> 60%. They are computed locally from bundled NASA Besselian elements covering 2025–2075 and
> make no network requests.

> ⚠️ **Never look at a partially eclipsed Sun without ISO 12312-2 eclipse glasses.** Only
> totality is safe unfiltered; an annular eclipse never is. Every solar eclipse entity carries
> `eye_protection_required`, `safe_without_filter` and an `eye_safety` string.

### 3. NOAA {OFFICE} Surf (Surf & Water Conditions)
Entities for beach safety and surf conditions, in the `NOAA Surf` entry for one coastal office.
Water Temperature needs a tide station and Surf Height a buoy, so a new surf entry only gets the
ones its office has.

**Entities in this group:**
- `sensor.noaa_{office}_surf_rip_current_risk`
- `binary_sensor.noaa_{office}_surf_unsafe_to_swim`
- `sensor.noaa_{office}_surf_water_temperature`
- `sensor.noaa_{office}_surf_surf_height`

### 4. NOAA {ZONE} Marine (Nearshore Marine Forecast)
The nearshore marine forecast for one Great Lakes marine zone, in its `NOAA Marine` entry.

**Entities in this group:**
- `sensor.noaa_{zone}_marine_period`
- `sensor.noaa_{zone}_marine_forecast`

### 5. NOAA Hurricane (Global Tropical Data)
A single shared device for National Hurricane Center data and GOES satellite images, in the
`NOAA Hurricane` entry. These entities are created once, regardless of how many locations you
configure, and carry **no office code**.

**Entities in this group:**
- `sensor.noaa_hurricane_alerts`
- `sensor.noaa_hurricane_activity`
- `image.noaa_hurricane_outlook_image`
- `image.noaa_hurricane_pacific_outlook_image`
- `image.noaa_hurricane_goes_air_mass`
- `image.noaa_hurricane_goes_geocolor`

### Creating Custom Groups

A binary sensor group gives you one entity that's on while any of its members is: a single
"something's unsafe" switch for automations and dashboards. Create it under **Settings → Devices &
services → Helpers → Create helper → Group → Binary sensor group**, or in YAML:

```yaml
# configuration.yaml
binary_sensor:
  - platform: group
    name: "NOAA Safety Alerts"
    device_class: safety
    entities:
      - binary_sensor.noaa_ilm_weather_severe_weather_alert
      - binary_sensor.noaa_ilm_weather_flood_winter_alert
      - binary_sensor.noaa_ilm_weather_heat_air_quality_alert
      - binary_sensor.noaa_ilm_surf_unsafe_to_swim
```

This creates `binary_sensor.noaa_safety_alerts`. To group sensors for display, put them on one
dashboard card instead; see below.

## Dashboard Card Examples

Each example is a card for **Edit dashboard → Add card → Manual**. The [README](README.md#dashboard-card-examples)
has more, with screenshots.

### Basic Weather Card
```yaml
type: entities
title: "Current Weather - Wilmington"
show_header_toggle: false
entities:
  - entity: sensor.noaa_ilm_weather_temperature
    name: "Temperature"
  - entity: sensor.noaa_ilm_weather_feels_like
    name: "Feels Like"
  - entity: sensor.noaa_ilm_weather_humidity
    name: "Humidity"
  - entity: sensor.noaa_ilm_weather_wind_speed
    name: "Wind Speed"
  - entity: sensor.noaa_ilm_weather_sky_conditions
    name: "Conditions"
```

### Alert Monitoring Card
```yaml
type: entities
title: "Weather Alerts"
state_color: true
entities:
  - entity: binary_sensor.noaa_ilm_weather_severe_weather_alert
    name: "Severe Weather"
  - entity: binary_sensor.noaa_ilm_weather_flood_winter_alert
    name: "Flood/Winter"
  - entity: binary_sensor.noaa_ilm_weather_heat_air_quality_alert
    name: "Heat/Air Quality"
  - entity: sensor.noaa_ilm_weather_active_nws_alerts
    name: "Alert Details"
```

### Beach Safety Card
```yaml
type: entities
title: "Beach Conditions"
state_color: true
entities:
  - entity: binary_sensor.noaa_ilm_surf_unsafe_to_swim
    name: "Swimming"
  - entity: sensor.noaa_ilm_surf_rip_current_risk
    name: "Rip Current Risk"
  - entity: sensor.noaa_ilm_surf_surf_height
    name: "Wave Height"
  - entity: sensor.noaa_ilm_surf_water_temperature
    name: "Water Temperature"
```

### Space Weather Card
```yaml
type: vertical-stack
cards:
  - type: entities
    title: "Space Weather"
    entities:
      - entity: sensor.noaa_ilm_space_planetary_k_index
        name: "Kp Index"
      - entity: sensor.noaa_ilm_space_geomagnetic_storm_interpretation
        name: "Geomagnetic Storm"
      - entity: sensor.noaa_ilm_space_aurora_visibility_probability
        name: "Aurora Probability"
  - type: picture-entity
    entity: image.noaa_ilm_space_aurora_forecast_image
    name: "Aurora Forecast"
    show_state: false
```

### Meteor Shower Card
```yaml
type: entities
title: "Meteor Showers"
entities:
  - entity: binary_sensor.noaa_ilm_space_meteor_shower_active
    name: "Worth Going Outside"
  - entity: sensor.noaa_ilm_space_meteor_shower_activity
    name: "Active Now"
  - entity: sensor.noaa_ilm_space_meteor_viewing_score
    name: "Viewing Score"
  - type: attribute
    entity: sensor.noaa_ilm_space_meteor_viewing_score
    attribute: expected_per_hour
    name: "Expected Meteors/Hour"
  - type: attribute
    entity: sensor.noaa_ilm_space_meteor_viewing_score
    attribute: best_window_start
    name: "Best Viewing From"
  - entity: sensor.noaa_ilm_space_next_meteor_shower
    name: "Next Shower"
```

### Eclipse Card
```yaml
type: entities
title: "Eclipses"
entities:
  - entity: binary_sensor.noaa_ilm_space_eclipse_visible_now
    name: "Go Outside Now"
  - entity: binary_sensor.noaa_ilm_space_eclipse_coming_up
    name: "Worth Planning For"
  - entity: sensor.noaa_ilm_space_next_eclipse
    name: "Next Eclipse"
  - entity: sensor.noaa_ilm_space_next_eclipse_time
    name: "Go Outside At"
  - entity: sensor.noaa_ilm_space_eclipse_coverage
    name: "Coverage"
  - entity: sensor.noaa_ilm_space_eclipse_viewing_score
    name: "Viewing Score"
  - type: attribute
    entity: sensor.noaa_ilm_space_eclipse_viewing_score
    attribute: rating
    name: "Conditions"
  - type: attribute
    entity: sensor.noaa_ilm_space_eclipse_viewing_score
    attribute: look_towards
    name: "Look Towards"
```

## Automation Examples

Each example uses Home Assistant's current automation syntax. Create an automation, open
**⋮ → Edit in YAML** and paste it in, or add it to `automations.yaml` as a list item. Replace the
notify action and the light and speaker entities with your own.

### Binary Sensor Alert Automation
```yaml
alias: "Unsafe Swimming Conditions"
description: "Alert when rip currents make swimming dangerous"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_surf_unsafe_to_swim
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Beach Safety Alert"
      message: "High rip current risk - swimming not recommended"
```

### Multi-Condition Weather Automation
```yaml
alias: "Perfect Beach Day"
description: "Notify when conditions are ideal for beach activities"
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.noaa_ilm_surf_unsafe_to_swim
    state: "off"
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_weather_temperature
    above: 75
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_weather_wind_speed
    below: 15
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "Perfect Beach Day!"
      message: >-
        Temperature {{ states('sensor.noaa_ilm_weather_temperature') }}°F,
        surf {{ states('sensor.noaa_ilm_surf_surf_height') }} ft,
        water {{ states('sensor.noaa_ilm_surf_water_temperature') }}°F.
```

### Severe Weather Response
```yaml
alias: "Severe Weather Actions"
description: "Automated responses to severe weather"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_weather_severe_weather_alert
    to: "on"
actions:
  # Close blinds
  - action: cover.close_cover
    target:
      entity_id: all
  # Turn on emergency lights
  - action: light.turn_on
    target:
      entity_id: light.emergency_lights
    data:
      brightness: 255
  # Send a notification naming the alert
  - action: notify.family
    data:
      title: "Severe Weather Alert"
      message: >-
        {{ (state_attr('binary_sensor.noaa_ilm_weather_severe_weather_alert', 'alerts') or [{}])[0].get('event', 'Severe weather alert') }}
        is active for your area!
      data:
        priority: high
```

## Script Examples

Each example is an entry for `scripts.yaml`. In the script editor, paste the part under the
script's name into **⋮ → Edit in YAML**.

### Weather Report Script
```yaml
weather_report:
  alias: "Get Weather Report"
  sequence:
    - action: notify.mobile_app_your_phone
      data:
        title: "Weather Report"
        message: >-
          Temperature: {{ states('sensor.noaa_ilm_weather_temperature') }}°F.
          Conditions: {{ states('sensor.noaa_ilm_weather_sky_conditions') }}.
          Wind: {{ states('sensor.noaa_ilm_weather_wind_speed') }} mph.
          Humidity: {{ states('sensor.noaa_ilm_weather_humidity') }}%.
          {% if is_state('binary_sensor.noaa_ilm_weather_active_alerts', 'on') %}⚠️ Weather alerts active!{% endif %}
```

### Space Weather Check Script
```yaml
space_weather_check:
  alias: "Check Space Weather"
  sequence:
    - action: tts.speak
      target:
        entity_id: tts.google_translate_en_com
      data:
        media_player_entity_id: media_player.living_room
        message: >-
          Space weather report. K P index is {{ states('sensor.noaa_ilm_space_planetary_k_index') }}.
          Geomagnetic storm level: {{ states('sensor.noaa_ilm_space_geomagnetic_storm_interpretation') }}.
          {% if states('sensor.noaa_ilm_space_aurora_visibility_probability') | int(0) > 50 %}
          Aurora visibility probability is high at
          {{ states('sensor.noaa_ilm_space_aurora_visibility_probability') }} percent.
          {% endif %}
```

## Best Practices

1. **Use Binary Sensors for Triggers**: Binary sensors provide clear on/off states perfect for automation triggers
2. **Check Entity Availability**: Use conditions to ensure data is available before acting on sensor states
3. **Group Related Entities**: Create groups for entities you commonly use together
4. **Customize Entity Names**: Use friendly names that make sense in your context
5. **Leverage Attributes**: Many sensors include additional data in attributes - explore with Developer Tools
6. **Test Automations**: Test weather alert automations with template sensors before relying on them
7. **Mobile Optimization**: Design dashboard cards that work well on mobile devices
8. **Use State History**: Review sensor history to understand patterns and optimize automation triggers

## Troubleshooting

### Entities Not Appearing
- Verify setup includes latitude and longitude
- Surf, space and hurricane entities are in their own `NOAA Surf`, `NOAA Space` and
  `NOAA Hurricane` entries; add them with **Add entry** if they're missing
- A new surf entry only gets Water Temperature and Surf Height if its office has a tide station or
  buoy (see the [README](README.md#nws-forecast-offices))

### Data Not Updating
- Check sensor attributes for error messages
- Verify internet connectivity
- NOAA APIs may have temporary outages

### Automation Not Triggering
- Verify entity IDs in automations match actual entities
- Check automation traces in Developer Tools
- Ensure conditions are not blocking the automation

## Additional Resources

- [Home Assistant Automation Documentation](https://www.home-assistant.io/docs/automation/)
- [Home Assistant Dashboard Cards](https://www.home-assistant.io/dashboards/)
- [NOAA Space Weather Prediction Center](https://www.swpc.noaa.gov/)
- [National Weather Service API](https://www.weather.gov/documentation/services-web-api)
