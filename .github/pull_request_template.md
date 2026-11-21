## Summary

Describe the change, why it is needed, and reference the tracking issue:

Closes #

## Step / issue alignment

- [ ] The linked issue contains the plan and acceptance criteria
- [ ] No private market data, credentials, local snapshots or derived private exports are added
- [ ] No release dates, schedules or private inputs are published
- [ ] Documentation updated when behaviour or contracts change

## Quality gate

- [ ] `python -m compileall -q src tests app.py`
- [ ] `ruff check .` and `ruff format --check .`
- [ ] `pytest -q`
- [ ] Tests use synthetic fixtures only and never read `private_data/` or `.adp-inputs/`

## Data / security

- [ ] No secrets or provider keys in code, tests, fixtures or logs
- [ ] Any provider data handling complies with the notices in NOTICE.md
- [ ] Security workflows remain green (dependency audit, bandit, detect-secrets, CodeQL)
