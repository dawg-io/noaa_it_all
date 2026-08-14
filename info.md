# NOAA It All for Home Assistant

Comprehensive NOAA data integration providing real-time space weather, hurricane tracking, surf conditions, weather alerts, and aurora predictions.

## Features

### 🌌 Space Weather Monitoring
- **Kp Index** - Planetary geomagnetic activity tracking
- **Geomagnetic Storm Measurements** - Long-term storm intensity monitoring
- **Aurora Predictions** - Location-aware aurora visibility forecasts with timing and duration
- **Solar Radiation Storm Alerts** - S1-S5 classification with location-specific risk assessment
- **Visual Displays** - Real-time geomagnetic field and aurora forecast images

### ☄️ Meteor Showers
- **Meteor Shower Alerts** - Binary sensor that turns on only when a shower is genuinely worth going outside for
- **Viewing Forecast** - 0-100 score from radiant altitude, moon phase and astronomical darkness, plus the best viewing window and expected meteors per hour
- **Upcoming Showers** - The next five showers with peak dates, for dashboard cards and automations
- **Works Offline** - ~29 showers keyed by solar longitude and computed locally; no API, no key, no extra dependency

### 🌊 Surf & Ocean Conditions (Location-Specific)
- **Rip Current Risk** - Low/Moderate/High risk assessment with safety alerts
- **Surf Height** - Wave height estimates from NWS surf zone forecasts
- **Water Temperature** - Local ocean temperature data
- **Unsafe to Swim** - Binary sensor for dangerous conditions

### 🌤️ Weather Monitoring
- **Hurricane Tracking** - Active alerts, warnings, and satellite imagery
- **Current Weather** - Temperature, humidity, wind, pressure, visibility, and sky conditions
- **NWS Alerts** - Severe weather, flood, winter storm, heat, and air quality warnings
- **Weather Radar** - Real-time radar imagery with timestamp tracking
- **Forecast Discussion** - Meteorologist-written technical analysis (AFD product)

### 🚨 Alert Categories (Location-Specific Binary Sensors)
- Severe Weather Alerts (tornado, thunderstorm, hurricane, extreme winds)
- Flood/Winter Alerts (flood, winter storm, snow, ice)
- Heat/Air Quality Alerts (heat advisories, air quality, fire weather)
- Active Alerts indicator (general NWS alerts)

## Installation

### Via HACS (Recommended)
1. Open HACS in Home Assistant
2. Search for "NOAA It All"
3. Click Install
4. Restart Home Assistant

### Configuration

#### Config Flow (Recommended)
For full functionality including location-specific data:
1. Go to **Settings** → **Integrations** → **Add Integration**
2. Search for "NOAA It All"
3. Select your **NWS Forecast Office** (e.g., SGX for San Diego, LOX for Los Angeles)
4. Enter your **Latitude and Longitude** (required for weather observations)
5. Complete setup

#### Legacy YAML Configuration
For basic global sensors only (no location-specific features):
```yaml
noaa_it_all:
```

## Device Organization

Entities are automatically grouped into logical devices:
- **NOAA Space** - Global space weather and aurora data
- **NOAA Weather** - Hurricane tracking and general weather
- **NOAA Surf** - Location-specific surf and ocean conditions
- **NOAA Weather [OFFICE]** - Severe weather alerts for your location

## Requirements

- Home Assistant 2024.9.1 or newer
- Internet connection for NOAA API access
- Latitude/Longitude coordinates for location-specific features

## Supported Locations

All NWS forecast offices that issue Surf Zone Forecasts (SRF products). Examples include:
- **East Coast**: Norfolk (AKQ), Boston (BOX), Wilmington (ILM), Charleston (CHS), Jacksonville (JAX), Miami (MFL)
- **West Coast**: San Diego (SGX), Los Angeles (LOX), San Francisco (MTR), Portland (PQR), Eureka (EKA)
- **Gulf Coast**: Mobile (MOB), Corpus Christi (CRP), Brownsville (BRO), Tallahassee (TAE)
- **Great Lakes**: Chicago (LOT), Cleveland (CLE), Detroit (DTX), Milwaukee (MKX), Duluth (DLH)
- **Pacific**: Honolulu (HFO), Guam (GUM)

*This is a partial list. See the full documentation for a complete list of supported offices.*

## Update Frequency

All sensors and images update every 5 minutes with fresh data from NOAA.

## Links

- [Full Documentation](https://github.com/dawg-io/noaa_it_all)
- [Report Issues](https://github.com/dawg-io/noaa_it_all/issues)
- [Changelog](https://github.com/dawg-io/noaa_it_all/releases)
- [Full Changelog](https://github.com/dawg-io/noaa_it_all/blob/main/CHANGELOG.md)
