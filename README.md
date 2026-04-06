# NOAA IT ALL HACS Integration for Solar Data, Hurricane Tracking, and Location-Specific Rip Current Forecasts

> [!NOTE]
> This integration and its developer are independent and are not affiliated, endorsed, or sponsored by NOAA in any way.


[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/dawg-io/noaa_it_all.svg)](https://github.com/dawg-io/noaa_it_all/releases)
[![License](https://img.shields.io/github/license/dawg-io/noaa_it_all.svg)](LICENSE)


<p align="center">
  <img src="/custom_components/noaa_it_all/brand/icon.png" width="120"><br>
</p>

This Home Assistant integration provides comprehensive NOAA data through sensors and images, with the latest addition of location-specific rip current and surf zone forecasts.

## Installation & Configuration

### HACS Installation (Recommended)

#### Option 1: HACS Default Store (after acceptance)
1. Open HACS in Home Assistant
2. Click **Integrations**
3. Search for "NOAA Integration"
4. Click **Download**
5. Restart Home Assistant

#### Option 2: HACS Custom Repository
1. Open HACS in Home Assistant
2. Click the three-dot menu (⋮) → **Custom repositories**
3. Add `https://github.com/dawg-io/noaa_it_all` with category **Integration**
4. Click **Download** on the NOAA Integration card
5. Restart Home Assistant

### Manual Installation
1. Download the latest release from [GitHub Releases](https://github.com/dawg-io/noaa_it_all/releases)
2. Copy the `custom_components/noaa_it_all` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

### Configuration

#### Config Flow (Recommended - New!)
For location-specific rip current, surf zone, and weather data:
1. Go to **Settings** → **Integrations** → **Add Integration**
2. Search for "NOAA Integration"
3. Select your **NWS Forecast Office** from the dropdown (e.g., SGX for San Diego, LOX for Los Angeles)
4. **Enter your Latitude and Longitude** (required) - Weather observations will be fetched from the nearest station to this location
5. Complete the setup

**Important:** Starting with version 1.0.20, latitude and longitude are required fields for proper weather entity setup. Weather data is now fetched from the nearest observation station to your specified coordinates using the weather.gov API, rather than defaulting to the Home Assistant location or using a predefined office-to-station mapping.

#### Legacy YAML Configuration
For basic sensors without location-specific data:
```yaml
noaa_it_all:
```

## Device Grouping and Organization

The NOAA Integration organizes entities into logical device groups for better organization in Home Assistant. All entities are automatically grouped under one of the following devices:

### Device Groups Overview

#### 🌌 NOAA Space
Global space weather monitoring - aurora visibility, geomagnetic storms, and solar radiation alerts
- **Device ID**: `noaa_space`
- **Location**: Independent (global data)
- **Update Frequency**: 5 minutes

#### 🌤️ NOAA Weather
Global hurricane tracking, forecasts, and general weather observations
- **Device ID**: `noaa_weather`
- **Location**: Independent for hurricanes, location-specific for weather observations
- **Update Frequency**: 5 minutes

#### 🌊 NOAA Surf
Location-specific surf conditions, rip currents, and water temperature
- **Device ID**: `noaa_surf`
- **Location**: Specific to configured NWS office
- **Update Frequency**: 5 minutes

#### 📍 NOAA Weather [OFFICE]
Location-specific severe weather alerts and warnings (e.g., "NOAA Weather SGX" for San Diego)
- **Device ID**: `noaa_weather_{office_code}`
- **Location**: Specific to configured NWS office and coordinates
- **Update Frequency**: 5 minutes

> **Tip**: In Home Assistant's device view (Settings → Devices & Services), click on any NOAA device to see all related entities grouped together. This makes it easy to create dashboard cards and automations for specific categories of data.

## Available Entities

### Global Sensors (Available with all configurations)
- **Kp Index**: Planetary average of geomagnetic activity, updated every 3 hours *(NOAA Space)*
- **Geomagnetic Storm Measurements**: Long-term measure of geomagnetic storm intensity *(NOAA Space)*
- **Hurricane Alerts**: Number of active hurricane/tropical storm warnings and watches *(NOAA Weather)*
- **Hurricane Activity**: Overall hurricane activity status (Quiet, Low, Moderate, High) *(NOAA Weather)*

### Location-Specific Sensors (Config Flow Only)
- **Rip Current Risk**: Current risk level (Low, Moderate, High) from your NWS office's surf zone forecast *(NOAA Surf)*
- **Surf Height**: Wave height estimates in feet from local surf zone forecasts *(NOAA Surf)*
- **Water Temperature**: Local water temperature from surf zone forecasts *(NOAA Surf)*
- **Unsafe to Swim**: Binary sensor indicating dangerous rip current conditions *(NOAA Surf)*

### NWS Active Weather Alerts (Config Flow Only)
Real-time monitoring of National Weather Service alerts for your location *(NOAA Weather [OFFICE])*:

**Binary Sensors (True/False):**
- **Severe Weather Alert**: Active tornado, thunderstorm, hurricane, or extreme wind warnings/watches *(binary_sensor.noaa_{office}_severe_weather_alert)*
- **Flood/Winter Alert**: Active flood, winter storm, snow, ice, or freezing rain warnings/watches *(binary_sensor.noaa_{office}_flood_winter_alert)*
- **Heat/Air Quality Alert**: Active heat, air quality, fire weather, or environmental advisories *(binary_sensor.noaa_{office}_heat_air_quality_alert)*
- **Active Alerts**: General indicator for any active NWS alerts *(binary_sensor.noaa_{office}_active_alerts)*

**Comprehensive Sensor:**
- **Active NWS Alerts**: Detailed alert information including *(NOAA Weather)*:
  - Total alert count
  - Summary by severity (Extreme, Severe, Moderate, Minor)
  - Summary by urgency (Immediate, Expected, Future)
  - Breakdown by alert type (warnings, watches, advisories, statements)
  - Full alert details with headlines, descriptions, and instructions
  - Location-specific filtering based on configured coordinates

> **Note**: Alert sensors update every 5 minutes and only include actual alerts (excludes test messages and drafts). All alerts are filtered to your specific location using latitude/longitude coordinates from config flow setup. Binary sensors are grouped under NOAA Weather [OFFICE] while the comprehensive sensor is under NOAA Weather.

### Current Weather Conditions (Config Flow Only)
Real-time weather observations from your local NWS observation station *(NOAA Weather)*:
- **Temperature**: Current temperature in °F *(sensor.noaa_{office}_temperature)*
- **Humidity**: Relative humidity percentage *(sensor.noaa_{office}_humidity)*
- **Wind Speed**: Wind speed in mph *(sensor.noaa_{office}_wind_speed)*
- **Wind Direction**: Wind direction in degrees with cardinal direction *(sensor.noaa_{office}_wind_direction)*
- **Barometric Pressure**: Barometric pressure in inHg *(sensor.noaa_{office}_barometric_pressure)*
- **Dewpoint**: Dewpoint temperature in °F *(sensor.noaa_{office}_dewpoint)*
- **Visibility**: Visibility distance in miles *(sensor.noaa_{office}_visibility)*
- **Sky Conditions**: Current sky conditions description (Clear, Cloudy, Fog, etc.) *(sensor.noaa_{office}_sky_conditions)*
- **Feels Like**: Apparent temperature incorporating wind chill or heat index *(sensor.noaa_{office}_feels_like)*

> **Note**: Weather observations update every 5 minutes from the primary observation station for your configured NWS office location. Data includes automatic unit conversions to US customary units.

### Aurora Visibility Alerts (Config Flow Only)
Location-aware aurora visibility predictions *(NOAA Space)*:
- **Aurora Next Time**: Predicted timing when aurora activity may begin at your location *(sensor.noaa_{office}_aurora_next_time)*
- **Aurora Duration**: Estimated length of aurora visibility in hours based on geomagnetic conditions *(sensor.noaa_{office}_aurora_duration)*
- **Aurora Visibility Probability**: Percentage chance of aurora visibility from your specific location *(sensor.noaa_{office}_aurora_visibility_probability)*

> **Note**: Aurora predictions are based on real-time Kp index data and your location's magnetic latitude. Northern locations (like Duluth, MN) have much higher visibility potential than southern locations (like Miami, FL).

### Solar Radiation Storm Alerts (Config Flow Only)
Location-aware monitoring of solar radiation storm activity *(NOAA Space)*:
- **Solar Radiation Storm Alerts**: Location-aware monitoring of solar radiation storm activity with S1-S5 classification *(sensor.noaa_{office}_solar_radiation_storm_alerts)*
  - **Storm Classification**: Automatic detection and classification of solar radiation storms (S1-S5 scale)
  - **Expected Timing**: Start and end times for radiation storm events when available
  - **Impact Assessment**: Potential impacts including satellite interference, radio blackouts, and radiation exposure risks
  - **Location Risk**: Risk assessment based on your magnetic latitude and current storm activity
  - **Real-time Alerts**: Live monitoring of NOAA Space Weather Prediction Center alerts

> **Note**: Solar radiation storm impacts vary by location and magnetic latitude. Higher latitudes (like Alaska and northern Canada) experience more severe effects, while equatorial regions are generally less affected. The integration provides location-specific risk assessments for your configured NWS office.

### Optional Secondary Sensors (Config Flow Only)
These sensors provide additional weather data where available from NOAA/NWS *(NOAA Weather)*:

- **Cloud Cover**: Current cloud coverage percentage from NWS gridpoint data *(sensor.noaa_{office}_cloud_cover)*
  - Returns percentage (0-100%) of sky covered by clouds
  - Updated from forecast gridpoint data for your location
  - Requires latitude/longitude configuration
  - May not be available for all locations

- **Radar Timestamp**: Timestamp of the latest radar image for your NWS office *(sensor.noaa_{office}_radar_timestamp)*
  - Shows when the most recent radar image was captured
  - Useful for automations or displaying radar freshness
  - Based on NEXRAD radar site for your office location
  - Available for most coastal and land-based offices

- **Forecast Discussion**: Meteorologist-written forecast discussion (AFD product) *(sensor.noaa_{office}_forecast_discussion)*
  - Detailed technical analysis from local NWS meteorologists
  - Includes reasoning behind forecast decisions
  - Updated when new forecast discussions are issued (typically 2-3 times daily)
  - Full text available in sensor attributes with summary in state
  - Provides insight into weather patterns and forecast confidence

> **Note**: These sensors gracefully handle missing data by returning `None` or `Unknown` when data is unavailable. The `availability` attribute indicates data source and current status. **UV Index is NOT available** through NWS APIs and cannot be provided by this integration.

### Image Entities
Visual representations of current conditions *(NOAA Space & NOAA Weather)*:
- **Geomagnetic Field Image**: Real-time geomagnetic storm intensity visualization *(NOAA Space)*
- **Aurora Forecast Image**: Tonight's aurora coverage forecast *(NOAA Space)*
- **Hurricane Outlook Image**: 2-day tropical weather outlook from NHC *(NOAA Weather)*
- **Hurricane Satellite Image**: Latest Atlantic satellite imagery *(NOAA Weather)*

> **Tip**: Image entities can be displayed on dashboards using the standard `picture-entity` or `picture-glance` cards. They automatically refresh every 5 minutes to show the latest data.

## NWS Forecast Offices

The integration supports all NWS offices that issue Surf Zone Forecasts (SRF):

**East Coast**: Norfolk (AKQ), Boston (BOX), Wilmington NC (ILM), Charleston (CHS), Jacksonville (JAX), Miami (MFL), Tampa (TBW), etc.

**West Coast**: San Diego (SGX), Los Angeles (LOX), San Francisco (MTR), Portland OR (PQR), Eureka (EKA)

**Gulf Coast**: Mobile (MOB), Corpus Christi (CRP), Brownsville (BRO), Tallahassee (TAE)

**Great Lakes**: Chicago (LOT), Cleveland (CLE), Detroit (DTX), Milwaukee (MKX), Duluth (DLH)

**Pacific**: Honolulu (HFO), Guam (GUM)

## Entity Naming Conventions

Understanding entity naming helps you quickly identify and use sensors in automations and dashboards.

### Naming Pattern
All NOAA Integration entities follow this pattern:
```
{entity_type}.noaa_{office_code}_{sensor_name}
```

**Examples:**
- `sensor.noaa_sgx_temperature` - Temperature sensor for San Diego (SGX office)
- `binary_sensor.noaa_sgx_unsafe_to_swim` - Rip current safety for San Diego
- `sensor.noaa_weather_kp_index` - Global K-index (no office code, space weather)
- `binary_sensor.noaa_sgx_severe_weather_alert` - Severe weather alert for San Diego

### Office Code Usage
- **Location-specific sensors**: Include the office code (e.g., `sgx`, `lox`, `box`)
- **Global sensors**: Omit office code or use `weather`/`space` identifier
- **Replace office code**: If you change NWS offices, entity names will include the new code

### Entity Types
- **sensor.**: Numeric or text state (temperature, humidity, alert count, etc.)
- **binary_sensor.**: On/Off or True/False state (unsafe conditions, active alerts)
- **image.**: Visual data (radar, satellite, forecast images)

### Best Practices

1. **Use Device Views**: Access entities by device (Settings → Devices & Services → NOAA Integration) for organized browsing
2. **Create Groups**: Use Home Assistant groups to combine related entities across device boundaries
3. **Label Your Location**: In automations, use friendly names in messages (e.g., "San Diego" instead of "SGX")
4. **Check Availability**: Sensors return `unknown` or `None` when data is unavailable - use conditions to verify state
5. **Binary Sensors for Triggers**: Use binary sensors (`on`/`off`) for automation triggers instead of checking sensor values
6. **Access Attributes**: Many sensors include detailed information in attributes (e.g., full alert text, forecast periods)

### Quick Reference: Common Entity Patterns

| Data Type | Entity Pattern | Example |
|-----------|---------------|---------|
| Weather Observation | `sensor.noaa_{office}_{metric}` | `sensor.noaa_sgx_temperature` |
| Weather Alert Binary | `binary_sensor.noaa_{office}_{alert_type}_alert` | `binary_sensor.noaa_sgx_severe_weather_alert` |
| Surf Conditions | `sensor.noaa_{office}_{surf_metric}` | `sensor.noaa_sgx_rip_current_risk` |
| Space Weather | `sensor.noaa_{space/weather}_{metric}` | `sensor.noaa_space_kp_index` |
| Aurora Predictions | `sensor.noaa_{office}_aurora_{metric}` | `sensor.noaa_dlh_aurora_next_time` |

## Example Automations

### Binary Sensor Triggers for Safety Alerts

#### Rip Current Safety Alert
```yaml
automation:
  - alias: "Rip Current Warning"
    description: "Alert when rip current conditions become dangerous"
    trigger:
      platform: state
      entity_id: binary_sensor.noaa_sgx_unsafe_to_swim
      to: 'on'
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ Beach Safety Alert"
          message: "High rip current risk detected - swimming not recommended!"
          data:
            priority: high
            tag: "rip-current-alert"
```

### Weather Alert Notifications

#### Severe Weather Alert Notification
```yaml
automation:
  - alias: "Severe Weather Alert"
    description: "Immediate notification for severe weather warnings"
    trigger:
      platform: state
      entity_id: binary_sensor.noaa_sgx_severe_weather_alert
      to: 'on'
    action:
      - service: notify.mobile_app
        data:
          title: "⚠️ {{ state_attr('binary_sensor.noaa_ilm_active_alerts','alerts')[0].event }}"
          message: "{{ state_attr('binary_sensor.noaa_ilm_active_alerts','alerts')[0].description | replace('\r\n',' ') }}"
          data:
            priority: high
            notification_icon: mdi:weather-lightning-rainy
      - service: tts.google_translate_say
        data:
          entity_id: media_player.home_speaker
          message: "{{ state_attr('binary_sensor.noaa_ilm_active_alerts','alerts')[0].description | replace('\r\n',' ') }}"
```

#### Winter Storm Alert with Light Flash
```yaml
automation:
  - alias: "Winter Storm Alert"
    description: "Visual and mobile notification for winter weather"
    trigger:
      platform: state
      entity_id: binary_sensor.noaa_sgx_flood_winter_alert
      to: 'on'
    action:
      - service: notify.mobile_app
        data:
          title: "❄️ Winter Weather Alert"
          message: "Winter storm or flood warning active for your area!"
          data:
            notification_icon: mdi:weather-snowy-heavy
      - service: light.turn_on
        target:
          entity_id: light.living_room
        data:
          flash: long
          rgb_color: [0, 100, 255]
```

#### Heat Advisory with Thermostat Adjustment
```yaml
automation:
  - alias: "Heat Advisory - Adjust Thermostat"
    description: "Auto-adjust cooling when heat advisory is active"
    trigger:
      platform: state
      entity_id: binary_sensor.noaa_sgx_heat_air_quality_alert
      to: 'on'
    action:
      - service: notify.mobile_app
        data:
          title: "🔥 Heat Advisory"
          message: "Heat advisory or air quality alert active!"
      - service: climate.set_temperature
        target:
          entity_id: climate.home
        data:
          temperature: 72
      - service: fan.turn_on
        target:
          entity_id: fan.bedroom
```

### Space Weather Monitoring

#### Aurora Alert for Northern Locations
```yaml
automation:
  - alias: "Aurora Alert - High Probability"
    description: "Notify when aurora visibility probability is high"
    trigger:
      - platform: numeric_state
        entity_id: sensor.noaa_dlh_aurora_visibility_probability
        above: 50
    condition:
      - condition: sun
        after: sunset
        before: sunrise
    action:
      - service: notify.mobile_app
        data:
          title: "🌌 Aurora Alert!"
          message: >
            Aurora visibility probability is {{ states('sensor.noaa_dlh_aurora_visibility_probability') }}%!
            Expected duration: {{ states('sensor.noaa_dlh_aurora_duration') }} hours.
          data:
            notification_icon: mdi:weather-night
```

#### Geomagnetic Storm Notification
```yaml
automation:
  - alias: "Geomagnetic Storm Alert"
    description: "Notify when Kp index indicates geomagnetic storm"
    trigger:
      - platform: numeric_state
        entity_id: sensor.noaa_space_kp_index
        above: 5
    action:
      - service: notify.mobile_app
        data:
          title: "⚡ Geomagnetic Storm"
          message: >
            Kp Index: {{ states('sensor.noaa_space_kp_index') }}
            Geomagnetic Storm Level: {{ states('sensor.noaa_space_geomagnetic_storm') }}
          data:
            notification_icon: mdi:solar-power
```

### Multi-Condition Automation with Grouping Logic

#### Safe Beach Day Notification
```yaml
automation:
  - alias: "Safe Beach Day Alert"
    description: "Notify when conditions are perfect for beach activities"
    trigger:
      - platform: time
        at: "08:00:00"
    condition:
      - condition: state
        entity_id: binary_sensor.noaa_sgx_unsafe_to_swim
        state: 'off'
      - condition: numeric_state
        entity_id: sensor.noaa_sgx_temperature
        above: 75
      - condition: numeric_state
        entity_id: sensor.noaa_sgx_wind_speed
        below: 15
      - condition: state
        entity_id: binary_sensor.noaa_sgx_active_alerts
        state: 'off'
    action:
      - service: notify.mobile_app
        data:
          title: "🏖️ Perfect Beach Day!"
          message: >
            Great conditions for beach activities:
            Temperature: {{ states('sensor.noaa_sgx_temperature') }}°F
            Rip Current Risk: {{ states('sensor.noaa_sgx_rip_current_risk') }}
            Surf Height: {{ states('sensor.noaa_sgx_surf_height') }} ft
            Water Temp: {{ states('sensor.noaa_sgx_water_temperature') }}°F
          data:
            actions:
              - action: "VIEW_SURF_CONDITIONS"
                title: "View Full Conditions"
```

#### Severe Weather Preparation
```yaml
automation:
  - alias: "Severe Weather Preparation"
    description: "Comprehensive preparation when multiple alerts are active"
    trigger:
      - platform: state
        entity_id: 
          - binary_sensor.noaa_sgx_severe_weather_alert
          - binary_sensor.noaa_sgx_flood_winter_alert
        to: 'on'
    action:
      # Close automated blinds/shades
      - service: cover.close_cover
        target:
          entity_id: all
      # Turn on weather alert lights
      - service: light.turn_on
        target:
          area_id: living_room
        data:
          brightness: 255
      # Send comprehensive alert
      - service: notify.family_group
        data:
          title: "🚨 Severe Weather - Take Action"
          message: >
            Multiple severe weather alerts are active.
            Total Alerts: {{ state_attr('sensor.noaa_weather_active_nws_alerts', 'total_alerts') }}
            Types: {{ state_attr('sensor.noaa_weather_active_nws_alerts', 'alert_types') | join(', ') }}
          data:
            priority: high
            ttl: 0
      # Announce on speakers
      - service: tts.google_translate_say
        target:
          entity_id: media_player.all_speakers
        data:
          message: "Attention: Multiple severe weather alerts are now active for your area."
```

### Script Examples

#### Check Current Conditions Script
```yaml
script:
  check_weather_conditions:
    alias: "Check Current Weather Conditions"
    description: "Announce current weather and space weather conditions"
    sequence:
      - service: tts.google_translate_say
        target:
          entity_id: media_player.home_speaker
        data:
          message: >
            Current conditions: 
            Temperature {{ states('sensor.noaa_sgx_temperature') }} degrees, 
            feels like {{ states('sensor.noaa_sgx_feels_like') }} degrees.
            {{ states('sensor.noaa_sgx_sky_conditions') }} skies.
            Wind {{ states('sensor.noaa_sgx_wind_speed') }} miles per hour from the {{ states('sensor.noaa_sgx_wind_direction') }}.
            {% if is_state('binary_sensor.noaa_sgx_active_alerts', 'on') %}
              Alert: {{ state_attr('sensor.noaa_weather_active_nws_alerts', 'total_alerts') }} weather alerts are currently active.
            {% endif %}
```

#### Space Weather Report
```yaml
script:
  space_weather_report:
    alias: "Space Weather Report"
    description: "Get current space weather conditions"
    sequence:
      - service: notify.mobile_app
        data:
          title: "🌌 Space Weather Report"
          message: >
            Kp Index: {{ states('sensor.noaa_space_kp_index') }}
            Geomagnetic Activity: {{ states('sensor.noaa_space_geomagnetic_storm') }}
            {% if states('sensor.noaa_dlh_aurora_visibility_probability') | int > 0 %}
            Aurora Visibility: {{ states('sensor.noaa_dlh_aurora_visibility_probability') }}%
            Expected at: {{ states('sensor.noaa_dlh_aurora_next_time') }}
            {% endif %}
            Solar Radiation: {{ states('sensor.noaa_sgx_solar_radiation_storm_alerts') }}
```

#### Morning Weather Briefing
```yaml
script:
  morning_weather_briefing:
    alias: "Morning Weather Briefing"
    description: "Complete morning weather and alert briefing"
    sequence:
      - service: notify.mobile_app
        data:
          title: "☀️ Good Morning - Weather Briefing"
          message: >
            **Current Conditions:**
            🌡️ {{ states('sensor.noaa_sgx_temperature') }}°F (feels like {{ states('sensor.noaa_sgx_feels_like') }}°F)
            💨 Wind {{ states('sensor.noaa_sgx_wind_speed') }} mph
            ☁️ {{ states('sensor.noaa_sgx_sky_conditions') }}
            
            **Beach Conditions:**
            🌊 Surf: {{ states('sensor.noaa_sgx_surf_height') }} ft
            🏊 Rip Current Risk: {{ states('sensor.noaa_sgx_rip_current_risk') }}
            🌡️ Water: {{ states('sensor.noaa_sgx_water_temperature') }}°F
            
            **Alerts:**
            {% if is_state('binary_sensor.noaa_sgx_active_alerts', 'on') %}
            ⚠️ {{ state_attr('sensor.noaa_weather_active_nws_alerts', 'total_alerts') }} active weather alerts
            {% else %}
            ✅ No active weather alerts
            {% endif %}
```

### Dashboard Card Examples

### Dashboard Card Examples

These examples demonstrate how to create effective dashboard cards organized by device groups.

#### Weather Alerts Card (NOAA Weather [OFFICE] Group)
```yaml
type: entities
title: "🚨 NWS Active Alerts - San Diego"
show_header_toggle: false
state_color: true
entities:
  - entity: sensor.noaa_weather_active_nws_alerts
    name: "Active Alerts"
    icon: mdi:alert-circle
  - type: divider
  - entity: binary_sensor.noaa_sgx_severe_weather_alert
    name: "Severe Weather"
    icon: mdi:weather-lightning
  - entity: binary_sensor.noaa_sgx_flood_winter_alert
    name: "Flood/Winter"
    icon: mdi:weather-snowy-rainy
  - entity: binary_sensor.noaa_sgx_heat_air_quality_alert
    name: "Heat/Air Quality"
    icon: mdi:sun-thermometer
  - entity: binary_sensor.noaa_sgx_active_alerts
    name: "Any Active Alerts"
    icon: mdi:bell-alert
```

#### Beach Conditions Card (NOAA Surf Group)
```yaml
type: entities
title: "🏖️ Beach Conditions - San Diego"
show_header_toggle: false
entities:
  - entity: sensor.noaa_sgx_rip_current_risk
    name: "Rip Current Risk"
    icon: mdi:waves
  - entity: binary_sensor.noaa_sgx_unsafe_to_swim
    name: "Safe to Swim"
    icon: mdi:swim
  - entity: sensor.noaa_sgx_surf_height
    name: "Surf Height"
    icon: mdi:wave
  - entity: sensor.noaa_sgx_water_temperature
    name: "Water Temperature"
    icon: mdi:thermometer-water
```

#### Current Weather Card (NOAA Weather Group)
```yaml
type: vertical-stack
cards:
  - type: markdown
    content: >
      <div style="display:flex;align-items:center;gap:14px;"> <img src="{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[0].icon }}"
      width="56"> <div> <b>{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[0].name }} ·
      {{
      as_timestamp(state_attr('sensor.noaa_weather_extended_forecast','periods')[0].start_time)
      | timestamp_custom('%a %m/%d') }}</b><br> <span
      style="font-size:1.4em;font-weight:700;"> {{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[0].temperature
      }}°{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[0].temperature_unit
      }} </span><br> {{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[0].detailed_forecast
      }} </div></div>
  - type: markdown
    content: >
      <div style="display:flex;align-items:center;gap:14px;"> <img src="{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[1].icon }}"
      width="56"> <div> <b>{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[1].name }} ·
      {{
      as_timestamp(state_attr('sensor.noaa_weather_extended_forecast','periods')[1].start_time)
      | timestamp_custom('%a %m/%d') }}</b><br> <span
      style="font-size:1.4em;font-weight:700;"> {{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[1].temperature
      }}°{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[1].temperature_unit
      }} </span><br> {{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[1].detailed_forecast
      }} </div></div>
  - type: markdown
    content: >
      <div style="display:flex;align-items:center;gap:14px;"> <img src="{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[2].icon }}"
      width="56"> <div> <b>{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[2].name }} ·
      {{
      as_timestamp(state_attr('sensor.noaa_weather_extended_forecast','periods')[2].start_time)
      | timestamp_custom('%a %m/%d') }}</b><br> <span
      style="font-size:1.4em;font-weight:700;"> {{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[2].temperature
      }}°{{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[2].temperature_unit
      }} </span><br> {{
      state_attr('sensor.noaa_weather_extended_forecast','periods')[2].detailed_forecast
      }} </div></div>

```

#### Space Weather Card (NOAA Space Group)
```yaml
type: entities
title: 🌌 Space Weather
show_header_toggle: false
entities:
  - entity: sensor.noaa_space_planetary_k_index
    name: Kp Index
    icon: mdi:chart-line
  - entity: sensor.noaa_space_geomagnetic_storm
    name: Geomagnetic Storm
    icon: mdi:earth
  - type: divider
  - entity: sensor.aurora_visibility_probability_ilm
    name: Aurora Probability
    icon: mdi:star-shooting
  - entity: sensor.aurora_next_time_ilm
    name: Next Aurora
    icon: mdi:clock-outline
  - entity: sensor.aurora_duration_ilm
    name: Duration
    icon: mdi:timer-outline
  - type: divider
  - entity: sensor.noaa_weather_active_nws_alerts
    name: Solar Radiation
    icon: mdi:radioactive

```

#### Hurricane Tracking Card (NOAA Weather Group)
```yaml
type: entities
title: "🌀 Hurricane Activity"
show_header_toggle: false
entities:
  - entity: sensor.noaa_weather_hurricane_alerts
    name: "Active Alerts"
    icon: mdi:alert-octagon
  - entity: sensor.noaa_weather_hurricane_activity
    name: "Activity Level"
    icon: mdi:weather-hurricane
```

#### Comprehensive Weather Dashboard View
```yaml
type: vertical-stack
cards:
  # Top row - Alerts and Safety
  - type: horizontal-stack
    cards:
      - type: conditional
        conditions:
          - entity: binary_sensor.noaa_sgx_active_alerts
            state: 'on'
        card:
          type: markdown
          content: |
            ## ⚠️ ACTIVE WEATHER ALERTS
            **{{ state_attr('sensor.noaa_weather_active_nws_alerts', 'total_alerts') }} Alert(s)**
            {{ state_attr('sensor.noaa_weather_active_nws_alerts', 'summary') }}
          card_mod:
            style: |
              ha-card {
                background-color: rgba(255, 0, 0, 0.2);
                border: 2px solid red;
              }
      
      - type: conditional
        conditions:
          - entity: binary_sensor.noaa_sgx_unsafe_to_swim
            state: 'on'
        card:
          type: markdown
          content: |
            ## 🌊 BEACH SAFETY ALERT
            **High Rip Current Risk**
            Swimming Not Recommended
          card_mod:
            style: |
              ha-card {
                background-color: rgba(255, 165, 0, 0.2);
                border: 2px solid orange;
              }
  
  # Second row - Current conditions
  - type: horizontal-stack
    cards:
      - type: gauge
        entity: sensor.noaa_sgx_temperature
        name: "Temperature"
        min: 0
        max: 120
        severity:
          green: 60
          yellow: 85
          red: 95
      
      - type: gauge
        entity: sensor.noaa_sgx_humidity
        name: "Humidity"
        min: 0
        max: 100
        severity:
          green: 30
          yellow: 60
          red: 80
      
      - type: gauge
        entity: sensor.noaa_space_kp_index
        name: "Kp Index"
        min: 0
        max: 9
        severity:
          green: 0
          yellow: 5
          red: 7
  
  # Third row - Detailed entities
  - type: entities
    title: "Weather Details"
    entities:
      - sensor.noaa_sgx_feels_like
      - sensor.noaa_sgx_wind_speed
      - sensor.noaa_sgx_barometric_pressure
      - sensor.noaa_sgx_sky_conditions
  
  # Fourth row - Space weather images
  - type: horizontal-stack
    cards:
      - type: picture-entity
        entity: image.noaa_geomagnetic_field
        name: "Geomagnetic Field"
        show_state: false
      
      - type: picture-entity
        entity: image.noaa_aurora_forecast
        name: "Aurora Forecast"
        show_state: false
```

#### Glance Card for Quick Overview
```yaml
type: glance
title: "NOAA Quick View"
show_name: true
show_state: true
columns: 4
entities:
  - entity: sensor.noaa_sgx_temperature
    name: "Temp"
  - entity: sensor.noaa_sgx_wind_speed
    name: "Wind"
  - entity: sensor.noaa_sgx_surf_height
    name: "Surf"
  - entity: binary_sensor.noaa_sgx_unsafe_to_swim
    name: "Safe Swim"
  - entity: sensor.noaa_space_kp_index
    name: "Kp Index"
  - entity: binary_sensor.noaa_sgx_active_alerts
    name: "Alerts"
  - entity: sensor.noaa_weather_hurricane_activity
    name: "Hurricanes"
  - entity: sensor.noaa_sgx_rip_current_risk
    name: "Rip Risk"
```

#### Mobile-Optimized Card
```yaml
type: vertical-stack
cards:
  - type: markdown
    content: |
      # 📍 San Diego Weather
      Updated: {{ as_timestamp(states.sensor.noaa_sgx_temperature.last_changed) | timestamp_custom('%I:%M %p') }}
  
  - type: entities
    entities:
      - entity: sensor.noaa_sgx_temperature
        name: "🌡️ Temperature"
      - entity: sensor.noaa_sgx_feels_like
        name: "🤒 Feels Like"
      - entity: sensor.noaa_sgx_sky_conditions
        name: "☁️ Conditions"
  
  - type: conditional
    conditions:
      - entity: binary_sensor.noaa_sgx_active_alerts
        state: 'on'
    card:
      type: button
      name: "View Active Alerts"
      icon: mdi:alert-circle
      tap_action:
        action: more-info
        entity: sensor.noaa_weather_active_nws_alerts
      hold_action:
        action: none
```

#### Forecast Discussion Card
```yaml
type: markdown
title: "📝 Forecast Discussion"
content: |
  **{{ state_attr('sensor.noaa_sgx_forecast_discussion', 'office') }}** - Updated {{ state_attr('sensor.noaa_sgx_forecast_discussion', 'issued_time') }}
  
  {{ states('sensor.noaa_sgx_forecast_discussion') }}
  
  [Read Full Discussion]({{ state_attr('sensor.noaa_sgx_forecast_discussion', 'product_link') }})
```

## Troubleshooting & FAQ

### Entities Not Appearing
- Ensure you completed Config Flow setup with valid latitude and longitude
- Verify your NWS office code is listed in the [supported offices](#nws-forecast-offices) table
- Restart Home Assistant after adding or reconfiguring the integration
- Check **Settings** → **System** → **Logs** for any error messages from `noaa_it_all`

### Data Not Updating
- Check sensor attributes for error messages
- Verify internet connectivity from your Home Assistant instance
- NOAA APIs occasionally experience temporary outages; sensors will recover automatically
- Confirm scan interval is running: entities should show a `last_changed` time within the last 10 minutes

### Incorrect or Missing Weather Data
- Weather observations are pulled from the nearest NWS station to your configured coordinates
- Confirm your latitude and longitude are accurate (you can reconfigure via **Settings** → **Integrations** → **NOAA Integration** → **Configure**)
- Some NWS offices may not have nearby observation stations; in that case observations will show `unknown`

### Binary Sensors Always Off
- Binary sensors require Config Flow setup with a valid office code and coordinates
- Legacy YAML configuration does not support location-specific binary sensors

### Integration Fails to Load
- Confirm Home Assistant version is **2024.9.1 or newer**
- Check that required Python packages (`requests`, `aiohttp`) are available (they are bundled with HACS installations)
- Review Home Assistant logs for specific import or configuration errors

### FAQ

**Q: Can I use this integration without configuring latitude/longitude?**
A: Yes. Adding `noaa_it_all:` to `configuration.yaml` provides global sensors (Kp Index, Geomagnetic Storm, Hurricane data) without location-specific features.

**Q: How do I find my NWS forecast office code?**
A: Visit [weather.gov](https://www.weather.gov/) and search for your location. The three-letter office code appears in the URL of your local forecast page (e.g., `forecast.weather.gov/MapClick.php?CityName=San+Diego&state=CA&site=SGX`).

**Q: Why don't I see aurora predictions?**
A: Aurora predictions are location-specific and require Config Flow setup. Also, aurora is only visible at high Kp levels for southern latitudes — check the Kp Index value and your office's magnetic latitude.

**Q: How often does data update?**
A: All sensors update every 5 minutes.

**Q: Are UV Index readings available?**
A: No. UV Index is not provided through NWS/NOAA APIs and cannot be included in this integration.

**Q: Where can I report bugs or request features?**
A: Please open an issue on [GitHub](https://github.com/dawg-io/noaa_it_all/issues).

## Data Sources

- **Space Weather**: NOAA Space Weather Prediction Center
  - Aurora visibility forecasts and geomagnetic storm data
  - Solar radiation storm alerts and classification (S1-S5 scale)
  - Real-time space weather alert monitoring
- **Hurricane Data**: National Hurricane Center (NHC) and National Weather Service (NWS)
- **NWS Active Alerts**: National Weather Service weather.gov API
  - Location-specific severe weather warnings and watches
  - Flood, winter storm, and environmental alerts
  - Real-time alert monitoring with automatic filtering
- **Rip Current/Surf Data**: Location-specific NWS Surf Zone Forecasts (SRF products)
- **Weather Observations**: National Weather Service observation stations (weather.gov API)
  - Real-time temperature, humidity, wind, pressure, and sky conditions
  - Automatic unit conversions to US customary units

## Update Frequency
All sensors update every 5 minutes to provide current conditions while respecting API rate limits.

**Note:** Legacy YAML configurations without lat/lon will continue to work but will use the fallback office-to-station mapping for weather data. Config Flow setups require the new fields.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a full history of changes and releases.
