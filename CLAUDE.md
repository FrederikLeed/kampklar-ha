# CLAUDE.md — KampKlar HA Integration

## Project Overview
Home Assistant custom integration for DBU KampKlar. Reverse-engineered API from the "Fodbold" app.

## Architecture
- `custom_components/kampklar/` — HA integration code
- `custom_components/kampklar/api/` — Standalone Python API client (no HA deps)
- `tests/` — pytest tests with pytest-homeassistant-custom-component
- `docs/` — API docs, setup guides, examples
- `.claude/memory/` — Claude Code memory files (see [docs/claude-code-memory.md](docs/claude-code-memory.md))

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

## Project Memory
- Project-specific memory lives in `.claude/memory/` (committed to repo)
- Read `.claude/memory/MEMORY.md` at the start of each conversation for project context
- Global memory (user prefs) is separate — stored in Claude Code's internal directory

## GitHub
- Project board: https://github.com/users/FrederikLeed/projects/1
- 5 milestones: Setup (done), Research, Phase 1: Read, Phase 2: Write, Release
