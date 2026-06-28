# Repository Layout

- `manifests/`: immutable specification, component, and reference inputs.
- `components/`: ordered patch series and component-specific documentation.
- `contracts/`: machine-readable vectors and interface contracts.
- `tests/`: interface and execution tests independent from component unit tests.
- `scripts/`: deterministic fetch, preparation, validation, and status tools.
- `code-agent/`: designs, task contracts, reviews, and distilled knowledge.
- `.work/source/`: disposable upstream source checkouts.
- `.work/build/`: disposable out-of-tree builds.
- `.work/install/`: disposable host tools and artifacts.
- `.work/sysroot/`: disposable target sysroots.
- `.work/logs/`: build and test logs.

The repository never tracks upstream source trees or build outputs. A source
checkout is reproducible from `components.lock.toml` plus the ordered patch
series.
