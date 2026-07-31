#!/usr/bin/env python3
"""KL-157a: K3 VFS root-mount wall bypass + next-wall diagnosis.

KL-157a frozen the boot reaching prepare_namespace() and panicking "VFS:
Unable to mount root fs on unknown-block(0,0)". This gate:

  1. verifies the frozen KL-157a root, Linux, QEMU and LLVM identities and
     evidence are unchanged;
  2. verifies the one new Linux commit this task adds (the empty placeholder
     /init in the built-in initramfs, the objtree-mirror build fix, the
     CONFIG_DADAO_M1_PROGRESS markers) and its exported
     patch/patch-id/patch-series bare-pin replay;
  3. rebuilds a fresh KCFLAGS=-O0 Image and boots it (under `-icount
     shift=0`, the KL-155a-mandated QEMU invocation), reading a 30-word
     oracle via QMP, confirming:
       - ROOTFS_FALLBACK fires (prepare_namespace() skipped => the root
         mount wall is gone; the initial rootfs IS the root);
       - INIT_EXEC fires (the kernel reached the exec of the init process);
       - NO_WORKING_INIT does NOT fire (the exec/mm machinery hits the
         fail-closed local_flush_tlb_all() BUG first -- the cfx_tlb
         milestone -- so "No working init found" is not yet reachable);
       - the old "Unable to mount root fs" panic is gone from the console
         and the new wall ("Run /init as init process" + tlbflush.h BUG +
         "Kernel panic - not syncing: BUG!") is present;
       - all KL-149a..156a markers and exception signatures still hold;
  4. reads back init_task's saved switch frame from guest memory and
     verifies its structural invariants (switch-machinery regression);
  5. runs the -serial none and wrong-mode negatives;
  6. runs full E2E lit, run_differential.py, manifest_check.py and
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
EVIDENCE = EVIDENCE_PARENT / "kl157a-vfs-root-mount-wall-diagnosis"
EVIDENCE_LOCK = EVIDENCE_PARENT / ".kl157a-vfs-root-mount-wall-diagnosis.lock"
EVIDENCE_CURRENT = (
    EVIDENCE_PARENT / ".kl157a-vfs-root-mount-wall-diagnosis.current.json"
)
LINUX_SERIES = ROOT / "components" / "linux" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"

KL156_SUMMARY = ROOT / ".work" / "evidence" / "kl156a-real-fork-and-context-switch" / "summary.json"
KL156_CURRENT = ROOT / ".work" / "evidence" / ".kl156a-real-fork-and-context-switch.current.json"
KL156_SUMMARY_SHA256 = "73b668a572461c5eeacbd80ae4c1eb2c4ae03e5726cff597a320787891f30b6f"

LLVM_HEAD = "d52f215cdd8af366bf497664750f241e5ef83f99"
QEMU_HEAD = "dfc7842229c139cc606141b82845ecf20086e657"
QEMU_SHA256 = "2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240"

LINUX_HEAD_BEFORE = "78601a1d2996788d1036b09a55e62784e523d89b"
LINUX_FIX_COMMIT = "ae32e45d19de107635fa24c55692af09ca92ed49"
LINUX_FIX_PATCH_NAME = "0035-dadao-bypass-root-mount-wall-via-empty-initramfs-init.patch"
LINUX_SERIES_COUNT = 35

RAM_BASE = 0x80000000
SCRATCH_BASE = 0x87FD0000
ORACLE_WORDS = 30
ORACLE_SIZE = ORACLE_WORDS * 8
# Word indexes within the 30-word oracle.
IDX_TIMER_IRQ_COUNT = 21
IDX_ROOT_MOUNT_ATTEMPT = 22
IDX_EXEC_INIT_ATTEMPT = 23
IDX_SWITCH_FROM_IDLE = 24
IDX_SWITCH_TO_IDLE = 25
IDX_SWITCH_COUNT = 26
IDX_ROOTFS_FALLBACK = 27
IDX_NO_WORKING_INIT = 28
IDX_INIT_EXEC = 29

MARKER_VALUE = 0x4B4C313439414845
FAILURE_VALUE = 0x4B4C313439424144

PRIOR_PROGRESS_VALUES = (
    0x4B4C313530534145,  # KL150SAE setup_arch_enter
    0x4B4C313530534144,  # KL150SAD setup_arch_done
    0x4B4C3135304D494E,  # KL150MIN mem_init_enter
    0x4B4C3135314D4944,  # KL151MID mem_init_done
    0x4B4C3135324D4D44,  # KL152MMD mm_init_done
)

# KL-154a marker words (indices 7..19). rest_init_pid is a raw sign-extended
# value (None => any non-zero). kernel_init_enter/idle_enter are at 18/19.
KL154_MARKERS = (
    ("sched_init_done", 0x4B4C313534534344, "index 7"),
    ("early_irq_init_done", 0x4B4C313534495251, "index 8"),
    ("tick_init_done", 0x4B4C31353454434B, "index 9"),
    ("timekeeping_init_done", 0x4B4C313534544B49, "index 10"),
    ("time_init_done", 0x4B4C313534544D49, "index 11"),
    ("console_init_done", 0x4B4C313534434F4E, "index 12"),
    ("locking_selftest_done", 0x4B4C3135344C4B54, "index 13"),
    ("calibrate_enter", 0x4B4C313534434145, "index 14"),
    ("calibrate_done", 0x4B4C313534434144, "index 15"),
    ("rest_init_enter", 0x4B4C313534524945, "index 16"),
    ("rest_init_pid", None, "index 17"),
    ("kernel_init_enter", 0x4B4C3135344B4945, "index 18"),
    ("idle_enter", 0x4B4C31353449444C, "index 19"),
)
CALIBRATE_CONVERGE_ENTER_VALUE = 0x4B4C3135344A464C  # index 20, KL154JFL

KL156_SWITCH_FROM_IDLE_VALUE = 0x4B4C313536534649  # KL156SFI
KL156_SWITCH_TO_IDLE_VALUE = 0x4B4C313536535449    # KL156STI
KL156_ROOT_MOUNT_ATTEMPT_VALUE = 0x4B4C313536524D41  # KL156RMA
KL156_EXEC_INIT_ATTEMPT_VALUE = 0x4B4C313536494558  # KL156IEX
KL157_ROOTFS_FALLBACK_VALUE = 0x4B4C313537524642    # KL157RFB
KL157_NO_WORKING_INIT_VALUE = 0x4B4C3135374E5749    # KL157NWI
KL157_INIT_EXEC_VALUE = 0x4B4C313537584543          # KL157XEC

ANCHORS = (
    b"DADAO M1 test-machine early console online\n",
    b"Linux version 5.4.0",
    b"DADAO M1 setup_arch complete\n",
    b"Memory:",
    b"SLUB: HWalign=",
)
VFS_PANIC_MARKER = b"Kernel panic - not syncing: VFS: Unable to mount root fs"
RUN_INIT_MARKER = b"Run /init as init process"
TLBFLUSH_BUG_MARKER = b"BUG: failure at arch/dadao/include/asm/tlbflush.h:13/local_flush_tlb_all()"
BUG_PANIC_MARKER = b"Kernel panic - not syncing: BUG!"
ROM_SHA256 = "46c1e4af50162dd9be1adb82eb9223a6902f0629a0a4c9d3f18822aee5e536c7"
WRONG_MODE_ROM_SHA256 = (
    "7cf369ba7b7cac026b693f560d991da91ddc201725848ab621c355488f9aca8c"
)

# offsetof(struct task_struct, thread.kernel_sp) == 1504 == 0x5E0, verified in
# the build's include/generated/asm-offsets.h during this task's bring-up.
THREAD_KERNEL_SP_OFFSET = 0x5E0
DADAO_SWITCH_FRAME_SIZE = 0x438
DADAO_SWITCH_RB1_OFF = 0x018
DADAO_SWITCH_RA63_OFF = 0x430

ACTIVE_RUN_ID: str | None = None
EVIDENCE_OWNED = False
STARTUP_TRANSIENT_CLEANUP: list[str] = []


class GateError(RuntimeError):
    pass


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
        "task": "KL-157a",
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
            f"another KL-157a runner owns exclusive lock {EVIDENCE_LOCK}"
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
            "task": "KL-157a",
            "state": "RUNNING",
            "run_id": ACTIVE_RUN_ID,
            "runner_identity": runner,
            "started_unix_ns": time.time_ns(),
        },
    )
    atomic_write_json(
        EVIDENCE_CURRENT,
        {
            "task": "KL-157a",
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
        "task": "KL-157a",
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
            "task": "KL-157a",
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

ROOT_KL156A_FIX_COMMIT = "af20c4cbb2b2ffd5f5467dbe2b94f9f350095503"


def verify_root_frozen_identity() -> dict[str, object]:
    head = execute("root-head", ["git", "-C", str(ROOT), "rev-parse", "HEAD"]).stdout.strip()
    expected = execute(
        "root-head-expected", ["git", "-C", str(ROOT), "rev-parse", ROOT_KL156A_FIX_COMMIT]
    ).stdout.strip()
    if head != expected:
        raise GateError(f"root HEAD drift: {head} != {expected} (KL-156a fix commit)")
    status = execute("root-status", ["git", "-C", str(ROOT), "status", "--porcelain=v1"]).stdout
    allowed_prefixes = (
        " M components/linux/README.md",
        " M components/linux/patches/series",
        " M docs/development-roadmap.md",
        "?? code-agent/tasks/KL-157a-",
        "?? components/linux/patches/0035-",
        "?? tests/scripts/run_kl157a_",
        "?? gcc-torture-results.json",
    )
    for line in status.splitlines():
        if not any(line.startswith(prefix) for prefix in allowed_prefixes):
            raise GateError(f"unexpected root worktree change: {line!r}")
    for source_name, source in (("QEMU", QEMU_SOURCE), ("LLVM", LLVM_SOURCE)):
        dirty = execute(
            f"{source_name.lower()}-status-before",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{source_name} source worktree dirty before start:\n{dirty}")
    linux_dirty = execute(
        "linux-status-before", ["git", "-C", str(LINUX_SOURCE), "status", "--porcelain=v1"]
    ).stdout.strip()
    if linux_dirty:
        raise GateError(f"Linux source worktree dirty before start:\n{linux_dirty}")
    return {"head": head}


def verify_kl156a_frozen_evidence() -> dict[str, object]:
    if not KL156_SUMMARY.is_file():
        raise GateError(f"KL-156a summary missing: {KL156_SUMMARY}")
    if sha256(KL156_SUMMARY) != KL156_SUMMARY_SHA256:
        raise GateError("KL-156a frozen summary identity drift")
    summary = json.loads(KL156_SUMMARY.read_text())
    required = {
        ("task",): "KL-156a",
        ("result",): "PASS",
        ("counts", "pass"): 3,
        ("counts", "fail"): 0,
        ("counts", "skip"): 0,
        ("qemu_identity", "head"): QEMU_HEAD,
        ("qemu_identity", "sha256"): QEMU_SHA256,
        ("llvm_identity", "head"): LLVM_HEAD,
        ("marker_analysis", "rest_init_pid_signed"): 1,
        ("marker_analysis", "kl156", "switch_to_idle"): True,
        ("marker_analysis", "kl156", "switch_count"): 1124,
    }
    for keys, expected in required.items():
        value: object = summary
        for key in keys:
            value = value[key]  # type: ignore[index]
        if value != expected:
            raise GateError(f"KL-156a evidence drift at {'.'.join(keys)}: {value!r} != {expected!r}")
    if not KL156_CURRENT.is_file():
        raise GateError("KL-156a external current-state file missing")
    current = json.loads(KL156_CURRENT.read_text())
    if current.get("state") != "PASS" or current.get("valid_pass") is not True:
        raise GateError("KL-156a external current-state is not a valid PASS")
    return {
        "path": str(KL156_SUMMARY),
        "sha256": sha256(KL156_SUMMARY),
        "counts": summary["counts"],
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
    patches = [str(series.parent / p) for p in series_names(series)]
    with tempfile.TemporaryDirectory(prefix=f"kl156a_{name}_replay_") as tmp:
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


def build_linux_image(output: Path, name_prefix: str, extra_cflags: str = "-O0") -> dict[str, object]:
    make_tree(f"{name_prefix}-mrproper", LINUX_SOURCE, output, extra_cflags, "mrproper")
    make_tree(f"{name_prefix}-defconfig", LINUX_SOURCE, output, extra_cflags, "dadao_defconfig")
    make_tree(f"{name_prefix}-olddefconfig", LINUX_SOURCE, output, extra_cflags, "olddefconfig")
    positive_build = make_tree(f"{name_prefix}-image", LINUX_SOURCE, output, extra_cflags, "Image")
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


def find_symbol_address(system_map: Path, symbol: str) -> int:
    for line in system_map.read_text().splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[2] == symbol:
            return int(parts[0], 16)
    raise GateError(f"symbol not found in System.map: {symbol}")


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


def dump_bytes(stream, addr: int, size: int, output: Path) -> bytes:
    output.unlink(missing_ok=True)
    result = qmp_roundtrip(
        stream,
        {
            "execute": "human-monitor-command",
            "arguments": {"command-line": f'pmemsave {addr:#x} {size} "{output}"'},
        },
    )
    if result:
        raise GateError(f"QEMU pmemsave failed: {result}")
    payload = output.read_bytes()
    if len(payload) != size:
        raise GateError(f"QEMU pmemsave size drift: {len(payload)} != {size}")
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
    sock.settimeout(5.0)
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


def scan_timer_real_entries(trace_path: Path) -> int:
    if not trace_path.is_file():
        return 0
    trace = trace_path.read_text()
    return len(re.findall(r"dadao: trap cfx=18 real-entry", trace))


def console_verdict(payload: bytes) -> tuple[bool, list[int], list[int]]:
    counts = [payload.count(anchor) for anchor in ANCHORS]
    positions = [payload.find(anchor) for anchor in ANCHORS]
    passed = counts == [1, 1, 1, 1, 1] and positions == sorted(positions)
    return passed, counts, positions


EXTENDED_OBSERVATION_SECONDS = 15.0
KNOWN_SYNC_HANDOFF_SIGNATURE = {"index": 5, "mode": 2, "cfx": 63}
KNOWN_ASYNC_TIMER_SIGNATURE = {"index": 7, "mode": 2, "cfx": 63}
EXPECTED_SYNC_HANDOFF_EXCEPTION_COUNT = 2
POLL_INTERVAL_SECONDS = 0.05


def assert_only_known_handoff_exceptions(exceptions: list[dict[str, object]], label: str) -> None:
    sync_count = 0
    for exc in exceptions:
        signature = {k: exc[k] for k in ("index", "mode", "cfx")}
        if signature == KNOWN_SYNC_HANDOFF_SIGNATURE:
            sync_count += 1
        elif signature == KNOWN_ASYNC_TIMER_SIGNATURE:
            continue
        else:
            raise GateError(
                f"{label} run observed an unexpected exception (must be zero "
                f"index=1/ILLI etc.): {exc}"
            )
    if sync_count != EXPECTED_SYNC_HANDOFF_EXCEPTION_COUNT:
        raise GateError(
            f"{label} run observed {sync_count} sync-handoff-signature exceptions, "
            f"expected exactly {EXPECTED_SYNC_HANDOFF_EXCEPTION_COUNT}: {exceptions}"
        )


def run_progress_guest(
    name: str, image: Path, rom: Path, *, serial_mode: str, jiffies_addr: int,
    timeout: float = 30.0,
) -> dict[str, object]:
    if serial_mode not in {"file", "none"}:
        raise GateError(f"invalid serial mode: {serial_mode}")
    transport = tempfile.TemporaryDirectory(prefix=f"kl156a_{name}_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    jiffies_path = transport_path / "jiffies.bin"
    console_path = EVIDENCE / f"{name}-console.bin"
    console_path.unlink(missing_ok=True)
    trace_path = EVIDENCE / f"{name}-qemu-trace.log"
    trace_path.unlink(missing_ok=True)
    serial_arg = f"file:{console_path}" if serial_mode == "file" else "none"
    command = [
        str(QEMU), "-M", "dadao-m1", "-S", "-icount", "shift=0",
        "-global", "dadao-cpu.cfx-smon-real=on",
        "-bios", str(rom), "-kernel", str(image),
        "-display", "none", "-serial", serial_arg,
        "-no-shutdown", "-d", "int", "-D", str(trace_path),
        "-qmp", f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    greeting = ""
    snapshots: list[dict[str, object]] = []
    jiffies_snapshots: list[int] = []
    initial = b""
    final = b""
    final_jiffies = 0
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_bytes(stream, SCRATCH_BASE, ORACLE_SIZE, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(f"{name}: scratch nonzero before CPU start: {initial.hex()}")
        (EVIDENCE / f"{name}-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})

        window_deadline = time.monotonic() + EXTENDED_OBSERVATION_SECONDS
        last_words: tuple[int, ...] | None = None
        last_jiffies: int | None = None
        while time.monotonic() < window_deadline:
            if proc.poll() is not None:
                raise GateError(f"{name}: QEMU exited during observation: rc={proc.returncode}")
            words = decode_oracle(dump_bytes(stream, SCRATCH_BASE, ORACLE_SIZE, oracle_path))
            jf = struct.unpack(">Q", dump_bytes(stream, jiffies_addr, 8, jiffies_path))[0]
            if words != last_words or jf != last_jiffies:
                snapshots.append(
                    {
                        "elapsed_seconds": round(
                            time.monotonic() - (window_deadline - EXTENDED_OBSERVATION_SECONDS), 6
                        ),
                        "words": [f"0x{value:016x}" for value in words],
                        "jiffies": f"0x{jf:016x}",
                    }
                )
                if jf != last_jiffies:
                    jiffies_snapshots.append(jf)
                last_words = words
                last_jiffies = jf
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(POLL_INTERVAL_SECONDS)
        final = dump_bytes(stream, SCRATCH_BASE, ORACLE_SIZE, oracle_path)
        final_jiffies = struct.unpack(">Q", dump_bytes(stream, jiffies_addr, 8, jiffies_path))[0]
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
    timer_real_entries = scan_timer_real_entries(trace_path)
    words = decode_oracle(final)
    return {
        "command": command,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "final_words": [f"0x{w:016x}" for w in words],
        "final_jiffies": f"0x{final_jiffies:016x}",
        "jiffies_snapshots": [f"0x{j:016x}" for j in jiffies_snapshots],
        "jiffies_distinct_values_observed": len(set(jiffies_snapshots)),
        "snapshots": snapshots,
        "final_status": final_status,
        "observation_seconds": EXTENDED_OBSERVATION_SECONDS,
        "exceptions_observed": exceptions,
        "timer_real_entries_observed": timer_real_entries,
        "console_path": str(console_path),
        "console_size": len(console),
        "console_sha256": sha256(console_path) if console_path.exists() else None,
        "console_anchor_counts": counts,
        "console_anchor_positions": positions,
        "console_verdict": verdict,
        "console_has_vfs_panic": VFS_PANIC_MARKER in console,
        "console_has_run_init": RUN_INIT_MARKER in console,
        "console_has_tlbflush_bug": TLBFLUSH_BUG_MARKER in console,
        "console_has_bug_panic": BUG_PANIC_MARKER in console,
        "trace_path": str(trace_path),
    }


def run_wrong_mode_guest(image: Path, rom: Path) -> dict[str, object]:
    transport = tempfile.TemporaryDirectory(prefix="kl156a_wrong_mode_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    command = [
        str(QEMU), "-M", "dadao-m1", "-S", "-icount", "shift=0",
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
        initial = dump_bytes(stream, SCRATCH_BASE, ORACLE_SIZE, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError("wrong-mode scratch nonzero before CPU start")
        (EVIDENCE / "wrong-mode-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            final = dump_bytes(stream, SCRATCH_BASE, ORACLE_SIZE, oracle_path)
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
    rom = EVIDENCE / "kl156a-handoff.bin"
    wrong_mode = EVIDENCE / "kl156a-handoff-wrong-mode.bin"
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
    marker, failure = words[0], words[1]
    prior = words[2:7]
    new = words[7:20]
    converge = words[20]
    timer_irq_count = words[IDX_TIMER_IRQ_COUNT]
    root_mount = words[IDX_ROOT_MOUNT_ATTEMPT]
    exec_init = words[IDX_EXEC_INIT_ATTEMPT]
    switch_from_idle = words[IDX_SWITCH_FROM_IDLE]
    switch_to_idle = words[IDX_SWITCH_TO_IDLE]
    switch_count = words[IDX_SWITCH_COUNT]
    rootfs_fallback = words[IDX_ROOTFS_FALLBACK]
    no_working_init = words[IDX_NO_WORKING_INIT]
    init_exec = words[IDX_INIT_EXEC]

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

    converge_reached = converge == CALIBRATE_CONVERGE_ENTER_VALUE
    if converge not in (0, CALIBRATE_CONVERGE_ENTER_VALUE):
        raise GateError(f"calibrate_converge_enter marker has unexpected value: {converge:#x}")

    ordered_reached: list[str] = []
    for (mname, expected, _source), actual in zip(KL154_MARKERS, new, strict=True):
        if expected is None:
            hit = actual != 0
        else:
            hit = actual == expected
            if not hit and actual != 0:
                raise GateError(f"KL-154a marker {mname} has unexpected value: {actual:#x}")
        if hit:
            ordered_reached.append(mname)
        if mname == "calibrate_enter" and converge_reached:
            ordered_reached.append("calibrate_converge_enter")

    rest_init_pid_raw = new[10]
    rest_init_pid_signed = (
        rest_init_pid_raw - (1 << 64) if rest_init_pid_raw >> 63 else rest_init_pid_raw
    )

    kl156 = {
        "root_mount_attempt": root_mount == KL156_ROOT_MOUNT_ATTEMPT_VALUE,
        "exec_init_attempt": exec_init == KL156_EXEC_INIT_ATTEMPT_VALUE,
        "switch_from_idle": switch_from_idle == KL156_SWITCH_FROM_IDLE_VALUE,
        "switch_to_idle": switch_to_idle == KL156_SWITCH_TO_IDLE_VALUE,
        "switch_count": switch_count,
    }
    if root_mount not in (0, KL156_ROOT_MOUNT_ATTEMPT_VALUE):
        raise GateError(f"root_mount_attempt unexpected value: {root_mount:#x}")
    if exec_init not in (0, KL156_EXEC_INIT_ATTEMPT_VALUE):
        raise GateError(f"exec_init_attempt unexpected value: {exec_init:#x}")
    if switch_from_idle not in (0, KL156_SWITCH_FROM_IDLE_VALUE):
        raise GateError(f"switch_from_idle unexpected value: {switch_from_idle:#x}")
    if switch_to_idle not in (0, KL156_SWITCH_TO_IDLE_VALUE):
        raise GateError(f"switch_to_idle unexpected value: {switch_to_idle:#x}")

    kl157 = {
        "rootfs_fallback": rootfs_fallback == KL157_ROOTFS_FALLBACK_VALUE,
        "no_working_init": no_working_init == KL157_NO_WORKING_INIT_VALUE,
        "init_exec": init_exec == KL157_INIT_EXEC_VALUE,
    }
    if rootfs_fallback not in (0, KL157_ROOTFS_FALLBACK_VALUE):
        raise GateError(f"rootfs_fallback unexpected value: {rootfs_fallback:#x}")
    if no_working_init not in (0, KL157_NO_WORKING_INIT_VALUE):
        raise GateError(f"no_working_init unexpected value: {no_working_init:#x}")
    if init_exec not in (0, KL157_INIT_EXEC_VALUE):
        raise GateError(f"init_exec unexpected value: {init_exec:#x}")

    return {
        "prior_progress_complete": prior_reached == len(PRIOR_PROGRESS_VALUES),
        "new_markers_reached": ordered_reached,
        "last_marker_reached": ordered_reached[-1] if ordered_reached else None,
        "rest_init_pid_raw_hex": f"0x{rest_init_pid_raw:016x}",
        "rest_init_pid_signed": rest_init_pid_signed,
        "calibrate_done_reached": "calibrate_done" in ordered_reached,
        "kernel_init_enter_reached": "kernel_init_enter" in ordered_reached,
        "idle_enter_reached": "idle_enter" in ordered_reached,
        "timer_irq_count": timer_irq_count,
        "kl156": kl156,
        "kl157": kl157,
    }


def verify_idle_frame_integrity(stream, system_map: Path, label: str) -> dict[str, object]:
    """Read init_task's saved switch frame from guest memory and check its
    structural invariants (the K2-style key-value readback of the boot/idle
    context's saved state)."""
    init_task_addr = find_symbol_address(system_map, "init_task")
    kernel_sp_addr = init_task_addr + THREAD_KERNEL_SP_OFFSET
    kernel_sp = struct.unpack(
        ">Q", dump_bytes(stream, kernel_sp_addr, 8, EVIDENCE / f"{label}-idle-kernel-sp.bin")
    )[0]
    frame = dump_bytes(
        stream, kernel_sp, DADAO_SWITCH_FRAME_SIZE, EVIDENCE / f"{label}-idle-switch-frame.bin"
    )
    words = struct.unpack(f">{DADAO_SWITCH_FRAME_SIZE // 8}Q", frame)
    saved_rb1 = words[DADAO_SWITCH_RB1_OFF // 8]
    saved_ra63 = words[DADAO_SWITCH_RA63_OFF // 8]
    ra63_refcount = saved_ra63 >> 48
    ra63_addr = saved_ra63 & 0xFFFFFFFFFFFF

    rb1_ok = 0x87FF0000 - 0x10000 <= saved_rb1 <= 0x87FF0000
    ra63_ok = ra63_refcount == 1 and RAM_BASE <= ra63_addr < 0x80690000
    if not rb1_ok:
        raise GateError(
            f"{label}: idle saved rb1 outside boot stack region: 0x{saved_rb1:x}"
        )
    if not ra63_ok:
        raise GateError(
            f"{label}: idle saved ra63 invalid (refcount={ra63_refcount} addr=0x{ra63_addr:x})"
        )
    return {
        "init_task_addr": f"0x{init_task_addr:016x}",
        "kernel_sp_addr": f"0x{kernel_sp_addr:016x}",
        "kernel_sp": f"0x{kernel_sp:016x}",
        "saved_rb1": f"0x{saved_rb1:016x}",
        "saved_rb1_in_boot_stack": rb1_ok,
        "saved_ra63": f"0x{saved_ra63:016x}",
        "ra63_refcount": ra63_refcount,
        "ra63_addr": f"0x{ra63_addr:016x}",
        "ra63_valid": ra63_ok,
    }


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
        "task": "KL-157a",
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
        manifest.get("task") != "KL-157a"
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
        "task": "KL-157a",
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
    kl156a = verify_kl156a_frozen_evidence()
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
    system_map = LINUX_OUTPUT / "System.map"
    jiffies_addr = find_symbol_address(system_map, "jiffies")
    rom, wrong_mode_rom = generate_roms()

    positive = run_progress_guest(
        "positive", Path(positive_image["image"]), rom, serial_mode="file",
        jiffies_addr=jiffies_addr,
    )
    if not positive["console_verdict"]:
        raise GateError(
            "positive console anchors are not unique and ordered: "
            f"counts={positive['console_anchor_counts']}"
        )
    assert_only_known_handoff_exceptions(positive["exceptions_observed"], "positive")

    serial_none = run_progress_guest(
        "serial-none", Path(positive_image["image"]), rom, serial_mode="none",
        jiffies_addr=jiffies_addr,
    )
    if serial_none["console_verdict"]:
        raise GateError("-serial none passed the console verdict")
    if serial_none["console_size"] != 0:
        raise GateError("-serial none unexpectedly produced console bytes")
    assert_only_known_handoff_exceptions(serial_none["exceptions_observed"], "-serial none")

    positive_words = decode_oracle(bytes.fromhex(positive["final_raw_hex"]))
    serial_none_words = decode_oracle(bytes.fromhex(serial_none["final_raw_hex"]))
    # Every write-once word must match between the two independent runs. The
    # two genuinely ever-incrementing counters (timer_irq_count, index 21, and
    # switch_count, index 26) are real-time dependent and compared for
    # magnitude elsewhere, not for exact equality.
    settle_positive = (
        positive_words[:IDX_TIMER_IRQ_COUNT]
        + positive_words[IDX_TIMER_IRQ_COUNT + 1:IDX_SWITCH_COUNT]
        + positive_words[IDX_SWITCH_COUNT + 1:]
    )
    settle_serial_none = (
        serial_none_words[:IDX_TIMER_IRQ_COUNT]
        + serial_none_words[IDX_TIMER_IRQ_COUNT + 1:IDX_SWITCH_COUNT]
        + serial_none_words[IDX_SWITCH_COUNT + 1:]
    )
    if settle_positive != settle_serial_none:
        raise GateError(
            "marker sequence differs between positive and -serial none runs: "
            f"{settle_positive} != {settle_serial_none}"
        )
    marker_analysis = analyze_marker_reach(positive_words)
    serial_none_marker_analysis = analyze_marker_reach(serial_none_words)
    if serial_none_marker_analysis["timer_irq_count"] < 2:
        raise GateError(
            "-serial none run: timer_irq_count too low to be real repeated "
            f"delivery: {serial_none_marker_analysis['timer_irq_count']}"
        )

    # ---- KL-157a headline acceptance ----
    if not marker_analysis["calibrate_done_reached"]:
        raise GateError(
            f"calibrate_done NOT reached -- regressed to KL-154a/155a diagnosis: {marker_analysis}"
        )
    if marker_analysis["rest_init_pid_signed"] != 1:
        raise GateError(
            "kernel_thread(kernel_init) must return a real pid (1), got: "
            f"{marker_analysis['rest_init_pid_signed']}"
        )
    if not marker_analysis["kernel_init_enter_reached"]:
        raise GateError("kernel_init_enter marker not reached (kernel_init never ran)")
    kl156 = marker_analysis["kl156"]
    if not kl156["switch_from_idle"]:
        raise GateError("SWITCH_FROM_IDLE not set (idle was never switched away)")
    if not kl156["switch_to_idle"]:
        raise GateError("SWITCH_TO_IDLE not set (scheduler never switched back to idle)")
    if not marker_analysis["idle_enter_reached"]:
        raise GateError("IDLE_ENTER not reached (idle never resumed after a switch)")
    if kl156["switch_count"] < 100:
        raise GateError(f"SWITCH_COUNT too low to be a real scheduler: {kl156['switch_count']}")
    if not kl156["root_mount_attempt"]:
        raise GateError("ROOT_MOUNT_ATTEMPT not reached (boot did not get to the root-mount wall)")
    if marker_analysis["timer_irq_count"] < 2:
        raise GateError(f"timer_irq_count too low: {marker_analysis['timer_irq_count']}")
    if positive["jiffies_distinct_values_observed"] < 2:
        raise GateError("jiffies did not advance across snapshots")
    if positive["timer_real_entries_observed"] < 1:
        raise GateError("no real cfx_timer hardware entry observed")

    # ---- KL-157a headline: the root-mount wall is bypassed ----
    kl157 = marker_analysis["kl157"]
    if not kl157["rootfs_fallback"]:
        raise GateError(
            "ROOTFS_FALLBACK not set (prepare_namespace() was not skipped -- "
            "the root-mount wall is still present)"
        )
    if positive["console_has_vfs_panic"]:
        raise GateError("the old 'Unable to mount root fs' panic is still present in the console")
    if not kl157["init_exec"]:
        raise GateError("INIT_EXEC not set (the kernel never reached the exec of the init process)")
    if kl157["no_working_init"]:
        raise GateError(
            "NO_WORKING_INIT unexpectedly set (it must not fire until the exec wall is crossed)"
        )
    if not positive["console_has_run_init"]:
        raise GateError("console missing 'Run /init as init process' (the exec attempt)")
    if not positive["console_has_tlbflush_bug"]:
        raise GateError(
            "console missing the local_flush_tlb_all() BUG -- the expected next "
            "wall (cfx_tlb milestone)"
        )
    if not positive["console_has_bug_panic"]:
        raise GateError("console missing 'Kernel panic - not syncing: BUG!' (the exec wall panic)")

    # K2-style readback of the boot/idle task's saved switch frame.
    transport = tempfile.TemporaryDirectory(prefix="kl156a_frame_")
    qmp_path = Path(transport.name) / "qmp.sock"
    command = [
        str(QEMU), "-M", "dadao-m1", "-S", "-icount", "shift=0",
        "-global", "dadao-cpu.cfx-smon-real=on",
        "-bios", str(rom), "-kernel", str(Path(positive_image["image"])),
        "-display", "none", "-serial", "none", "-no-shutdown",
        "-qmp", f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    frame_identity = None
    try:
        sock, stream, _ = connect_qmp(proc, qmp_path, 10.0)
        qmp_roundtrip(stream, {"execute": "cont"})
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.5)
        frame_identity = verify_idle_frame_integrity(stream, system_map, "positive")
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        (EVIDENCE / "frame-check-qemu-runtime.log").write_text(
            "=== command ===\n" + shlex.join(command)
            + "\n=== stdout ===\n" + stdout.decode(errors="replace")
            + "\n=== stderr ===\n" + stderr.decode(errors="replace")
        )
        transport.cleanup()

    wrong_mode = run_wrong_mode_guest(Path(positive_image["image"]), wrong_mode_rom)

    verify_sources_clean_after()

    counts = {"pass": 3, "fail": 0, "skip": 0}
    summary = {
        "task": "KL-157a",
        "run_id": ACTIVE_RUN_ID,
        "result": "PASS",
        "counts": counts,
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "qemu_invocation_requirement": "-icount shift=0 (see time.c and KL-155a task record)",
        "root_identity": root_identity,
        "kl156a_frozen_evidence": kl156a,
        "linux_component": linux_queue,
        "linux_patch_series_replay": linux_replay,
        "qemu_identity": qemu,
        "llvm_identity": llvm_identity,
        "e2e_suite": e2e,
        "differential_harness": differential,
        "manifest_check": manifest_check,
        "issues_check": issues_check,
        "linux_positive": positive_image,
        "jiffies_symbol_address": f"0x{jiffies_addr:016x}",
        "rom": {
            "path": str(rom), "sha256": sha256(rom),
            "wrong_mode_path": str(wrong_mode_rom), "wrong_mode_sha256": sha256(wrong_mode_rom),
        },
        "positive_runtime": positive,
        "negative_serial_none": serial_none,
        "negative_wrong_mode": wrong_mode,
        "marker_analysis": marker_analysis,
        "idle_frame_integrity": frame_identity,
        "diagnosis": {
            "result": (
                "The 'Unable to mount root fs' wall is bypassed: the empty "
                "placeholder /init in the built-in initramfs makes "
                "ksys_access('/init') succeed, prepare_namespace() is skipped "
                "and the initial rootfs IS the root (ROOTFS_FALLBACK marker). "
                "run_init_process('/init') now runs (INIT_EXEC marker, "
                "'Run /init as init process' in the console) and hits the "
                "fail-closed local_flush_tlb_all() BUG -- the mmu_gather flush "
                "in exit_mmap() while tearing down the fresh exec mm after the "
                "empty file fails the ELF check -- which is the cfx_tlb "
                "range-invalidate milestone (documented later K3 work), so "
                "'No working init found' (NO_WORKING_INIT) is not yet "
                "reachable. This does NOT claim full boot to userspace/login."
            ),
        },
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
        raise GateError("runner changed while KL-157a gate was executing")
    summary["artifact_manifest"] = publish_artifact_manifest(runner_identity)
    finalize_success(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-157a K3 VFS root-mount wall bypass (3/3, FAIL=0, SKIP=0)")
    print(f"rest_init_pid: {marker_analysis['rest_init_pid_signed']}")
    print(f"kernel_init_enter: {marker_analysis['kernel_init_enter_reached']}")
    print(f"switch_to_idle: {kl156['switch_to_idle']}")
    print(f"switch_count: {kl156['switch_count']}")
    print(f"root_mount_attempt: {kl156['root_mount_attempt']}")
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
            raise SystemExit(f"KL-157a FAIL: {exc}") from exc
        raise
    finally:
        if lock_descriptor is not None:
            release_exclusive_lock(lock_descriptor)
