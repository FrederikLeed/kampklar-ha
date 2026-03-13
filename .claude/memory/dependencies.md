# KampKlar Issue Dependency Tree

```
#6 mitmproxy guide
  └─ #7 cert pinning
     └─ #8 API discovery (XL, critical path)
        ├─ #9 auth analysis
        ├─ #11 DBU contact
        ├─ #12 API client core
        │   ├─ #13 activity endpoints
        │   ├─ #14 registration endpoints
        │   ├─ #15 team endpoints
        │   ├─ #17 API tests
        │   │   └─ #18 integration tests (recorded)
        │   └─ #19 HA scaffold
        │       ├─ #20 config flow
        │       │   ├─ #27 options flow
        │       │   └─ #29 config flow tests
        │       │       └─ #32 integration tests
        │       ├─ #21 coordinator
        │       │   ├─ #22 sensor: next activity
        │       │   │   ├─ #30 sensor/calendar tests
        │       │   │   ├─ #37 Lovelace dashboards
        │       │   │   └─ #38 automations
        │       │   ├─ #23 sensor: registration
        │       │   ├─ #24 sensor: availability
        │       │   ├─ #25 calendar entity
        │       │   ├─ #26 service calls
        │       │   │   └─ #31 service call tests
        │       │   └─ #28 error handling
        │       └─ #33 README
        │           └─ #36 HACS docs
        └─ #34 API docs
#4 CI/CD
  └─ #35 dev guide
#10 iCal research
  └─ #16 iCal parser
#39 HACS prep (deps: #32, #33, #36 — in body, not sub-issue due to depth limit)
  └─ #40 first release
     └─ #41 HACS submission
```

## Parallel tracks (no dependencies between them)
- #4, #5 (setup) — can start immediately
- #6-#11 (research) — requires human participation
- #10 (iCal) — parallel with #6-#9
