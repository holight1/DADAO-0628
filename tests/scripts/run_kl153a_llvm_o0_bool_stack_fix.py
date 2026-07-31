#!/usr/bin/env python3
"""KL-153a: DADAO LLVM -O0 bool/i1 stack-slot root-cause fix gate.

Verifies: the frozen KL-152a root and its 223-item evidence manifest;
the LLVM patch queue including the new i1-load-promotion fix commit and
its regression test; the Linux patch queue including the 11 new
commits that remove all 10 task-listed bool-carrier workarounds plus 8
additional pre-existing carriers found by a tree-wide sweep; source and
disassembly proof that every carrier site is gone and no site still
exhibits the same-slot `stb`-then-`ldo` pattern; a fresh KCFLAGS=-O0
Linux Image build; and a QEMU boot that preserves the KL-152a seven-word
oracle sequence, then continues running (not crashing on a new
EXCP_MALIGN) through an extended observation window instead of the
node_tag_get shutdown KL-152a expected.
"""

from __future__ import annotations

import hashlib
import fcntl
import json
import os
import re
import shlex
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = Path(__file__).resolve()
LINUX_SOURCE = ROOT / ".work" / "source" / "linux"
LINUX_OUTPUT = ROOT / ".work" / "build" / "linux"
LLVM_SOURCE = ROOT / ".work" / "source" / "llvm"
LLVM_BUILD = ROOT / ".work" / "build" / "llvm"
LLVM_BIN = LLVM_BUILD / "bin"
QEMU_SOURCE = ROOT / ".work" / "source" / "qemu"
QEMU_BUILD = QEMU_SOURCE / "build"
QEMU = QEMU_BUILD / "qemu-system-dadao"
EVIDENCE_PARENT = ROOT / ".work" / "evidence"
EVIDENCE = EVIDENCE_PARENT / "kl153a-llvm-o0-bool-stack-fix"
EVIDENCE_LOCK = EVIDENCE_PARENT / ".kl153a-llvm-o0-bool-stack-fix.lock"
EVIDENCE_CURRENT = EVIDENCE_PARENT / ".kl153a-llvm-o0-bool-stack-fix.current.json"
LINUX_SERIES = ROOT / "components" / "linux" / "patches" / "series"
LLVM_SERIES = ROOT / "components" / "llvm" / "patches" / "series"
QEMU_SERIES = ROOT / "components" / "qemu" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"
KL152_SUMMARY = (
    ROOT / ".work" / "evidence" / "kl152a-mm-init-completion" / "summary.json"
)
KL152_CURRENT = (
    ROOT / ".work" / "evidence" / ".kl152a-mm-init-completion.current.json"
)

# Frozen root state this task starts from (KL-152a's own two commits).
ROOT_FROZEN_TASK_COMMIT = "f227056aa46590999552bb748ee08e7ef45cb338"
ROOT_KL153A_DEFINE_COMMIT = "a25328c8b9297544975e1b5b0f07a1792cc2281f"
KL152_SUMMARY_SHA256 = (
    "d36592267f91c35f6770012d95ab1c697aa190bcc908c1c501b360c080f219e5"
)
KL152_ARTIFACT_COUNT = 223

LLVM_HEAD_BEFORE = "1146c671a1ae418fd84733fa98fd58a559a5112d"
LLVM_FIX_COMMIT = "d52f215cdd8af366bf497664750f241e5ef83f99"
LLVM_FIX_PATCH_ID = "23eeeae4bec2e97f86d3afc00758cb79ae197a82"
LLVM_FIX_PATCH_NAME = (
    "0066-DADAO-promote-i1-loads-to-byte-sized-loads-KL-153a.patch"
)
LLVM_FIX_PATCH_SIZE = 21277
LLVM_FIX_PATCH_SHA256 = (
    "0790df79271613d9f6349e8a426b35ec09d75463de2a9cc4c20a2ce49ff8a0fd"
)
LLVM_SERIES_COUNT = 66

LINUX_HEAD_BEFORE = "e054a68cc86b045881afdc26a028ee4d16c3d217"

# The 11 new Linux commits: 10 revert the task-listed bool-widening
# workarounds (newest-first, matching the task file's own list order),
# the 11th removes 8 further pre-existing carriers found by a tree-wide
# grep for CONFIG_DADAO_K3_O0_LINK_COMPAT / "_result_t" / "_match_t"
# typedefs that predate the task's 10-commit list (from 06c3d571a
# "harden K3 O0 early boot progress", 537c61bae "complete K3 mem_init
# progress", 4f32b2dd2 "complete K3 mm_init progress" -- each of those
# origin commits mixes a legitimate unrelated change with a carrier
# workaround, so they were hand-edited rather than reverted wholesale).
LINUX_NEW_PATCHES = (
    (
        "0021-dadao-revert-widen-SLUB-init-on-alloc-result-for-K3-O0.patch",
        "bd4944be6a78e82482d94699d6e533bb06a2fd5f",
        "fc93616ecfdfcaa06f54d1e34e2a023970264866",
    ),
    (
        "0022-dadao-revert-widen-SLUB-init-on-free-result-for-K3-O0.patch",
        "d238938d25914568e25687ffb5175852a77416fd",
        "0c5e0862161d8ee237f303a4a2d771184e7ecdb7",
    ),
    (
        "0023-dadao-revert-widen-SLUB-cmpxchg-result-for-K3-O0.patch",
        "fc6fa6835c5adf729d3d47d487c4d9d0d094fdfb",
        "5b60b65d0ab6ec620d65f215c2bc8739cc91da6d",
    ),
    (
        "0024-dadao-revert-widen-SLUB-pfmemalloc-result-for-K3-O0.patch",
        "de42acd5370c44184ca54463a9931dd7bc4a9e6b",
        "980be1d280459c69ba9c38b6ca266c70d532cb38",
    ),
    (
        "0025-dadao-revert-widen-new-PCP-check-result-for-K3-O0.patch",
        "1e173405023da9316597c540fdb9f2dcd8e536b1",
        "ead303df75d6e3ed4c324c557e43dee820c35a0a",
    ),
    (
        "0026-dadao-revert-widen-rmqueue-fallback-result-for-K3-O0.patch",
        "a29de929c6a4df624c8ff67f321bf327510ab664",
        "ebdcea38c1b98c0f17f6d86d36ece974a7aa4aed",
    ),
    (
        "0027-dadao-revert-widen-fallback-steal-result-for-K3-O0.patch",
        "c44a6503d87ec4fdc0c69022a7712fd688384016",
        "48323eb5c0d5dd3022dca225c2896ee517e96f51",
    ),
    (
        "0028-dadao-revert-widen-zone-watermark-result-for-K3-O0.patch",
        "bce7a8264197f5e87935e5e7f38d4d44f3de7444",
        "cae2b9f14d76ef2064d2adef1d74812b13e93ecb",
    ),
    (
        "0029-dadao-revert-widen-compaction-capture-result-for-K3-O0.patch",
        "73adec5c4c4391ff3b54f7accafc76abe38ef3ed",
        "342d11207f4d4fdb89555bcfe8e87cf78b55c72a",
    ),
    (
        "0030-dadao-revert-widen-page-expected-state-result-for-K3-O0.patch",
        "d3d4b4ab61cb5869bc4a129fd007c12a466a8be5",
        "7659276d615a0d01002357304b18b48d09a79a05",
    ),
    (
        "0031-dadao-remove-additional-K3-O0-bool-carrier-workarounds.patch",
        "83992fe62ac26252622ca888421602abafe20b44",
        "5644a2aa560dc900f0a42e7e6ccd2eec9d1d4f9e",
    ),
)
LINUX_HEAD_AFTER = LINUX_NEW_PATCHES[-1][1]

QEMU_HEAD = "dfc7842229c139cc606141b82845ecf20086e657"
QEMU_SHA256 = "2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240"

RAM_BASE = 0x80000000
SCRATCH_BASE = 0x87FD0000
ORACLE_SIZE = 56

MARKER_VALUE = 0x4B4C313439414845
FAILURE_VALUE = 0x4B4C313439424144
PROGRESS_VALUES = (
    0x4B4C313530534145,  # KL150SAE
    0x4B4C313530534144,  # KL150SAD
    0x4B4C3135304D494E,  # KL150MIN
    0x4B4C3135314D4944,  # KL151MID
    0x4B4C3135324D4D44,  # KL152MMD
)
PROGRESS_NAMES = (
    "setup_arch_enter",
    "setup_arch_done",
    "mem_init_enter",
    "mem_init_done",
    "mm_init_done",
)
ANCHORS = (
    b"DADAO M1 test-machine early console online\n",
    b"Linux version 5.4.0",
    b"DADAO M1 setup_arch complete\n",
    b"Memory:",
    b"SLUB: HWalign=",
)
ROM_SHA256 = "46c1e4af50162dd9be1adb82eb9223a6902f0629a0a4c9d3f18822aee5e536c7"
WRONG_MODE_ROM_SHA256 = (
    "7cf369ba7b7cac026b693f560d991da91ddc201725848ab621c355488f9aca8c"
)

# All previously-frozen carrier functions (10 task-listed + node_tag_get
# + 8 additional found beyond the task's list) checked for the same-slot
# stb-then-ldo anti-pattern after the fix. Some are `static inline`/
# `__always_inline` and may be fully inlined away at -O0 for some call
# sites (no standalone symbol) -- that is recorded, not a failure, since
# a fully-inlined body has no separate return-value stack round trip for
# the bug to occur in.
FROZEN_CARRIER_SYMBOLS = (
    "node_tag_get",
    "page_expected_state",
    "compaction_capture",
    "zone_watermark_fast",
    "can_steal_fallback",
    "rmqueue_bulk",
    "check_new_pcp",
    "pfmemalloc_match",
    "__cmpxchg_double_slab",
    "slab_want_init_on_free",
    "slab_want_init_on_alloc",
    "free_pages_prepare",
    "free_pcp_prepare",
    "free_unref_page_prepare",
    "prepare_alloc_pages",
    "should_skip_region",
    "obsolete_checksetup",
    "__mutex_trylock",
    "__mutex_trylock_fast",
    "__mutex_unlock_fast",
    "cont_add",
    "want_init_on_alloc",
    "want_init_on_free",
    "parameq",
    "parameqn",
    "param_check_unsafe",
)

# Source-level carrier contracts that must be ABSENT after this fix
# (typedef name -> file). Presence of any of these strings is a FAIL.
REMOVED_CARRIER_MARKERS = (
    ("mm/page_alloc.c", "page_expected_state_result_t"),
    ("mm/page_alloc.c", "compaction_capture_result_t"),
    ("mm/page_alloc.c", "zone_watermark_fast_result_t"),
    ("mm/page_alloc.c", "can_steal_fallback_result_t"),
    ("mm/page_alloc.c", "rmqueue_fallback_result_t"),
    ("mm/page_alloc.c", "check_new_pcp_result_t"),
    ("mm/page_alloc.c", "free_pages_result_t"),
    ("mm/page_alloc.c", "prepare_alloc_pages_result_t"),
    ("mm/slub.c", "pfmemalloc_match_result_t"),
    ("mm/slub.c", "cmpxchg_double_slab_result_t"),
    ("mm/slab.h", "slab_want_init_on_free_result_t"),
    ("mm/slab.h", "slab_want_init_on_alloc_result_t"),
    ("mm/memblock.c", "memblock_skip_region_t"),
    ("init/main.c", "obsolete_setup_result_t"),
    ("kernel/locking/mutex.c", "mutex_fast_result_t"),
    ("kernel/printk/printk.c", "printk_cont_result_t"),
    ("include/linux/mm.h", "page_init_result_t"),
    ("include/linux/moduleparam.h", "kernel_param_match_t"),
    ("kernel/params.c", "kernel_param_match_t"),
)

# Plain `bool` signatures that must be PRESENT after this fix (source
# text -> file), proving each carrier-only typedef/ifdef was actually
# removed rather than merely renamed.
RESTORED_BOOL_MARKERS = (
    ("mm/page_alloc.c", "static inline bool page_expected_state("),
    ("mm/memblock.c", "static bool should_skip_region("),
    ("init/main.c", "static bool __init obsolete_checksetup("),
    ("kernel/locking/mutex.c", "static inline bool __mutex_trylock("),
    ("kernel/printk/printk.c", "static bool cont_add("),
    ("include/linux/mm.h", "static inline bool want_init_on_alloc("),
    ("include/linux/mm.h", "static inline bool want_init_on_free("),
    ("include/linux/moduleparam.h", "extern bool parameq("),
    ("include/linux/moduleparam.h", "extern bool parameqn("),
    ("kernel/params.c", "bool parameqn(const char *a, const char *b, size_t n)"),
    ("kernel/params.c", "bool parameq(const char *a, const char *b)"),
    ("mm/page_alloc.c", "static inline bool\nprepare_alloc_pages("),
)

ACTIVE_RUN_ID: str | None = None
EVIDENCE_OWNED = False
STARTUP_TRANSIENT_CLEANUP: list[str] = []


class GateError(RuntimeError):
    pass


# ---------------------------------------------------------------------
# Evidence / locking infrastructure (KL-152a conventions, reused as-is:
# external exclusive lock, run-id, staging/current-state, atomic
# summary, byte-level manifest).
# ---------------------------------------------------------------------

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_identity(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise GateError(f"evidence artifact missing: {path}")
    return {"path": str(path), "size": path.stat().st_size, "sha256": sha256(path)}


def fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def atomic_write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    with temporary.open("w") as stream:
        stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


def write_lock_audit(descriptor: int, state: str) -> None:
    payload = {
        "task": "KL-153a",
        "state": state,
        "pid": os.getpid(),
        "run_id": ACTIVE_RUN_ID,
        "updated_unix_ns": time.time_ns(),
    }
    data = (json.dumps(payload, sort_keys=True) + "\n").encode()
    os.lseek(descriptor, 0, os.SEEK_SET)
    os.ftruncate(descriptor, 0)
    os.write(descriptor, data)
    os.fsync(descriptor)


def acquire_exclusive_lock() -> int:
    EVIDENCE_PARENT.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(EVIDENCE_LOCK, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(descriptor)
        raise GateError(
            f"another KL-153a runner owns exclusive lock {EVIDENCE_LOCK}"
        ) from exc
    write_lock_audit(descriptor, "LOCKED")
    return descriptor


def release_exclusive_lock(descriptor: int) -> None:
    try:
        write_lock_audit(descriptor, "UNLOCKED")
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def cleanup_publication_transients() -> list[str]:
    removed: list[str] = []
    prefixes = (
        f".{EVIDENCE.name}.staging-",
        f".{EVIDENCE.name}.retired-",
        f".{EVIDENCE.name}.failed-",
    )
    if not EVIDENCE_PARENT.is_dir():
        return removed
    for path in sorted(EVIDENCE_PARENT.iterdir()):
        if not any(path.name.startswith(prefix) for prefix in prefixes):
            continue
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(str(path))
    if removed:
        fsync_directory(EVIDENCE_PARENT)
    return removed


def prepare_single_run_evidence() -> dict[str, object]:
    global ACTIVE_RUN_ID, EVIDENCE_OWNED, STARTUP_TRANSIENT_CLEANUP

    ACTIVE_RUN_ID = f"{time.time_ns()}-{os.getpid()}-{os.urandom(8).hex()}"
    EVIDENCE_OWNED = False
    STARTUP_TRANSIENT_CLEANUP = cleanup_publication_transients()
    runner = file_identity(RUNNER)
    staging = EVIDENCE_PARENT / f".{EVIDENCE.name}.staging-{ACTIVE_RUN_ID}"
    retired = EVIDENCE_PARENT / f".{EVIDENCE.name}.retired-{ACTIVE_RUN_ID}"
    staging.mkdir(parents=True)
    atomic_write_json(
        staging / "RUNNING.json",
        {
            "task": "KL-153a",
            "state": "RUNNING",
            "run_id": ACTIVE_RUN_ID,
            "runner_identity": runner,
            "started_unix_ns": time.time_ns(),
        },
    )
    atomic_write_json(
        EVIDENCE_CURRENT,
        {
            "task": "KL-153a",
            "state": "RUNNING",
            "run_id": ACTIVE_RUN_ID,
            "runner_identity": runner,
            "canonical_evidence": str(EVIDENCE),
            "started_unix_ns": time.time_ns(),
            "valid_pass": False,
        },
    )
    if EVIDENCE.is_symlink():
        raise GateError("canonical evidence path must not be a symlink")
    if EVIDENCE.exists():
        os.rename(EVIDENCE, retired)
    os.rename(staging, EVIDENCE)
    EVIDENCE_OWNED = True
    fsync_directory(EVIDENCE_PARENT)
    if retired.exists():
        shutil.rmtree(retired)
        fsync_directory(EVIDENCE_PARENT)
    return runner


def publish_failure(error: BaseException) -> None:
    global EVIDENCE_OWNED

    if ACTIVE_RUN_ID is None:
        return
    failed_payload = {
        "task": "KL-153a",
        "state": "FAILED",
        "run_id": ACTIVE_RUN_ID,
        "error": str(error),
        "runner_identity": file_identity(RUNNER) if RUNNER.is_file() else None,
        "failed_unix_ns": time.time_ns(),
    }
    if not EVIDENCE_OWNED:
        failed = EVIDENCE_PARENT / f".{EVIDENCE.name}.failed-{ACTIVE_RUN_ID}"
        retired = EVIDENCE_PARENT / f".{EVIDENCE.name}.retired-{ACTIVE_RUN_ID}"
        if failed.exists():
            shutil.rmtree(failed)
        failed.mkdir()
        atomic_write_json(failed / "FAILED.json", failed_payload)
        if EVIDENCE.exists():
            os.rename(EVIDENCE, retired)
        os.rename(failed, EVIDENCE)
        EVIDENCE_OWNED = True
        fsync_directory(EVIDENCE_PARENT)
        if retired.exists():
            shutil.rmtree(retired)
            fsync_directory(EVIDENCE_PARENT)
    (EVIDENCE / "summary.json").unlink(missing_ok=True)
    (EVIDENCE / "artifact-manifest.json").unlink(missing_ok=True)
    atomic_write_json(EVIDENCE / "FAILED.json", failed_payload)
    (EVIDENCE / "RUNNING.json").unlink(missing_ok=True)
    fsync_directory(EVIDENCE)
    failure_identity = file_identity(EVIDENCE / "FAILED.json")
    atomic_write_json(
        EVIDENCE_CURRENT,
        {
            "task": "KL-153a",
            "state": "FAILED",
            "run_id": ACTIVE_RUN_ID,
            "canonical_evidence": str(EVIDENCE),
            "failure_identity": failure_identity,
            "valid_pass": False,
        },
    )


def execute(
    name: str, command: list[str], *, cwd: Path = ROOT, check: bool = True
) -> subprocess.CompletedProcess[str]:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    (EVIDENCE / f"{name}.log").write_text(
        "=== command ===\n"
        + shlex.join(command)
        + "\n=== cwd ===\n"
        + str(cwd)
        + "\n=== returncode ===\n"
        + str(result.returncode)
        + "\n=== stdout ===\n"
        + result.stdout
        + "\n=== stderr ===\n"
        + result.stderr
    )
    if check and result.returncode:
        raise GateError(f"{name}: rc={result.returncode}")
    return result


def make_tree(
    name: str, source: Path, output: Path, *targets: str
) -> subprocess.CompletedProcess[str]:
    return execute(
        name,
        [
            "make",
            "-C",
            str(source),
            f"O={output}",
            "ARCH=dadao",
            f"CC={LLVM_BIN / 'clang'} --target=dadao",
            f"LD={LLVM_BIN / 'ld.lld'}",
            f"AR={LLVM_BIN / 'llvm-ar'}",
            f"NM={LLVM_BIN / 'llvm-nm'}",
            f"OBJCOPY={LLVM_BIN / 'llvm-objcopy'}",
            f"OBJDUMP={LLVM_BIN / 'llvm-objdump'}",
            f"READELF={LLVM_BIN / 'llvm-readelf'}",
            "HOSTCC=cc",
            "HOSTCXX=c++",
            "KCFLAGS=-O0",
            "KBUILD_LDFLAGS=--error-limit=0",
            *targets,
        ],
    )


def make(name: str, output: Path, *targets: str) -> subprocess.CompletedProcess[str]:
    return make_tree(name, LINUX_SOURCE, output, *targets)


def component_pin(name: str) -> str:
    with MANIFEST.open("rb") as stream:
        manifest = tomllib.load(stream)
    for component in manifest["component"]:
        if component["name"] == name:
            return component["commit"]
    raise GateError(f"manifest component missing: {name}")


def patch_id(payload: str) -> str:
    result = subprocess.run(
        ["git", "patch-id", "--stable"],
        cwd=ROOT,
        text=True,
        input=payload,
        capture_output=True,
    )
    if result.returncode or not result.stdout.strip():
        raise GateError("cannot calculate stable patch-id")
    return result.stdout.split()[0]


def series_names(series: Path) -> list[str]:
    return [
        line.strip()
        for line in series.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def verify_queue(name: str, source: Path, series: Path) -> list[dict[str, object]]:
    patches = series_names(series)
    commits = execute(
        f"{name}-commits",
        ["git", "-C", str(source), "rev-list", "--reverse", f"{component_pin(name)}..HEAD"],
    ).stdout.splitlines()
    if len(commits) != len(patches):
        raise GateError(
            f"{name} commit/patch count mismatch: {len(commits)} != {len(patches)}"
        )
    rows: list[dict[str, object]] = []
    for index, (commit, patch_name) in enumerate(zip(commits, patches, strict=True)):
        patch_path = series.parent / patch_name
        if not patch_path.is_file():
            raise GateError(f"{name} patch missing: {patch_name}")
        commit_mail = execute(
            f"{name}-commit-{index + 1:04d}",
            ["git", "-C", str(source), "show", "--pretty=email", commit],
        ).stdout
        commit_id = patch_id(commit_mail)
        payload_id = patch_id(patch_path.read_text())
        if commit_id != payload_id:
            raise GateError(
                f"{name} patch payload drift: {patch_name}: {payload_id} != {commit_id}"
            )
        payload_identity = file_identity(patch_path)
        rows.append(
            {
                "patch": patch_name,
                "patch_path": str(patch_path),
                "patch_size": payload_identity["size"],
                "patch_sha256": payload_identity["sha256"],
                "commit": commit,
                "patch_id": payload_id,
            }
        )
    return rows


# ---------------------------------------------------------------------
# Frozen precondition verification.
# ---------------------------------------------------------------------

def verify_root_frozen_identity() -> dict[str, str]:
    for source_name, source in (("Linux", LINUX_SOURCE), ("QEMU", QEMU_SOURCE), ("LLVM", LLVM_SOURCE)):
        dirty = execute(
            f"{source_name.lower()}-status-before",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{source_name} source worktree dirty before start:\n{dirty}")
    head = execute("root-head", ["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    parent = execute("root-parent", ["git", "-C", str(ROOT), "rev-parse", "HEAD^"]).stdout.strip()
    if head != ROOT_KL153A_DEFINE_COMMIT:
        raise GateError(f"KL-153a task-define commit drift: {head}")
    if parent != ROOT_FROZEN_TASK_COMMIT:
        raise GateError(f"KL-152a frozen root commit drift: {parent}")
    return {"task_define_commit": head, "kl152_frozen_commit": parent}


def verify_kl152_frozen_evidence() -> dict[str, object]:
    if not KL152_SUMMARY.is_file():
        raise GateError(f"KL-152a summary missing: {KL152_SUMMARY}")
    if sha256(KL152_SUMMARY) != KL152_SUMMARY_SHA256:
        raise GateError("KL-152a frozen summary identity drift")
    summary = json.loads(KL152_SUMMARY.read_text())
    required = {
        ("task",): "KL-152a",
        ("result",): "PASS",
        ("counts", "pass"): 3,
        ("counts", "fail"): 0,
        ("counts", "skip"): 0,
        ("qemu_identity", "head"): QEMU_HEAD,
        ("qemu_identity", "sha256"): QEMU_SHA256,
        ("positive_runtime", "console_verdict"): True,
        ("negative_serial_none", "console_verdict"): False,
        ("negative_wrong_mode", "status", "status"): "shutdown",
    }
    for keys, expected in required.items():
        value: object = summary
        for key in keys:
            value = value[key]  # type: ignore[index]
        if value != expected:
            raise GateError(f"KL-152a evidence drift at {'.'.join(keys)}: {value!r} != {expected!r}")
    if not KL152_CURRENT.is_file():
        raise GateError("KL-152a external current-state file missing")
    current = json.loads(KL152_CURRENT.read_text())
    if current.get("state") != "PASS" or current.get("valid_pass") is not True:
        raise GateError("KL-152a external current-state is not a valid PASS")
    manifest_path = Path(str(summary["artifact_manifest"]["path"]))
    if not manifest_path.is_file() or file_identity(manifest_path) != summary["artifact_manifest"]:
        raise GateError("KL-152a frozen manifest identity drifted")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("artifact_count") != KL152_ARTIFACT_COUNT or len(manifest.get("artifacts", [])) != KL152_ARTIFACT_COUNT:
        raise GateError("KL-152a frozen 223-item manifest contract drifted")
    for artifact in manifest["artifacts"]:
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_file() or file_identity(artifact_path) != artifact:
            raise GateError(f"KL-152a frozen manifest artifact drifted: {artifact_path}")
    return {
        "path": str(KL152_SUMMARY),
        "sha256": sha256(KL152_SUMMARY),
        "counts": summary["counts"],
        "artifact_manifest": summary["artifact_manifest"],
        "artifact_count": manifest["artifact_count"],
        "current_state": current,
    }


def verify_llvm_component_identity() -> dict[str, object]:
    # NOTE: unlike verify_linux_component_identity (which validates every
    # commit/patch-id pair KL-153a itself created), this task does not
    # re-audit the full pre-existing 65-patch LLVM queue's commit<->patch-id
    # fidelity -- KL-152a's own script never checked LLVM identity at all
    # (LLVM wasn't touched by that task), and a scan here found patch 0003
    # ("dadao-register-info.patch", pre-dating this task by dozens of
    # patches) already has a three-way commit/orphaned-duplicate/patch-file
    # patch-id mismatch, i.e. pre-existing drift unrelated to KL-153a and
    # out of this task's scope to repair. What KL-153a verifies precisely
    # is its OWN new patch: exact commit, patch-id, size, SHA256, series
    # position, and that it sits directly on the recorded pre-fix HEAD.
    names = series_names(LLVM_SERIES)
    if len(names) != LLVM_SERIES_COUNT:
        raise GateError(f"LLVM series count drift: {len(names)} != {LLVM_SERIES_COUNT}")
    if names[-1] != LLVM_FIX_PATCH_NAME:
        raise GateError(f"LLVM series final patch name drift: {names[-1]}")
    commits = execute(
        "llvm-commits",
        ["git", "-C", str(LLVM_SOURCE), "rev-list", "--reverse", f"{component_pin('llvm')}..HEAD"],
    ).stdout.splitlines()
    if len(commits) != len(names):
        raise GateError(f"LLVM commit/patch count mismatch: {len(commits)} != {len(names)}")
    if commits[-1] != LLVM_FIX_COMMIT:
        raise GateError(f"LLVM HEAD commit drift: {commits[-1]} != {LLVM_FIX_COMMIT}")
    fix_patch_path = LLVM_SERIES.parent / LLVM_FIX_PATCH_NAME
    commit_mail = execute(
        "llvm-fix-commit-email", ["git", "-C", str(LLVM_SOURCE), "show", "--pretty=email", LLVM_FIX_COMMIT]
    ).stdout
    commit_id = patch_id(commit_mail)
    payload_id = patch_id(fix_patch_path.read_text())
    if commit_id != payload_id:
        raise GateError(f"LLVM fix patch payload drift: commit={commit_id} payload={payload_id}")
    fix_identity = file_identity(fix_patch_path)
    fix_row = {
        "patch": LLVM_FIX_PATCH_NAME,
        "commit": LLVM_FIX_COMMIT,
        "patch_id": payload_id,
        "patch_size": fix_identity["size"],
        "patch_sha256": fix_identity["sha256"],
    }
    if (
        fix_row["patch_id"] != LLVM_FIX_PATCH_ID
        or fix_row["patch_size"] != LLVM_FIX_PATCH_SIZE
        or fix_row["patch_sha256"] != LLVM_FIX_PATCH_SHA256
    ):
        raise GateError(f"LLVM fix patch identity drift: {fix_row}")
    parent = execute(
        "llvm-fix-parent", ["git", "-C", str(LLVM_SOURCE), "rev-parse", f"{LLVM_FIX_COMMIT}^"]
    ).stdout.strip()
    if parent != LLVM_HEAD_BEFORE:
        raise GateError(f"LLVM pre-fix HEAD drift: {parent} != {LLVM_HEAD_BEFORE}")
    return {
        "series": file_identity(LLVM_SERIES),
        "patch_count": len(names),
        "fix_patch": fix_row,
        "pre_fix_head": parent,
        "pre_existing_patch0003_drift_out_of_scope": (
            "components/llvm/patches/0003-dadao-register-info.patch does not "
            "patch-id-match either the live commit at that series position or "
            "an orphaned duplicate commit with the same message; this predates "
            "KL-153a by dozens of patches and is not touched by this task"
        ),
    }


def verify_linux_component_identity() -> dict[str, object]:
    rows = verify_queue("linux", LINUX_SOURCE, LINUX_SERIES)
    names = series_names(LINUX_SERIES)
    expected_new_names = [row[0] for row in LINUX_NEW_PATCHES]
    if names[-len(LINUX_NEW_PATCHES):] != expected_new_names:
        raise GateError("Linux KL-153a new series names/order drifted")
    new_rows = rows[-len(LINUX_NEW_PATCHES):]
    for row, expected in zip(new_rows, LINUX_NEW_PATCHES, strict=True):
        if (row["patch"], row["commit"], row["patch_id"]) != expected:
            raise GateError(f"Linux KL-153a new patch identity drift: {row}")
    parent = execute(
        "linux-pre-fix-parent",
        ["git", "-C", str(LINUX_SOURCE), "rev-parse", f"{LINUX_NEW_PATCHES[0][1]}^"],
    ).stdout.strip()
    if parent != LINUX_HEAD_BEFORE:
        raise GateError(f"Linux pre-fix HEAD drift: {parent} != {LINUX_HEAD_BEFORE}")
    return {
        "series": file_identity(LINUX_SERIES),
        "patch_count": len(rows),
        "new_patches": new_rows,
        "pre_fix_head": parent,
    }


def verify_patch_series_replay(
    name: str, source: Path, series: Path, base_commit: str, expected_head: str
) -> dict[str, object]:
    """Prove the exported patch series reproduces the dev tree byte-for-
    byte: `git am` the entire series, in order, into a fresh detached
    worktree at the pinned upstream base commit, then compare the
    replayed tree's `git rev-parse HEAD^{tree}` against the real dev
    tree's. Persists the full `git am` transcript and the two tree
    hashes as evidence artifacts (not just an asserted claim)."""
    patches = [str(series.parent / p) for p in series_names(series)]
    with tempfile.TemporaryDirectory(prefix=f"kl153a_{name}_replay_") as tmp:
        worktree = Path(tmp) / "wt"
        execute(
            f"{name}-replay-worktree-add",
            ["git", "-C", str(source), "worktree", "add", "--detach", str(worktree), base_commit],
        )
        try:
            am_result = execute(
                f"{name}-replay-git-am", ["git", "am", *patches], cwd=worktree, check=False
            )
            if am_result.returncode:
                execute(f"{name}-replay-git-am-abort", ["git", "am", "--abort"], cwd=worktree, check=False)
                raise GateError(f"{name} patch series does not apply cleanly in replay: rc={am_result.returncode}")
            replay_tree = execute(
                f"{name}-replay-tree-hash", ["git", "-C", str(worktree), "rev-parse", "HEAD^{tree}"]
            ).stdout.strip()
            devtree_head = execute(
                f"{name}-replay-devtree-head", ["git", "-C", str(source), "rev-parse", expected_head + "^{tree}"]
            ).stdout.strip()
            if replay_tree != devtree_head:
                raise GateError(
                    f"{name} patch series replay tree hash mismatch: "
                    f"replay={replay_tree} devtree={devtree_head}"
                )
        finally:
            execute(
                f"{name}-replay-worktree-remove",
                ["git", "-C", str(source), "worktree", "remove", "--force", str(worktree)],
                check=False,
            )
            execute(f"{name}-replay-worktree-prune", ["git", "-C", str(source), "worktree", "prune"], check=False)
    return {
        "base_commit": base_commit,
        "expected_head": expected_head,
        "patch_count": len(patches),
        "replay_tree_hash": replay_tree,
        "devtree_tree_hash": devtree_head,
        "match": True,
        "am_transcript_log": str(EVIDENCE / f"{name}-replay-git-am.log"),
    }


def verify_qemu_unchanged_identity() -> dict[str, object]:
    dirty = execute(
        "qemu-status-before", ["git", "-C", str(QEMU_SOURCE), "status", "--porcelain=v1"]
    ).stdout.strip()
    if dirty:
        raise GateError(f"QEMU source worktree dirty:\n{dirty}")
    head = execute("qemu-head", ["git", "-C", str(QEMU_SOURCE), "rev-parse", "HEAD"]).stdout.strip()
    if head != QEMU_HEAD:
        raise GateError(f"QEMU HEAD drift: {head} != {QEMU_HEAD}")
    execute("qemu-rebuild", ["ninja", "-C", str(QEMU_BUILD), "qemu-system-dadao"], cwd=QEMU_SOURCE)
    binary_hash = sha256(QEMU)
    if binary_hash != QEMU_SHA256:
        raise GateError(f"rebuilt QEMU hash drift: {binary_hash} != {QEMU_SHA256}")
    version = execute("qemu-version", [str(QEMU), "--version"]).stdout.splitlines()[0]
    if QEMU_HEAD[:7] not in version:
        raise GateError(f"QEMU version does not bind HEAD: {version}")
    return {"path": str(QEMU), "head": head, "sha256": binary_hash, "version": version}


# ---------------------------------------------------------------------
# LLVM rebuild + CodeGen regression.
# ---------------------------------------------------------------------

def rebuild_and_verify_llvm() -> dict[str, object]:
    execute(
        "llvm-rebuild",
        ["ninja", "llc", "clang", "llvm-objdump", "llvm-nm", "FileCheck", "count", "not"],
        cwd=LLVM_BUILD,
    )
    head = execute("llvm-head", ["git", "-C", str(LLVM_SOURCE), "rev-parse", "HEAD"]).stdout.strip()
    if head != LLVM_FIX_COMMIT:
        raise GateError(f"LLVM HEAD drift: {head} != {LLVM_FIX_COMMIT}")
    identities = {}
    for tool in ("clang", "llc", "llvm-objdump"):
        version = execute(f"llvm-{tool}-version", [str(LLVM_BIN / tool), "--version"]).stdout
        first_line = version.splitlines()[0] if version else ""
        # Only clang's --version embeds the source git hash; llc and
        # llvm-objdump have no such string. Their identity is instead
        # bound by construction: LLVM_SOURCE HEAD was already verified to
        # equal LLVM_FIX_COMMIT immediately before this same `ninja`
        # invocation rebuilt all three from that one source tree, plus
        # each binary's own SHA256 recorded below.
        if tool == "clang" and LLVM_FIX_COMMIT[:12] not in version:
            raise GateError(f"clang version does not bind fix commit: {first_line}")
        identities[tool] = {
            "path": str(LLVM_BIN / tool),
            "sha256": sha256(LLVM_BIN / tool),
            "version_first_line": first_line,
        }
    return {"head": head, "tools": identities}


def run_llvm_codegen_regression() -> dict[str, object]:
    lit_bin = str(LLVM_BIN / "llvm-lit")
    targeted = execute(
        "llvm-lit-kl153a-test",
        [lit_bin, "-v", str(LLVM_SOURCE / "llvm/test/CodeGen/DADAO/bool-retval-stack-slot-load.ll")],
    )
    full_codegen = execute(
        "llvm-lit-codegen-dadao",
        [lit_bin, "-v", str(LLVM_SOURCE / "llvm/test/CodeGen/DADAO")],
    )

    def parse_counts(text: str) -> dict[str, int]:
        discovered = re.search(r"Total Discovered Tests:\s*(\d+)", text)
        passed = re.search(r"Passed:\s*(\d+)", text)
        failed = re.search(r"Failed:\s*(\d+)", text)
        skipped = re.search(r"(?:Unsupported|Skipped):\s*(\d+)", text)
        return {
            "discovered": int(discovered.group(1)) if discovered else -1,
            "passed": int(passed.group(1)) if passed else 0,
            "failed": int(failed.group(1)) if failed else 0,
            "skipped": int(skipped.group(1)) if skipped else 0,
        }

    targeted_counts = parse_counts(targeted.stdout)
    full_counts = parse_counts(full_codegen.stdout)
    if targeted_counts["discovered"] != 1 or targeted_counts["passed"] != 1 or targeted_counts["failed"]:
        raise GateError(f"KL-153a targeted CodeGen test did not cleanly pass: {targeted_counts}")
    if full_counts["failed"] or full_counts["skipped"]:
        raise GateError(f"CodeGen/DADAO regression suite is not fully clean: {full_counts}")

    # MIR/asm-level machine evidence: rebuild the exact node_tag_get-shape
    # repro at -O0 and assert the retval slot uses a legal byte load +
    # zero extension (or a naturally aligned same-width slot), and
    # explicitly reject the old same-slot stb-then-ldo pattern.
    repro_ir = EVIDENCE / "repro-node-tag-get-shape.ll"
    repro_ir.write_text(
        "define i1 @kl153a_repro(i1 %x, i1 %y) {\n"
        "entry:\n"
        "  %retval = alloca i1, align 1\n"
        "  br i1 %y, label %a, label %b\n"
        "a:\n"
        "  store i1 %x, ptr %retval, align 1\n"
        "  br label %join\n"
        "b:\n"
        "  store i1 %x, ptr %retval, align 1\n"
        "  br label %join\n"
        "join:\n"
        "  %v = load i1, ptr %retval, align 1\n"
        "  ret i1 %v\n"
        "}\n"
    )
    asm = execute(
        "repro-node-tag-get-shape-asm",
        [str(LLVM_BIN / "llc"), "-O0", "-mtriple=dadao", str(repro_ir), "-o", "-"],
    ).stdout
    mir = execute(
        "repro-node-tag-get-shape-mir",
        [
            str(LLVM_BIN / "llc"),
            "-O0",
            "-mtriple=dadao",
            "-stop-after=finalize-isel",
            str(repro_ir),
            "-o",
            "-",
        ],
    ).stdout
    if "ldbu" not in asm:
        raise GateError("repro asm evidence missing expected ldbu byte load")
    stb_then_ldo = re.search(
        r"stb\s+\S+,\s*(rb\d+),\s*0.*?\n(?:.*\n)*?\s*addi\s+\1,.*\n\s*ldo\s+\S+,\s*\1,\s*0",
        asm,
    )
    if stb_then_ldo is not None:
        raise GateError("repro asm still exhibits same-slot stb-then-ldo pattern")
    return {
        "targeted_test": {
            "path": str(
                LLVM_SOURCE / "llvm/test/CodeGen/DADAO/bool-retval-stack-slot-load.ll"
            ),
            "counts": targeted_counts,
        },
        "full_codegen_dadao": {"counts": full_counts},
        "repro_ir": file_identity(repro_ir),
        "repro_asm": file_identity(EVIDENCE / "repro-node-tag-get-shape-asm.log"),
        "repro_mir": file_identity(EVIDENCE / "repro-node-tag-get-shape-mir.log"),
        "repro_asserts": [
            "asm contains ldbu (byte load, zero extend)",
            "asm does not contain same-slot stb-then-ldo",
        ],
    }


def run_full_e2e_suite() -> dict[str, object]:
    result = execute(
        "e2e-lit", [str(LLVM_BIN / "llvm-lit"), "-sv", "tests/lit/E2E/"], cwd=ROOT
    )
    text = result.stdout + result.stderr
    discovered = re.search(r"Total Discovered Tests:\s*(\d+)", text)
    passed = re.search(r"Passed:\s*(\d+)\s*\(([\d.]+)%\)", text)
    failed = "Failed:" in text
    unsupported = "Unsupported:" in text
    counts = {
        "discovered": int(discovered.group(1)) if discovered else -1,
        "passed": int(passed.group(1)) if passed else -1,
        "passed_pct": float(passed.group(2)) if passed else -1.0,
        "failed_present": failed,
        "unsupported_present": unsupported,
    }
    if counts["discovered"] != 81 or counts["passed"] != 81 or failed or unsupported:
        raise GateError(f"E2E lit suite is not clean 81/81: {counts}")
    return counts


# ---------------------------------------------------------------------
# Linux carrier-removal source + disassembly verification.
# ---------------------------------------------------------------------

def verify_carrier_removal_source_contract() -> dict[str, object]:
    for rel_path, marker in REMOVED_CARRIER_MARKERS:
        text = (LINUX_SOURCE / rel_path).read_text()
        if marker in text:
            raise GateError(f"carrier marker still present: {rel_path}: {marker!r}")
    for rel_path, marker in RESTORED_BOOL_MARKERS:
        text = (LINUX_SOURCE / rel_path).read_text()
        if marker not in text:
            raise GateError(f"restored bool signature missing: {rel_path}: {marker!r}")
    # CONFIG_DADAO_K3_O0_LINK_COMPAT must survive exactly once outside
    # o0-link-compat.c (the legitimate huge_mm.h disabled-feature macro
    # fallback), plus its own definition site and o0-link-compat.c's use.
    remaining = execute(
        "carrier-grep-remaining",
        [
            "grep", "-rl", "CONFIG_DADAO_K3_O0_LINK_COMPAT",
            "--include=*.c", "--include=*.h", str(LINUX_SOURCE),
        ],
        check=False,
    ).stdout.splitlines()
    remaining_rel = sorted(str(Path(p).relative_to(LINUX_SOURCE)) for p in remaining)
    # arch/dadao/mm/o0-link-compat.c is gated by the Makefile
    # (obj-$(CONFIG_DADAO_K3_O0_LINK_COMPAT) += o0-link-compat.o), not an
    # in-file #ifdef, and Kconfig's own `config DADAO_K3_O0_LINK_COMPAT`
    # block is the option's definition, not a use of it -- neither shows
    # up in a #ifdef-usage grep. include/linux/huge_mm.h is the one
    # legitimate remaining #ifdef use (disabled-feature HPAGE_PMD_* macro
    # fallback), which the task requires be left untouched.
    expected_rel = sorted(["include/linux/huge_mm.h"])
    if remaining_rel != expected_rel:
        raise GateError(
            f"CONFIG_DADAO_K3_O0_LINK_COMPAT usage drift: {remaining_rel} != {expected_rel}"
        )
    o0_link_compat = (LINUX_SOURCE / "arch/dadao/mm/o0-link-compat.c").read_text()
    if "frontswap_store" not in o0_link_compat:
        raise GateError("o0-link-compat.c disabled-feature contract appears damaged")
    return {
        "removed_markers_checked": len(REMOVED_CARRIER_MARKERS),
        "restored_bool_markers_checked": len(RESTORED_BOOL_MARKERS),
        "config_dadao_k3_o0_link_compat_sites": remaining_rel,
    }


def nearest_symbols(vmlinux: Path, name: str) -> list[tuple[int, int]]:
    """Return [(start_addr, end_addr_exclusive), ...] for every symbol
    named `name` in vmlinux, end being the next symbol's address."""
    lines = execute(
        f"nm-lookup-{name}", [str(LLVM_BIN / "llvm-nm"), "-n", str(vmlinux)]
    ).stdout.splitlines()
    rows: list[tuple[int, str]] = []
    for line in lines:
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            address = int(fields[0], 16)
        except ValueError:
            continue
        rows.append((address, fields[2]))
    spans: list[tuple[int, int]] = []
    for index, (address, symbol) in enumerate(rows):
        if symbol != name:
            continue
        end = rows[index + 1][0] if index + 1 < len(rows) else address + 0x400
        spans.append((address, end))
    return spans


_LINE_RE = re.compile(r"^\s*(?:[0-9a-f]+:\s+[0-9a-f ]+\s+)?(\S+)\s+(.*)$")
_ADDI_RB1_RE = re.compile(r"^(rb\d+),\s*rb1,\s*(-?\d+)\s*$")
# DADAOISelDAGToDAG.cpp's FrameIndex-addressed narrow load/store path emits
# `Ops = {NewAddr, GEPOff ? Offset : Zero, Chain}` -- i.e. the instruction's
# own trailing immediate is NOT always literal 0; a non-zero secondary
# GEP-style offset on top of the tracked scratch register (e.g. an i1
# struct member reached through `&base->field` rather than a bare
# `alloca i1`) shows up as that immediate instead. Capture it generally
# and add it to the tracked base offset, rather than requiring the
# immediate to be exactly "0", so the same-slot check still holds for
# that shape too.
_MEM_OP_RE = re.compile(r"^\S+,\s*(rb\d+),\s*(-?\d+)\s*$")
_DEST_REG_RE = re.compile(r"^(rb\d+)\b")


def scan_no_same_slot_stb_then_ldo(disassembly: str) -> list[str]:
    """Linear-scan register tracker: for each `rbN`, remember the last
    `addi rbN, rb1, OFFSET` seen so far (any number of instructions may
    separate that address computation from its use). Any OTHER
    instruction that writes rbN (e.g. `rd2rb rbN, ...` materializing a
    jump-table/pointer target, or `addi rbN, rbM, ...` with a non-rb1
    base) invalidates the tracked offset for rbN, so an unrelated later
    reuse of the same scratch register for a genuinely different address
    (a real, observed DADAO codegen pattern in switch-like dispatch code)
    is not misattributed to the earlier frame slot. Record the EFFECTIVE
    address (tracked base offset + the instruction's own trailing
    immediate, which is not always 0 -- see _MEM_OP_RE) used by both an
    `stb` and an `ldo` anywhere in the disassembly; that overlap is
    exactly the same-slot byte-store/doubleword-reload defect this task
    fixes."""
    current_offset: dict[str, int] = {}
    stores: set[int] = set()
    loads: set[int] = set()
    for line in disassembly.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        mnemonic, operands = m.group(1), m.group(2)
        dest = _DEST_REG_RE.match(operands)
        if mnemonic == "addi":
            am = _ADDI_RB1_RE.match(operands)
            if am:
                current_offset[am.group(1)] = int(am.group(2))
                continue
            if dest:
                current_offset.pop(dest.group(1), None)
            continue
        if mnemonic == "stb":
            sm = _MEM_OP_RE.match(operands)
            if sm and sm.group(1) in current_offset:
                stores.add(current_offset[sm.group(1)] + int(sm.group(2)))
            continue
        if mnemonic == "ldo":
            lm = _MEM_OP_RE.match(operands)
            if lm and lm.group(1) in current_offset:
                loads.add(current_offset[lm.group(1)] + int(lm.group(2)))
            continue
        if dest:
            current_offset.pop(dest.group(1), None)
    return sorted(str(v) for v in (stores & loads))


def verify_carrier_removal_disassembly(vmlinux: Path) -> dict[str, object]:
    results: dict[str, object] = {}
    for name in FROZEN_CARRIER_SYMBOLS:
        spans = nearest_symbols(vmlinux, name)
        if not spans:
            results[name] = {"status": "inlined-away-no-standalone-symbol"}
            continue
        violations: list[dict[str, object]] = []
        for start, end in spans:
            disas = execute(
                f"disasm-{name}-{start:x}",
                [
                    str(LLVM_BIN / "llvm-objdump"),
                    "--arch-name=dadao",
                    "-d",
                    f"--start-address={start:#x}",
                    f"--stop-address={end:#x}",
                    str(vmlinux),
                ],
            ).stdout
            overlap = scan_no_same_slot_stb_then_ldo(disas)
            if overlap:
                violations.append({"address": f"0x{start:016x}", "overlap": overlap})
        if violations:
            raise GateError(f"same-slot stb-then-ldo still present: {name}: {violations}")
        results[name] = {
            "status": "clean",
            "occurrences": len(spans),
            "addresses": [f"0x{s:016x}" for s, _ in spans],
        }
    return results


def reject_forbidden_diagnostics(result: subprocess.CompletedProcess[str]) -> None:
    diagnostics = result.stdout + result.stderr
    found = []
    if "shift count is negative" in diagnostics:
        found.append("shift count is negative")
    if any("ELF_CLASS" in line and "is not defined" in line for line in diagnostics.splitlines()):
        found.append("ELF_CLASS is not defined")
    if found:
        raise GateError(f"forbidden Linux build diagnostics: {found}")


def build_linux_image() -> dict[str, object]:
    make("linux-mrproper", LINUX_OUTPUT, "mrproper")
    make("linux-defconfig", LINUX_OUTPUT, "dadao_defconfig")
    make("linux-olddefconfig", LINUX_OUTPUT, "olddefconfig")
    positive_build = make("linux-image", LINUX_OUTPUT, "Image")
    reject_forbidden_diagnostics(positive_build)
    vmlinux = LINUX_OUTPUT / "vmlinux"
    image = LINUX_OUTPUT / "arch" / "dadao" / "boot" / "Image"
    for path in (vmlinux, image):
        if not path.is_file() or path.stat().st_size == 0:
            raise GateError(f"missing or empty Linux output: {path}")
    disassembly = verify_carrier_removal_disassembly(vmlinux)
    return {
        "vmlinux": str(vmlinux),
        "vmlinux_sha256": sha256(vmlinux),
        "image": str(image),
        "image_sha256": sha256(image),
        "carrier_disassembly": disassembly,
    }


# ---------------------------------------------------------------------
# QEMU runtime.
# ---------------------------------------------------------------------

def qmp_roundtrip(stream, request: dict) -> object:
    stream.write(json.dumps(request) + "\n")
    stream.flush()
    while True:
        line = stream.readline()
        if not line:
            raise GateError("QMP connection closed")
        reply = json.loads(line)
        if "error" in reply:
            raise GateError(f"QMP error: {reply['error']}")
        if "return" in reply:
            return reply["return"]


def dump_oracle(stream, output: Path) -> bytes:
    output.unlink(missing_ok=True)
    result = qmp_roundtrip(
        stream,
        {
            "execute": "human-monitor-command",
            "arguments": {"command-line": f'pmemsave {SCRATCH_BASE:#x} {ORACLE_SIZE} "{output}"'},
        },
    )
    if result:
        raise GateError(f"QEMU pmemsave failed: {result}")
    payload = output.read_bytes()
    if len(payload) != ORACLE_SIZE:
        raise GateError(f"QEMU oracle size drift: {len(payload)}")
    return payload


def decode_oracle(payload: bytes) -> tuple[int, ...]:
    return struct.unpack(">QQQQQQQ", payload)


def progress_is_ordered(words: tuple[int, ...]) -> bool:
    seen_zero = False
    for actual, expected in zip(words, PROGRESS_VALUES, strict=True):
        if actual == 0:
            seen_zero = True
        elif actual != expected or seen_zero:
            return False
    return True


def progress_depth(words: tuple[int, ...]) -> int:
    depth = 0
    for actual, expected in zip(words, PROGRESS_VALUES, strict=True):
        if actual == expected:
            depth += 1
        else:
            break
    return depth


def console_verdict(payload: bytes) -> tuple[bool, list[int], list[int]]:
    counts = [payload.count(anchor) for anchor in ANCHORS]
    positions = [payload.find(anchor) for anchor in ANCHORS]
    passed = counts == [1, 1, 1, 1, 1] and positions == sorted(positions)
    return passed, counts, positions


def connect_qmp(proc: subprocess.Popen[bytes], qmp_path: Path, timeout: float):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout
    while True:
        try:
            sock.connect(str(qmp_path))
            break
        except OSError:
            if proc.poll() is not None:
                raise GateError(f"QEMU exited before QMP connect: rc={proc.returncode}")
            if time.monotonic() >= deadline:
                raise GateError("QMP connect timeout")
            time.sleep(0.02)
    sock.settimeout(3.0)
    stream = sock.makefile("rw", encoding="utf-8", newline="\n")
    greeting = stream.readline()
    if not greeting:
        raise GateError("QMP greeting missing")
    qmp_roundtrip(stream, {"execute": "qmp_capabilities"})
    return sock, stream, greeting


def scan_trace_for_malign(trace_path: Path) -> list[tuple[int, int]]:
    if not trace_path.is_file():
        return []
    trace = trace_path.read_text()
    return [
        (int(index), int(pc, 16))
        for index, pc in re.findall(r"dadao: exception index=(\d+) pc=(0x[0-9a-f]+)", trace)
        if int(index) == 3
    ]


EXTENDED_OBSERVATION_SECONDS = 8.0


def run_progress_guest(
    name: str, image: Path, rom: Path, *, serial_mode: str, timeout: float = 30.0
) -> dict[str, object]:
    if serial_mode not in {"file", "none"}:
        raise GateError(f"invalid serial mode: {serial_mode}")
    transport = tempfile.TemporaryDirectory(prefix=f"kl153a_{name}_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    console_path = EVIDENCE / f"{name}-console.bin"
    console_path.unlink(missing_ok=True)
    trace_path = EVIDENCE / f"{name}-qemu-trace.log"
    trace_path.unlink(missing_ok=True)
    serial_arg = f"file:{console_path}" if serial_mode == "file" else "none"
    command = [
        str(QEMU), "-M", "dadao-m1", "-S",
        "-global", "dadao-cpu.cfx-smon-real=on",
        "-bios", str(rom), "-kernel", str(image),
        "-display", "none", "-serial", serial_arg,
        "-no-shutdown", "-d", "int", "-D", str(trace_path),
        "-qmp", f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    greeting = ""
    snapshots: list[dict[str, object]] = []
    marker_running_status: object = None
    extended_status: object = None
    initial = b""
    final = b""
    reached_full_progress = False
    shutdown_reason: dict[str, object] | None = None
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(f"{name}: scratch nonzero before CPU start: {initial.hex()}")
        (EVIDENCE / f"{name}-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        last_words: tuple[int, ...] | None = None
        last_progress_depth = 0
        start = time.monotonic()
        deadline = start + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise GateError(f"{name}: QEMU exited before progress: rc={proc.returncode}")
            final = dump_oracle(stream, oracle_path)
            words = decode_oracle(final)
            if words != last_words:
                snapshots.append(
                    {
                        "elapsed_seconds": round(time.monotonic() - start, 6),
                        "words": [f"0x{value:016x}" for value in words],
                    }
                )
                last_words = words
            marker, failure, *progress = words
            if marker == MARKER_VALUE and marker_running_status is None:
                marker_running_status = qmp_roundtrip(stream, {"execute": "query-status"})
                if marker_running_status.get("status") != "running" or not marker_running_status.get("running"):
                    raise GateError(f"{name}: KL-149 marker not observed running: {marker_running_status}")
            if marker not in (0, MARKER_VALUE) or failure != 0:
                raise GateError(f"{name}: KL-149 positive oracle regressed: marker={marker:#x} failure={failure:#x}")
            if not progress_is_ordered(tuple(progress)):
                raise GateError(f"{name}: unordered/invalid progress words: {progress}")
            if any(progress) and marker != MARKER_VALUE:
                raise GateError(f"{name}: progress appeared before KL-149 marker: {words}")
            current_progress_depth = progress_depth(tuple(progress))
            if current_progress_depth < last_progress_depth:
                raise GateError(f"{name}: progress regressed: {current_progress_depth} < {last_progress_depth}")
            last_progress_depth = current_progress_depth
            if tuple(progress) == PROGRESS_VALUES:
                reached_full_progress = True
                break
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                malign = scan_trace_for_malign(trace_path)
                raise GateError(f"{name}: shutdown before all progress words: {words} malign={malign}")
            time.sleep(0.02)
        else:
            raise GateError(f"{name}: progress timeout: {snapshots[-1:]}")
        if marker_running_status is None:
            raise GateError(f"{name}: KL-149 marker was never observed")

        # KL-153a extended observation window: unlike KL-152a (which
        # expected node_tag_get's MALIGN to shut the guest down right
        # after mm_init_done), the fix means the guest should keep
        # running. Poll for EXTENDED_OBSERVATION_SECONDS; a shutdown
        # during the window is only acceptable if it is NOT caused by a
        # new EXCP_MALIGN (index=3) -- any EXCP_MALIGN at all during the
        # whole run (before or during the window) is an immediate FAIL.
        window_deadline = time.monotonic() + EXTENDED_OBSERVATION_SECONDS
        while time.monotonic() < window_deadline:
            if proc.poll() is not None:
                break
            extended_status = qmp_roundtrip(stream, {"execute": "query-status"})
            if extended_status.get("status") == "shutdown":
                shutdown_reason = {
                    "status": extended_status,
                    "malign": scan_trace_for_malign(trace_path),
                    "elapsed_since_full_progress": round(
                        time.monotonic() - (window_deadline - EXTENDED_OBSERVATION_SECONDS), 6
                    ),
                }
                break
            time.sleep(0.05)
        final = dump_oracle(stream, oracle_path)
        expected_final = (MARKER_VALUE, 0, *PROGRESS_VALUES)
        final_words = decode_oracle(final)
        if final_words != expected_final:
            raise GateError(f"{name}: final oracle regressed after progress: {final_words} != {expected_final}")
        malign_total = scan_trace_for_malign(trace_path)
        if malign_total:
            raise GateError(f"{name}: new EXCP_MALIGN observed: {malign_total}")
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        (EVIDENCE / f"{name}-qemu-runtime.log").write_text(
            "=== command ===\n" + shlex.join(command)
            + "\n=== greeting ===\n" + greeting
            + "\n=== stdout ===\n" + stdout.decode(errors="replace")
            + "\n=== stderr ===\n" + stderr.decode(errors="replace")
        )
        transport.cleanup()
    if not final:
        raise GateError(f"{name}: final oracle missing")
    (EVIDENCE / f"{name}-progress-final.bin").write_bytes(final)
    console = console_path.read_bytes() if console_path.exists() else b""
    verdict, counts, positions = console_verdict(console)
    malign_after_all = scan_trace_for_malign(trace_path)
    return {
        "command": command,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "final_words": {
            "kl149_marker": f"0x{decode_oracle(final)[0]:016x}",
            "kl149_failure": f"0x{decode_oracle(final)[1]:016x}",
            **{
                key: f"0x{value:016x}"
                for key, value in zip(PROGRESS_NAMES, decode_oracle(final)[2:], strict=True)
            },
        },
        "snapshots": snapshots,
        "kl149_marker_running_status": marker_running_status,
        "reached_full_progress": reached_full_progress,
        "extended_observation_seconds": EXTENDED_OBSERVATION_SECONDS,
        "extended_observation_final_status": extended_status,
        "shutdown_during_extended_observation": shutdown_reason,
        "malign_observed_total": malign_after_all,
        "console_path": str(console_path),
        "console_size": len(console),
        "console_sha256": sha256(console_path) if console_path.exists() else None,
        "console_anchor_counts": counts,
        "console_anchor_positions": positions,
        "console_verdict": verdict,
        "trace_path": str(trace_path),
    }


def run_wrong_mode_guest(image: Path, rom: Path) -> dict[str, object]:
    transport = tempfile.TemporaryDirectory(prefix="kl153a_wrong_mode_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    command = [
        str(QEMU), "-M", "dadao-m1", "-S",
        "-global", "dadao-cpu.cfx-smon-real=on",
        "-bios", str(rom), "-kernel", str(image),
        "-display", "none", "-serial", "none", "-no-shutdown",
        "-qmp", f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    greeting = ""
    initial = b""
    final = b""
    status: object = None
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError("wrong-mode scratch nonzero before CPU start")
        (EVIDENCE / "wrong-mode-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            final = dump_oracle(stream, oracle_path)
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.02)
        else:
            raise GateError("wrong-mode negative did not shut down")
        words = decode_oracle(final)
        if words != (0, FAILURE_VALUE, 0, 0, 0, 0, 0):
            raise GateError(f"wrong-mode oracle drift: {words}")
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        (EVIDENCE / "wrong-mode-qemu-runtime.log").write_text(
            "=== command ===\n" + shlex.join(command)
            + "\n=== greeting ===\n" + greeting
            + "\n=== stdout ===\n" + stdout.decode(errors="replace")
            + "\n=== stderr ===\n" + stderr.decode(errors="replace")
        )
        transport.cleanup()
    (EVIDENCE / "wrong-mode-progress-final.bin").write_bytes(final)
    return {"initial_raw_hex": initial.hex(), "final_raw_hex": final.hex(), "status": status}


def generate_roms() -> tuple[Path, Path]:
    rom = EVIDENCE / "kl153a-handoff.bin"
    wrong_mode = EVIDENCE / "kl153a-handoff-wrong-mode.bin"
    execute(
        "handoff-rom",
        [sys.executable, str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"), str(rom)],
    )
    execute(
        "handoff-rom-wrong-mode",
        [
            sys.executable, str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(wrong_mode), "--previous-mode", "3",
        ],
    )
    if sha256(rom) != ROM_SHA256:
        raise GateError("positive HBI ROM identity drift")
    if sha256(wrong_mode) != WRONG_MODE_ROM_SHA256:
        raise GateError("wrong-mode HBI ROM identity drift")
    return rom, wrong_mode


def verify_sources_clean_after() -> None:
    for source_name, source in (("Linux", LINUX_SOURCE), ("QEMU", QEMU_SOURCE), ("LLVM", LLVM_SOURCE)):
        dirty = execute(
            f"{source_name.lower()}-status-after",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{source_name} source worktree dirty after gate:\n{dirty}")


def publish_artifact_manifest(runner_identity: dict[str, object]) -> dict[str, object]:
    if ACTIVE_RUN_ID is None:
        raise GateError("artifact publication has no active run id")
    running_path = EVIDENCE / "RUNNING.json"
    if not running_path.is_file() or (EVIDENCE / "FAILED.json").exists():
        raise GateError("manifest publication requires RUNNING and forbids FAILED")
    running = json.loads(running_path.read_text())
    if running.get("state") != "RUNNING" or running.get("run_id") != ACTIVE_RUN_ID:
        raise GateError("RUNNING identity does not match active run")
    excluded_names = {"summary.json", "artifact-manifest.json", "RUNNING.json", "FAILED.json"}
    artifacts = [
        file_identity(path)
        for path in sorted(EVIDENCE.rglob("*"))
        if path.is_file()
        and path.name not in excluded_names
        and not path.name.startswith(".summary.json.tmp-")
        and not path.name.startswith(".artifact-manifest.json.tmp-")
    ]
    if not artifacts:
        raise GateError("artifact manifest would be empty")
    manifest = {
        "schema": 1,
        "task": "KL-153a",
        "run_id": ACTIVE_RUN_ID,
        "scope": (
            "All non-state files in the canonical clean single-run evidence "
            "directory before artifact-manifest.json and summary.json are published"
        ),
        "cycle_break": (
            "The manifest excludes itself, summary.json, RUNNING.json, and FAILED.json"
        ),
        "runner_identity": runner_identity,
        "artifact_count": len(artifacts),
        "artifacts": artifacts,
    }
    manifest_path = EVIDENCE / "artifact-manifest.json"
    atomic_write_json(manifest_path, manifest)
    return file_identity(manifest_path)


def verify_manifest_artifacts(manifest_identity: dict[str, object]) -> None:
    manifest_path = Path(str(manifest_identity["path"]))
    if file_identity(manifest_path) != manifest_identity:
        raise GateError("published artifact manifest identity drifted")
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("task") != "KL-153a"
        or manifest.get("run_id") != ACTIVE_RUN_ID
        or manifest.get("artifact_count") != len(manifest.get("artifacts", []))
    ):
        raise GateError("published artifact manifest contract drifted")
    for artifact in manifest["artifacts"]:
        path = Path(artifact["path"])
        if file_identity(path) != artifact:
            raise GateError(f"published artifact drifted: {path}")


def finalize_success(summary: dict[str, object]) -> dict[str, object]:
    if ACTIVE_RUN_ID is None:
        raise GateError("success publication has no active run id")
    running_path = EVIDENCE / "RUNNING.json"
    if not running_path.is_file() or (EVIDENCE / "FAILED.json").exists():
        raise GateError("success publication requires RUNNING only")
    if json.loads(running_path.read_text()).get("run_id") != ACTIVE_RUN_ID:
        raise GateError("success RUNNING identity drifted")
    if summary.get("run_id") != ACTIVE_RUN_ID:
        raise GateError("summary run id does not match active run")
    manifest_identity = summary.get("artifact_manifest")
    if not isinstance(manifest_identity, dict):
        raise GateError("summary artifact manifest identity is missing")
    verify_manifest_artifacts(manifest_identity)
    summary_path = EVIDENCE / "summary.json"
    atomic_write_json(summary_path, summary)
    published_summary = json.loads(summary_path.read_text())
    if published_summary != summary:
        raise GateError("atomically published summary content drifted")
    verify_manifest_artifacts(manifest_identity)
    if file_identity(RUNNER) != summary["runner_identity"]:
        raise GateError("runner drifted during final publication")
    summary_identity = file_identity(summary_path)
    running_path.unlink()
    fsync_directory(EVIDENCE)
    current_payload = {
        "task": "KL-153a",
        "state": "PASS",
        "run_id": ACTIVE_RUN_ID,
        "canonical_evidence": str(EVIDENCE),
        "summary_identity": summary_identity,
        "artifact_manifest": manifest_identity,
        "committed_unix_ns": time.time_ns(),
        "valid_pass": True,
    }
    atomic_write_json(EVIDENCE_CURRENT, current_payload)
    if json.loads(EVIDENCE_CURRENT.read_text()) != current_payload:
        raise GateError("external current-state PASS publication drifted")
    if any((EVIDENCE / name).exists() for name in ("RUNNING.json", "FAILED.json")):
        raise GateError("transient state survived PASS publication")
    return summary_identity


def main() -> int:
    runner_identity = prepare_single_run_evidence()
    root_identity = verify_root_frozen_identity()
    kl152 = verify_kl152_frozen_evidence()
    llvm_queue = verify_llvm_component_identity()
    linux_queue = verify_linux_component_identity()
    llvm_replay = verify_patch_series_replay(
        "llvm", LLVM_SOURCE, LLVM_SERIES, component_pin("llvm"), LLVM_FIX_COMMIT
    )
    linux_replay = verify_patch_series_replay(
        "linux", LINUX_SOURCE, LINUX_SERIES, component_pin("linux"), LINUX_HEAD_AFTER
    )
    qemu = verify_qemu_unchanged_identity()
    llvm_identity = rebuild_and_verify_llvm()
    codegen = run_llvm_codegen_regression()
    e2e = run_full_e2e_suite()
    source_contract = verify_carrier_removal_source_contract()
    positive_image = build_linux_image()
    rom, wrong_mode_rom = generate_roms()

    positive = run_progress_guest("positive", Path(positive_image["image"]), rom, serial_mode="file")
    if not positive["console_verdict"]:
        raise GateError(
            "positive console anchors are not unique and ordered: "
            f"counts={positive['console_anchor_counts']}"
        )
    serial_none = run_progress_guest("serial-none", Path(positive_image["image"]), rom, serial_mode="none")
    if serial_none["console_verdict"]:
        raise GateError("-serial none passed the console verdict")
    if serial_none["console_size"] != 0:
        raise GateError("-serial none unexpectedly produced console bytes")

    wrong_mode = run_wrong_mode_guest(Path(positive_image["image"]), wrong_mode_rom)
    verify_sources_clean_after()

    counts = {"pass": 3, "fail": 0, "skip": 0}
    summary = {
        "task": "KL-153a",
        "run_id": ACTIVE_RUN_ID,
        "result": "PASS",
        "counts": counts,
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "root_identity": root_identity,
        "kl152_frozen_evidence": kl152,
        "llvm_component": llvm_queue,
        "linux_component": linux_queue,
        "llvm_patch_series_replay": llvm_replay,
        "linux_patch_series_replay": linux_replay,
        "qemu_identity": qemu,
        "llvm_identity": llvm_identity,
        "llvm_codegen_regression": codegen,
        "e2e_suite": e2e,
        "carrier_removal_source_contract": source_contract,
        "linux_positive": positive_image,
        "rom": {
            "path": str(rom), "sha256": sha256(rom),
            "wrong_mode_path": str(wrong_mode_rom), "wrong_mode_sha256": sha256(wrong_mode_rom),
        },
        "positive_runtime": positive,
        "negative_serial_none": serial_none,
        "negative_wrong_mode": wrong_mode,
        "runner_identity": runner_identity,
        "evidence_publication": {
            "semantics": "exclusive clean single-run canonical directory with external atomic current-state authority",
            "exclusive_lock": {
                "path": str(EVIDENCE_LOCK),
                "mechanism": "fcntl.flock LOCK_EX|LOCK_NB",
                "outside_evidence": True,
                "held_for_entire_run_and_publication": True,
            },
            "current_state": {"path": str(EVIDENCE_CURRENT), "run_id": ACTIVE_RUN_ID},
            "startup_transient_cleanup": STARTUP_TRANSIENT_CLEANUP,
        },
    }
    current_runner_identity = file_identity(RUNNER)
    if current_runner_identity != runner_identity:
        raise GateError("runner changed while KL-153a gate was executing")
    summary["artifact_manifest"] = publish_artifact_manifest(runner_identity)
    finalize_success(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-153a LLVM O0 bool/i1 stack-slot root fix (3/3, FAIL=0, SKIP=0)")
    return 0


if __name__ == "__main__":
    lock_descriptor: int | None = None
    try:
        lock_descriptor = acquire_exclusive_lock()
        try:
            raise SystemExit(main())
        except BaseException as exc:
            if not isinstance(exc, SystemExit):
                publish_failure(exc)
            raise
    except Exception as exc:
        if isinstance(exc, GateError):
            raise SystemExit(f"KL-153a FAIL: {exc}") from exc
        raise
    finally:
        if lock_descriptor is not None:
            release_exclusive_lock(lock_descriptor)
