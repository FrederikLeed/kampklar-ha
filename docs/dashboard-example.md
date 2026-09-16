# Example dashboard

A Lovelace view for one tracked child (activities, matches, call-ups, live score and a calendar),
using only built-in cards. Replace `PERSON` with the child's entity slug (Settings > Devices & Services
> KampKlar), and duplicate the column inside a `horizontal-stack` for more children.

The entity ids below are the ones a fresh install creates. Installs from before v0.5.0 keep their
original Danish ids (for example `_naeste_aktivitet` instead of `_next_activity`); adjust if yours differ.

```yaml
title: KampKlar
path: kampklar
icon: mdi:soccer
cards:
- type: markdown
  content: '# ⚽ KampKlar

    Aktiviteter, kampe og tilmeldinger fra DBU Fodbold. En udtagelse til kamp vises med ⭐ i kalenderen
    og herunder.'
- type: vertical-stack
  cards:
  - type: markdown
    content: '## ⚽ Barnets navn'
  - type: conditional
    conditions:
    - condition: state
      entity: sensor.PERSON_live_match
      state_not: unknown
    - condition: state
      entity: sensor.PERSON_live_match
      state_not: unavailable
    card:
      type: markdown
      content: '### 🔴 Live kamp

        {% set l = ''sensor.PERSON_live_match'' %}**{{ state_attr(l,''home_team'') }} {{ state_attr(l,''home_score'')
        if state_attr(l,''home_score'') is not none else ''-'' }} : {{ state_attr(l,''away_score'') if
        state_attr(l,''away_score'') is not none else ''-'' }} {{ state_attr(l,''away_team'') }}**


        {% if state_attr(l,''is_live'') %}🟢 {{ state_attr(l,''minute'') }}''{% else %}{{ state_attr(l,''status'')
        or ''Ikke startet'' }}{% endif %}

        {% for e in state_attr(l,''events'') or [] %}

        - {{ e.minute }}'' {{ e.type }} ({{ ''hjemme'' if e.team == ''home'' else ''ude'' }}) {{ e.player
        }}{% endfor %}'
  - type: conditional
    conditions:
    - condition: state
      entity: sensor.PERSON_next_call_up
      state_not: unknown
    - condition: state
      entity: sensor.PERSON_next_call_up
      state_not: unavailable
    card:
      type: markdown
      content: '### ⭐ Udtaget til kamp

        **{{ states(''sensor.PERSON_next_call_up'') }}**


        {% set st = state_attr(''sensor.PERSON_next_call_up'',''start_time'') %}{% if st %}🕒 {{ as_timestamp(st)
        | timestamp_custom(''%d/%m %H:%M'') }}{% endif %}{% if state_attr(''sensor.PERSON_next_call_up'',''stadium'')
        %} · 🏟️ {{ state_attr(''sensor.PERSON_next_call_up'',''stadium'') }}{% endif %}'
  - type: entities
    state_color: true
    entities:
    - entity: sensor.PERSON_next_activity
      name: Næste aktivitet
    - entity: sensor.PERSON_next_match
      name: Næste kamp
    - entity: sensor.PERSON_next_call_up
      name: Næste udtagelse
    - entity: sensor.PERSON_pending_signups
      name: Afventende tilmeldinger
  - type: markdown
    content: '#### 🗓️ Næste aktivitet

      {% set a = ''sensor.PERSON_next_activity'' %}{% if states(a) not in [''unknown'',''unavailable'']
      %}**{{ states(a) | trim }}** ({{ state_attr(a,''type'') }})

      {% set st = state_attr(a,''start_time'') %}{% if st %}- 🕒 {{ as_timestamp(st) | timestamp_custom(''%d/%m
      kl. %H:%M'') }}

      {% endif %}{% if state_attr(a,''meeting_place'') %}- 📍 {{ state_attr(a,''meeting_place'') }}

      {% endif %}{% set mt = state_attr(a,''meeting_time'') %}{% if mt %}- 🤝 Mødetid {{ as_timestamp(mt)
      | timestamp_custom(''%H:%M'') }}

      {% endif %}- ✅ {{ state_attr(a,''signup_status'') or ''Ikke svaret'' }}{% else %}Ingen kommende
      aktivitet.{% endif %}


      #### ⚽ Næste kamp

      {% set k = ''sensor.PERSON_next_match'' %}{% if states(k) not in [''unknown'',''unavailable''] %}**{{
      states(k) | trim }}**

      {% set st = state_attr(k,''start_time'') %}{% if st %}- 🕒 {{ as_timestamp(st) | timestamp_custom(''%d/%m
      kl. %H:%M'') }}

      {% endif %}{% if state_attr(k,''stadium'') %}- 🏟️ {{ state_attr(k,''stadium'') }}{% if state_attr(k,''field'')
      %}, bane {{ state_attr(k,''field'') }}{% endif %}

      {% endif %}{% if state_attr(k,''row'') %}- 🏆 {{ state_attr(k,''row'') }}

      {% endif %}{% set dl = state_attr(k,''subscription_deadline'') %}{% if dl %}- ⏳ Tilmeldingsfrist
      {{ as_timestamp(dl) | timestamp_custom(''%d/%m %H:%M'') }}

      {% endif %}{% else %}Ingen kommende kamp.{% endif %}'
  - type: markdown
    content: '#### 📋 Afventende tilmeldinger: {{ states(''sensor.PERSON_pending_signups'') }}

      {% for act in state_attr(''sensor.PERSON_pending_signups'',''activities'') or [] %}- {{ act }}

      {% else %}Alt besvaret 👍{% endfor %}'
  - type: horizontal-stack
    cards:
    - type: button
      entity: script.kampklar_tilmeld_barnets
      name: Tilmeld næste
      icon: mdi:account-check
      show_state: false
      tap_action:
        action: perform-action
        perform_action: script.kampklar_tilmeld_barnets
    - type: button
      entity: script.kampklar_afmeld_barnets
      name: Afmeld næste
      icon: mdi:account-remove
      show_state: false
      tap_action:
        action: perform-action
        perform_action: script.kampklar_afmeld_barnets
  - type: calendar
    title: Kalender
    initial_view: listWeek
    entities:
    - calendar.PERSON_calendar

```
