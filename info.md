# NOAA It All for Home Assistant

Comprehensive NOAA data integration providing weather observations, forecasts, alerts and radar, surf conditions for any coast, Great Lakes nearshore marine forecasts, hurricane tracking, and space weather, meteor showers and eclipses.

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

### 🌑 Solar & Lunar Eclipses
- **Go Outside Now** - Binary sensor that turns on an hour before first contact and off at last contact
- **Coming Up** - A two-week warning for an eclipse actually worth planning around
- **How Much You Get** - The percentage of the Sun or Moon covered *from where you are*, because a "total" eclipse is total along a strip and partial across a continent
- **A Real Date** - A timestamp sensor for when to go outside, so Home Assistant shows "in 3 days" and a time trigger can fire straight off it
- **Eye Safety Built In** - Every solar eclipse carries the ISO 12312-2 warning and flags the one phase, totality, that is safe unfiltered
- **Works Offline** - Lunar eclipses computed from first principles and correct indefinitely; solar eclipses from bundled NASA elements for 2025-2075, accurate to 20 seconds. No API, no key, no extra dependency

### 🌊 Surf & Ocean Conditions (Any Coast)
- **Rip Current Risk** - Low/Moderate/High risk from the NWS Surf Zone Forecast of the coastal office you choose
- **Surf Height** - Wave height from the office's NDBC buoy, where it has one
- **Water Temperature** - Water temperature from the office's NOAA tide station, where it has one
- **Unsafe to Swim** - Binary sensor for a high rip current risk

### ⛵ Nearshore Marine Forecasts
- **Great Lakes Zones** - The current period and forecast for any nearshore marine zone, such as `LMZ741` on Lake Michigan, with every period and advisory in its attributes

### 🌤️ Weather Monitoring
- **Any NWS Office** - Setup picks the office NWS names for your location, inland or coastal
- **Hurricane Tracking** - Active storms, watches and warnings, Atlantic and East Pacific outlooks, and GOES satellite imagery
- **Current Weather** - Temperature, humidity, wind, pressure, visibility, and sky conditions
- **Forecasts** - Extended and hourly forecasts, plus a Home Assistant weather entity
- **NWS Alerts** - Severe weather, flood, winter storm, heat, and air quality warnings
- **Weather Radar** - Real-time radar imagery with timestamp tracking, plus an animated loop covering up to 24 hours
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
3. Click Download
4. Restart Home Assistant

### Configuration

#### Config Flow
1. Go to **Settings** → **Devices & services** → **Add integration**
2. Search for "NOAA It All" and choose **Weather for a location**
3. Enter your **Latitude and Longitude** (pre-filled from your Home zone)
4. Select your **NWS Forecast Office**; the one NWS names for your location is pre-selected
5. Choose a **surf forecast office**, or **No surf data**
6. Complete setup

The surf office becomes its own `NOAA Surf` entry, and the first location also adds the `NOAA Hurricane` entry. Use **Add entry** for more beaches, Great Lakes marine zones, or hurricanes.

#### Legacy YAML Configuration

> **Removed.** YAML configuration is no longer supported and creates **no entities**. If
> `noaa_it_all:` is present in `configuration.yaml`, the integration logs an error and sets nothing
> up. Remove the block and add the integration through **Settings → Devices & services → Add
> Integration → NOAA It All**.

## Device Organization

Entities are automatically grouped into logical devices:
- **NOAA {OFFICE} Weather** - Observations, forecasts, radar and severe weather alerts
- **NOAA {OFFICE} Space** - Space weather, aurora, meteor shower and eclipse data
- **NOAA {OFFICE} Surf** - Surf and ocean conditions for one coastal office
- **NOAA {ZONE} Marine** - The nearshore marine forecast for one Great Lakes zone
- **NOAA Hurricane** - Global tropical data and satellite imagery, created once across all offices

`{OFFICE}` is your NWS forecast office code, e.g. `NOAA ILM Weather`, and `{ZONE}` the marine zone, e.g. `NOAA LMZ741 Marine`.

## Requirements

- Home Assistant 2026.3.0 or newer
- Internet connection for NOAA API access
- Latitude/Longitude coordinates for location-specific features

## Supported Locations

- **Weather**: any NWS forecast office, inland or coastal
- **Surf**: the 36 coastal offices that issue Surf Zone Forecasts (SRF products), for example:
  - **East Coast**: Norfolk (AKQ), Boston (BOX), Wilmington (ILM), Charleston (CHS), Jacksonville (JAX), Miami (MFL)
  - **West Coast**: San Diego (SGX), Los Angeles (LOX), San Francisco (MTR), Portland (PQR), Eureka (EKA)
  - **Gulf Coast**: Mobile (MOB), Corpus Christi (CRP), Brownsville (BRO), Tallahassee (TAE)
  - **Great Lakes**: Chicago (LOT), Cleveland (CLE), Detroit (DTX), Milwaukee (MKX), Duluth (DLH)
  - **Pacific & Caribbean**: Honolulu (HFO), Guam (GUM), San Juan (SJU)
- **Nearshore marine**: the Great Lakes nearshore zones

*See the [full documentation](https://github.com/dawg-io/noaa_it_all#nws-forecast-offices) for every surf office and which have water temperature and surf height.*

## Update Frequency

Most entities, images included, update every 10 minutes with fresh data from NOAA. Meteor shower sensors recompute every 30 minutes. Eclipse sensors recompute hourly, more often as an eclipse approaches and every minute while one is under way.

## Links

- [Full Documentation](https://github.com/dawg-io/noaa_it_all)
- [Report Issues](https://github.com/dawg-io/noaa_it_all/issues)
- [Changelog](https://github.com/dawg-io/noaa_it_all/releases)
- [Full Changelog](https://github.com/dawg-io/noaa_it_all/blob/main/CHANGELOG.md)
