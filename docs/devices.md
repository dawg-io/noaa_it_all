# Devices

Every entity belongs to one of five kinds of device, one for each kind of entry. The screenshots below are from a Wilmington, NC (ILM) setup. [Entities](entities.md) lists every entity on each device.

## 📍 NOAA {OFFICE} Weather
Location-specific weather observations, forecasts, alerts and radar, in the `NOAA Weather - <office>` entry
- **Device ID**: `noaa_{office}_weather` (e.g., `noaa_ILM_weather`)
- **Location**: Your configured NWS office and coordinates
- **Update Frequency**: 10 minutes
- **Entities**: 22: nine observations, two forecasts, the weather entity, Active NWS Alerts and four alert binary sensors, cloud cover, the forecast discussion, and the radar timestamp, image and loop

<p align="left">
  <img width="270" alt="NOAA ILM Weather device: weather entity, alert binary sensors, observations, forecasts and radar images" src="images/device-weather.png" />
</p>

## 🌌 NOAA {OFFICE} Space
Space weather (geomagnetic storms, Kp, aurora, solar radiation storms) plus the meteor shower and eclipse forecasts, in the office's `NOAA Space - <office>` entry
- **Device ID**: `noaa_{office}_space` (e.g., `noaa_ILM_space`)
- **Location**: Space weather is global; aurora, meteor shower and eclipse entities use the Space entry's location
- **More than one Space entry**: space weather is the same everywhere, so these show the same values in each: Planetary K-index and its rating, Geomagnetic Storm and its interpretation, Solar Radiation Storm Alerts, and the Geoelectric Field and Aurora Forecast images. Aurora, meteor shower and eclipse entities are worked out for each entry
- **Update Frequency**: 10 minutes for space weather and its images, 30 minutes for meteor showers. Eclipses recompute hourly, every 5 minutes in the 6 hours before one, and every minute while one is under way
- **Entities**: 20: eight space weather sensors, three meteor shower and four eclipse sensors, three binary sensors, and two images

<p align="left">
  <img width="295" alt="NOAA ILM Space device: aurora, eclipse, geomagnetic, meteor shower, Kp and solar radiation entities" src="images/device-space.png" />
</p>

## 🌊 NOAA {OFFICE} Surf
Rip current risk, surf height and water temperature for one coastal office, in its `NOAA Surf - <office>` entry
- **Device ID**: `noaa_{office}_surf` (e.g., `noaa_ILM_surf`)
- **Location**: The coastal office's surf zones. A new surf entry only gets Water Temperature and Surf Height where the office has a tide station or buoy
- **Update Frequency**: 10 minutes
- **Entities**: 2 to 4: Rip Current Risk and Unsafe to Swim, plus Water Temperature and Surf Height where available

<p align="left">
  <img width="320" alt="NOAA ILM Surf device: Rip Current Risk, Surf Height, Unsafe to Swim, Water Temperature" src="images/device-surf.png" />
</p>

## ⛵ NOAA {ZONE} Marine
The nearshore marine forecast for one Great Lakes marine zone, in its `NOAA Marine - <zone name>` entry
- **Device ID**: `noaa_{ZONE}_marine` (e.g., `noaa_LMZ741_marine`)
- **Location**: The marine zone
- **Update Frequency**: 10 minutes
- **Entities**: `sensor.noaa_{zone}_marine_period` and `sensor.noaa_{zone}_marine_forecast`

<p align="left">
  <img width="320" alt="NOAA LMZ741 Marine device: Forecast and Period sensors" src="images/device-marine.png" />
</p>

## 🌀 NOAA Hurricane
Global hurricane tracking and GOES satellite imagery, in the `NOAA Hurricane` entry
- **Device ID**: `noaa_hurricane`
- **Location**: Independent (global NHC/GOES data)
- **Update Frequency**: 10 minutes
- **Entities**: `sensor.noaa_hurricane_activity`, `sensor.noaa_hurricane_alerts`, `image.noaa_hurricane_outlook_image`, `image.noaa_hurricane_pacific_outlook_image`, `image.noaa_hurricane_goes_air_mass`, `image.noaa_hurricane_goes_geocolor`

<p align="left">
  <img width="320" alt="NOAA Hurricane device: Activity, Alerts, GOES Air Mass, GOES Geocolor, Outlook Image, Pacific Outlook Image" src="images/device-hurricane.png" />
</p>

> **Important**: Hurricane and GOES satellite entities live under **NOAA Hurricane** only, in its own entry. There is one, however many locations are configured.

> **Tip**: Under **Settings → Devices & services**, click any NOAA device to see its entities together. This makes it easy to create dashboard cards and automations for specific categories of data.

## Grouping entities across devices

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
dashboard card instead; see [Dashboard Card Examples](dashboards.md).
