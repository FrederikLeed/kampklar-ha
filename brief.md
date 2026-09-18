---
project: kampklar-ha
repo: https://github.com/FrederikLeed/kampklar-ha
updated: 2026-09-18
status: active
---

# KampKlar for Home Assistant

Custom integration that brings DBU KampKlar (the "Fodbold" app's activity management for Danish
football clubs) into Home Assistant. Per tracked person (the children linked to the DBU account) it
creates sensors (next activity, next match, next call-up, pending signups, live match) and a calendar.

## Current state

- v0.9.1 (2026-09-18): the calendar marker is the star alone (`⭐ Gug B - AaB`), not `⭐ Udtaget: ` or
  `⭐ Tilmeldt: `. A relay that filters on `⭐ ` and strips the filter is then left with the activity's own
  name instead of `Tilmeldt: Gug B - AaB`, and one filter still covers both modes. Whether the child was
  picked or signed up stays in the description's `Status:` line and in the `is_udtaget` / `is_playing`
  attributes, which is where automations read it. Anyone relaying with a `⭐ Udtaget: ` filter must widen it
  to `⭐ ` before upgrading, or the relay stops matching and deletes what it wrote.
- v0.9.0 (2026-09-18): a call-up is not the only way a child gets on a team. A DBU team activity runs in
  one of two modes and only `subscribedText` names which: "8 udtaget" means the coach picks a squad,
  "14 tilmeldte" means people sign up, and on a sign-up activity `signupStatusId` never reaches 4, so
  2 (Tilmeldt) is the strongest answer there is. The mode is per activity, not per team - the same team's
  practice matches picked a squad ("0 udtaget") while its league matches asked for sign-ups. Before this,
  a child on a sign-up team was never "udtaget": the call-up sensor stayed unknown, the calendar wrote no
  marker, and Calendar Relay's `⭐ Udtaget: ` filter matched nothing, so none of his matches ever reached
  the family calendar. Now `Activity.selection_mode` reads the mode off the counter text and
  `const.is_playing` treats the strongest status that mode allows as being on the team. Next call-up names
  that activity in either mode; the calendar marks it `⭐ Udtaget: ` or `⭐ Tilmeldt: `, both starting with
  the star so one relay filter (`⭐ `) catches either, and the word stays true to what DBU says. Training
  never counts - everyone is tilmeldt to training, which would mark every week. An activity whose counter
  text says neither keeps the pre-0.9 rule (udtaget only). New attributes: `selection_mode` and
  `is_playing` on the activity sensors, `is_playing`, `next_playing` and `next_playing_start` on the
  calendar, beside the unchanged `is_udtaget` / `next_udtaget`. Verified against the live account and
  cross-checked with `TeamActivity/GetListTeamActivityTeamMemberPerson`, which agreed with the person's
  own feed on every activity.
- v0.8.1 (2026-09-16): repo tidy-up for public use. The workspace notes under `.claude/` are no longer
  tracked (they are in `.gitignore`), CLAUDE.md keeps only the conventions, the pre-push checks and the
  no-personal-data rule, and the doc and test examples that had grown real venue names and addresses are
  back to invented "Testby" data. README gained a disclaimer: unofficial, not backed by DBU, and the
  sign-up actions change real club data.
- v0.8.0 (2026-09-16): venues for stævner. A DBU stævne (typeId 7) has no match object, only
  `stadiumRound.stadiumName`, so that name is looked up in DBU's stadium register
  (`Stadium/GetListStadiumSearch?name=`), which answers with address, zip, city and coordinates. The
  search matches anywhere in a name or city, so the row whose name equals the searched one wins, with a
  single hit as fallback; an empty name is never sent (the register would answer with all ~3,900
  stadiums). Lookups share the venue cache, store, age, cap, timeout and retry backoff with match
  lookups, keyed by the case-folded stadium name instead of match and pool id, so two children at the
  same stævne cost one call. The stævne then gets the same calendar LOCATION, `Kort:` map link and
  `stadium_address`/`latitude`/`longitude` sensor attributes as a match, and Calendar Relay can turn
  them into an Apple structured location with travel time. When the register does not place the
  stadium, its bare name is still used as the calendar location.
- v0.7.0 (2026-09-15, issue #42): stadium address and meeting time. Each match's venue (address, zip,
  city, coordinates, field) comes from `Match/GetMatch`, one call per (match id, pool id), cached on the
  coordinator and in a `helpers.storage.Store` (`kampklar.venues.<entry_id>`, loaded in the coordinator's
  `_async_setup`, deleted in `async_remove_entry`). It is fetched again after 7 days or when the
  activity's stadium name changes. A failed lookup never fails the refresh; it is retried after 15 min,
  doubling up to 24 h, and a venue fetched earlier for the same stadium stays meanwhile. Due lookups run
  together, at most 10 per refresh (nearest matches first, the rest next refresh without a failure), each
  cut off after 10 s: HA's shared aiohttp session sets no timeout, so aiohttp's 300 s default would apply
  and stall setup and live polling. The coordinator stops saving the store once shut down, so a refresh
  that finishes after the entry is removed does not write the deleted file back. A stadium with only a
  name (no address, zip, city or coordinates) is no venue. Calendar events for matches use
  `MatchVenue.location_text` as LOCATION: the stadium name, a line break, then "address, zip city", which
  is how Apple Calendar writes a place and what Calendar Relay turns into the structured location's title and
  address (the one-line `formatted_address` stays in the description and the sensors). They start the
  description with `Mødetid: HH:MM`, add `Mødested:` when the meeting place
  is not the venue, and add a `Kort:` Apple Maps link with the coordinates. The calendar's state follows
  the event that starts first, which with the option on can be a later activity's meeting. New option
  "Start calendar events at the meeting time" (off by default). Next match and next call-up sensors expose
  `stadium_address`, `latitude`, `longitude` and the repaired `meeting_time`; next activity keeps the raw
  `meeting_time` as in 0.6.1. A meeting time at exactly 00:00 (DBU's date-only form) is ignored.
  Diagnostics leave out venue address and coordinates.
- v0.6.1 (2026-09-15): services.yaml fix. Non-entity services may not use device filters on `target`
  (hassfest), so the child is a `device_id` field with a KampKlar device selector. Calls that pass the
  device as a target still work.
- v0.6.0 (2026-09-15): tilmeld/afmeld target the child (device or entity) and default to the next
  activity, returning which activity changed; the old person_id + activity_id form still works.
  Diagnostics download (credentials, names and ids removed). Blueprint
  `blueprints/automation/kampklar/udtaget.yaml` notifies a phone when a child is called up.
- v0.5.2 (2026-09-15): fixes the live-match window, which compared UTC "now" with the API's naive
  local kickoff times (off by one to two hours). Dashboard example uses fresh-install entity ids.
- v0.5.1: club and team crest URLs on the activity and match sensors.
- v0.5.0 (2026-09-15): live match scores, brand icon, and packaging cleanup. Adds a "Live match" sensor
  (score, running minute, event list) that polls only during a match window and faster while live;
  the DBU crest as the integration brand icon (custom_components/kampklar/brand/, served locally on HA
  2026.3+); proper runtime localization (translations/en.json + da.json, English strings.json) so the
  config flow, options and services are localized; icons.json for entity and service icons; manifest
  integration_type hub + loggers; hacs.json minimum HA 2024.12.0. Entity names now come from the
  translation keys, so new-install entity_ids use English slugs (existing installs keep their ids).
- v0.4.0: write support and call-ups. `kampklar.tilmeld` / `kampklar.afmeld` services
  (POST TeamActivity/UpdateTeamActivityPerson, verified live), a call-up ("udtagelse") sensor and
  calendar marking, an options flow for the poll interval, iCal URLs captured at login.
- v0.3.0: richer read-side data. Sensors expose subscription deadline, meeting time/place,
  open-for-signup, subscribed count, team assignment and task count. Built on the full
  reverse-engineering pass (see docs/reverse-engineering-findings.md).
- v0.2.1: fixed the integration showing nothing in production. The live API returns
  `personContactId: null` on a person's own activity list, and v0.1.4 had started dropping those
  entries, so every sensor went `unknown`. Pending signups now also count unanswered open activities
  (`signupStatusId: null`), and next match uses any activity with match details (practice matches too).
- Installed through HACS on the user's production HA Yellow.
- Sign-up write path confirmed live 2026-09-15: `POST TeamActivity/UpdateTeamActivityPerson?userId={parent}&deviceId=0`
  with a JSON body `{ActivityId, PersonId, SignUpStatusId, ...}`; SignUpStatusId 2 = tilmeld, 1 = afmeld.
  Tested reversibly on a real activity (afmeld then back to tilmeld). A parent uses the same endpoint as
  a coach, TeamPersonId can be null.
- Still open: team endpoints (#15), attendance sensor (#24, needs GetListTeamActivityTeamMemberPerson -
  may require coach role), dashboard and blueprint examples (#37, #38). iCal URLs are now captured at
  login but not yet exposed as entities.

## How it works

- `api/` is a standalone aiohttp client (no HA imports). JSON API at `https://dbuappwebapi.dbu.dk`,
  app-level Basic auth plus `User/GetUserByCredentials`, then `PersonActivity/GetList?personId=`.
  Endpoint notes: `docs/api-reference.md`.
- One `DataUpdateCoordinator` polls every 5 minutes for all tracked persons.
- The coordinator attaches each match's venue to the `Activity` (`dataclasses.replace`), and
  `Activity.effective_meeting_time` repairs the meeting time, while the raw `meeting_time` field stays as
  DBU sent it (visible in diagnostics). Calendar and sensor code, and their tests, work on plain
  activities, since most tests patch `_async_update_data`.

## Live API facts worth knowing

- Activity `typeId`: 1 Træning, 2 Kamp, 4 Stævne, 5 Træningskamp, 7 DBU-Stævne.
- `signupStatusId`: null when unanswered (with `isOpenForSignUp` telling whether answering is possible
  yet), 2 Tilmeldt, 4 Udtaget. The list is sorted by start time and covers about four weeks ahead.
- `subscribedText` is the only field naming how an activity picks players ("8 udtaget" vs "14 tilmeldte"),
  and it decides whether 4 (Udtaget) can appear at all. Per activity, not per team. Seen live: DBU-Stævne,
  Stævne and Træningskamp counted "udtaget"; Kamp and Træning counted "tilmeldte".
- `personContactName` is empty and `personContactId` null for the person's own activities.
- `Match/GetMatch` and `GetMatchExtended` return `stadium {name, address, zip, city, latitude, longitude}`
  and `fieldName` for every match (checked on 12 matches at 6 venues). Text can have trailing spaces, and
  DBU can truncate `city`.
- `meetingPlace` is often empty or junk (a club abbreviation) for matches. `meetingTime` can be missing,
  and on some practice matches its date lies weeks before the match while the time of day is right.

## Constraints

- Public repo: never commit personal data. Real API captures live outside the repo. Tests and docs use
  invented venues and coordinates.
- English for code and docs. Danish only in `translations/da.json` and in the calendar text;
  `strings.json` must stay identical to `translations/en.json`.
- No CI. Before every push and release, run locally: `ruff check`/`ruff format --check`, `pytest`, and
  hassfest (`python -m script.hassfest --integration-path <repo>/custom_components/kampklar` from a Home
  Assistant core checkout).
