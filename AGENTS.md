# Repository instructions for every coding agent

Read [CLAUDE.md](CLAUDE.md) before working. It is the shared project rulebook
for Claude Code, Cursor, Codex and other hosts; its filename is historical.
The shared execution plan remains [.claude/PLAN.md](.claude/PLAN.md). Do not
create a separate host-specific plan or copy of the project rules.

Canonical workflows: [run-slice](docs/playbooks/run-slice.md),
[review-pr](docs/playbooks/review-pr.md), and the
[Gate 1 matrix](docs/process-evidence.md). Read applicable `.mdc` rule bodies:

| Work | Rule |
| --- | --- |
| All changes | [.cursor/rules/00-guardrails.mdc](.cursor/rules/00-guardrails.mdc) |
| Python API | [.cursor/rules/10-api-python.mdc](.cursor/rules/10-api-python.mdc) |
| Frontend | [.cursor/rules/20-web-typescript.mdc](.cursor/rules/20-web-typescript.mdc) |
| Tests, evals, scripts | [.cursor/rules/30-evals-and-tests.mdc](.cursor/rules/30-evals-and-tests.mdc) |
| Census behavior | [.cursor/rules/40-census-domain.mdc](.cursor/rules/40-census-domain.mdc) |

Gate 1, Gate 2 and E2E use fresh contexts without caller history per the playbook.
Owner-only merges, budgets and waivers still apply. Never read sealed eval sets
or E2E transcripts, regardless of host protections. Codex skills are in
`.agents/skills/`; Claude skills and Cursor commands retain their existing paths.
Without skill support read the playbook; without `make` run its Makefile recipes.
