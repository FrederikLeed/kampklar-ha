# CLAUDE.md — KampKlar HA Integration

## Project Overview
Home Assistant custom integration for DBU KampKlar. Reverse-engineered API from the "Fodbold" app.

## Architecture
- `custom_components/kampklar/` — HA integration code
- `custom_components/kampklar/api/` — Standalone Python API client (no HA deps)
- `tests/` — pytest tests with pytest-homeassistant-custom-component
- `docs/` — API docs, setup guides, examples
- `.claude/memory/` - Claude Code memory files

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

## Before pushing
There is no CI; these run locally:
- `ruff check custom_components tests` and `ruff format --check custom_components tests`
- `pytest`
- hassfest against a Home Assistant core checkout:
  `python -m script.hassfest --integration-path <repo>/custom_components/kampklar`

## Data in the repo
Never commit personal data. Test fixtures, docs and examples use invented names, ids and
addresses ("Testby BK", person id 100001, test@example.com). Raw API captures stay out of the
repo entirely.
