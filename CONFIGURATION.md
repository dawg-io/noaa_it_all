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

### Config Flow (Recommended)
The Config Flow method provides location-specific features including weather alerts, surf conditions, and aurora predictions.

**Steps:**
1. Navigate to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "NOAA It All"
3. Select your NWS Forecast Office (e.g., SGX for San Diego)
4. Enter your **Latitude** (e.g., 32.7157)
5. Enter your **Longitude** (e.g., -117.1611)
6. Click Submit

**Example Configuration Data:**
```yaml
# This is stored internally by Home Assistant
office_code: "SGX"
latitude: 32.7157
longitude: -117.1611
```

### Legacy YAML Configuration

> **Removed.** YAML configuration is no longer supported and creates **no entities**. If
> `noaa_it_all:` is present in `configuration.yaml`, the integration logs an error and sets nothing
> up. Remove the block and add the integration through **Settings → Devices & Services → Add
> Integration → NOAA It All**.

## Options

**Settings** → **Devices & Services** → **NOAA It All** → **Configure**. The flow walks through
latitude and longitude, then the forecast office, then the radar loop. Saving reloads the
integration so the new values take effect immediately.

| Option | Default | Notes |
|---|---|---|
| Latitude / Longitude | Home Assistant's Home location | Used for alerts, surf and aurora |
| NWS Forecast Office | Nearest office to those coordinates | Determines the radar site |
| Hours of radar history | `24` | Length of the Radar Loop animation, `0`–`24` |

### Hours of radar history

NOAA's own radar animation is fixed at about 50 minutes, and only its ten most recent frames exist
on the server — there is no longer version to download. To show more than that, the integration
saves one frame each time it refreshes and assembles the animation itself.

```yaml
# Stored in the config entry's options
office_code: "SGX"
latitude: 32.7157
longitude: -117.1611
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
code. See [Exceptions to the pattern](#exceptions-to-the-pattern).

**Every example in this guide uses the `ILM` office.** To adapt one, replace `ilm` with your own
office code in lower case, leaving the exceptions below untouched.

**Examples:**
- `sensor.noaa_ilm_weather_temperature` - Temperature for the Wilmington (ILM) office
- `binary_sensor.noaa_ilm_surf_unsafe_to_swim` - Rip current safety sensor
- `sensor.noaa_ilm_space_planetary_k_index` - Space weather sensor
- `image.noaa_ilm_weather_radar_base_reflectivity` - Radar image for the office

### Exceptions to the pattern

These five entity IDs contain **no office code** — they live on the shared, office-independent
`NOAA Hurricane` device. Do not substitute into them:

| Entity ID | Why |
|---|---|
| `sensor.noaa_hurricane_alerts` | Global NHC data on the shared `NOAA Hurricane` device |
| `sensor.noaa_hurricane_activity` | Global NHC data on the shared `NOAA Hurricane` device |
| `image.noaa_hurricane_outlook_image` | Global NHC imagery |
| `image.noaa_hurricane_goes_air_mass` | Global GOES imagery |
| `image.noaa_hurricane_goes_geocolor` | Global GOES imagery |

And two that follow the rule but read oddly:

- `sensor.noaa_{office}_surf_surf_height` — "surf" twice: device group, then entity name.
- `weather.noaa_{office}_weather` — a single `weather`, not `_weather_weather`.

### Customizing Entity Properties

You can customize friendly names, icons, and other properties in `customize.yaml`:

```yaml
# customize.yaml
homeassistant:
  customize:
    sensor.noaa_ilm_weather_temperature:
      friendly_name: "San Diego Temperature"
      icon: mdi:thermometer
    
    binary_sensor.noaa_ilm_surf_unsafe_to_swim:
      friendly_name: "Beach Safety"
      icon: mdi:swim
      device_class: safety
    
    sensor.noaa_ilm_space_planetary_k_index:
      friendly_name: "Geomagnetic Activity"
      icon: mdi:earth
```

## Device Grouping

NOAA It All automatically organizes entities into four device groups:

### 1. NOAA Space (Space Weather & Meteor Showers)
Entities that monitor space weather conditions worldwide, plus the meteor shower forecast for
your configured location.

**Entities in this group:**
- `sensor.noaa_ilm_space_planetary_k_index`
- `sensor.noaa_ilm_space_geomagnetic_storm`
- `sensor.noaa_{office}_space_aurora_next_time`
- `sensor.noaa_{office}_space_aurora_duration`
- `sensor.noaa_{office}_space_aurora_visibility_probability`
- `sensor.noaa_{office}_space_solar_radiation_storm_alerts`
- `sensor.noaa_{office}_space_meteor_shower_activity`
- `sensor.noaa_{office}_space_next_meteor_shower`
- `sensor.noaa_{office}_space_meteor_viewing_score`
- `binary_sensor.noaa_{office}_space_meteor_shower_active`
- `image.noaa_ilm_space_geoelectric_field_image`
- `image.noaa_ilm_space_aurora_forecast_image`

> Meteor shower entities require latitude/longitude (Config Flow setup) because the radiant's
> altitude — the single biggest factor in how many meteors you see — depends on where you are.
> They are computed locally from a bundled catalog and make no network requests.

### 2. NOAA Weather (Global & Location Weather)
Entities for hurricane tracking, forecasts, and weather observations.

**Entities in this group:**
- `sensor.noaa_hurricane_alerts`
- `sensor.noaa_hurricane_activity`
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
- `sensor.noaa_{office}_weather_radar_timestamp`
- `sensor.noaa_{office}_weather_forecast_discussion`
- `sensor.noaa_ilm_weather_active_nws_alerts`
- `image.noaa_hurricane_outlook_image`
- `image.noaa_hurricane_goes_geocolor`

### 3. NOAA Surf (Surf & Water Conditions)
Entities for beach safety and surf conditions.

**Entities in this group:**
- `sensor.noaa_{office}_surf_rip_current_risk`
- `sensor.noaa_{office}_surf_height`
- `sensor.noaa_{office}_surf_water_temperature`
- `binary_sensor.noaa_{office}_surf_unsafe_to_swim`

### 4. NOAA Hurricane (Global Tropical Data)
A single shared device for National Hurricane Center data. These entities are created once,
regardless of how many offices you configure, and carry **no office code**.

**Entities in this group:**
- `sensor.noaa_hurricane_alerts`
- `sensor.noaa_hurricane_activity`
- `image.noaa_hurricane_outlook_image`
- `image.noaa_hurricane_goes_air_mass`
- `image.noaa_hurricane_goes_geocolor`

### 5. Location-specific alert binary sensors
These live on the **NOAA {OFFICE} Weather** device alongside the observation sensors.

**Entities in this group:**
- `binary_sensor.noaa_{office}_weather_severe_weather_alert`
- `binary_sensor.noaa_{office}_weather_flood_winter_alert`
- `binary_sensor.noaa_{office}_weather_heat_air_quality_alert`
- `binary_sensor.noaa_{office}_weather_active_alerts`

### Creating Custom Groups

You can create additional groups combining entities from different devices:

```yaml
# groups.yaml
noaa_safety_alerts:
  name: "NOAA Safety Alerts"
  entities:
    - binary_sensor.noaa_ilm_weather_severe_weather_alert
    - binary_sensor.noaa_ilm_weather_flood_winter_alert
    - binary_sensor.noaa_ilm_weather_heat_air_quality_alert
    - binary_sensor.noaa_ilm_surf_unsafe_to_swim

noaa_current_conditions:
  name: "Current Weather"
  entities:
    - sensor.noaa_ilm_weather_temperature
    - sensor.noaa_ilm_weather_humidity
    - sensor.noaa_ilm_weather_wind_speed
    - sensor.noaa_ilm_weather_barometric_pressure

noaa_space_weather:
  name: "Space Weather"
  entities:
    - sensor.noaa_ilm_space_planetary_k_index
    - sensor.noaa_ilm_space_geomagnetic_storm
    - sensor.noaa_ilm_space_aurora_visibility_probability
```

## Dashboard Card Examples

### Basic Weather Card
```yaml
type: entities
title: "Current Weather - San Diego"
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
entities:
  - entity: binary_sensor.noaa_ilm_surf_unsafe_to_swim
    name: "Safe to Swim"
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
      - sensor.noaa_ilm_space_planetary_k_index
      - sensor.noaa_ilm_space_geomagnetic_storm
      - sensor.noaa_ilm_space_aurora_visibility_probability
  
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
  - binary_sensor.noaa_ilm_space_meteor_shower_active
  - sensor.noaa_ilm_space_meteor_shower_activity
  - sensor.noaa_ilm_space_meteor_viewing_score
  - type: attribute
    entity: sensor.noaa_ilm_space_meteor_viewing_score
    attribute: expected_per_hour
    name: "Expected Meteors/Hour"
  - type: attribute
    entity: sensor.noaa_ilm_space_meteor_viewing_score
    attribute: best_window_start
    name: "Best Viewing From"
  - sensor.noaa_ilm_space_next_meteor_shower
```

## Automation Examples

### Binary Sensor Alert Automation
```yaml
automation:
  - alias: "Unsafe Swimming Conditions"
    description: "Alert when rip currents make swimming dangerous"
    trigger:
      - platform: state
        entity_id: binary_sensor.noaa_ilm_surf_unsafe_to_swim
        to: 'on'
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Beach Safety Alert"
          message: "High rip current risk - swimming not recommended"
```

### Multi-Condition Weather Automation
```yaml
automation:
  - alias: "Perfect Beach Day"
    description: "Notify when conditions are ideal for beach activities"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.noaa_ilm_surf_unsafe_to_swim
        state: 'off'
      - condition: numeric_state
        entity_id: sensor.noaa_ilm_weather_temperature
        above: 75
      - condition: numeric_state
        entity_id: sensor.noaa_ilm_weather_wind_speed
        below: 15
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "Perfect Beach Day!"
          message: >
            Temperature: {{ states('sensor.noaa_ilm_weather_temperature') }}°F
            Surf: {{ states('sensor.noaa_ilm_surf_surf_height') }} ft
            Water: {{ states('sensor.noaa_ilm_surf_water_temperature') }}°F
```

### Severe Weather Response
```yaml
automation:
  - alias: "Severe Weather Actions"
    description: "Automated responses to severe weather"
    trigger:
      - platform: state
        entity_id: binary_sensor.noaa_ilm_weather_severe_weather_alert
        to: 'on'
    action:
      # Close blinds
      - service: cover.close_cover
        target:
          entity_id: all
      # Turn on emergency lights
      - service: light.turn_on
        target:
          entity_id: light.emergency_lights
        data:
          brightness: 255
      # Send notification
      - service: notify.family
        data:
          title: "Severe Weather Alert"
          message: "Tornado or severe thunderstorm warning active!"
          data:
            priority: high
```

## Script Examples

### Weather Report Script
```yaml
script:
  weather_report:
    alias: "Get Weather Report"
    sequence:
      - service: notify.mobile_app_your_phone
        data:
          title: "Weather Report"
          message: >
            Temperature: {{ states('sensor.noaa_ilm_weather_temperature') }}°F
            Conditions: {{ states('sensor.noaa_ilm_weather_sky_conditions') }}
            Wind: {{ states('sensor.noaa_ilm_weather_wind_speed') }} mph
            Humidity: {{ states('sensor.noaa_ilm_weather_humidity') }}%
            {% if is_state('binary_sensor.noaa_ilm_weather_active_alerts', 'on') %}
            ⚠️ Weather alerts active!
            {% endif %}
```

### Space Weather Check Script
```yaml
script:
  space_weather_check:
    alias: "Check Space Weather"
    sequence:
      - service: tts.google_translate_say
        target:
          entity_id: media_player.living_room
        data:
          message: >
            Space weather report.
            K P index is {{ states('sensor.noaa_ilm_space_planetary_k_index') }}.
            Geomagnetic activity: {{ states('sensor.noaa_ilm_space_geomagnetic_storm') }}.
            {% if states('sensor.noaa_ilm_space_aurora_visibility_probability') | int > 50 %}
            Aurora visibility probability is high at {{ states('sensor.noaa_ilm_space_aurora_visibility_probability') }} percent.
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
- Verify Config Flow setup includes latitude and longitude
- Check that your NWS office code is valid
- Restart Home Assistant after adding the integration

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
