# ADR-0001: Greenfield Rebuild

Status: Accepted

## Context

Legacy implementations contain assumptions from earlier ISA, ABI, exception,
and MMU designs. Their worktrees are also not clean reproducible baselines.

## Decision

Implement DADAO from clean upstream component commits. Reuse only the legacy
meta-repository's orchestration concepts and documented engineering lessons.

## Consequences

- No legacy implementation cherry-picks.
- Initial progress may be slower but each behavior has a traceable contract.
- Historical tests are rewritten from independent expectations.
- Compatibility with development-only legacy objects is not a goal.
