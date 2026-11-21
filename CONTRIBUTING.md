# Contributing

All changes to this repository go through pull requests; `main` is protected.

## Workflow

1. Pick or open an issue. Issues are the plan of record: every capability, defect, security task
   and release step is tracked there, with acceptance criteria.
2. Create a branch named `<type>/<short-slug>` (for example `feat/seed-import`).
3. Implement the change with tests. Run locally:
   ```bash
   python -m compileall -q src tests app.py
   ruff check .
   pytest -q
   ```
4. Open a PR using the template, link the issue (`Closes #<n>`), and keep all checks green.
5. Merge is squash-only; merged branches are deleted. Do not force-push or push directly to
   `main`.

## Rules

- **No private data in git.** Never commit data under `private_data/`, `.adp-inputs/`, personal
  exports, cached derivatives or local snapshots. Tests use synthetic fixtures only.
- **No credentials or secrets.** Do not commit `.env` files or provider keys. Use environment
  variables locally.
- **No release dates or schedules** in repository content (README, docs, issues, PRs, releases).
  Describe scope, acceptance criteria and milestones only.
- Keep dependencies minimal and pinned by the project metadata; CI runs lint, tests and security
  scanning.
- Keep changes small and reviewable; update documentation and tests with behaviour changes.
