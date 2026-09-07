# Issue tracker: local markdown

This repo has a GitHub remote but no issue tracker in use (solo project). Issues live as
markdown files under `.scratch/<feature>/`, not in an external tracker.

## Convention

- One directory per feature/effort under `.scratch/`, named with a short
  kebab-case slug (e.g. `.scratch/invoice-overbill-check/`).
- One markdown file per issue inside that directory, named
  `<slug>.md` (e.g. `.scratch/invoice-overbill-check/detect-po-mismatch.md`).
- Each issue file's frontmatter carries at minimum:
  ```
  ---
  status: needs-triage
  ---
  ```
  `status` is the triage label (see `docs/agents/triage-labels.md`) — update
  it in place as the issue moves through its lifecycle. No separate label
  store; the file's frontmatter *is* the label.
- Body: plain description of the problem/task. Link to relevant files with
  repo-relative paths.

## Consumer rules

- `to-tickets` writes new issue files here instead of calling `gh issue create`.
- `triage` reads/updates the `status:` frontmatter field in place.
- `to-spec` reads an issue file's body as its spec input when asked to work
  from "the ticket."

PRs-as-a-request-surface flag: **off** (not applicable — no remote, no PRs).
