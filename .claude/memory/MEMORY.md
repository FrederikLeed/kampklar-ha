# Workspace Memory

## User Environment
- Running remotely via VS Code Tunnel — all config changes must be doable remotely (no local terminal access)
- GitHub authenticated as FrederikLeed (device code flow)

## Project: KampKlar HA
- Repo: `/workspace/kampklar-ha/` (cloned from github.com/FrederikLeed/kampklar-ha)
- Home Assistant custom integration for DBU KampKlar (Danish football activity management)
- Reverse-engineered API from "Fodbold" app
- See `CLAUDE.md` in repo for coding conventions and architecture
- Project board: https://github.com/users/FrederikLeed/projects/1
- 8 milestones created (0-7), all issues assigned
- Sub-issue dependency tree set up (GitHub limits: 1 parent per issue, max 7 layers)
- Issue #39 has no sub-issue parent (depth limit) — deps documented in body text
- Dependency details: see [dependencies.md](dependencies.md)

## User Preferences
- Prefers fewer permission prompts — suggest `claude config set autoApprove.tools` or Shift+Tab
- Remote workflow: cannot run local terminal commands, everything via VS Code Tunnel + Claude Code

## Feedback
- [No PII in repo](feedback_no_pii.md) — never commit personal data, always anonymize
- [English docs](feedback_english_docs.md) — all documentation in English, Danish only for strings.json
