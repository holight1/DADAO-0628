#!/usr/bin/env bash
# Build the DADAO Sail rehearsal-slice C simulator (SL-002a / ADR-0011 M2b).
#
#   sail -c  →  dadao_model.{c,h}  →  gcc (+ sail runtime + GMP/zlib)
#            →  c_harness/dadao_sail_sim
#
# Sail toolchain: prebuilt release binary at $SAIL_HOME (opam `sail` also works).
# The generated C (dadao_model.*) is a build product — see .gitignore.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Locate sail + its lib. Prefer an explicit SAIL_HOME, else the prebuilt binary
# install, else whatever `sail` is on PATH (opam switch).
SAIL_HOME="${SAIL_HOME:-$HOME/.local/opt/sail-0.20.2}"
if [ -x "$SAIL_HOME/bin/sail" ]; then
  SAIL="$SAIL_HOME/bin/sail"
  SAILLIB="$SAIL_HOME/share/sail/lib"
  # Sail's typechecker invokes `z3` from PATH; the prebuilt release bundles it
  # next to the sail binary.
  export PATH="$SAIL_HOME/bin:$PATH"
else
  SAIL="$(command -v sail)"
  SAILLIB="$(dirname "$(dirname "$SAIL")")/share/sail/lib"
fi
command -v z3 >/dev/null || { echo "error: z3 not on PATH (Sail needs it)"; exit 1; }
echo "sail    = $SAIL ($($SAIL --version))"
echo "saillib = $SAILLIB"

SRCS="dadao_types.sail dadao_state.sail dadao_insts.sail dadao_main.sail"

echo ">> sail -c"
"$SAIL" -c --c-no-main --c-include c_harness/dadao_externs.h \
  --c-preserve dadao_step --c-preserve dadao_init \
  $SRCS -o dadao_model

echo ">> gcc"
# gmp.h/zlib.h are multiarch on this host; add the arch include dir if present.
ARCHINC=""
[ -d /usr/include/aarch64-linux-gnu ] && ARCHINC="-I/usr/include/aarch64-linux-gnu"
gcc -O2 -w \
  dadao_model.c c_harness/dadao_harness.c \
  "$SAILLIB/sail.c" "$SAILLIB/rts.c" "$SAILLIB/elf.c" \
  "$SAILLIB/sail_failure.c" "$SAILLIB/sail_config.c" "$SAILLIB/cJSON.c" \
  -I. -Ic_harness -I"$SAILLIB" $ARCHINC \
  -lgmp -lz -o c_harness/dadao_sail_sim

echo "built: c_harness/dadao_sail_sim"
