#!/usr/bin/env python3
"""KL-154a: precise diagnosis of the K3 boot progress beyond mm_init_done.

KL-153a froze Linux boot in a state where the guest stays QEMU
`running` for an extended window with zero new EXCP_MALIGN, but
produces no console output beyond `NR_IRQS: 64` and never shuts down.
KL-153a explicitly declined to guess *where* it is stuck and handed
that precise diagnosis to this task.

This gate:
  1. verifies the frozen KL-153a root/Linux/QEMU/LLVM identities and
     evidence are unchanged (KL-153a made no further changes);
  2. verifies the one new Linux commit this task adds (fourteen new
     CONFIG_DADAO_M1_PROGRESS words bracketing every start_kernel()
     milestone from sched_init() through rest_init()/kernel_init(),
     plus one inside the generic calibrate_delay_converge() itself)
     and its exported patch/patch-id/patch-series replay;
  3. rebuilds a fresh KCFLAGS=-O0 Image and boots it, reading the
     extended oracle window to report exactly which marker is the
     last one ever written -- pinpointing the precise blocked source
     location -- and confirms the KL-152a/KL-153a seven-word oracle
     and console-anchor behavior are unchanged;
  4. runs a throwaway (non-committed, diagnostic-only) second build
     with a preset `lpj=` boot argument -- the standard Linux
     mechanism for boards without a working early timer -- purely to
     empirically confirm what the *next* blocker is once this one is
     bypassed, without adopting that preset as part of the shipped
     configuration;
  5. runs full E2E lit, run_differential.py, manifest_check.py and
     check_issues.py and asserts no regression.
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
EVIDENCE = EVIDENCE_PARENT / "kl154a-post-mm-init-boot-progress-diagnosis"
EVIDENCE_LOCK = EVIDENCE_PARENT / ".kl154a-post-mm-init-boot-progress-diagnosis.lock"
EVIDENCE_CURRENT = (
    EVIDENCE_PARENT / ".kl154a-post-mm-init-boot-progress-diagnosis.current.json"
)
LINUX_SERIES = ROOT / "components" / "linux" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"

KL153_SUMMARY = ROOT / ".work" / "evidence" / "kl153a-llvm-o0-bool-stack-fix" / "summary.json"
KL153_CURRENT = ROOT / ".work" / "evidence" / ".kl153a-llvm-o0-bool-stack-fix.current.json"
KL153_SUMMARY_SHA256 = "f45f9c675a7998389cb4a33a518d450dae229f94cd7b54fa0b6bd2656a700edd"
KL153_ARTIFACT_COUNT = 144

# Frozen root state this task starts from: KL-153a's own two root
# commits ("define" then "fix"). No KL-154a "define" commit was made
# to the root repo before this worker started -- per this task's own
# instructions, the worker leaves the root repo uncommitted and the
# architect commits after independent review, so root HEAD stays at
# the KL-153a fix commit throughout this run.
ROOT_KL153A_FIX_COMMIT = "5b18b53a89e38bc809e7d0ff41a99669d82f7fef"
ROOT_KL153A_DEFINE_COMMIT = "a25328c8b9297544975e1b5b0f07a1792cc2281f"
ROOT_KL152A_FIX_COMMIT = "f227056aa46590999552bb748ee08e7ef45cb338"

LLVM_HEAD = "d52f215cdd8af366bf497664750f241e5ef83f99"
QEMU_HEAD = "dfc7842229c139cc606141b82845ecf20086e657"
QEMU_SHA256 = "2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240"

LINUX_HEAD_BEFORE = "83992fe62ac26252622ca888421602abafe20b44"
LINUX_FIX_COMMIT = "76f2a87852a8e71d4168af4a18df159bff86b723"
LINUX_FIX_PATCH_NAME = "0032-dadao-add-KL-154a-post-mm_init-boot-progress-markers.patch"
LINUX_SERIES_COUNT = 32

RAM_BASE = 0x80000000
SCRATCH_BASE = 0x87FD0000
# 21 words: the 7 pre-existing (KL-149a..KL-152a) + 13 new KL-154a
# start_kernel()/rest_init()/kernel_init() bracket markers + 1 extra
# marker placed inside the generic calibrate_delay_converge() itself.
ORACLE_WORDS = 21
ORACLE_SIZE = ORACLE_WORDS * 8

MARKER_VALUE = 0x4B4C313439414845
FAILURE_VALUE = 0x4B4C313439424144

# Pre-existing KL-150a..KL-152a words (indices 2..6), unchanged by
# this task -- must still appear exactly as KL-153a froze them.
PRIOR_PROGRESS_VALUES = (
    0x4B4C313530534145,  # KL150SAE setup_arch_enter
    0x4B4C313530534144,  # KL150SAD setup_arch_done
    0x4B4C3135304D494E,  # KL150MIN mem_init_enter
    0x4B4C3135314D4944,  # KL151MID mem_init_done
    0x4B4C3135324D4D44,  # KL152MMD mm_init_done
)

# New KL-154a words (indices 7..19), in the exact order start_kernel()
# executes them, plus the extra converge-entry word at index 20. Each
# entry: (name, expected_value_or_None_for_raw_pid, source_location).
KL154_MARKERS = (
    ("sched_init_done", 0x4B4C313534534344,
     "init/main.c: after sched_init() in start_kernel()"),
    ("early_irq_init_done", 0x4B4C313534495251,
     "init/main.c: after init_IRQ() in start_kernel()"),
    ("tick_init_done", 0x4B4C31353454434B,
     "init/main.c: after tick_init() in start_kernel()"),
    ("timekeeping_init_done", 0x4B4C313534544B49,
     "init/main.c: after timekeeping_init() in start_kernel()"),
    ("time_init_done", 0x4B4C313534544D49,
     "init/main.c: after time_init() in start_kernel()"),
    ("console_init_done", 0x4B4C313534434F4E,
     "init/main.c: after console_init() in start_kernel()"),
    ("locking_selftest_done", 0x4B4C3135344C4B54,
     "init/main.c: after locking_selftest() in start_kernel()"),
    ("calibrate_enter", 0x4B4C313534434145,
     "init/main.c: immediately before calibrate_delay() call in start_kernel()"),
    ("calibrate_done", 0x4B4C313534434144,
     "init/main.c: immediately after calibrate_delay() call in start_kernel()"),
    ("rest_init_enter", 0x4B4C313534524945,
     "init/main.c: rest_init() entry"),
    ("rest_init_pid", None,  # raw sign-extended kernel_thread() retval, not an ASCII magic
     "init/main.c: rest_init(), immediately after "
     "kernel_thread(kernel_init, NULL, CLONE_FS)"),
    ("kernel_init_enter", 0x4B4C3135344B4945,
     "init/main.c: kernel_init() entry (the forked thread body)"),
    ("idle_enter", 0x4B4C31353449444C,
     "init/main.c: rest_init(), immediately before cpu_startup_entry(CPUHP_ONLINE)"),
)
CALIBRATE_CONVERGE_ENTER_VALUE = 0x4B4C3135344A464C  # KL154JFL
CALIBRATE_CONVERGE_ENTER_SOURCE = (
    "init/calibrate.c: calibrate_delay_converge() entry, immediately "
    "before `ticks = jiffies; while (ticks == jiffies) ;`"
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

ACTIVE_RUN_ID: str | None = None
EVIDENCE_OWNED = False
STARTUP_TRANSIENT_CLEANUP: list[str] = []


class GateError(RuntimeError):
    pass


# ---------------------------------------------------------------------
# Evidence / locking infrastructure (KL-152a/KL-153a conventions,
# reused as-is: external exclusive lock, run-id, staging/current-state,
# atomic summary, byte-level manifest).
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
        "task": "KL-154a",
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
            f"another KL-154a runner owns exclusive lock {EVIDENCE_LOCK}"
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
            "task": "KL-154a",
            "state": "RUNNING",
            "run_id": ACTIVE_RUN_ID,
            "runner_identity": runner,
            "started_unix_ns": time.time_ns(),
        },
    )
    atomic_write_json(
        EVIDENCE_CURRENT,
        {
            "task": "KL-154a",
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
        "task": "KL-154a",
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
            "task": "KL-154a",
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
    name: str, source: Path, output: Path, extra_cflags: str, *targets: str
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
            f"KCFLAGS={extra_cflags}",
            "KBUILD_LDFLAGS=--error-limit=0",
            *targets,
        ],
    )


def make(name: str, output: Path, *targets: str) -> subprocess.CompletedProcess[str]:
    return make_tree(name, LINUX_SOURCE, output, "-O0", *targets)


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


# ---------------------------------------------------------------------
# Frozen precondition verification.
# ---------------------------------------------------------------------

def verify_root_frozen_identity() -> dict[str, object]:
    head = execute("root-head", ["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    if head != ROOT_KL153A_FIX_COMMIT:
        raise GateError(f"root HEAD drift: {head} != {ROOT_KL153A_FIX_COMMIT}")
    parent = execute("root-parent", ["git", "-C", str(ROOT), "rev-parse", "HEAD^"]).stdout.strip()
    if parent != ROOT_KL153A_DEFINE_COMMIT:
        raise GateError(f"KL-153a define commit drift: {parent}")
    grandparent = execute(
        "root-grandparent", ["git", "-C", str(ROOT), "rev-parse", "HEAD^^"]
    ).stdout.strip()
    if grandparent != ROOT_KL152A_FIX_COMMIT:
        raise GateError(f"KL-152a fix commit drift: {grandparent}")
    status = execute("root-status", ["git", "-C", str(ROOT), "status", "--porcelain=v1"]).stdout
    # This task deliberately leaves new/modified root-tree files
    # uncommitted (task file, patch, series, README, roadmap, this
    # probe script) for the architect to review and commit -- root
    # HEAD itself must not move. Assert only that no *other* file is
    # dirty, and that the untracked gcc-torture-results.json this task
    # must not touch is unaffected by this gate (present or absent
    # either way, just not something this gate ever writes to).
    allowed_prefixes = (
        " M components/linux/README.md",
        " M components/linux/patches/series",
        " M docs/development-roadmap.md",
        "?? code-agent/tasks/KL-154a-",
        "?? components/linux/patches/0032-",
        "?? tests/scripts/run_kl154a_",
        "?? gcc-torture-results.json",
    )
    for line in status.splitlines():
        if not any(line.startswith(prefix) for prefix in allowed_prefixes):
            raise GateError(f"unexpected root worktree change: {line!r}")
    for source_name, source, expected_clean in (
        ("QEMU", QEMU_SOURCE, True),
        ("LLVM", LLVM_SOURCE, True),
    ):
        dirty = execute(
            f"{source_name.lower()}-status-before",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if expected_clean and dirty:
            raise GateError(f"{source_name} source worktree dirty before start:\n{dirty}")
    linux_dirty = execute(
        "linux-status-before", ["git", "-C", str(LINUX_SOURCE), "status", "--porcelain=v1"]
    ).stdout.strip()
    if linux_dirty:
        raise GateError(f"Linux source worktree dirty before start:\n{linux_dirty}")
    return {"head": head, "kl153a_define_commit": parent, "kl152a_fix_commit": grandparent}


def verify_kl153a_frozen_evidence() -> dict[str, object]:
    if not KL153_SUMMARY.is_file():
        raise GateError(f"KL-153a summary missing: {KL153_SUMMARY}")
    if sha256(KL153_SUMMARY) != KL153_SUMMARY_SHA256:
        raise GateError("KL-153a frozen summary identity drift")
    summary = json.loads(KL153_SUMMARY.read_text())
    required = {
        ("task",): "KL-153a",
        ("result",): "PASS",
        ("counts", "pass"): 3,
        ("counts", "fail"): 0,
        ("counts", "skip"): 0,
        ("qemu_identity", "head"): QEMU_HEAD,
        ("qemu_identity", "sha256"): QEMU_SHA256,
        ("llvm_identity", "head"): LLVM_HEAD,
        ("positive_runtime", "console_verdict"): True,
        ("negative_serial_none", "console_verdict"): False,
        ("negative_wrong_mode", "status", "status"): "shutdown",
    }
    for keys, expected in required.items():
        value: object = summary
        for key in keys:
            value = value[key]  # type: ignore[index]
        if value != expected:
            raise GateError(f"KL-153a evidence drift at {'.'.join(keys)}: {value!r} != {expected!r}")
    if not KL153_CURRENT.is_file():
        raise GateError("KL-153a external current-state file missing")
    current = json.loads(KL153_CURRENT.read_text())
    if current.get("state") != "PASS" or current.get("valid_pass") is not True:
        raise GateError("KL-153a external current-state is not a valid PASS")
    manifest_path = Path(str(summary["artifact_manifest"]["path"]))
    if not manifest_path.is_file() or file_identity(manifest_path) != summary["artifact_manifest"]:
        raise GateError("KL-153a frozen manifest identity drifted")
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("artifact_count") != KL153_ARTIFACT_COUNT
        or len(manifest.get("artifacts", [])) != KL153_ARTIFACT_COUNT
    ):
        raise GateError("KL-153a frozen artifact manifest contract drifted")
    for artifact in manifest["artifacts"]:
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_file() or file_identity(artifact_path) != artifact:
            raise GateError(f"KL-153a frozen manifest artifact drifted: {artifact_path}")
    return {
        "path": str(KL153_SUMMARY),
        "sha256": sha256(KL153_SUMMARY),
        "counts": summary["counts"],
        "artifact_manifest": summary["artifact_manifest"],
        "artifact_count": manifest["artifact_count"],
        "current_state": current,
    }


def verify_linux_component_identity() -> dict[str, object]:
    names = series_names(LINUX_SERIES)
    if len(names) != LINUX_SERIES_COUNT:
        raise GateError(f"Linux series count drift: {len(names)} != {LINUX_SERIES_COUNT}")
    if names[-1] != LINUX_FIX_PATCH_NAME:
        raise GateError(f"Linux series final patch name drift: {names[-1]}")
    commits = execute(
        "linux-commits",
        ["git", "-C", str(LINUX_SOURCE), "rev-list", "--reverse", f"{component_pin('linux')}..HEAD"],
    ).stdout.splitlines()
    if len(commits) != len(names):
        raise GateError(f"Linux commit/patch count mismatch: {len(commits)} != {len(names)}")
    if commits[-1] != LINUX_FIX_COMMIT:
        raise GateError(f"Linux HEAD commit drift: {commits[-1]} != {LINUX_FIX_COMMIT}")
    fix_patch_path = LINUX_SERIES.parent / LINUX_FIX_PATCH_NAME
    commit_mail = execute(
        "linux-fix-commit-email", ["git", "-C", str(LINUX_SOURCE), "show", "--pretty=email", LINUX_FIX_COMMIT]
    ).stdout
    commit_id = patch_id(commit_mail)
    payload_id = patch_id(fix_patch_path.read_text())
    if commit_id != payload_id:
        raise GateError(f"Linux fix patch payload drift: commit={commit_id} payload={payload_id}")
    fix_identity = file_identity(fix_patch_path)
    parent = execute(
        "linux-fix-parent", ["git", "-C", str(LINUX_SOURCE), "rev-parse", f"{LINUX_FIX_COMMIT}^"]
    ).stdout.strip()
    if parent != LINUX_HEAD_BEFORE:
        raise GateError(f"Linux pre-fix HEAD drift: {parent} != {LINUX_HEAD_BEFORE}")
    return {
        "series": file_identity(LINUX_SERIES),
        "patch_count": len(names),
        "fix_patch": {
            "patch": LINUX_FIX_PATCH_NAME,
            "commit": LINUX_FIX_COMMIT,
            "patch_id": payload_id,
            "patch_size": fix_identity["size"],
            "patch_sha256": fix_identity["sha256"],
        },
        "pre_fix_head": parent,
    }


def verify_patch_series_replay(
    name: str, source: Path, series: Path, base_commit: str, expected_head: str
) -> dict[str, object]:
    """Prove the exported patch series reproduces the dev tree byte-for-
    byte: `git am` the entire series, in order, into a fresh detached
    worktree at the pinned upstream base commit, then compare the
    replayed tree's `git rev-parse HEAD^{tree}` against the real dev
    tree's."""
    patches = [str(series.parent / p) for p in series_names(series)]
    with tempfile.TemporaryDirectory(prefix=f"kl154a_{name}_replay_") as tmp:
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


def verify_llvm_unchanged_identity() -> dict[str, object]:
    head = execute("llvm-head", ["git", "-C", str(LLVM_SOURCE), "rev-parse", "HEAD"]).stdout.strip()
    if head != LLVM_HEAD:
        raise GateError(f"LLVM HEAD drift: {head} != {LLVM_HEAD}")
    execute(
        "llvm-rebuild",
        ["ninja", "llc", "clang", "llvm-objdump", "llvm-nm"],
        cwd=LLVM_BUILD,
    )
    identities = {}
    for tool in ("clang", "llc", "llvm-objdump"):
        version = execute(f"llvm-{tool}-version", [str(LLVM_BIN / tool), "--version"]).stdout
        first_line = version.splitlines()[0] if version else ""
        identities[tool] = {
            "path": str(LLVM_BIN / tool),
            "sha256": sha256(LLVM_BIN / tool),
            "version_first_line": first_line,
        }
    if LLVM_HEAD[:12] not in identities["clang"]["version_first_line"]:
        raise GateError("clang version does not bind unchanged LLVM HEAD")
    return {"head": head, "tools": identities}


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


def run_differential_harness() -> dict[str, object]:
    result = execute("run-differential", [sys.executable, "tools/run_differential.py"], cwd=ROOT)
    text = result.stdout
    match = re.search(
        r"AGREE\(3-way\)=(\d+)\s+AGREE\(interp\+QEMU, gem5-SKIP\)=(\d+)\s+DIVERGE=(\d+)\s+HARNESS=(\d+)\s+QEMU-SKIP=(\d+)",
        text,
    )
    sail_match = re.search(
        r"AGREE\(4-way\)=(\d+)\s+Sail-SKIP\(out-of-slice\)=(\d+)\s+SAIL-DIVERGE=(\d+)", text
    )
    if not match or not sail_match:
        raise GateError(f"run_differential.py output not parseable:\n{text}")
    counts = {
        "agree_3way": int(match.group(1)),
        "gem5_skip": int(match.group(2)),
        "diverge": int(match.group(3)),
        "harness": int(match.group(4)),
        "qemu_skip": int(match.group(5)),
        "agree_4way": int(sail_match.group(1)),
        "sail_skip": int(sail_match.group(2)),
        "sail_diverge": int(sail_match.group(3)),
    }
    if counts["diverge"] != 0 or counts["harness"] != 0 or counts["qemu_skip"] != 0 or counts["sail_diverge"] != 0:
        raise GateError(f"run_differential.py regression: {counts}")
    return counts


def run_manifest_check() -> dict[str, object]:
    result = execute("manifest-check", [sys.executable, "scripts/manifest_check.py"], cwd=ROOT)
    if "manifest validation: PASS" not in result.stdout:
        raise GateError(f"manifest_check.py did not report PASS:\n{result.stdout}")
    return {"stdout_tail": result.stdout.strip().splitlines()[-3:]}


def run_check_issues() -> dict[str, object]:
    result = execute("check-issues", [sys.executable, "scripts/check_issues.py"], cwd=ROOT)
    if "ISSUE REGISTRY: PASS" not in result.stdout:
        raise GateError(f"check_issues.py did not report PASS:\n{result.stdout}")
    return {"stdout_tail": result.stdout.strip().splitlines()[-3:]}


def reject_forbidden_diagnostics(result: subprocess.CompletedProcess[str]) -> None:
    diagnostics = result.stdout + result.stderr
    found = []
    if "shift count is negative" in diagnostics:
        found.append("shift count is negative")
    if any("ELF_CLASS" in line and "is not defined" in line for line in diagnostics.splitlines()):
        found.append("ELF_CLASS is not defined")
    if found:
        raise GateError(f"forbidden Linux build diagnostics: {found}")


def build_linux_image(output: Path, name_prefix: str) -> dict[str, object]:
    make_tree(f"{name_prefix}-mrproper", LINUX_SOURCE, output, "-O0", "mrproper")
    make_tree(f"{name_prefix}-defconfig", LINUX_SOURCE, output, "-O0", "dadao_defconfig")
    make_tree(f"{name_prefix}-olddefconfig", LINUX_SOURCE, output, "-O0", "olddefconfig")
    positive_build = make_tree(f"{name_prefix}-image", LINUX_SOURCE, output, "-O0", "Image")
    reject_forbidden_diagnostics(positive_build)
    vmlinux = output / "vmlinux"
    image = output / "arch" / "dadao" / "boot" / "Image"
    for path in (vmlinux, image):
        if not path.is_file() or path.stat().st_size == 0:
            raise GateError(f"missing or empty Linux output: {path}")
    return {
        "vmlinux": str(vmlinux),
        "vmlinux_sha256": sha256(vmlinux),
        "image": str(image),
        "image_sha256": sha256(image),
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
    return struct.unpack(f">{ORACLE_WORDS}Q", payload)


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


def scan_trace_exceptions(trace_path: Path) -> list[dict[str, object]]:
    if not trace_path.is_file():
        return []
    trace = trace_path.read_text()
    return [
        {"index": int(index), "pc": pc, "mode": int(mode), "cfx": int(cfx)}
        for index, pc, mode, cfx in re.findall(
            r"dadao: exception index=(\d+) pc=(0x[0-9a-f]+) mode=(\d+) cfx=(\d+)", trace
        )
    ]


def console_verdict(payload: bytes) -> tuple[bool, list[int], list[int]]:
    counts = [payload.count(anchor) for anchor in ANCHORS]
    positions = [payload.find(anchor) for anchor in ANCHORS]
    passed = counts == [1, 1, 1, 1, 1] and positions == sorted(positions)
    return passed, counts, positions


EXTENDED_OBSERVATION_SECONDS = 10.0
# Must match scan_trace_exceptions()'s dict shape exactly (index, pc, mode,
# cfx) -- this is the one-time KL-149a hypv->supv mode-handoff mechanism
# already established by prior K3 tasks, not a new exception.
KNOWN_HANDOFF_EXCEPTION = {
    "index": 5, "pc": "0x0000000080000014", "mode": 2, "cfx": 63,
}


def run_progress_guest(
    name: str, image: Path, rom: Path, *, serial_mode: str, timeout: float = 30.0
) -> dict[str, object]:
    if serial_mode not in {"file", "none"}:
        raise GateError(f"invalid serial mode: {serial_mode}")
    transport = tempfile.TemporaryDirectory(prefix=f"kl154a_{name}_")
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
    initial = b""
    final = b""
    last_marker_state: object = None
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(f"{name}: scratch nonzero before CPU start: {initial.hex()}")
        (EVIDENCE / f"{name}-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})

        window_deadline = time.monotonic() + EXTENDED_OBSERVATION_SECONDS
        last_words: tuple[int, ...] | None = None
        while time.monotonic() < window_deadline:
            if proc.poll() is not None:
                raise GateError(f"{name}: QEMU exited during observation: rc={proc.returncode}")
            words = decode_oracle(dump_oracle(stream, oracle_path))
            if words != last_words:
                snapshots.append(
                    {
                        "elapsed_seconds": round(
                            time.monotonic() - (window_deadline - EXTENDED_OBSERVATION_SECONDS), 6
                        ),
                        "words": [f"0x{value:016x}" for value in words],
                    }
                )
                last_words = words
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                last_marker_state = status
                break
            time.sleep(0.05)
        final = dump_oracle(stream, oracle_path)
        final_status = qmp_roundtrip(stream, {"execute": "query-status"})
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
    exceptions = scan_trace_exceptions(trace_path)
    words = decode_oracle(final)
    return {
        "command": command,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "final_words": [f"0x{w:016x}" for w in words],
        "snapshots": snapshots,
        "final_status": final_status,
        "observation_seconds": EXTENDED_OBSERVATION_SECONDS,
        "exceptions_observed": exceptions,
        "console_path": str(console_path),
        "console_size": len(console),
        "console_sha256": sha256(console_path) if console_path.exists() else None,
        "console_anchor_counts": counts,
        "console_anchor_positions": positions,
        "console_verdict": verdict,
        "trace_path": str(trace_path),
    }


def run_wrong_mode_guest(image: Path, rom: Path) -> dict[str, object]:
    transport = tempfile.TemporaryDirectory(prefix="kl154a_wrong_mode_")
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
        expected = (0, FAILURE_VALUE) + (0,) * (ORACLE_WORDS - 2)
        if words != expected:
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
    rom = EVIDENCE / "kl154a-handoff.bin"
    wrong_mode = EVIDENCE / "kl154a-handoff-wrong-mode.bin"
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


def analyze_marker_reach(words: tuple[int, ...]) -> dict[str, object]:
    """Decode the 21-word oracle into a precise "last marker reached"
    report, without assuming any particular marker is expected to fire
    (this task's whole point is to discover that empirically)."""
    marker, failure = words[0], words[1]
    prior = words[2:7]
    new = words[7:20]
    converge = words[20]

    if marker not in (0, MARKER_VALUE) or failure not in (0, FAILURE_VALUE):
        raise GateError(f"KL-149 oracle regressed: marker={marker:#x} failure={failure:#x}")
    if failure == FAILURE_VALUE:
        raise GateError("wrong-mode failure marker set on a positive/serial-none run")

    for actual, expected in zip(prior, PRIOR_PROGRESS_VALUES, strict=True):
        if actual not in (0, expected):
            raise GateError(f"KL-150..152 prior progress word regressed: {actual:#x} != {expected:#x}")
    prior_reached = sum(1 for a, e in zip(prior, PRIOR_PROGRESS_VALUES, strict=True) if a == e)
    if prior_reached != len(PRIOR_PROGRESS_VALUES):
        raise GateError(f"KL-150..152 prior progress did not fully complete: {prior_reached}/5")

    reached: list[str] = []
    last_reached: str | None = None
    for (mname, expected, _source), actual in zip(KL154_MARKERS, new, strict=True):
        if expected is None:
            # rest_init_pid: any value is "reached" iff nonzero raw word
            # was ever written (0 is indistinguishable from "not yet",
            # but a real kernel_thread() pid is never exactly 0 anyway).
            if actual != 0:
                reached.append(mname)
                last_reached = mname
            continue
        if actual == expected:
            reached.append(mname)
            last_reached = mname
        elif actual != 0:
            raise GateError(f"KL-154a marker {mname} has unexpected value: {actual:#x}")

    converge_reached = converge == CALIBRATE_CONVERGE_ENTER_VALUE
    if converge not in (0, CALIBRATE_CONVERGE_ENTER_VALUE):
        raise GateError(f"calibrate_converge_enter marker has unexpected value: {converge:#x}")
    if converge_reached:
        reached.append("calibrate_converge_enter")
        last_reached = "calibrate_converge_enter"

    rest_init_pid_raw = new[10]
    return {
        "prior_progress_complete": prior_reached == len(PRIOR_PROGRESS_VALUES),
        "new_markers_reached": reached,
        "new_markers_reached_count": len(reached),
        "last_marker_reached": last_reached,
        "rest_init_pid_raw_hex": f"0x{rest_init_pid_raw:016x}",
        "rest_init_pid_signed": rest_init_pid_raw - (1 << 64) if rest_init_pid_raw >> 63 else rest_init_pid_raw,
    }


def run_lpj_diagnostic_experiment(rom: Path) -> dict[str, object]:
    """Throwaway, non-committed diagnostic-only build: preset `lpj=` on
    the kernel command line (the standard Linux mechanism for a board
    without a working early timer) via a build-tree-only .config edit,
    purely to empirically observe what the *next* blocker is once the
    calibrate_delay_converge() busy-wait is bypassed. This value is
    NOT calibrated against any real clock (there is no working
    timer/clocksource yet) and is not adopted as part of the shipped
    kernel configuration -- it exists only inside this throwaway build
    output directory, which is deleted at the end of this function."""
    output = ROOT / ".work" / "build" / "linux-kl154a-lpj-diagnostic"
    if output.exists():
        shutil.rmtree(output)
    try:
        build_linux_image(output, "lpj-diag")
        config_path = output / ".config"
        config_text = config_path.read_text()
        patched = config_text.replace(
            'CONFIG_CMDLINE="console=dadao0 init=/init panic=-1"',
            'CONFIG_CMDLINE="console=dadao0 init=/init panic=-1 lpj=1000000"',
        )
        if patched == config_text:
            raise GateError("lpj diagnostic: CONFIG_CMDLINE pattern not found to patch")
        config_path.write_text(patched)
        image_build = make_tree("lpj-diag-image-rebuild", LINUX_SOURCE, output, "-O0", "Image")
        reject_forbidden_diagnostics(image_build)
        image = output / "arch" / "dadao" / "boot" / "Image"
        vmlinux_strings = execute(
            "lpj-diag-cmdline-check", ["strings", str(output / "vmlinux")]
        ).stdout
        if "lpj=1000000" not in vmlinux_strings:
            raise GateError("lpj diagnostic: preset cmdline not embedded in rebuilt vmlinux")
        result = run_progress_guest(
            "lpj-diagnostic", image, rom, serial_mode="file", timeout=30.0
        )
        analysis = analyze_marker_reach(decode_oracle(bytes.fromhex(result["final_raw_hex"])))
        return {
            "purpose": (
                "diagnostic-only: confirm what the next blocker is once the "
                "calibrate_delay_converge() jiffies busy-wait is bypassed; "
                "this build and its CONFIG_CMDLINE preset are NOT part of "
                "the committed patch series"
            ),
            "runtime": result,
            "marker_analysis": analysis,
        }
    finally:
        if output.exists():
            shutil.rmtree(output)


def verify_sources_clean_after() -> None:
    for source_name, source in (("QEMU", QEMU_SOURCE), ("LLVM", LLVM_SOURCE)):
        dirty = execute(
            f"{source_name.lower()}-status-after",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{source_name} source worktree dirty after gate:\n{dirty}")
    linux_dirty = execute(
        "linux-status-after", ["git", "-C", str(LINUX_SOURCE), "status", "--porcelain=v1"]
    ).stdout.strip()
    if linux_dirty:
        raise GateError(f"Linux source worktree dirty after gate:\n{linux_dirty}")
    linux_worktrees = execute(
        "linux-worktree-list-after", ["git", "-C", str(LINUX_SOURCE), "worktree", "list"]
    ).stdout
    if len(linux_worktrees.splitlines()) != 1:
        raise GateError(f"Linux source has residual worktrees:\n{linux_worktrees}")


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
        "task": "KL-154a",
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
        manifest.get("task") != "KL-154a"
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
        "task": "KL-154a",
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
    kl153a = verify_kl153a_frozen_evidence()
    linux_queue = verify_linux_component_identity()
    linux_replay = verify_patch_series_replay(
        "linux", LINUX_SOURCE, LINUX_SERIES, component_pin("linux"), LINUX_FIX_COMMIT
    )
    qemu = verify_qemu_unchanged_identity()
    llvm_identity = verify_llvm_unchanged_identity()
    e2e = run_full_e2e_suite()
    differential = run_differential_harness()
    manifest_check = run_manifest_check()
    issues_check = run_check_issues()

    positive_image = build_linux_image(LINUX_OUTPUT, "linux")
    rom, wrong_mode_rom = generate_roms()

    positive = run_progress_guest("positive", Path(positive_image["image"]), rom, serial_mode="file")
    if not positive["console_verdict"]:
        raise GateError(
            "positive console anchors are not unique and ordered: "
            f"counts={positive['console_anchor_counts']}"
        )
    for exc in positive["exceptions_observed"]:
        if exc != KNOWN_HANDOFF_EXCEPTION:
            raise GateError(f"positive run observed an unexpected exception: {exc}")

    serial_none = run_progress_guest("serial-none", Path(positive_image["image"]), rom, serial_mode="none")
    if serial_none["console_verdict"]:
        raise GateError("-serial none passed the console verdict")
    if serial_none["console_size"] != 0:
        raise GateError("-serial none unexpectedly produced console bytes")
    for exc in serial_none["exceptions_observed"]:
        if exc != KNOWN_HANDOFF_EXCEPTION:
            raise GateError(f"-serial none run observed an unexpected exception: {exc}")

    positive_words = decode_oracle(bytes.fromhex(positive["final_raw_hex"]))
    serial_none_words = decode_oracle(bytes.fromhex(serial_none["final_raw_hex"]))
    if positive_words != serial_none_words:
        raise GateError(
            "marker sequence differs between positive and -serial none runs: "
            f"{positive_words} != {serial_none_words}"
        )
    marker_analysis = analyze_marker_reach(positive_words)
    if marker_analysis["last_marker_reached"] != "calibrate_converge_enter":
        raise GateError(
            "diagnosis regressed: expected boot to be stuck exactly at "
            f"calibrate_delay_converge() entry, got: {marker_analysis}"
        )
    if "calibrate_done" in marker_analysis["new_markers_reached"]:
        raise GateError("calibrate_done unexpectedly reached: diagnosis has changed, re-derive")

    wrong_mode = run_wrong_mode_guest(Path(positive_image["image"]), wrong_mode_rom)

    lpj_diagnostic = run_lpj_diagnostic_experiment(rom)
    lpj_analysis = lpj_diagnostic["marker_analysis"]
    if lpj_analysis["rest_init_pid_signed"] != -38:
        raise GateError(
            "lpj diagnostic expected kernel_thread() to return -ENOSYS (-38), "
            f"got: {lpj_analysis['rest_init_pid_signed']}"
        )

    verify_sources_clean_after()

    counts = {"pass": 3, "fail": 0, "skip": 0}
    summary = {
        "task": "KL-154a",
        "run_id": ACTIVE_RUN_ID,
        "result": "PASS",
        "counts": counts,
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "root_identity": root_identity,
        "kl153a_frozen_evidence": kl153a,
        "linux_component": linux_queue,
        "linux_patch_series_replay": linux_replay,
        "qemu_identity": qemu,
        "llvm_identity": llvm_identity,
        "e2e_suite": e2e,
        "differential_harness": differential,
        "manifest_check": manifest_check,
        "issues_check": issues_check,
        "linux_positive": positive_image,
        "rom": {
            "path": str(rom), "sha256": sha256(rom),
            "wrong_mode_path": str(wrong_mode_rom), "wrong_mode_sha256": sha256(wrong_mode_rom),
        },
        "marker_table": [
            {"name": name, "address": f"0x{addr:08x}", "expected_value": (
                f"0x{expected:016x}" if expected is not None else "raw kernel_thread() retval"
            ), "source": source}
            for (name, expected, source), addr in zip(
                KL154_MARKERS,
                range(0x87FD0038, 0x87FD0038 + 8 * len(KL154_MARKERS), 8),
                strict=True,
            )
        ] + [
            {
                "name": "calibrate_converge_enter",
                "address": "0x87fd00a0",
                "expected_value": f"0x{CALIBRATE_CONVERGE_ENTER_VALUE:016x}",
                "source": CALIBRATE_CONVERGE_ENTER_SOURCE,
            }
        ],
        "positive_runtime": positive,
        "negative_serial_none": serial_none,
        "negative_wrong_mode": wrong_mode,
        "marker_analysis": marker_analysis,
        "diagnosis": {
            "last_marker_reached": marker_analysis["last_marker_reached"],
            "root_cause": (
                "Boot is stuck forever in calibrate_delay_converge() "
                "(init/calibrate.c), specifically the first statement "
                "`ticks = jiffies; while (ticks == jiffies) ;` -- a busy-"
                "wait for jiffies to advance by at least one tick. "
                "arch/dadao's time_init() (arch/dadao/kernel/time.c) is an "
                "explicit no-op, and init_IRQ()/trap_init() "
                "(arch/dadao/kernel/irq.c, arch/dadao/kernel/traps.c) "
                "install no real interrupt/exception delivery mechanism, "
                "so nothing ever calls do_timer()/tick handling to "
                "advance jiffies -- the busy-wait spins forever, matching "
                "the observed symptom exactly."
            ),
            "scope_boundary": (
                "Per KL-154a's explicit scope boundary, this diagnosis is "
                "frozen rather than fixed: unblocking it for real requires "
                "installing a working CFX exception vector and a real "
                "timer clockevent, which is the K3 phase-3 scope "
                "(KL-146a's 'precise trap/syscall, timer/irq and "
                "scheduler integration'), likely KL-155a."
            ),
        },
        "lpj_diagnostic_experiment": lpj_diagnostic,
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
        raise GateError("runner changed while KL-154a gate was executing")
    summary["artifact_manifest"] = publish_artifact_manifest(runner_identity)
    finalize_success(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-154a K3 post-mm_init boot progress diagnosis (3/3, FAIL=0, SKIP=0)")
    print(f"Last marker reached: {marker_analysis['last_marker_reached']}")
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
            raise SystemExit(f"KL-154a FAIL: {exc}") from exc
        raise
    finally:
        if lock_descriptor is not None:
            release_exclusive_lock(lock_descriptor)
