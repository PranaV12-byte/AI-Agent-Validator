# Test Lab and decision feedback

## Safe local use

Test Lab stores manually written synthetic prompts only. Do not paste real
personal data, passwords, API keys, or customer messages. The editor requires an
explicit synthetic-data confirmation, rejects recognized credential patterns,
and limits each tenant to 20 cases with prompts up to 4,000 characters.

Each run is explicit and evaluates the saved prompt against one frozen snapshot
of the tenant's current guardrail settings and rules. Test Lab compares the
observed action (`allow`, `redact`, or `block`) with the chosen expected action.
A matching outcome is not proof of complete redaction or overall security
accuracy. The latest result is saved with its case revision and snapshot
fingerprint; edits or settings/rule changes make that result stale. Runs do not
create audit records or API-usage rows.

The result states are:

- **Matching expected outcome** — the observed action matched the selected
  expected action.
- **Outcome differs** — the observed action did not match.
- **Unavailable** — evaluation, settings, or result persistence was incomplete.
  An enabled `llm_eval` rule requires an external judge; Test Lab does not call
  providers and reports that case unavailable.
- **Not run** — a case was not started before the run deadline.
- **Stale** — the case or frozen settings/rules snapshot no longer matches the
  saved result.
- **Case changed during run** — a concurrent edit prevented writing a result
  against the wrong revision.

Activity History can hold one human decision review per audit record: Correct,
Incorrect (with a required expected action), or Unsure; each review is Open or
Resolved and may have a short sanitized note. Feedback does not edit the
original audit record, its preview, or the active protection rules. Creating a
synthetic follow-up starts with a blank prompt; enter a complete fictional
scenario by hand and confirm it is synthetic before saving. Audit previews are
never copied into stored test cases.

## Isolated local preview

The feature preview is served at `http://localhost:5177` and its API at
`http://localhost:8103`. The fallback checkout remains at commit `1e536d3`,
served at `http://127.0.0.1:5176` with API `http://127.0.0.1:8102`; keep its
accounts, rules, database, and runtime unchanged. For feature-authenticated
checks, use only a fresh synthetic tenant with no original accounts or rules.

This is a local development workflow only. It does not enable a live external
judge, contact a provider, or change deployment configuration.
