# Legacy Toolchain Index

The machine-readable index is `manifests/references.toml`.

The 2026-06-28 audit found:

| Reference | State | Permitted use |
|---|---|---|
| DADAO Wiki | Clean at `7ddb632` | Candidate SPEC baseline |
| DADAO meta-repository | 8 dirty entries | Build-layout and workflow reference |
| llvm-unicore | 128 dirty entries | Failure archaeology and test intent |
| Linux 5.4 tree | Detached, 6 dirty entries | Bring-up retrospective only |
| musl tree | Clean, local branch ahead | ABI glue lessons only |
| LLVM test-suite | 1 dirty entry | Workload inventory only |

Dirty references cannot be reproduced by their HEAD alone and are never used
as source inputs. If historical evidence is needed, record the exact path and
observation in a task or review document.
