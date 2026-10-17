# Troubleshooting & FAQ

## Entities Not Appearing
- Ensure you completed setup with valid latitude and longitude
- Surf entities are in their own `NOAA Surf` entry, space weather, aurora, meteor shower and eclipse entities in a `NOAA Space` entry, and hurricane and satellite entities in the `NOAA Hurricane` entry. If you chose **No surf data** or **No space data**, or deleted the hurricane entry, add them back with **Add entry**
- A new surf entry only gets Water Temperature and Surf Height if its office has a tide station or buoy; see [NWS Forecast Offices](forecast-offices.md)
- After upgrading, reload the Home Assistant page so the new setup screens show
- Check **Settings** → **System** → **Logs** for any error messages from `noaa_it_all`

## Data Not Updating
- Check sensor attributes for error messages
- Verify internet connectivity from your Home Assistant instance
- NOAA APIs occasionally experience temporary outages; sensors will recover automatically
- Check an observation sensor's `timestamp` attribute: it's when that reading was made. NWS often publishes observations tens of minutes late, and during an outage the last one stays for up to an hour after the last successful refresh

## Incorrect or Missing Weather Data
- Weather observations are pulled from the nearest NWS station to your configured coordinates. If it stops answering or has nothing from the last two hours, the next nearest of up to three is used instead, and a warning naming the skipped station is logged
- Confirm your latitude and longitude are accurate (you can change them with **Configure** on the `NOAA Weather` entry under **Settings** → **Devices & services** → **NOAA It All**)
- If no nearby station answers, the last observation stays for up to an hour after the last successful refresh, with a warning naming each station tried and why it failed. After an hour, observation entities show `unavailable` and the log line `Error fetching NOAA Observations data` names the stations again
- A sensor shows `unknown` only if none of the station's observations in the last two hours has that field
- NOAA It All shows US customary units, °F, mph, inHg, miles and feet, in any Home Assistant. For another unit, pick it in the entity's settings, which it then keeps after a restart and whatever the unit system. That is the way to change one: changing the unit system with its option to update existing entities sets the unit of every sensor in Home Assistant again, other integrations' too
- In a metric Home Assistant, sensors added under 0.10.3 or 0.11.0 keep the metric units they show. Before 0.11.1, a restart after a unit-system change could set a sensor back to its old unit, which it keeps until you pick one in its settings
- An entry deleted and added again within 30 days gets its entities' old settings back from Home Assistant. In a metric Home Assistant, sensors added before 0.11.1 then show metric units until the next restart and US customary ones after it, and the weather entity follows the unit system. Pick the units you want in their settings

## Binary Sensors Always Off
- The alert binary sensors only turn on while NWS has an active alert for your coordinates, and Unsafe to Swim only when the Surf Zone Forecast gives a high rip current risk. Their `alerts` and `risk_level` attributes show what they're reading
- Meteor Shower Active, Eclipse Visible Now and Eclipse Coming Up are off most of the year by design

## Automation Not Triggering
- Verify the entity IDs in the automation match actual entities; see [Entity Naming Conventions](entity-naming.md), especially the [exceptions](entity-naming.md#exceptions-to-the-pattern)
- Open the automation and check its trace (**⋮ → Traces**) to see what triggered and which condition stopped it
- Ensure conditions are not blocking the automation

## Integration Fails to Load
- Confirm Home Assistant version is **2026.3.0 or newer**
- Review Home Assistant logs for specific import or configuration errors

## "icon not available" in HACS
- HACS shows "icon not available" for NOAA It All in its repository list and on its entry under **Settings** → **Updates**. This is a HACS bug, not a problem with your install. HACS still loads integration icons from the public Home Assistant brands site, which stopped accepting custom integrations in Home Assistant 2026.3. The icon ships in the integration's `brand/` folder, and Home Assistant itself shows it (for example under **Settings** → **Devices & services**) once the integration is installed. HACS is tracking the fix in [HACS issue 5171](https://github.com/hacs/integration/issues/5171) and [HACS frontend PR 937](https://github.com/hacs/frontend/pull/937).
- The HACS list can't be changed from this integration. To show the icon on the **Settings** → **Updates** entry, add this to `configuration.yaml` and restart Home Assistant. If you renamed the HACS update entity, use its ID from **Settings** → **Entities**.

```yaml
homeassistant:
  customize:
    update.noaa_it_all_update:
      entity_picture: /api/brands/integration/noaa_it_all/icon.png
```

## FAQ

**Q: Can I use this integration without configuring latitude/longitude?**
A: No. Setup requires latitude and longitude. They are pre-filled from your Home Assistant Home zone when one is set, and you can enter a different location instead. YAML setup has been removed and creates no entities (see [Legacy YAML Configuration](configuration.md#legacy-yaml-configuration)).

**Q: How do I find my NWS forecast office code?**
A: You don't need to: setup asks NWS which office covers your coordinates and pre-selects it. To look one up yourself, search for your location on [weather.gov](https://www.weather.gov/); the three-letter office code appears in the URL of your local forecast page (e.g., `forecast.weather.gov/MapClick.php?CityName=San+Diego&state=CA&site=SGX`).

**Q: Why don't I see aurora predictions?**
A: The aurora sensors are on the `NOAA {OFFICE} Space` device of a `NOAA Space` entry. Aurora is only visible at high Kp levels for southern latitudes — check the Planetary K-index value and the `magnetic_latitude` and `required_kp` attributes of Aurora Visibility Probability.

**Q: How often does data update?**
A: Most entities update every 10 minutes; see [Update Frequency](data-sources.md#update-frequency).

**Q: Are UV Index readings available?**
A: No. UV Index is not provided through NWS/NOAA APIs and cannot be included in this integration.

**Q: Where can I report bugs or request features?**
A: Please open an issue on [GitHub](https://github.com/dawg-io/noaa_it_all/issues).
