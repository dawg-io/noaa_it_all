# NOAA It All - Configuration Guide

This guide provides detailed configuration examples for NOAA It All, including entity setup, device grouping, dashboard cards, and automation patterns.

## Table of Contents
1. [Installation Methods](#installation-methods)
2. [Entity Configuration](#entity-configuration)
3. [Device Grouping](#device-grouping)
4. [Dashboard Card Examples](#dashboard-card-examples)
5. [Automation Examples](#automation-examples)
6. [Script Examples](#script-examples)

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
For basic sensors without location-specific data:

```yaml
# configuration.yaml
noaa_it_all:
```

**Note:** Legacy YAML configuration provides only global sensors (Kp Index, Geomagnetic Storm, Hurricane data) and does not include location-specific features like weather alerts, surf conditions, or aurora predictions.

## Entity Configuration

### Understanding Entity IDs
All NOAA It All entities follow consistent naming patterns:

**Pattern:**
```
{entity_type}.noaa_{identifier}_{sensor_name}
```

**Examples:**
- `sensor.noaa_sgx_temperature` - Temperature for San Diego office
- `binary_sensor.noaa_sgx_surf_unsafe_to_swim` - Rip current safety sensor
- `sensor.noaa_space_kp_index` - Global space weather sensor
- `image.noaa_geomagnetic_field` - Space weather image

### Customizing Entity Properties

You can customize friendly names, icons, and other properties in `customize.yaml`:

```yaml
# customize.yaml
homeassistant:
  customize:
    sensor.noaa_sgx_temperature:
      friendly_name: "San Diego Temperature"
      icon: mdi:thermometer
    
    binary_sensor.noaa_sgx_surf_unsafe_to_swim:
      friendly_name: "Beach Safety"
      icon: mdi:swim
      device_class: safety
    
    sensor.noaa_space_kp_index:
      friendly_name: "Geomagnetic Activity"
      icon: mdi:earth
```

## Device Grouping

NOAA It All automatically organizes entities into four device groups:

### 1. NOAA Space (Space Weather & Meteor Showers)
Entities that monitor space weather conditions worldwide, plus the meteor shower forecast for
your configured location.

**Entities in this group:**
- `sensor.noaa_space_kp_index`
- `sensor.noaa_space_geomagnetic_storm`
- `sensor.noaa_{office}_aurora_next_time`
- `sensor.noaa_{office}_aurora_duration`
- `sensor.noaa_{office}_aurora_visibility_probability`
- `sensor.noaa_{office}_solar_radiation_storm_alerts`
- `sensor.noaa_{office}_space_meteor_shower_activity`
- `sensor.noaa_{office}_space_next_meteor_shower`
- `sensor.noaa_{office}_space_meteor_viewing_score`
- `binary_sensor.noaa_{office}_space_meteor_shower_active`
- `image.noaa_geomagnetic_field`
- `image.noaa_aurora_forecast`

> Meteor shower entities require latitude/longitude (Config Flow setup) because the radiant's
> altitude — the single biggest factor in how many meteors you see — depends on where you are.
> They are computed locally from a bundled catalog and make no network requests.

### 2. NOAA Weather (Global & Location Weather)
Entities for hurricane tracking, forecasts, and weather observations.

**Entities in this group:**
- `sensor.noaa_weather_hurricane_alerts`
- `sensor.noaa_weather_hurricane_activity`
- `sensor.noaa_{office}_temperature`
- `sensor.noaa_{office}_humidity`
- `sensor.noaa_{office}_wind_speed`
- `sensor.noaa_{office}_wind_direction`
- `sensor.noaa_{office}_barometric_pressure`
- `sensor.noaa_{office}_dewpoint`
- `sensor.noaa_{office}_visibility`
- `sensor.noaa_{office}_sky_conditions`
- `sensor.noaa_{office}_feels_like`
- `sensor.noaa_{office}_cloud_cover`
- `sensor.noaa_{office}_radar_timestamp`
- `sensor.noaa_{office}_forecast_discussion`
- `sensor.noaa_weather_active_nws_alerts`
- `image.noaa_hurricane_outlook`
- `image.noaa_hurricane_satellite`

### 3. NOAA Surf (Surf & Water Conditions)
Entities for beach safety and surf conditions.

**Entities in this group:**
- `sensor.noaa_{office}_rip_current_risk`
- `sensor.noaa_{office}_surf_height`
- `sensor.noaa_{office}_water_temperature`
- `binary_sensor.noaa_{office}_surf_unsafe_to_swim`

### 4. NOAA Weather [OFFICE] (Location-Specific Alerts)
Device per office for location-specific weather alerts.

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
    - binary_sensor.noaa_sgx_weather_severe_weather_alert
    - binary_sensor.noaa_sgx_weather_flood_winter_alert
    - binary_sensor.noaa_sgx_weather_heat_air_quality_alert
    - binary_sensor.noaa_sgx_surf_unsafe_to_swim

noaa_current_conditions:
  name: "Current Weather"
  entities:
    - sensor.noaa_sgx_temperature
    - sensor.noaa_sgx_humidity
    - sensor.noaa_sgx_wind_speed
    - sensor.noaa_sgx_barometric_pressure

noaa_space_weather:
  name: "Space Weather"
  entities:
    - sensor.noaa_space_kp_index
    - sensor.noaa_space_geomagnetic_storm
    - sensor.noaa_dlh_aurora_visibility_probability
```

## Dashboard Card Examples

### Basic Weather Card
```yaml
type: entities
title: "Current Weather - San Diego"
show_header_toggle: false
entities:
  - entity: sensor.noaa_sgx_temperature
    name: "Temperature"
  - entity: sensor.noaa_sgx_feels_like
    name: "Feels Like"
  - entity: sensor.noaa_sgx_humidity
    name: "Humidity"
  - entity: sensor.noaa_sgx_wind_speed
    name: "Wind Speed"
  - entity: sensor.noaa_sgx_sky_conditions
    name: "Conditions"
```

### Alert Monitoring Card
```yaml
type: entities
title: "Weather Alerts"
state_color: true
entities:
  - entity: binary_sensor.noaa_sgx_weather_severe_weather_alert
    name: "Severe Weather"
  - entity: binary_sensor.noaa_sgx_weather_flood_winter_alert
    name: "Flood/Winter"
  - entity: binary_sensor.noaa_sgx_weather_heat_air_quality_alert
    name: "Heat/Air Quality"
  - entity: sensor.noaa_weather_active_nws_alerts
    name: "Alert Details"
```

### Beach Safety Card
```yaml
type: entities
title: "Beach Conditions"
entities:
  - entity: binary_sensor.noaa_sgx_surf_unsafe_to_swim
    name: "Safe to Swim"
  - entity: sensor.noaa_sgx_rip_current_risk
    name: "Rip Current Risk"
  - entity: sensor.noaa_sgx_surf_height
    name: "Wave Height"
  - entity: sensor.noaa_sgx_water_temperature
    name: "Water Temperature"
```

### Space Weather Card
```yaml
type: vertical-stack
cards:
  - type: entities
    title: "Space Weather"
    entities:
      - sensor.noaa_space_kp_index
      - sensor.noaa_space_geomagnetic_storm
      - sensor.noaa_dlh_aurora_visibility_probability
  
  - type: picture-entity
    entity: image.noaa_aurora_forecast
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
        entity_id: binary_sensor.noaa_sgx_surf_unsafe_to_swim
        to: 'on'
    action:
      - service: notify.mobile_app
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
        entity_id: binary_sensor.noaa_sgx_surf_unsafe_to_swim
        state: 'off'
      - condition: numeric_state
        entity_id: sensor.noaa_sgx_temperature
        above: 75
      - condition: numeric_state
        entity_id: sensor.noaa_sgx_wind_speed
        below: 15
    action:
      - service: notify.mobile_app
        data:
          title: "Perfect Beach Day!"
          message: >
            Temperature: {{ states('sensor.noaa_sgx_temperature') }}°F
            Surf: {{ states('sensor.noaa_sgx_surf_height') }} ft
            Water: {{ states('sensor.noaa_sgx_water_temperature') }}°F
```

### Severe Weather Response
```yaml
automation:
  - alias: "Severe Weather Actions"
    description: "Automated responses to severe weather"
    trigger:
      - platform: state
        entity_id: binary_sensor.noaa_sgx_weather_severe_weather_alert
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
      - service: notify.mobile_app
        data:
          title: "Weather Report"
          message: >
            Temperature: {{ states('sensor.noaa_sgx_temperature') }}°F
            Conditions: {{ states('sensor.noaa_sgx_sky_conditions') }}
            Wind: {{ states('sensor.noaa_sgx_wind_speed') }} mph
            Humidity: {{ states('sensor.noaa_sgx_humidity') }}%
            {% if is_state('binary_sensor.noaa_sgx_weather_active_alerts', 'on') %}
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
            K P index is {{ states('sensor.noaa_space_kp_index') }}.
            Geomagnetic activity: {{ states('sensor.noaa_space_geomagnetic_storm') }}.
            {% if states('sensor.noaa_dlh_aurora_visibility_probability') | int > 50 %}
            Aurora visibility probability is high at {{ states('sensor.noaa_dlh_aurora_visibility_probability') }} percent.
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
