# Automation and Script Examples

Every example uses Home Assistant's current automation syntax (`triggers`, `conditions` and `actions`). To use one, create an automation, open **⋮ → Edit in YAML**, and paste it in. In `automations.yaml`, add it as a list item instead (`- alias: …`, with the rest indented under it).

The examples use the `ILM` office; see [Entity Naming Conventions](entity-naming.md) to adapt them. Replace `notify.mobile_app_your_phone` with your own notify action, and the light, climate, fan and speaker entities with yours. Speech uses `tts.speak` with the Google Translate text-to-speech entity, `tts.google_translate_en_com`; use any text-to-speech entity you have.

## Binary Sensor Triggers for Safety Alerts

### Rip Current Safety Alert
```yaml
alias: "Rip Current Warning"
description: "Alert when rip current conditions become dangerous"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_surf_unsafe_to_swim
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "⚠️ Beach Safety Alert"
      message: >-
        Rip current risk is {{ states('sensor.noaa_ilm_surf_rip_current_risk') }} -
        swimming not recommended!
      data:
        priority: high
        tag: rip-current-alert
```

## Weather Alert Notifications

### Severe Weather Alert Notification
Sends the alert's name and description, then reads its headline out on a speaker. The binary sensor's `alerts` attribute lists only the severe alerts, so the first one is the one that turned it on.
```yaml
alias: "Severe Weather Alert"
description: "Immediate notification for severe weather warnings"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_weather_severe_weather_alert
    to: "on"
actions:
  - variables:
      alert: >-
        {{ (state_attr('binary_sensor.noaa_ilm_weather_severe_weather_alert', 'alerts') or [{}])[0] }}
  - action: notify.mobile_app_your_phone
    data:
      title: "⚠️ {{ alert.get('event', 'Severe weather alert') }}"
      message: >-
        {{ alert.get('description', 'See the NWS alert for details.') | replace('\n', ' ') }}
      data:
        priority: high
        notification_icon: mdi:weather-lightning-rainy
  - action: tts.speak
    target:
      entity_id: tts.google_translate_en_com
    data:
      media_player_entity_id: media_player.home_speaker
      message: "{{ alert.get('headline', 'A severe weather alert is active.') }}"
```

### Winter Storm Alert with Light Flash
```yaml
alias: "Winter Storm Alert"
description: "Visual and mobile notification for winter weather"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_weather_flood_winter_alert
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "❄️ Winter Weather Alert"
      message: >-
        {{ (state_attr('binary_sensor.noaa_ilm_weather_flood_winter_alert', 'alerts') or [{}])[0].get('event', 'Winter storm or flood alert') }}
        is active for your area.
      data:
        notification_icon: mdi:weather-snowy-heavy
  - action: light.turn_on
    target:
      entity_id: light.living_room
    data:
      flash: long
      rgb_color: [0, 100, 255]
```

### Heat Advisory with Thermostat Adjustment
```yaml
alias: "Heat Advisory - Adjust Thermostat"
description: "Auto-adjust cooling when a heat advisory is active"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_weather_heat_air_quality_alert
    to: "on"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "🔥 Heat Advisory"
      message: "Heat advisory or air quality alert active!"
  - action: climate.set_temperature
    target:
      entity_id: climate.home
    data:
      temperature: 72
  - action: fan.turn_on
    target:
      entity_id: fan.bedroom
```

## Space Weather Monitoring

### Aurora Alert for Northern Locations
```yaml
alias: "Aurora Alert - High Probability"
description: "Notify when aurora visibility probability is high after dark"
triggers:
  - trigger: numeric_state
    entity_id: sensor.noaa_ilm_space_aurora_visibility_probability
    above: 50
conditions:
  - condition: state
    entity_id: sun.sun
    state: below_horizon
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "🌌 Aurora Alert!"
      message: >-
        Aurora visibility probability is
        {{ states('sensor.noaa_ilm_space_aurora_visibility_probability') }}%!
        Expected duration: {{ states('sensor.noaa_ilm_space_aurora_duration') }} hours.
      data:
        notification_icon: mdi:weather-night
```

### Geomagnetic Storm Notification
A Kp of 5 or more is a geomagnetic storm (G1 and up).
```yaml
alias: "Geomagnetic Storm Alert"
description: "Notify when the Kp index reaches storm level"
triggers:
  - trigger: numeric_state
    entity_id: sensor.noaa_ilm_space_planetary_k_index
    above: 4
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "⚡ Geomagnetic Storm"
      message: >-
        Kp index {{ states('sensor.noaa_ilm_space_planetary_k_index') }}:
        {{ states('sensor.noaa_ilm_space_geomagnetic_storm_interpretation') }}
        (Dst {{ states('sensor.noaa_ilm_space_geomagnetic_storm') }} nT).
      data:
        notification_icon: mdi:solar-power
```

### Meteor Shower Tonight
```yaml
alias: "Meteor Shower Tonight"
description: "Notify in the early evening when a shower is worth staying up for"
triggers:
  - trigger: time
    at: "19:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.noaa_ilm_space_meteor_shower_active
    state: "on"
actions:
  - variables:
      s: binary_sensor.noaa_ilm_space_meteor_shower_active
  - action: notify.mobile_app_your_phone
    data:
      title: "☄️ {{ state_attr(s, 'shower') }} tonight"
      message: >-
        Up to {{ state_attr(s, 'expected_per_hour') }} meteors/hour. Best viewing
        {{ as_timestamp(state_attr(s, 'best_window_start')) | timestamp_custom('%-I:%M %p') }} to
        {{ as_timestamp(state_attr(s, 'best_window_end')) | timestamp_custom('%-I:%M %p') }}.
        Conditions: {{ state_attr(s, 'rating') }}.
      data:
        notification_icon: mdi:meteor
```

### Wake Me for the Peak
```yaml
alias: "Meteor Shower Peak Reminder"
description: "Alert the evening before a major shower peaks"
triggers:
  - trigger: time
    at: "20:00:00"
conditions:
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_space_next_meteor_shower
    attribute: days_until
    below: 1.5
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_space_next_meteor_shower
    attribute: zhr_max
    above: 20
actions:
  - variables:
      s: sensor.noaa_ilm_space_next_meteor_shower
  - action: notify.mobile_app_your_phone
    data:
      title: "☄️ {{ states(s) }} peaks soon"
      message: >-
        Peak {{ as_timestamp(state_attr(s, 'peak_local')) | timestamp_custom('%A %-I:%M %p') }},
        up to {{ state_attr(s, 'zhr_max') }} meteors/hour under ideal conditions.
        Radiant in {{ state_attr(s, 'constellation') }}.
```

### Go Outside, the Eclipse Is Starting
Fires an hour before first contact. While the binary sensor is on, its attributes describe the eclipse, including the eye-safety warning.
```yaml
alias: "Eclipse Starting"
description: "Fires an hour before first contact, and reads the eye-safety warning out"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_space_eclipse_visible_now
    to: "on"
actions:
  - variables:
      s: binary_sensor.noaa_ilm_space_eclipse_visible_now
  - action: notify.mobile_app_your_phone
    data:
      title: "🌑 {{ state_attr(s, 'eclipse') }}"
      message: >-
        {{ state_attr(s, 'disc_covered') }}% covered from here. Watchable from
        {{ as_timestamp(states('sensor.noaa_ilm_space_next_eclipse_time')) | timestamp_custom('%-I:%M %p') }},
        maximum {{ as_timestamp(state_attr(s, 'maximum_local')) | timestamp_custom('%-I:%M %p') }}
        — look {{ state_attr(s, 'look_towards') }}.
        {% if state_attr(s, 'eye_protection_required') %}⚠️ {{ state_attr(s, 'eye_safety') }}{% endif %}
      data:
        notification_icon: mdi:weather-sunny-alert
```

### Order the Eclipse Glasses
```yaml
alias: "Eclipse Coming Up"
description: "Two weeks' warning for an eclipse actually worth planning around"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_space_eclipse_coming_up
    to: "on"
actions:
  - variables:
      s: binary_sensor.noaa_ilm_space_eclipse_coming_up
  - action: notify.mobile_app_your_phone
    data:
      title: >-
        🌑 {{ state_attr(s, 'eclipse') }} in {{ state_attr(s, 'days_until') | round(0) | int }} days
      message: >-
        {{ state_attr(s, 'date') }}: {{ state_attr(s, 'disc_covered') }}% covered from here
        ({{ state_attr(s, 'rating') }}).
        {% if state_attr(s, 'eye_protection_required') %}Order ISO 12312-2 eclipse glasses now.{% endif %}
```

### Remind Me an Hour Before
A timestamp sensor can be used directly as a time trigger, offset and all — no templating, no polling. This is what the Next Eclipse Time entity is for.
```yaml
alias: "Eclipse Hour Warning"
description: "An hour before the eclipse becomes watchable from here"
triggers:
  - trigger: time
    at:
      entity_id: sensor.noaa_ilm_space_next_eclipse_time
      offset: "-01:00:00"
actions:
  - variables:
      s: sensor.noaa_ilm_space_next_eclipse_time
  - action: notify.mobile_app_your_phone
    data:
      title: "🌑 Eclipse in an hour"
      message: >-
        {{ state_attr(s, 'eclipse') }}: {{ state_attr(s, 'disc_covered') }}% covered,
        look {{ state_attr(s, 'look_towards') }}.
```

### Only Bother if the Sky Is Clear
The eclipse entities know nothing about cloud on purpose, so that the percentages stay correct for an eclipse fifty years out. Pair them with the cloud cover sensor yourself.
```yaml
alias: "Eclipse Worth Watching"
description: "Only announce the eclipse if the sky is mostly clear"
triggers:
  - trigger: state
    entity_id: binary_sensor.noaa_ilm_space_eclipse_visible_now
    to: "on"
conditions:
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_weather_cloud_cover
    below: 40
actions:
  - variables:
      s: binary_sensor.noaa_ilm_space_eclipse_visible_now
  - action: notify.mobile_app_your_phone
    data:
      title: "🌑 Clear skies for the eclipse"
      message: >-
        {{ state_attr(s, 'eclipse') }}, {{ state_attr(s, 'disc_covered') }}% covered,
        and only {{ states('sensor.noaa_ilm_weather_cloud_cover') }}% cloud.
```

## Multi-Condition Automations

### Safe Beach Day Notification
```yaml
alias: "Safe Beach Day Alert"
description: "Notify when conditions are good for the beach"
triggers:
  - trigger: time
    at: "08:00:00"
conditions:
  - condition: state
    entity_id: binary_sensor.noaa_ilm_surf_unsafe_to_swim
    state: "off"
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_weather_temperature
    above: 75  # °F; 24 for °C
  - condition: numeric_state
    entity_id: sensor.noaa_ilm_weather_wind_speed
    below: 15  # mph; 24 for km/h
  - condition: state
    entity_id: binary_sensor.noaa_ilm_weather_active_alerts
    state: "off"
actions:
  - action: notify.mobile_app_your_phone
    data:
      title: "🏖️ Perfect Beach Day!"
      message: >-
        Temperature {{ states('sensor.noaa_ilm_weather_temperature', rounded=True, with_unit=True) }},
        rip current risk {{ states('sensor.noaa_ilm_surf_rip_current_risk') }},
        surf {{ states('sensor.noaa_ilm_surf_surf_height') }} ft,
        water {{ states('sensor.noaa_ilm_surf_water_temperature') }}°F.
```

### Severe Weather Preparation
```yaml
alias: "Severe Weather Preparation"
description: "Close up and warn everyone when a severe or flood/winter alert starts"
triggers:
  - trigger: state
    entity_id:
      - binary_sensor.noaa_ilm_weather_severe_weather_alert
      - binary_sensor.noaa_ilm_weather_flood_winter_alert
    to: "on"
actions:
  # Close automated blinds/shades
  - action: cover.close_cover
    target:
      entity_id: all
  # Turn on weather alert lights
  - action: light.turn_on
    target:
      area_id: living_room
    data:
      brightness: 255
  # Tell everyone which alerts are active
  - action: notify.family_group
    data:
      title: "🚨 Severe Weather - Take Action"
      message: >-
        {{ state_attr('sensor.noaa_ilm_weather_active_nws_alerts', 'alert_count') }} NWS alert(s) active:
        {{ (state_attr('sensor.noaa_ilm_weather_active_nws_alerts', 'alerts') or []) | map(attribute='event') | unique | join(', ') }}
      data:
        priority: high
        ttl: 0
  # Announce on speakers
  - action: tts.speak
    target:
      entity_id: tts.google_translate_en_com
    data:
      media_player_entity_id: media_player.all_speakers
      message: "Attention: severe weather alerts are now active for your area."
```

## Script Examples

Each example is an entry for `scripts.yaml`. To use one in the script editor, create a script, open **⋮ → Edit in YAML**, and paste the part under the script's name.

### Check Current Conditions Script
```yaml
check_weather_conditions:
  alias: "Check Current Weather Conditions"
  description: "Announce current weather conditions and alerts"
  sequence:
    - action: tts.speak
      target:
        entity_id: tts.google_translate_en_com
      data:
        media_player_entity_id: media_player.home_speaker
        message: >-
          Current conditions: temperature {{ states('sensor.noaa_ilm_weather_temperature', rounded=True) }} degrees,
          feels like {{ states('sensor.noaa_ilm_weather_feels_like', rounded=True) }} degrees.
          {{ states('sensor.noaa_ilm_weather_sky_conditions') }} skies.
          Wind {{ states('sensor.noaa_ilm_weather_wind_speed', rounded=True, with_unit=True) }} from the
          {{ state_attr('sensor.noaa_ilm_weather_wind_direction', 'cardinal_direction') }}.
          {% if is_state('binary_sensor.noaa_ilm_weather_active_alerts', 'on') %}
          {{ state_attr('sensor.noaa_ilm_weather_active_nws_alerts', 'alert_count') }} weather alerts are active.
          {% endif %}
```

### Space Weather Report
```yaml
space_weather_report:
  alias: "Space Weather Report"
  description: "Send the current space weather conditions"
  sequence:
    - action: notify.mobile_app_your_phone
      data:
        title: "🌌 Space Weather Report"
        message: >-
          Kp index: {{ states('sensor.noaa_ilm_space_planetary_k_index') }}
          ({{ states('sensor.noaa_ilm_space_planetary_k_index_rating') }}).
          Geomagnetic storm: {{ states('sensor.noaa_ilm_space_geomagnetic_storm_interpretation') }}.
          {% if states('sensor.noaa_ilm_space_aurora_visibility_probability') | int(0) > 0 %}
          Aurora visibility: {{ states('sensor.noaa_ilm_space_aurora_visibility_probability') }}%.
          {% endif %}
          {% set aurora = states('sensor.noaa_ilm_space_aurora_next_time') | as_datetime(None) %}
          {% if aurora %}
          Aurora may be visible from {{ (aurora | as_local).strftime('%a %-I:%M %p') }}.
          {% endif %}
          Solar radiation alerts: {{ states('sensor.noaa_ilm_space_solar_radiation_storm_alerts') }}.
```

### Morning Weather Briefing
Phone notifications are plain text, so the briefing uses line breaks and emoji rather than markdown.
```yaml
morning_weather_briefing:
  alias: "Morning Weather Briefing"
  description: "Morning weather, beach and alert briefing"
  sequence:
    - action: notify.mobile_app_your_phone
      data:
        title: "☀️ Good Morning - Weather Briefing"
        message: |-
          🌡️ {{ states('sensor.noaa_ilm_weather_temperature', rounded=True, with_unit=True) }} (feels like {{ states('sensor.noaa_ilm_weather_feels_like', rounded=True, with_unit=True) }})
          💨 Wind {{ states('sensor.noaa_ilm_weather_wind_speed', rounded=True, with_unit=True) }}
          ☁️ {{ states('sensor.noaa_ilm_weather_sky_conditions') }}
          🌊 Surf {{ states('sensor.noaa_ilm_surf_surf_height') }} ft, rip current risk {{ states('sensor.noaa_ilm_surf_rip_current_risk') }}
          🏊 Water {{ states('sensor.noaa_ilm_surf_water_temperature') }}°F
          {% if is_state('binary_sensor.noaa_ilm_weather_active_alerts', 'on') -%}
          ⚠️ {{ state_attr('sensor.noaa_ilm_weather_active_nws_alerts', 'alert_count') }} active weather alert(s)
          {%- else -%}
          ✅ No active weather alerts
          {%- endif %}
```
