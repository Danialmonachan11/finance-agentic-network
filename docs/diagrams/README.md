# Diagrams

Each diagram is authored as Archify JSON (the source of truth), delivered as
a self-contained interactive HTML, and captured once as a 1440px PNG.
`*.visual-check.json` is the browser-evidence receipt from the last delivery.

| Diagram | Type | Shows |
|---|---|---|
| `architecture` | architecture | One pair, two company instances, the pair in the middle (PRD v0.2) |
| `status-inquiry` | sequence | B asks A "where is my payment" by email, answered with zero human touches |
| `claim-lifecycle` | lifecycle | A discount claim from received to executed, declined, awaiting, or expired |
| `pii-dataflow` | dataflow | Which text leaves the company for the model, which stays in house |

Regenerate after editing a JSON (skill installed at `~/.claude/skills/archify`):

```bash
node ~/.claude/skills/archify/bin/archify.mjs deliver <type> <name>.json <name>.html --quality showcase --repo-root ../..
# --repo-root only for the architecture type; drop it for sequence, lifecycle, dataflow
node ~/.claude/skills/archify/bin/archify.mjs visual-check <name>.html --json
```
