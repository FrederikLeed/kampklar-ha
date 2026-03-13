# KampKlar Issue Dependency Tree

## Milestone structure

| Milestone | Focus | Status |
|-----------|-------|--------|
| 0 - Project Setup | CI/CD, devcontainer | ✅ Complete |
| 1 - Research | mitmproxy, cert pinning, iCal, DBU contact | Parallel track |
| **2 - Phase 1: Read** | Sensors, calendar, options, error handling, docs, dashboards | In progress |
| **3 - Phase 2: Write** | Signup endpoints, service calls, related tests | Blocked by Phase 1 |
| 4 - Release | HACS prep, v0.1.0, HACS submission | After Phase 1 |

## Dependency tree

✅ = closed/done

```
#6 mitmproxy guide
  └─ #7 cert pinning
     └─ ✅ #8 API discovery
        ├─ ✅ #9 auth analysis
        ├─ #11 DBU contact
        ├─ ✅ #12 API client core
        │   ├─ ✅ #13 activity endpoints
        │   ├─ #14 registration endpoints [Phase 2: Write]
        │   ├─ #15 team endpoints [Phase 1: Read]
        │   ├─ ✅ #17 API tests
        │   │   └─ #18 integration tests (recorded) [Phase 1: Read]
        │   └─ ✅ #19 HA scaffold
        │       ├─ ✅ #20 config flow
        │       │   ├─ #27 options flow [Phase 1: Read]
        │       │   └─ ✅ #29 config flow tests
        │       │       └─ ✅ #32 integration tests
        │       ├─ ✅ #21 coordinator
        │       │   ├─ ✅ #22 sensor: next activity
        │       │   │   ├─ #30 sensor/calendar tests [Phase 1: Read]
        │       │   │   ├─ #37 Lovelace dashboards [Phase 1: Read]
        │       │   │   └─ #38 automations [Phase 1: Read]
        │       │   ├─ #23 sensor: registration [Phase 1: Read]
        │       │   ├─ #24 sensor: availability [Phase 1: Read]
        │       │   ├─ #25 calendar entity [Phase 1: Read]
        │       │   ├─ #26 service calls [Phase 2: Write]
        │       │   │   └─ #31 service call tests [Phase 2: Write]
        │       │   └─ #28 error handling [Phase 1: Read]
        │       └─ ✅ #33 README
        │           └─ #36 HACS docs [Phase 1: Read]
        └─ ✅ #34 API docs
#4 CI/CD ✅
  └─ #35 dev guide [Phase 1: Read]
#10 iCal research
  └─ #16 iCal parser [Phase 1: Read]
#39 HACS prep [Release]
  └─ #40 first release [Release]
     └─ #41 HACS submission [Release]
```

## Phase 1: Read — priority order
1. #25 Calendar entity (L) — high-value new feature
2. #23 Sensor: tilmeldingsstatus (partially done)
3. #24 Sensor: holdtilgængelighed
4. #15 API client: hold/spiller-endpoints
5. #27 Options flow
6. #28 Fejlhåndtering (partially done)
7. #18 Integration tests med recorded responses
8. #30 Unit tests for sensors og calendar
9. #35, #36, #37, #38 — docs and UX
