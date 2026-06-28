# ADR-0002: Manifest-Driven Build Orchestration

Status: Accepted

## Decision

Use Make as the stable user interface and Python standard-library scripts for
manifest processing. Keep all disposable data under `.work/`. Fetch each
component at a full commit and apply one ordered patch series.

## Rejected Legacy Behavior

- Environment-specific Git URL rewriting.
- Version selection by mutable branch alone.
- Separate unreviewed `fixups` layers.
- Copying upstream repositories into the meta-repository.
- Treating a dirty generated source tree as the authoritative implementation.
