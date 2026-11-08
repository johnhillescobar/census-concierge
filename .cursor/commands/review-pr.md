# Review PR

Read `CLAUDE.md` and **`docs/playbooks/review-pr.md`**, the canonical procedure.
Run its machine checks first, including `check_invariants --base origin/main`;
a non-zero exit stops the invariants review. Preserve raw evidence and use
the playbook's three-verdict format, most important reason first.
For Gate 2, follow `docs/playbooks/run-slice.md`: a fresh code-only bug pass
precedes this project invariants pass.
