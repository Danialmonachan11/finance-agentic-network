# Triage labels

Default vocabulary, unchanged — kept as-is per setup confirmation.

| Label | Meaning |
|---|---|
| `needs-triage` | New, not yet categorized |
| `needs-info` | Blocked — waiting on missing details before it can be scoped |
| `ready-for-agent` | Specified well enough for an AI agent to implement directly |
| `ready-for-human` | Needs a judgment call or design decision only a person can make |
| `wontfix` | Decided, not being addressed |

## Where these live

This repo uses the local-markdown issue tracker (`docs/agents/issue-tracker.md`),
not GitHub/GitLab labels. A label here is the `status:` frontmatter field on
an issue file under `.scratch/<feature>/<slug>.md` — set it to one of the
five values above, exact string match.
