# CLAUDE.md — KampKlar HA Integration

## Project Overview
Home Assistant custom integration for DBU KampKlar. Reverse-engineered API from the "Fodbold" app.

## Architecture
- `custom_components/kampklar/` — HA integration code
- `custom_components/kampklar/api/` — Standalone Python API client (no HA deps)
- `tests/` — pytest tests with pytest-homeassistant-custom-component
- `docs/` — API docs, setup guides, examples

## Coding Conventions
- Python 3.12+
- Async/await throughout (aiohttp for HTTP)
- Type hints on all public functions
- Ruff for linting (HA-compatible config)
- Danish variable names only where matching API/domain terms (tilmeldt, afmeldt, etc.)
- English for code, Danish for user-facing strings (strings.json)

## Key Files
- `manifest.json` — Integration metadata (domain: kampklar)
- `const.py` — Constants
- `config_flow.py` — UI setup flow
- `coordinator.py` — DataUpdateCoordinator (polling)
- `sensor.py` — Sensor entities
- `calendar.py` — Calendar entity
- `services.yaml` — Service definitions

## Testing
- `pytest` with `pytest-homeassistant-custom-component`
- Fixtures in `tests/fixtures/`
- Target: 90%+ coverage

## GitHub
- Project board: https://github.com/users/FrederikLeed/projects/1
- 41 issues across 8 milestones
