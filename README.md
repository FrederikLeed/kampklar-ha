# KampKlar for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Test](https://github.com/FrederikLeed/kampklar-ha/actions/workflows/test.yml/badge.svg)](https://github.com/FrederikLeed/kampklar-ha/actions/workflows/test.yml)
[![Lint](https://github.com/FrederikLeed/kampklar-ha/actions/workflows/lint.yml/badge.svg)](https://github.com/FrederikLeed/kampklar-ha/actions/workflows/lint.yml)

Home Assistant custom integration for [DBU KampKlar](https://klubservice.dbu.dk/kampklar/) — activity management for Danish football clubs.

The integration fetches data from DBU's "Fodbold" app and exposes upcoming matches, training sessions, and signup status as sensors in Home Assistant.

## Features

### Sensors (per tracked person)

| Sensor | State | Attributes |
|--------|-------|------------|
| **Next activity** | Activity name | Type, start/end time, meeting time/place, team, signup status, subscriber count |
| **Next match** | "Home - Away" | All of the above + match ID, stadium, field |
| **Pending signups** | Count of unanswered | List of activity names awaiting response |

### Config flow

Setup via the Home Assistant UI:

1. Log in with your DBU credentials (username + password)
2. Select which persons to track (children linked to your account)

### Example: Sensor card

```
┌──────────────────────────────────────────┐
│ ⚽ Player Name                           │
├──────────────────────────────────────────┤
│ Next activity    Team A - Team B         │
│   Type           Kamp                    │
│   Start          2026-03-14 11:00        │
│   Meeting place  Sportsvej 1, 9000       │
│   Team           U14 Drenge              │
│   Signup         Tilmeldt                │
│   Subscribers    13                      │
├──────────────────────────────────────────┤
│ Next match       Team A - Team B         │
│   Stadium        Example Stadion         │
│   Field          Bane 1                  │
├──────────────────────────────────────────┤
│ Pending signups  2                       │
│   Activities     Træning, Træning 2      │
└──────────────────────────────────────────┘
```

### Example: Automation

```yaml
automation:
  - alias: "Remind about unanswered signups"
    trigger:
      - platform: numeric_state
        entity_id: sensor.player_name_afventende_tilmeldinger
        above: 0
    action:
      - service: notify.mobile_app
        data:
          title: "KampKlar"
          message: >
            {{ state_attr('sensor.player_name_afventende_tilmeldinger', 'activities') | join(', ') }}
            needs a response!
```

## Installation

### HACS (recommended)

1. Open HACS in Home Assistant
2. Click **Integrations** > **Custom repositories**
3. Add `https://github.com/FrederikLeed/kampklar-ha` as **Integration**
4. Install **KampKlar**
5. Restart Home Assistant
6. Go to **Settings** > **Devices & Services** > **Add Integration** > **KampKlar**

### Manual installation

Copy `custom_components/kampklar/` to your `config/custom_components/` directory.

## Roadmap

- **Calendar entity**: All team activities as HA calendar events
- **Service calls**: Sign up / sign off for activities from HA
- **League standings**: Sensor with team position in the table
- **Extended match data**: GPS coordinates, referee, kit colors

See the [project board](https://github.com/users/FrederikLeed/projects/1) for full status.

## License

MIT
