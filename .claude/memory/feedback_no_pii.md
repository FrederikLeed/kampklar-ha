---
name: No personal data in repo
description: Never commit PII (real names, IDs, emails, addresses, phone numbers) to the GitHub repo — always use anonymized/fictional test data
type: feedback
---

Never commit personal identifiable information (PII) to the repo. This includes real names, person IDs, email addresses, phone numbers, physical addresses, dates of birth, and usernames.

**Why:** The repo is public on GitHub. Real personal data from API captures was accidentally committed and had to be scrubbed.

**How to apply:**
- Test fixtures must use fictional data (e.g. "Test Ansen", ID 100001, test@example.com)
- API reference docs must use anonymized examples
- README examples must use generic placeholder names ("Player Name", "Team A")
- Raw API captures (docs/api-capture/) must never be committed — they're in .gitignore
- When creating new fixtures from real API responses, always anonymize before saving
