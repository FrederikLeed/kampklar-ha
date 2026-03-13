# Claude Code Memory

This project uses [Claude Code](https://claude.ai/claude-code) as an AI-assisted development tool. Claude Code has a **memory system** that stores project context, user preferences, and feedback across conversations.

## What is Claude Code memory?

Memory files are structured markdown documents that help Claude Code maintain context between sessions. They contain:

- **User preferences** — how the developer likes to work (e.g., language preferences, workflow style)
- **Feedback** — corrections and rules learned from past interactions (e.g., "never commit PII")
- **Project context** — ongoing work, issue dependencies, architecture decisions
- **References** — pointers to external resources (project boards, dashboards, etc.)

Memory files live in `.claude/memory/` and are indexed by `MEMORY.md`.

## For contributors: excluding memory files

The memory files in this repo are specific to the maintainer's Claude Code setup. If you clone this repo and use Claude Code yourself, you have two options:

### Option A: Use your own memory (recommended)

Replace the contents of `.claude/memory/` with your own memory files. To avoid accidentally committing your personal memory:

```bash
# Tell git to ignore your local changes to memory files
git update-index --skip-worktree .claude/memory/MEMORY.md
git update-index --skip-worktree .claude/memory/feedback_no_pii.md
git update-index --skip-worktree .claude/memory/feedback_english_docs.md
git update-index --skip-worktree .claude/memory/dependencies.md
```

To undo this later:
```bash
git update-index --no-skip-worktree .claude/memory/MEMORY.md
# ... repeat for each file
```

### Option B: Ignore memory entirely

Add `.claude/memory/` to your local git exclude file (not committed):

```bash
echo '.claude/memory/' >> .git/info/exclude
```

This prevents git from tracking any changes you make to memory files, without affecting the repo's `.gitignore`.

## File structure

```
.claude/
└── memory/
    ├── MEMORY.md                 # Index file — pointers to all memory files
    ├── dependencies.md           # Issue dependency tree
    ├── feedback_no_pii.md        # Rule: never commit personal data
    └── feedback_english_docs.md  # Rule: documentation in English
```

## Why commit memory files?

Memory files are committed so they persist across machine rebuilds and environment resets. They are lightweight markdown files containing no sensitive data — just project rules and context that help Claude Code work effectively on this codebase.
