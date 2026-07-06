# Repository Working Rules

- Treat `manifests/spec.lock.toml` as the specification baseline.
- Do not copy or cherry-pick legacy DADAO implementation code.
- Use current upstream projects as API and implementation-style references.
- Every implementation change must name its specification clause and tests.
- Keep source, build, install, sysroot, logs, and generated files under `.work/`.
- Record architecture decisions in `docs/adr/` before they become cross-component contracts.
- Track substantial work in `code-agent/tasks/` and design changes in `code-agent/designs/`.
- Unsupported semantics must fail explicitly; do not add compatibility stubs that silently succeed.

## Review

Reviewers: read `reviewer.md` before reviewing. Verdicts must rest on the reviewer's own re-run of the task's acceptance block, not on the worker's narrative.
