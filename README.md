# NOAA It All - Solar Data, Hurricane Tracking, and Location-Specific Rip Current Forecasts

> [!NOTE]
> This integration and its developer are independent and are not affiliated, endorsed, or sponsored by NOAA in any way.


[![HACS Default](https://img.shields.io/badge/HACS-Default-41BDF5.svg?style=for-the-badge)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/dawg-io/noaa_it_all?style=for-the-badge&color=green)](https://github.com/dawg-io/noaa_it_all/releases)
[![License](https://img.shields.io/github/license/dawg-io/noaa_it_all?style=for-the-badge&color=green)](https://github.com/dawg-io/noaa_it_all/blob/main/LICENSE)

<p align="center">
  <img src="https://raw.githubusercontent.com/dawg-io/noaa_it_all/main/icon.png" width="120" alt="NOAA It All"><br>
</p>

This Home Assistant integration brings NOAA and National Weather Service data into Home Assistant as sensors, binary sensors, images and a weather entity:

- **Weather for your location**: observations, forecasts, NWS alerts, radar and the forecast discussion, from any NWS forecast office
- **Surf for any coast**: rip current risk, surf height and water temperature from the coastal office you choose
- **Nearshore marine forecasts** for Great Lakes marine zones
- **Hurricanes**: NHC activity and outlooks, and GOES satellite images
- **Space**: geomagnetic activity, aurora, solar radiation storms, meteor showers and eclipses, worked out for where you are

> example using mushroom-template-card

<p align="center">
<img width="429" height="221" alt="Forecast card showing Today and Tonight with icons, temperatures and the NWS detailed forecast" src="https://github.com/user-attachments/assets/9ba0e041-afbc-4dcd-8457-5a09dc33814d" />


</p>

## Installation

Requires Home Assistant **2026.3.0** or newer.

### HACS Installation (Recommended)
1. Open HACS in Home Assistant
2. Search for "NOAA It All" and open it
3. Click **Download**
4. Restart Home Assistant

### Manual Installation
1. Download the latest release from [GitHub Releases](https://github.com/dawg-io/noaa_it_all/releases)
2. Copy the `custom_components/noaa_it_all` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Getting Started

1. Go to **Settings** → **Devices & services** → **Add integration**, search for "NOAA It All", and choose **Weather for a location**.
2. Enter the **latitude and longitude**. They're pre-filled from your Home zone.
3. Select your **NWS Forecast Office**. The office NWS names for your location is pre-selected.
4. Choose a **surf forecast office** for the coast you want rip current risk, surf height and water temperature for, or **No surf data**.
5. Choose **Space** for the office, or **No space data**.
6. Assign the device to an area, or choose **Skip and finish**.

The first location also adds the `NOAA Hurricane` entry. Use **Add entry** on the NOAA It All page for more beaches, Great Lakes marine zones, Space for another location, or hurricanes. [Setup and configuration](docs/configuration.md) walks through each step with screenshots, and covers **Configure**, the radar loop and upgrading from 0.9.x or 0.7.x.

## What You Get

Each kind of entry has one device, listed under **Settings → Devices & services → NOAA It All**:

| Entry | Device | Entities |
|---|---|---|
| Weather for a location | `NOAA ILM Weather` | Observations, extended and hourly forecasts, a weather entity, NWS alerts, cloud cover, the forecast discussion, and a radar image, timestamp and animated loop (22) |
| Surf forecast for a coast | `NOAA ILM Surf` | Rip current risk and Unsafe to Swim, plus water temperature and surf height where the office has a tide station or buoy (2 to 4) |
| Nearshore marine forecast for a Great Lakes zone | `NOAA LMZ741 Marine` | The current forecast period and its forecast (2) |
| Space weather, aurora, meteor showers and eclipses | `NOAA ILM Space` | Kp index, geomagnetic and solar radiation storms, aurora, meteor shower and eclipse forecasts for the location, and SWPC images (20) |
| Hurricanes and satellite images | `NOAA Hurricane` | NHC activity and watches and warnings, Atlantic and East Pacific outlooks, and GOES satellite images (6) |

Entity IDs are built from the device name, such as `sensor.noaa_ilm_weather_temperature` for the Wilmington, NC (ILM) office. See [Entity Naming Conventions](docs/entity-naming.md) for the exceptions.

## Documentation

- [Setup and configuration](docs/configuration.md): adding locations, beaches, marine zones, Space and hurricanes; **Configure**; radar loop history; upgrading
- [NWS Forecast Offices](docs/forecast-offices.md): which offices give surf, water temperature, surf height and marine forecasts
- [Devices](docs/devices.md) and [Entities](docs/entities.md): every device and entity, with their states and attributes
- [Entity Naming Conventions](docs/entity-naming.md): how entity IDs are built, and IDs that changed
- [Automation and Script Examples](docs/automations.md)
- [Dashboard Card Examples](docs/dashboards.md), with screenshots
- [Troubleshooting & FAQ](docs/troubleshooting.md)
- [Data Sources](docs/data-sources.md) and update frequency

## Support

Please report bugs and request features on [GitHub](https://github.com/dawg-io/noaa_it_all/issues).

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for a full history of changes and releases.
