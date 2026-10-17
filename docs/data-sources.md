# Data Sources

- **Space Weather**: NOAA Space Weather Prediction Center
  - Aurora visibility forecasts, from the planetary K-index and its 3-day forecast, and
    geomagnetic storm data
  - Solar radiation storm alerts and classification (S1-S5 scale)
  - Real-time space weather alert monitoring
- **Meteor Showers**: bundled catalog, computed locally — **not** a NOAA feed
  - NOAA/NWS publish no meteor shower data of any kind: the NWS alert taxonomy covers terrestrial
    hazards, and the Space Weather Prediction Center covers geomagnetic activity, not meteors
  - Shower parameters come from the IMO Meteor Shower Calendar and the IAU Meteor Data Center
    working list, stored by **solar longitude** rather than by date
  - Peak times, radiant altitudes, moon phase and astronomical darkness are all computed on your
    machine using standard positional astronomy — no API call, no API key, no extra dependency,
    and it works with no internet connection at all
- **Eclipses**: computed locally — lunar eclipses from first principles, solar eclipses from NASA's
  Besselian elements for 2025–2075, bundled with the integration. *Eclipse Predictions by Fred
  Espenak, NASA's GSFC*
- **Hurricane Data**: National Hurricane Center (NHC) active storms and two-day outlook images,
  and NWS hurricane and tropical storm watches and warnings
- **Satellite Images**: GOES-19 Air Mass and GeoColor images from NOAA NESDIS STAR
- **NWS Active Alerts**: National Weather Service weather.gov API
  - Location-specific severe weather warnings and watches
  - Flood, winter storm, and environmental alerts
  - Real-time alert monitoring with automatic filtering
- **Rip Current/Surf Data**: NWS Surf Zone Forecasts (SRF products) for rip current risk,
  water temperature from NOAA CO-OPS tide stations, and surf height from NDBC buoys
- **Marine Forecasts**: NWS Nearshore Marine Forecasts (NSH products) from the Great Lakes offices,
  and the NWS active alerts for each marine zone (advisories, warnings and watches) for its Hazard sensor.
  The zones offered at setup come from `marine_zones.py`, generated from NWS by `scripts/build_marine_zones.py`
- **Forecasts, Radar and Discussion**: NWS forecasts and gridpoint data (weather.gov API), NEXRAD
  radar images from radar.weather.gov, and the office's Area Forecast Discussion (AFD)
- **Weather Observations**: National Weather Service observation stations (weather.gov API)
  - Real-time temperature, humidity, wind, pressure, and sky conditions
  - Metric values from NWS, shown in US customary units by default

## Update Frequency
Most entities, images included, update every 10 minutes to provide current conditions while
respecting API rate limits.

Meteor shower entities update every 30 minutes. They fetch nothing, so there is no rate limit to
respect — but the best-of-night result is stable for hours, so a slower cadence keeps the recorder
database smaller for no loss of accuracy.

Eclipse entities fetch nothing either. They recompute hourly, every 5 minutes in the 6 hours before
an eclipse, and every minute while one is under way.
