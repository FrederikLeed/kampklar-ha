# KampKlar for Home Assistant

<img src="custom_components/kampklar/brand/icon.svg" alt="KampKlar" width="110" align="right">

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Home Assistant custom integration for [DBU KampKlar](https://klubservice.dbu.dk/kampklar/), the activity
management used by Danish football clubs through DBU's "Fodbold" app. For each tracked child it brings the
upcoming activities, matches, sign-up status, call-ups and live match scores into Home Assistant, and lets
you sign up or off from an automation.

## Features

### Per tracked person

One device per child, with these entities:

| Entity | State | Notes |
|--------|-------|-------|
| **Next activity** (sensor) | Activity name | Attributes: type, start/end time, meeting time and place, team, sign-up status, subscriber count, sign-up deadline, is-open-for-signup |
| **Next match** (sensor) | "Home - Away" | Plus match id, stadium, field, row (tournament) and deadline. The venue as `stadium_address`, `latitude` and `longitude`, so a map card can show it |
| **Next call-up** (sensor) | Activity name | The next match or tournament the child is expected at, or unknown. That is *udtaget* where a coach picks the squad and *tilmeldt* where the team signs up instead (see [Two ways a team picks players](#two-ways-a-team-picks-players)). Same venue attributes as next match |
| **Pending signups** (sensor) | Count | Attribute `activities`: the list still awaiting a response |
| **Live match** (sensor) | "1 - 2" | During a match window: running minute, live result, event list (goals, cards), stadium |
| **Calendar** | Next event | All activities as calendar events. A match the child is on shows as `⭐ ...` so it stands out. Matches and DBU tournaments have the venue address as location |

### Venue and meeting time

The activity feed only names the stadium, so the integration looks up each activity's venue (address and
coordinates) with one extra request: per match for a match, and per stadium name in DBU's stadium register
for a DBU tournament (*stævne*), which has no match to ask about. It keeps the result for a week, also across restarts. At most
10 lookups run per update, together and nearest matches first, and one that takes over 10 seconds is tried
again later. A calendar event for a match gets the venue as its location, with the stadium name on the first
line and the address on the second (`Testby Stadion` then `Prøvevej 1, 1234 Testby`), the way Apple Calendar
writes a place. Its description looks like this:

```text
Mødetid: 09:45
Type: Kamp
Hold: U13 Piger
Status: Tilmeldt
Stadion: Testby Stadion, Prøvevej 1, 1234 Testby
Bane: Bane 2
Kort: https://maps.apple.com/?ll=56.123456,9.654321&q=Testby%20Stadion
```

The `Kort` link opens the map on a phone, and other tools can read the coordinates from it. When the team
meets somewhere other than the stadium, a `Mødested:` line after the times names that place.

DBU sometimes stores a meeting time with the wrong date; the integration keeps its time of day on the
activity's date. It ignores a meeting time that is not before the start, or that is exactly midnight (how DBU
writes a date without a time). The calendar and the next match and next call-up sensors use this repaired
meeting time. The next activity sensor shows `meeting_time` as DBU sent it, as in earlier versions.

Show the next venue on a map card:

```yaml
type: map
entities:
  - sensor.PERSON_next_match
```

### Services

- `kampklar.tilmeld` - sign a child up for an activity.
- `kampklar.afmeld` - sign a child off an activity.

Pick the child (its KampKlar device, `device_id`; several children are allowed). Leave `activity_id`
empty to use the child's next activity, or set it to a specific one (the `activity_id` attribute on the
child's sensors). The action can return which activity it changed:

```yaml
action: kampklar.tilmeld
data:
  device_id: <the child's KampKlar device>
response_variable: result
# result.results[0] -> {person, activity_id, activity, start_time, status}
```

The older form with `person_id` + `activity_id` still works.

### Options

Per entry, under Settings > Devices & Services > KampKlar > Configure:

- **Update interval**: how often activities are refreshed. While a match is live the integration polls
  faster on its own.
- **Start calendar events at the meeting time** (off by default): an activity with a meeting time starts
  its calendar event then, and the description adds `Kampstart: HH:MM` for matches or `Start: HH:MM` for
  other activities. Sensors keep the real start. Calendar triggers, the calendar's on state and anything
  that copies the calendar elsewhere or works out a travel time from it follow the meeting time.

## Installation

### HACS (recommended)

1. Open HACS, go to the three-dot menu > **Custom repositories**.
2. Add `https://github.com/FrederikLeed/kampklar-ha` with category **Integration**.
3. Install **KampKlar**, then restart Home Assistant.
4. Go to **Settings** > **Devices & Services** > **Add Integration** > **KampKlar**.

### Manual

Copy `custom_components/kampklar/` into your `config/custom_components/` directory and restart.

## Configuration

1. Log in with your DBU credentials (the same username and password as the Fodbold app).
2. Select which of the linked children to track.

Entity names follow your Home Assistant language (Danish and English are provided).

## Dashboard

A ready-made Lovelace view (activities, matches, call-ups, live score and a calendar per child) is in
[docs/dashboard-example.md](docs/dashboard-example.md).

## Two ways a team picks players

A DBU team activity runs in one of two modes, and only the counter text names which:

| Counter text | Mode | How far `signupStatusId` goes |
|---|---|---|
| `8 udtaget` | The coach picks a squad (*udtagelse*) | `4` Udtaget |
| `14 tilmeldte` | People sign up (*tilmelding*) | `2` Tilmeldt — nobody is ever udtaget |

The mode is per activity, not per team: the same team's practice matches often pick a squad while its
league matches ask for sign-ups. So "the child is playing" cannot mean udtaget everywhere. The
integration reads the mode off each activity and treats the strongest status that mode allows as being
on the team:

- **Next call-up** names that activity, whichever mode it is.
- **The calendar** marks its event with a star: `⭐ Gug B - AaB`. The same marker for both modes, so a
  single filter (`⭐ `) catches a child's matches whichever way the team picks them, and a relay that
  strips the filter is left with the activity's own name. Which of the two it was stays in the
  description's `Status:` line and in the `is_udtaget` and `is_playing` attributes.
- **Training never counts.** Everyone is signed up for training by default, so counting it would mark
  every week of the season.
- An activity whose counter text says neither counts only udtaget, as before 0.9.0.

Every activity sensor also exposes `selection_mode` (`udtagelse`, `tilmelding` or absent) and
`is_playing`, and the calendar exposes `is_playing`, `next_playing` and `next_playing_start` beside the
unchanged `is_udtaget`, `next_udtaget` and `next_udtaget_start`.


## Blueprint: notify on call-up

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2FFrederikLeed%2Fkampklar-ha%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Fkampklar%2Fudtaget.yaml)

[`blueprints/automation/kampklar/udtaget.yaml`](blueprints/automation/kampklar/udtaget.yaml) sends a
phone notification when a child is picked for a new match. Pick the child's "Next call-up"
sensor and the phone; it fires once per new call-up, not on restarts. Since 0.9.0 that sensor also
covers teams that sign up rather than pick a squad, so the blueprint fires for them too.

## Automations

Or write it yourself - notify when a child is called up for a match:

```yaml
automation:
  - alias: "KampKlar: called up"
    trigger:
      - platform: state
        entity_id: sensor.PERSON_next_call_up
        not_to:
          - unknown
          - unavailable
    action:
      - service: notify.mobile_app
        data:
          title: "Udtaget til kamp"
          message: "{{ states('sensor.PERSON_next_call_up') }}"
```

Remind about unanswered sign-ups:

```yaml
automation:
  - alias: "KampKlar: pending signups"
    trigger:
      - platform: numeric_state
        entity_id: sensor.PERSON_pending_signups
        above: 0
    action:
      - service: notify.mobile_app
        data:
          title: "KampKlar"
          message: >
            {{ state_attr('sensor.PERSON_pending_signups', 'activities') | join(', ') }} needs a response.
```

Replace `PERSON` with the child's entity slug (see Settings > Devices & Services > KampKlar).

## Troubleshooting

Settings > Devices & Services > KampKlar > three-dot menu > **Download diagnostics** gives a file you can
attach to an issue. Your username, password, user id, the children's names and ids, and the venues' street
addresses and coordinates are removed.

## Documentation

- [docs/api-reference.md](docs/api-reference.md) - the DBU app API this integration uses.
- [docs/reverse-engineering-findings.md](docs/reverse-engineering-findings.md) - the full reverse-engineering write-up.

## Roadmap

- League standings sensor (team position in the table).
- Attendance (who is coming) per activity.
- Extended match data (referee, kit colors).

See the [issues](https://github.com/FrederikLeed/kampklar-ha/issues) for status.

## Disclaimer

This is an unofficial, community-built integration. It is not made, backed or approved by DBU
(Dansk Boldspil-Union), and "KampKlar" and "Fodbold" belong to them. It talks to the same undocumented
API as DBU's own app, using your own account, so DBU can change or block it at any time. The write
actions (`kampklar.tilmeld` and `kampklar.afmeld`) change real sign-ups for a real club, exactly as
pressing the button in the app would; use them on your own family's activities only.

## License

MIT
