#!/usr/bin/env python3
"""KL-152a fail-closed K3 mm_init completion gate."""

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
LLVM_BIN = ROOT / ".work" / "build" / "llvm" / "bin"
QEMU_SOURCE = ROOT / ".work" / "source" / "qemu"
QEMU_BUILD = QEMU_SOURCE / "build"
QEMU = QEMU_BUILD / "qemu-system-dadao"
EVIDENCE_PARENT = ROOT / ".work" / "evidence"
EVIDENCE = EVIDENCE_PARENT / "kl152a-mm-init-completion"
EVIDENCE_LOCK = EVIDENCE_PARENT / ".kl152a-mm-init-completion.lock"
EVIDENCE_CURRENT = EVIDENCE_PARENT / ".kl152a-mm-init-completion.current.json"
LINUX_SERIES = ROOT / "components" / "linux" / "patches" / "series"
QEMU_SERIES = ROOT / "components" / "qemu" / "patches" / "series"
MANIFEST = ROOT / "manifests" / "components.lock.toml"
KL151_SUMMARY = (
    ROOT / ".work" / "evidence" / "kl151a-mem-init-completion" / "summary.json"
)
ROOT_FROZEN_COMMIT = "81b21dd6a58ba668309d09b619f79e93c67121bd"
ROOT_TASK_COMMIT = "cb0e9ccf5357f9386a3310d84b5eb2c736c4e600"

LINUX_PATCHES = (
    (
        "0001-dadao-add-K3-configuration-skeleton.patch",
        "6dbd09a49be915128bb6a55360df79cf8c7c419a",
        "14ef129f2b38c5bd058f38316bf00de9e72a13a3",
    ),
    (
        "0002-dadao-add-Linux-compile-substrate.patch",
        "c06b6f93a3c33968145f001859f29702e47f3244",
        "728747dae1a19c159825459a485c624e403f9d6e",
    ),
    (
        "0003-dadao-link-K3-image-and-add-reset-entry.patch",
        "fca53b59dc8048ba9c4cd3965e488d8a11e07dbd",
        "476ab7b802482f307123dc7aa3e165d948323ca0",
    ),
    (
        "0004-dadao-harden-KL-149a-mode-and-O0-link-gates.patch",
        "b5f89a803600ecbe445c3aad64fceb51d8a61140",
        "94de1e4bf4c4f25c9771963989f43bfce0125a2b",
    ),
    (
        "0005-dadao-identify-KL-149a-bad-mode-path.patch",
        "f1349f6ee7858f8be8f6e91d18ea9b006f52c281",
        "aa1651702ecaa5c80918c376662f72489e9e015f",
    ),
    (
        "0006-dadao-add-M1-early-console-and-boot-progress.patch",
        "fdfdb9ca682c8839a7d59595a1b9d5fc9c46da5b",
        "44ff19d0599cc24b3715e88f587ca3a4e9b3dc87",
    ),
    (
        "0007-dadao-harden-K3-O0-early-boot-progress.patch",
        "06c3d571a8ae249e451dc4f2151e6bfd8e8a5873",
        "d4a778294298992ca7255c96972b24d72c05aea0",
    ),
    (
        "0008-dadao-complete-K3-mem_init-progress.patch",
        "537c61baef6e8ca04cc3d77f6cc9da7856fd6d5e",
        "dd1a1b39796f9ebf27ed6e6f07ba02c22252fcd4",
    ),
    (
        "0009-dadao-widen-page-expected-state-result-for-K3-O0.patch",
        "3e83c7744f5d093eba3a46284416b8409f3d452c",
        "bc9463edbe258e4e3c417c5c9563f00748d57cb2",
    ),
    (
        "0010-dadao-widen-compaction-capture-result-for-K3-O0.patch",
        "8f0b11da8346dc46402974e7a6a8626cff103ed3",
        "80d0cabb985e3d30b95c8cdc61038ea0f494bc0b",
    ),
    (
        "0011-dadao-complete-K3-mm_init-progress.patch",
        "4f32b2dd26662ed48cbca155792edd88dd3e9e52",
        "93fd5b7cde954b7f8f1635a1d4182f10f0f910e0",
    ),
    (
        "0012-dadao-widen-zone-watermark-result-for-K3-O0.patch",
        "ba60ea713bbca2224acbd5332bb265ff26afb64d",
        "b6ca6ffa3c4be423704abd4e94dc31a851a7cf77",
    ),
    (
        "0013-dadao-widen-fallback-steal-result-for-K3-O0.patch",
        "1aae897eb20cad2cc856bb082cf713d186a8e1d8",
        "7a2593c7ae9521ebe9badd2245cb1a7d0c40491b",
    ),
    (
        "0014-dadao-widen-rmqueue-fallback-result-for-K3-O0.patch",
        "0f822ec071294067d3827c82bd7b331a974fb251",
        "3c2fc71c815f10fd0d28586fc9bda7e71dd94ce5",
    ),
    (
        "0015-dadao-widen-new-PCP-check-result-for-K3-O0.patch",
        "ee9ed8174efb893c7c48d85cd27ef9264cac6c66",
        "dc2e7aff85a34cba68bb17f33056cb3d0e0ff12e",
    ),
    (
        "0016-dadao-widen-SLUB-pfmemalloc-result-for-K3-O0.patch",
        "2aad5665523d56f829b516ac919203953cf87a69",
        "a36d5f2cc8513586d1d487852f88be8357c02712",
    ),
    (
        "0017-dadao-widen-SLUB-cmpxchg-result-for-K3-O0.patch",
        "8d49b7e041970743bb39e9dab94091a9036faeae",
        "c7d2521a92bea303bb963fb332dfd548f269d623",
    ),
    (
        "0018-dadao-widen-SLUB-init-on-free-result-for-K3-O0.patch",
        "8f84618d05c9e413946ed5b8fb6e265cb56f449d",
        "5b48eb0027964ba7157114f2c28aef4957f6f468",
    ),
    (
        "0019-dadao-widen-SLUB-init-on-alloc-result-for-K3-O0.patch",
        "bd10b11e2780d392e57f1b18f0e9dc8c2db28ed4",
        "6fdc09201d10ee41897de53117b4128651560cde",
    ),
    (
        "0020-dadao-separate-M1-progress-from-O0-compatibility.patch",
        "e054a68cc86b045881afdc26a028ee4d16c3d217",
        "876cc96f3a6221d74739eab84fb9d0d47835f9e2",
    ),
)

QEMU_PARENT = "eee0933b064014f3ab305eaa275883f025223d53"
QEMU_PATCHES = (
    (
        "0037-hw-dadao-add-M1-test-machine-debug-console.patch",
        "247344a110fa99e18e66b4e2ce373e9ddb96d8f7",
        "1e8d1730f84776a0e50db4f77afe14d2c3ac9c58",
    ),
    (
        "0038-target-dadao-log-precise-exception-state.patch",
        "dfc7842229c139cc606141b82845ecf20086e657",
        "b9bb21ea84eac178d7957cfa2faa4e793e9f101e",
    ),
)
QEMU_HEAD = QEMU_PATCHES[-1][1]
QEMU_SHA256 = "2326a4b69f3f8dc3e0c1b5c2f335d0df4c71182a481dd7f6071e4a38f6ac8240"

KL151_SUMMARY_SHA256 = (
    "e6682d902e067e69ce0384d468ec3067e831999d2c573633be1ca6d2a093cd08"
)
KL151_RUNNER_SHA256 = (
    "74f6c02ef1fa4ac5320ffe77a313614b541301b4e30b7f5b1bfc664b6ca6b5c7"
)
KL151_MANIFEST_SHA256 = (
    "a661f9241bb028f8aaf3cdd23bb582e8db788cb8c1be5d75f48d6be4f64923df"
)
ROM_SHA256 = "46c1e4af50162dd9be1adb82eb9223a6902f0629a0a4c9d3f18822aee5e536c7"
WRONG_MODE_ROM_SHA256 = (
    "7cf369ba7b7cac026b693f560d991da91ddc201725848ab621c355488f9aca8c"
)

RAM_BASE = 0x80000000
RAM_SIZE = 0x08000000
SCRATCH_BASE = 0x87FD0000
STACK_TOP = 0x87FF0000
SCRATCH_END = 0x88000000
ORACLE_SIZE = 56

MARKER_VALUE = 0x4B4C313439414845
FAILURE_VALUE = 0x4B4C313439424144
PROGRESS_VALUES = (
    0x4B4C313530534145,  # KL150SAE: entered setup_arch
    0x4B4C313530534144,  # KL150SAD: setup_arch memory setup done
    0x4B4C3135304D494E,  # KL150MIN: entered mem_init
    0x4B4C3135314D4944,  # KL151MID: mem_init completed
    0x4B4C3135324D4D44,  # KL152MMD: mm_init completed
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
NEXT_BLOCKER_EXCEPTION_INDEX = 3
NEXT_BLOCKER_PC = 0x8063D868
NEXT_BLOCKER_SYMBOL = "node_tag_get"
NEXT_BLOCKER_SYMBOL_ADDRESS = 0x8063D7A4
NEXT_BLOCKER_STACK_SLOT = 31

CARRIER_FIX_STAGES = (
    {
        "label": "pre-0011-prepare-alloc-pages",
        "commit": "8f0b11da8346dc46402974e7a6a8626cff103ed3",
        "exception_index": 3,
        "pc": 0x8027985C,
        "symbol": "prepare_alloc_pages",
        "symbol_address": 0x80279694,
        "source": "mm/page_alloc.c::prepare_alloc_pages",
        "stack_slot_offset": 71,
    },
    {
        "label": "pre-0012-zone-watermark-fast",
        "commit": "4f32b2dd26662ed48cbca155792edd88dd3e9e52",
        "exception_index": 3,
        "pc": 0x80284840,
        "symbol": "zone_watermark_fast",
        "symbol_address": 0x80284758,
        "source": "mm/page_alloc.c::zone_watermark_fast",
        "stack_slot_offset": 71,
        "store_register": "rd31",
    },
    {
        "label": "pre-0013-can-steal-fallback",
        "commit": "ba60ea713bbca2224acbd5332bb265ff26afb64d",
        "exception_index": 3,
        "pc": 0x80276380,
        "symbol": "can_steal_fallback",
        "symbol_address": 0x802762D4,
        "source": "mm/page_alloc.c::can_steal_fallback",
        "stack_slot_offset": 15,
    },
    {
        "label": "pre-0014-rmqueue-fallback",
        "commit": "1aae897eb20cad2cc856bb082cf713d186a8e1d8",
        "exception_index": 3,
        "pc": 0x80285E1C,
        "symbol": "rmqueue_bulk",
        "symbol_address": 0x80285964,
        "source": "mm/page_alloc.c::rmqueue_bulk(__rmqueue_fallback return)",
        "stack_slot_offset": 247,
        "reload_register": "rd16",
    },
    {
        "label": "pre-0015-check-new-pcp",
        "commit": "0f822ec071294067d3827c82bd7b331a974fb251",
        "exception_index": 3,
        "pc": 0x80285F60,
        "symbol": "check_new_pcp",
        "symbol_address": 0x80285EF8,
        "source": "mm/page_alloc.c::check_new_pcp",
        "stack_slot_offset": 15,
    },
    {
        "label": "pre-0016-slub-pfmemalloc-match",
        "commit": "ee9ed8174efb893c7c48d85cd27ef9264cac6c66",
        "exception_index": 3,
        "pc": 0x802B7294,
        "symbol": "pfmemalloc_match",
        "symbol_address": 0x802B7234,
        "source": "mm/slub.c::pfmemalloc_match",
        "stack_slot_offset": 23,
    },
    {
        "label": "pre-0017-slub-cmpxchg-double",
        "commit": "2aad5665523d56f829b516ac919203953cf87a69",
        "exception_index": 3,
        "pc": 0x802B7BB0,
        "symbol": "__cmpxchg_double_slab",
        "symbol_address": 0x802B7AA8,
        "source": "mm/slub.c::__cmpxchg_double_slab",
        "stack_slot_offset": 71,
    },
    {
        "label": "pre-0018-slub-init-on-free",
        "commit": "8d49b7e041970743bb39e9dab94091a9036faeae",
        "exception_index": 3,
        "pc": 0x802B3E18,
        "symbol": "slab_want_init_on_free",
        "symbol_address": 0x802B3D4C,
        "source": "mm/slab.h::slab_want_init_on_free",
        "stack_slot_offset": 31,
    },
    {
        "label": "pre-0019-slub-init-on-alloc",
        "commit": "8f84618d05c9e413946ed5b8fb6e265cb56f449d",
        "exception_index": 3,
        "pc": 0x802AF63C,
        "symbol": "slab_want_init_on_alloc",
        "symbol_address": 0x802AF550,
        "source": "mm/slab.h::slab_want_init_on_alloc",
        "stack_slot_offset": 23,
    },
)

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
    return {
        "path": str(path),
        "size": path.stat().st_size,
        "sha256": sha256(path),
    }


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
        "task": "KL-152a",
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
            f"another KL-152a runner owns exclusive lock {EVIDENCE_LOCK}"
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

    ACTIVE_RUN_ID = (
        f"{time.time_ns()}-{os.getpid()}-{os.urandom(8).hex()}"
    )
    EVIDENCE_OWNED = False
    STARTUP_TRANSIENT_CLEANUP = cleanup_publication_transients()
    runner = file_identity(RUNNER)
    staging = EVIDENCE_PARENT / (
        f".{EVIDENCE.name}.staging-{ACTIVE_RUN_ID}"
    )
    retired = EVIDENCE_PARENT / (
        f".{EVIDENCE.name}.retired-{ACTIVE_RUN_ID}"
    )
    staging.mkdir()
    atomic_write_json(
        staging / "RUNNING.json",
        {
            "task": "KL-152a",
            "state": "RUNNING",
            "run_id": ACTIVE_RUN_ID,
            "runner_identity": runner,
            "started_unix_ns": time.time_ns(),
        },
    )
    atomic_write_json(
        EVIDENCE_CURRENT,
        {
            "task": "KL-152a",
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
        "task": "KL-152a",
        "state": "FAILED",
        "run_id": ACTIVE_RUN_ID,
        "error": str(error),
        "runner_identity": (
            file_identity(RUNNER) if RUNNER.is_file() else None
        ),
        "failed_unix_ns": time.time_ns(),
    }
    if not EVIDENCE_OWNED:
        failed = EVIDENCE_PARENT / (
            f".{EVIDENCE.name}.failed-{ACTIVE_RUN_ID}"
        )
        retired = EVIDENCE_PARENT / (
            f".{EVIDENCE.name}.retired-{ACTIVE_RUN_ID}"
        )
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
    atomic_write_json(
        EVIDENCE / "FAILED.json",
        failed_payload,
    )
    (EVIDENCE / "RUNNING.json").unlink(missing_ok=True)
    fsync_directory(EVIDENCE)
    failure_identity = file_identity(EVIDENCE / "FAILED.json")
    atomic_write_json(
        EVIDENCE_CURRENT,
        {
            "task": "KL-152a",
            "state": "FAILED",
            "run_id": ACTIVE_RUN_ID,
            "canonical_evidence": str(EVIDENCE),
            "failure_identity": failure_identity,
            "valid_pass": False,
        },
    )


def execute(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    check: bool = True,
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


def make(
    name: str, output: Path, *targets: str
) -> subprocess.CompletedProcess[str]:
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


def verify_queue(
    name: str, source: Path, series: Path
) -> list[dict[str, object]]:
    patches = series_names(series)
    commits = execute(
        f"{name}-commits",
        [
            "git",
            "-C",
            str(source),
            "rev-list",
            "--reverse",
            f"{component_pin(name)}..HEAD",
        ],
    ).stdout.splitlines()
    if len(commits) != len(patches):
        raise GateError(
            f"{name} commit/patch count mismatch: "
            f"{len(commits)} != {len(patches)}"
        )

    rows: list[dict[str, object]] = []
    for index, (commit, patch_name) in enumerate(
        zip(commits, patches, strict=True)
    ):
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
                f"{name} patch payload drift: {patch_name}: "
                f"{payload_id} != {commit_id}"
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


def verify_root_frozen_identity() -> dict[str, str]:
    head = execute(
        "root-head", ["git", "-C", str(ROOT), "rev-parse", "HEAD"]
    ).stdout.strip()
    parent = execute(
        "root-parent", ["git", "-C", str(ROOT), "rev-parse", "HEAD^"]
    ).stdout.strip()
    if head != ROOT_TASK_COMMIT:
        raise GateError(f"KL-152a task commit drift: {head}")
    if parent != ROOT_FROZEN_COMMIT:
        raise GateError(f"KL-151a frozen root commit drift: {parent}")
    return {"task_commit": head, "kl151_frozen_commit": parent}


def verify_kl151_frozen_evidence() -> dict[str, object]:
    if not KL151_SUMMARY.is_file():
        raise GateError(f"KL-151a summary missing: {KL151_SUMMARY}")
    if sha256(KL151_SUMMARY) != KL151_SUMMARY_SHA256:
        raise GateError("KL-151a frozen summary identity drift")
    summary = json.loads(KL151_SUMMARY.read_text())
    required = {
        ("task",): "KL-151a",
        ("result",): "PASS",
        ("counts", "pass"): 3,
        ("counts", "fail"): 0,
        ("counts", "skip"): 0,
        ("build_flags", "KCFLAGS"): "-O0",
        ("qemu_identity", "head"): QEMU_HEAD,
        ("qemu_identity", "sha256"): QEMU_SHA256,
        ("positive_runtime", "console_anchor_counts"): [1, 1, 1, 1],
        ("positive_runtime", "console_verdict"): True,
        ("negative_serial_none", "console_verdict"): False,
        ("negative_wrong_mode", "status", "status"): "shutdown",
        ("runner_identity", "sha256"): KL151_RUNNER_SHA256,
        ("artifact_manifest", "sha256"): KL151_MANIFEST_SHA256,
    }
    for keys, expected in required.items():
        value: object = summary
        for key in keys:
            value = value[key]  # type: ignore[index]
        if value != expected:
            raise GateError(
                f"KL-151a evidence drift at {'.'.join(keys)}: "
                f"{value!r} != {expected!r}"
            )
    expected_final = (
        "4b4c3134394148450000000000000000"
        "4b4c3135305341454b4c313530534144"
        "4b4c3135304d494e4b4c3135314d4944"
    )
    if summary["positive_runtime"]["final_raw_hex"] != expected_final:
        raise GateError("KL-151a positive six-word oracle drifted")
    if summary["negative_serial_none"]["final_raw_hex"] != expected_final:
        raise GateError("KL-151a serial-none QMP oracle drifted")
    expected_wrong = (
        "00000000000000004b4c313439424144"
        "00000000000000000000000000000000"
        "00000000000000000000000000000000"
    )
    if summary["negative_wrong_mode"]["final_raw_hex"] != expected_wrong:
        raise GateError("KL-151a wrong-mode oracle drifted")
    console = Path(summary["positive_runtime"]["console_path"]).read_bytes()
    if not all(console.count(anchor) == 1 for anchor in ANCHORS[:4]):
        raise GateError("KL-151a frozen console anchors drifted")
    linux_rows = summary["component_queues"]["linux"]
    expected_patches = [
        {"patch": name, "commit": commit, "patch_id": payload_id}
        for name, commit, payload_id in LINUX_PATCHES[:10]
    ]
    if linux_rows != expected_patches:
        raise GateError("KL-151a frozen Linux patch identities drifted")
    runner = Path(summary["runner_identity"]["path"])
    if (
        not runner.is_file()
        or file_identity(runner) != summary["runner_identity"]
    ):
        raise GateError("KL-151a frozen runner identity drifted")
    manifest_path = Path(summary["artifact_manifest"]["path"])
    if (
        not manifest_path.is_file()
        or file_identity(manifest_path) != summary["artifact_manifest"]
    ):
        raise GateError("KL-151a frozen manifest identity drifted")
    manifest = json.loads(manifest_path.read_text())
    if (
        manifest.get("task") != "KL-151a"
        or manifest.get("artifact_count") != 85
        or len(manifest.get("artifacts", [])) != 85
        or manifest.get("runner_identity") != summary["runner_identity"]
    ):
        raise GateError("KL-151a frozen 85-item manifest contract drifted")
    for artifact in manifest["artifacts"]:
        artifact_path = Path(artifact["path"])
        if not artifact_path.is_file() or file_identity(artifact_path) != artifact:
            raise GateError(
                f"KL-151a frozen manifest artifact drifted: {artifact_path}"
            )
    evidence_dir = KL151_SUMMARY.parent
    if any(
        (evidence_dir / name).exists()
        for name in ("RUNNING.json", "FAILED.json")
    ):
        raise GateError("KL-151a frozen evidence has transient state files")
    return {
        "path": str(KL151_SUMMARY),
        "sha256": sha256(KL151_SUMMARY),
        "counts": summary["counts"],
        "qemu_head": summary["qemu_identity"]["head"],
        "linux_patches": linux_rows,
        "runner_identity": summary["runner_identity"],
        "artifact_manifest": summary["artifact_manifest"],
        "artifact_count": manifest["artifact_count"],
    }


def verify_component_identities() -> dict[str, object]:
    for source_name, source in (
        ("Linux", LINUX_SOURCE),
        ("QEMU", QEMU_SOURCE),
    ):
        dirty = execute(
            f"{source_name.lower()}-status-before",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{source_name} source worktree dirty:\n{dirty}")

    linux_rows = verify_queue("linux", LINUX_SOURCE, LINUX_SERIES)
    expected_linux_names = [row[0] for row in LINUX_PATCHES]
    if series_names(LINUX_SERIES) != expected_linux_names:
        raise GateError("Linux KL-152a series names/order drifted")
    for row, expected in zip(linux_rows, LINUX_PATCHES, strict=True):
        if (
            row["patch"],
            row["commit"],
            row["patch_id"],
        ) != expected:
            raise GateError(f"Linux frozen identity drift: {row}")

    qemu_patches = series_names(QEMU_SERIES)
    qemu_payloads = []
    for patch_name in qemu_patches:
        patch_path = QEMU_SERIES.parent / patch_name
        identity = file_identity(patch_path)
        qemu_payloads.append(
            {
                "patch": patch_name,
                "patch_path": str(patch_path),
                "patch_size": identity["size"],
                "patch_sha256": identity["sha256"],
            }
        )
    qemu_commits = execute(
        "qemu-commits",
        [
            "git",
            "-C",
            str(QEMU_SOURCE),
            "rev-list",
            "--reverse",
            f"{component_pin('qemu')}..HEAD",
        ],
    ).stdout.splitlines()
    if len(qemu_patches) != 38 or len(qemu_commits) != 38:
        raise GateError(
            "QEMU patch/commit count drifted: "
            f"{len(qemu_patches)}/{len(qemu_commits)}"
        )
    qemu_kl150a = []
    for offset, (patch_name, commit, expected_id) in enumerate(
        QEMU_PATCHES, start=1
    ):
        patch_path = QEMU_SERIES.parent / patch_name
        commit_mail = execute(
            f"qemu-kl150a-commit-{offset}",
            ["git", "-C", str(QEMU_SOURCE), "show", "--pretty=email", commit],
        ).stdout
        payload_id = patch_id(patch_path.read_text())
        payload_identity = file_identity(patch_path)
        row = {
            "patch": qemu_patches[-len(QEMU_PATCHES) + offset - 1],
            "commit": qemu_commits[-len(QEMU_PATCHES) + offset - 1],
            "patch_id": payload_id,
            "patch_path": str(patch_path),
            "patch_size": payload_identity["size"],
            "patch_sha256": payload_identity["sha256"],
        }
        expected = {
            "patch": patch_name,
            "commit": commit,
            "patch_id": expected_id,
        }
        if patch_id(commit_mail) != payload_id:
            raise GateError(
                f"QEMU KL-150a commit/patch payload drift: {patch_name}"
            )
        if any(row[key] != value for key, value in expected.items()):
            raise GateError(f"QEMU KL-150a identity drift: {row}")
        qemu_kl150a.append(row)
    parent = execute(
        "qemu-kl150a-parent",
        [
            "git",
            "-C",
            str(QEMU_SOURCE),
            "rev-parse",
            f"{QEMU_PATCHES[0][1]}^",
        ],
    ).stdout.strip()
    if parent != QEMU_PARENT:
        raise GateError(f"QEMU KL-149a parent drift: {parent}")
    return {
        "linux": linux_rows,
        "linux_series": file_identity(LINUX_SERIES),
        "qemu": {
            "baseline": component_pin("qemu"),
            "series": file_identity(QEMU_SERIES),
            "patch_payloads": qemu_payloads,
            "kl149_parent": parent,
            "patch_count": len(qemu_patches),
            "commit_count": len(qemu_commits),
            "kl150a": qemu_kl150a,
            "historical_replay_debt": (
                "QEMU patches 0001..0036 retain their pre-existing replay "
                "mismatch debt; KL-152a does not claim that debt is repaired"
            ),
        },
    }


def rebuild_and_verify_qemu() -> dict[str, str]:
    execute(
        "qemu-rebuild",
        ["ninja", "-C", str(QEMU_BUILD), "qemu-system-dadao"],
        cwd=QEMU_SOURCE,
    )
    head = execute(
        "qemu-head", ["git", "-C", str(QEMU_SOURCE), "rev-parse", "HEAD"]
    ).stdout.strip()
    if head != QEMU_HEAD:
        raise GateError(f"QEMU HEAD drift: {head} != {QEMU_HEAD}")
    binary_hash = sha256(QEMU)
    if binary_hash != QEMU_SHA256:
        raise GateError(
            f"rebuilt QEMU hash drift: {binary_hash} != {QEMU_SHA256}"
        )
    version_lines = execute("qemu-version", [str(QEMU), "--version"]).stdout
    version = version_lines.splitlines()[0] if version_lines else ""
    if QEMU_HEAD[:7] not in version:
        raise GateError(f"QEMU version does not bind final HEAD: {version}")
    return {
        "path": str(QEMU),
        "head": head,
        "sha256": binary_hash,
        "version": version,
    }


def reject_forbidden_diagnostics(result: subprocess.CompletedProcess[str]) -> None:
    diagnostics = result.stdout + result.stderr
    found = []
    if "shift count is negative" in diagnostics:
        found.append("shift count is negative")
    if any(
        "ELF_CLASS" in line and "is not defined" in line
        for line in diagnostics.splitlines()
    ):
        found.append("ELF_CLASS is not defined")
    if found:
        raise GateError(f"forbidden Linux build diagnostics: {found}")


def verify_image(output: Path, *, expect_console: bool) -> dict[str, object]:
    vmlinux = output / "vmlinux"
    image = output / "arch" / "dadao" / "boot" / "Image"
    for path in (vmlinux, image):
        if not path.is_file() or path.stat().st_size == 0:
            raise GateError(f"missing or empty Linux output: {path}")

    headers = execute(
        f"{output.name}-vmlinux-readobj",
        [str(LLVM_BIN / "llvm-readobj"), "--file-headers", str(vmlinux)],
    ).stdout
    required = (
        "Class: 64-bit (0x2)",
        "DataEncoding: BigEndian (0x2)",
        "Type: Executable (0x2)",
        "Machine: 0xDA0",
        "Entry: 0x80000000",
    )
    missing = [marker for marker in required if marker not in headers]
    if missing:
        raise GateError(f"vmlinux ELF markers missing: {missing}")
    undefined = execute(
        f"{output.name}-vmlinux-undefined",
        [str(LLVM_BIN / "llvm-nm"), "-u", str(vmlinux)],
    ).stdout.strip()
    if undefined:
        raise GateError(f"vmlinux has undefined symbols:\n{undefined}")
    symbols = execute(
        f"{output.name}-vmlinux-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(vmlinux)],
    ).stdout.splitlines()
    end_rows = [line for line in symbols if line.rstrip().endswith(" _end")]
    if len(end_rows) != 1:
        raise GateError(f"unexpected _end symbols: {end_rows}")
    end = int(end_rows[0].split()[0], 16)
    image_bytes = image.read_bytes()
    if RAM_BASE + len(image_bytes) > SCRATCH_BASE:
        raise GateError("flat Image overlaps K3 bring-up scratch")
    if not (
        end <= SCRATCH_BASE
        < SCRATCH_BASE + ORACLE_SIZE
        < STACK_TOP
        < SCRATCH_END
    ):
        raise GateError("ELF/scratch/progress/stack layout overlaps")
    config = (output / ".config").read_text()
    expected_config = (
        "CONFIG_DADAO_M1_DEBUG_CONSOLE=y"
        if expect_console
        else "# CONFIG_DADAO_M1_DEBUG_CONSOLE is not set"
    )
    for option in (
        "CONFIG_DADAO_K3_O0_LINK_COMPAT=y",
        "CONFIG_DADAO_K3_EARLY_MARKER=y",
        "CONFIG_DADAO_M1_PROGRESS=y",
        expected_config,
    ):
        if option not in config:
            raise GateError(f"required Linux config missing: {option}")
    expected_anchor_counts = (
        (1, 1, 1, 1, 1) if expect_console else (0, 1, 0, 1, 1)
    )
    for anchor, expected_count in zip(
        ANCHORS, expected_anchor_counts, strict=True
    ):
        count = image_bytes.count(anchor)
        if count != expected_count:
            raise GateError(
                f"Image anchor identity drift for {anchor!r}: "
                f"{count} != {expected_count}"
            )
    return {
        "vmlinux": str(vmlinux),
        "vmlinux_size": vmlinux.stat().st_size,
        "vmlinux_sha256": sha256(vmlinux),
        "image": str(image),
        "image_size": image.stat().st_size,
        "image_sha256": sha256(image),
        "end": f"0x{end:016x}",
        "debug_console": expect_console,
    }


def verify_progress_source_contract() -> dict[str, str]:
    kconfig = LINUX_SOURCE / "arch/dadao/Kconfig"
    defconfig = LINUX_SOURCE / "arch/dadao/configs/dadao_defconfig"
    header = LINUX_SOURCE / "arch/dadao/include/asm/dadao-m1.h"
    setup = LINUX_SOURCE / "arch/dadao/kernel/setup.c"
    arch_mem_init = LINUX_SOURCE / "arch/dadao/mm/init.c"
    main = LINUX_SOURCE / "init/main.c"
    page_alloc = LINUX_SOURCE / "mm/page_alloc.c"
    early_console = LINUX_SOURCE / "arch/dadao/kernel/early-console.c"
    head = LINUX_SOURCE / "arch/dadao/kernel/head.S"
    required = {
        header: (
            "DADAO_M1_DEBUG_CONSOLE_TX\t0x10001000UL",
            "DADAO_M1_PROGRESS_SETUP_ENTER\t0x87fd0010UL",
            "DADAO_M1_PROGRESS_SETUP_DONE\t0x87fd0018UL",
            "DADAO_M1_PROGRESS_MEM_INIT\t0x87fd0020UL",
            "DADAO_M1_PROGRESS_MEM_INIT_DONE\t0x87fd0028UL",
            "DADAO_M1_PROGRESS_MM_INIT_DONE\t0x87fd0030UL",
            "DADAO_M1_PROGRESS_MM_INIT_DONE_VALUE\t0x4b4c3135324d4d44ULL",
        ),
        setup: (
            "DADAO_M1_PROGRESS_SETUP_ENTER_VALUE",
            "DADAO_M1_PROGRESS_SETUP_DONE_VALUE",
        ),
        arch_mem_init: (
            "DADAO_M1_PROGRESS_MEM_INIT_VALUE",
            "DADAO_M1_PROGRESS_MEM_INIT_DONE_VALUE",
        ),
        main: (
            "DADAO_M1_PROGRESS_MM_INIT_DONE_VALUE",
        ),
        early_console: (
            "DADAO M1 test-machine early console online",
            "DADAO M1 setup_arch complete",
            "register_console(&dadao_m1_debug_console)",
            "dadao_m1_debug_console_setup_done",
        ),
    }
    for path, markers in required.items():
        text = path.read_text()
        for marker in markers:
            if text.count(marker) != 1:
                raise GateError(
                    f"source stage marker drift: {path}: {marker!r}"
                )
    kconfig_text = kconfig.read_text()
    progress_config = re.search(
        r"(?ms)^config DADAO_M1_PROGRESS\n"
        r"(?P<body>.*?)(?=^config |\Z)",
        kconfig_text,
    )
    if progress_config is None:
        raise GateError("DADAO_M1_PROGRESS Kconfig contract is missing")
    progress_config_body = progress_config.group("body")
    for marker in (
        '\tbool "DADAO M1 test-machine boot progress words"',
        "\tdepends on DADAO_M1",
        "setup_arch, mem_init, and mm_init source",
        "Disabling this option removes all of those progress writes",
    ):
        if progress_config_body.count(marker) != 1:
            raise GateError(
                f"DADAO_M1_PROGRESS Kconfig contract drift: {marker!r}"
            )
    if defconfig.read_text().count("CONFIG_DADAO_M1_PROGRESS=y") != 1:
        raise GateError("dadao_defconfig must enable DADAO_M1_PROGRESS once")
    progress_guard = "#ifdef CONFIG_DADAO_M1_PROGRESS"
    for path, expected_guards in (
        (setup, 3),
        (arch_mem_init, 3),
        (main, 2),
    ):
        actual_guards = path.read_text().count(progress_guard)
        if actual_guards != expected_guards:
            raise GateError(
                f"M1 progress guard count drift: {path}: "
                f"{actual_guards} != {expected_guards}"
            )
    main_text = main.read_text()
    if re.search(
        r"#ifdef CONFIG_DADAO_K3_O0_LINK_COMPAT\s+"
        r"#include <asm/dadao-m1.h>",
        main_text,
    ):
        raise GateError("init/main.c progress include is coupled to O0 compat")
    setup_text = setup.read_text()
    setup_start = setup_text.find("void __init setup_arch(char **cmdline_p)")
    setup_end = setup_text.find("\n}\n", setup_start)
    if setup_start < 0 or setup_end < 0:
        raise GateError("cannot isolate setup_arch source body")
    setup_body = setup_text[setup_start:setup_end]
    setup_order = (
        setup_body.find("DADAO_M1_PROGRESS_SETUP_ENTER_VALUE"),
        setup_body.find("paging_init();"),
        setup_body.find("DADAO_M1_PROGRESS_SETUP_DONE_VALUE"),
    )
    if min(setup_order) < 0 or tuple(sorted(setup_order)) != setup_order:
        raise GateError(
            "setup_arch progress source order drifted: "
            f"enter/paging/done={setup_order}"
        )

    mem_text = arch_mem_init.read_text()
    mem_start = mem_text.find("void __init mem_init(void)")
    mem_end = mem_text.find("\n}\n", mem_start)
    if mem_start < 0 or mem_end < 0:
        raise GateError("cannot isolate mem_init source body")
    mem_body = mem_text[mem_start:mem_end]
    mem_order = (
        mem_body.find("DADAO_M1_PROGRESS_MEM_INIT_VALUE"),
        mem_body.find("memblock_free_all();"),
        mem_body.find("mem_init_print_info(NULL);"),
        mem_body.find("DADAO_M1_PROGRESS_MEM_INIT_DONE_VALUE"),
    )
    if min(mem_order) < 0 or tuple(sorted(mem_order)) != mem_order:
        raise GateError(
            "mem_init progress source order drifted: "
            f"enter/free/print/done={mem_order}"
        )
    mem_done_write = re.compile(
        r"dadao_m1_progress_write\(\s*"
        r"DADAO_M1_PROGRESS_MEM_INIT_DONE\s*,\s*"
        r"DADAO_M1_PROGRESS_MEM_INIT_DONE_VALUE\s*\);"
    )
    mem_done_matches = list(mem_done_write.finditer(mem_body))
    if len(mem_done_matches) != 1:
        raise GateError(
            "mem_init completion write must occur exactly once in mem_init"
        )
    mem_tail = mem_body[mem_done_matches[0].end():]
    mem_tail = re.sub(r"(?m)^\s*#endif\s*$", "", mem_tail)
    if mem_tail.strip():
        raise GateError(
            "KL151MID write is not the final real statement in mem_init"
        )

    mm_start = main_text.find("static void __init mm_init(void)")
    mm_end = main_text.find("\n}\n", mm_start)
    if mm_start < 0 or mm_end < 0:
        raise GateError("cannot isolate mm_init source body")
    mm_body = main_text[mm_start:mm_end]
    if "CONFIG_DADAO_K3_O0_LINK_COMPAT" in mm_body:
        raise GateError("mm_init progress write is coupled to O0 compat")
    mm_markers = (
        "mem_init();",
        "kmem_cache_init();",
        "kmemleak_init();",
        "pgtable_init();",
        "debug_objects_mem_init();",
        "vmalloc_init();",
        "ioremap_huge_init();",
        "init_espfix_bsp();",
        "pti_init();",
        "DADAO_M1_PROGRESS_MM_INIT_DONE_VALUE",
    )
    mm_order = tuple(mm_body.find(marker) for marker in mm_markers)
    if min(mm_order) < 0 or tuple(sorted(mm_order)) != mm_order:
        raise GateError(
            "mm_init source order drifted: "
            + ", ".join(
                f"{marker}={offset}"
                for marker, offset in zip(mm_markers, mm_order, strict=True)
            )
        )
    mm_done_write = re.compile(
        r"dadao_m1_progress_write\(\s*"
        r"DADAO_M1_PROGRESS_MM_INIT_DONE\s*,\s*"
        r"DADAO_M1_PROGRESS_MM_INIT_DONE_VALUE\s*\);"
    )
    mm_done_matches = list(mm_done_write.finditer(mm_body))
    if len(mm_done_matches) != 1:
        raise GateError(
            "mm_init completion write must occur exactly once in mm_init"
        )
    mm_tail = mm_body[mm_done_matches[0].end():]
    mm_tail = re.sub(r"(?m)^\s*#endif\s*$", "", mm_tail)
    if mm_tail.strip():
        raise GateError(
            "KL152MMD write is not the final real statement in mm_init"
        )

    page_alloc_text = page_alloc.read_text()
    carrier_contract = (
        "#ifdef CONFIG_DADAO_K3_O0_LINK_COMPAT\n"
        "typedef unsigned long prepare_alloc_pages_result_t;\n"
        "#else\n"
        "typedef bool prepare_alloc_pages_result_t;\n"
        "#endif"
    )
    if page_alloc_text.count(carrier_contract) != 1:
        raise GateError("prepare_alloc_pages result carrier contract drifted")
    if page_alloc_text.count(
        "static inline prepare_alloc_pages_result_t\n"
        "prepare_alloc_pages("
    ) != 1:
        raise GateError("prepare_alloc_pages widened signature drifted")
    carrier_contracts = (
        (
            page_alloc,
            "typedef unsigned long zone_watermark_fast_result_t;",
            1,
        ),
        (
            page_alloc,
            "static inline zone_watermark_fast_result_t\n"
            "zone_watermark_fast(",
            1,
        ),
        (
            page_alloc,
            "typedef unsigned long can_steal_fallback_result_t;",
            1,
        ),
        (
            page_alloc,
            "static can_steal_fallback_result_t\ncan_steal_fallback(",
            1,
        ),
        (
            page_alloc,
            "typedef unsigned long rmqueue_fallback_result_t;",
            1,
        ),
        (
            page_alloc,
            "static __always_inline rmqueue_fallback_result_t\n"
            "__rmqueue_fallback(",
            1,
        ),
        (
            page_alloc,
            "typedef unsigned long check_new_pcp_result_t;",
            1,
        ),
        (
            page_alloc,
            "static inline check_new_pcp_result_t check_new_pcp(",
            2,
        ),
        (
            LINUX_SOURCE / "mm/slub.c",
            "typedef unsigned long pfmemalloc_match_result_t;",
            1,
        ),
        (
            LINUX_SOURCE / "mm/slub.c",
            "static inline pfmemalloc_match_result_t\npfmemalloc_match(",
            2,
        ),
        (
            LINUX_SOURCE / "mm/slub.c",
            "typedef unsigned long cmpxchg_double_slab_result_t;",
            1,
        ),
        (
            LINUX_SOURCE / "mm/slub.c",
            "static inline cmpxchg_double_slab_result_t\n"
            "__cmpxchg_double_slab(",
            1,
        ),
        (
            LINUX_SOURCE / "mm/slab.h",
            "typedef unsigned long slab_want_init_on_free_result_t;",
            1,
        ),
        (
            LINUX_SOURCE / "mm/slab.h",
            "static inline slab_want_init_on_free_result_t\n"
            "slab_want_init_on_free(",
            1,
        ),
        (
            LINUX_SOURCE / "mm/slab.h",
            "typedef unsigned long slab_want_init_on_alloc_result_t;",
            1,
        ),
        (
            LINUX_SOURCE / "mm/slab.h",
            "static inline slab_want_init_on_alloc_result_t\n"
            "slab_want_init_on_alloc(",
            1,
        ),
    )
    for path, marker, expected_count in carrier_contracts:
        actual_count = path.read_text().count(marker)
        if actual_count != expected_count:
            raise GateError(
                f"carrier source contract drift: {path}: "
                f"{marker!r}: {actual_count} != {expected_count}"
            )
    slab_header = (LINUX_SOURCE / "mm/slab.h").read_text()
    if slab_header.count("return !!(flags & __GFP_ZERO);") != 2:
        raise GateError("SLUB init-on-alloc carrier is not normalized to 0/1")

    head_text = head.read_text()
    for value in (
        "4b4c313530534145",
        "4b4c313530534144",
        "4b4c3135304d494e",
        "4b4c3135314d4944",
        "4b4c3135324d4d44",
    ):
        if value in head_text.lower():
            raise GateError("head.S pre-fills a KL-150..KL-152 progress value")
    return {
        "progress_kconfig": str(kconfig),
        "progress_defconfig": str(defconfig),
        "setup_arch_enter": str(setup),
        "setup_arch_done": str(setup),
        "mem_init_enter": str(arch_mem_init),
        "mem_init_done": str(arch_mem_init),
        "mm_init_done": str(main),
        "prepare_alloc_pages_carrier": str(page_alloc),
        "console": str(early_console),
        "contract": str(header),
    }


def build_linux_image() -> dict[str, object]:
    make("linux-mrproper", LINUX_OUTPUT, "mrproper")
    make("linux-defconfig", LINUX_OUTPUT, "dadao_defconfig")
    make("linux-olddefconfig", LINUX_OUTPUT, "olddefconfig")
    positive_build = make("linux-image", LINUX_OUTPUT, "Image")
    reject_forbidden_diagnostics(positive_build)
    return verify_image(LINUX_OUTPUT, expect_console=True)


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
            "arguments": {
                "command-line":
                    f'pmemsave {SCRATCH_BASE:#x} {ORACLE_SIZE} "{output}"'
            },
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


def identify_post_mm_init_blocker(
    name: str, trace_path: Path
) -> dict[str, object]:
    trace = trace_path.read_text()
    matches = re.findall(
        r"dadao: exception index=(\d+) pc=(0x[0-9a-f]+)", trace
    )
    maligned = [
        (int(index), int(pc, 16))
        for index, pc in matches
        if int(index) == NEXT_BLOCKER_EXCEPTION_INDEX
    ]
    if not maligned:
        raise GateError(f"{name}: no post-mm-init MALIGN in QEMU trace")
    if any(item != (NEXT_BLOCKER_EXCEPTION_INDEX, NEXT_BLOCKER_PC)
           for item in maligned):
        raise GateError(f"{name}: post-mm-init exception drift: {maligned}")

    symbols = execute(
        f"{name}-post-mm-init-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(LINUX_OUTPUT / "vmlinux")],
    ).stdout.splitlines()
    resolved: tuple[int, str] | None = None
    for line in symbols:
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            address = int(fields[0], 16)
        except ValueError:
            continue
        if address <= NEXT_BLOCKER_PC:
            resolved = (address, fields[2])
        else:
            break
    expected = (NEXT_BLOCKER_SYMBOL_ADDRESS, NEXT_BLOCKER_SYMBOL)
    if resolved != expected:
        raise GateError(
            f"{name}: post-mm-init symbol drift: {resolved} != {expected}"
        )

    disassembly = execute(
        f"{name}-post-mm-init-disassembly",
        [
            str(LLVM_BIN / "llvm-objdump"),
            "--arch-name=dadao",
            "-d",
            f"--start-address={NEXT_BLOCKER_PC - 0x28:#x}",
            f"--stop-address={NEXT_BLOCKER_PC + 0xc:#x}",
            str(LINUX_OUTPUT / "vmlinux"),
        ],
    ).stdout
    required_disassembly = (
        f"addi rb8, rb1, {NEXT_BLOCKER_STACK_SLOT}",
        "stb rd16, rb8, 0",
        f"{NEXT_BLOCKER_PC:x}:",
        "ldo rd31, rb8, 0",
    )
    missing = [
        marker for marker in required_disassembly if marker not in disassembly
    ]
    if missing:
        raise GateError(
            f"{name}: post-mm-init stack-slot proof drift: {missing}"
        )
    radix_tree = (LINUX_SOURCE / "lib/radix-tree.c").read_text()
    if radix_tree.count(
        "static bool node_tag_get(const struct radix_tree_root *root,"
    ) != 1:
        raise GateError(
            f"{name}: next-blocker source signature is no longer frozen"
        )
    return {
        "exception": "EXCP_MALIGN",
        "exception_index": NEXT_BLOCKER_EXCEPTION_INDEX,
        "pc": f"0x{NEXT_BLOCKER_PC:016x}",
        "symbol": NEXT_BLOCKER_SYMBOL,
        "symbol_address": f"0x{NEXT_BLOCKER_SYMBOL_ADDRESS:016x}",
        "symbol_offset": f"0x{NEXT_BLOCKER_PC - NEXT_BLOCKER_SYMBOL_ADDRESS:x}",
        "source": "lib/radix-tree.c::node_tag_get",
        "stack_slot_evidence": {
            "offset_from_rb1": NEXT_BLOCKER_STACK_SLOT,
            "store": "stb",
            "reload": "ldo",
        },
        "trace_path": str(trace_path),
        "disassembly_path": str(
            EVIDENCE / f"{name}-post-mm-init-disassembly.log"
        ),
    }


def connect_qmp(proc: subprocess.Popen[bytes], qmp_path: Path, timeout: float):
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    deadline = time.monotonic() + timeout
    while True:
        try:
            sock.connect(str(qmp_path))
            break
        except OSError:
            if proc.poll() is not None:
                raise GateError(
                    f"QEMU exited before QMP connect: rc={proc.returncode}"
                )
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


def analyze_carrier_failure(
    stage: dict[str, object], vmlinux: Path, trace_path: Path
) -> dict[str, object]:
    label = str(stage["label"])
    expected_index = int(stage["exception_index"])
    expected_pc = int(stage["pc"])
    expected_symbol = str(stage["symbol"])
    expected_symbol_address = int(stage["symbol_address"])
    stack_slot_offset = int(stage["stack_slot_offset"])
    store_register = str(stage.get("store_register", "rd16"))
    reload_register = str(stage.get("reload_register", "rd31"))

    trace = trace_path.read_text()
    exceptions = [
        (int(index), int(pc, 16))
        for index, pc in re.findall(
            r"dadao: exception index=(\d+) pc=(0x[0-9a-f]+)", trace
        )
        if int(index) == expected_index
    ]
    expected_exception = (expected_index, expected_pc)
    if not exceptions or any(item != expected_exception for item in exceptions):
        raise GateError(
            f"{label}: carrier-fix exception drift: {exceptions}"
        )

    symbol_result = execute(
        f"{label}-symbols",
        [str(LLVM_BIN / "llvm-nm"), "-n", str(vmlinux)],
    )
    resolved: tuple[int, str] | None = None
    for line in symbol_result.stdout.splitlines():
        fields = line.split()
        if len(fields) != 3:
            continue
        try:
            address = int(fields[0], 16)
        except ValueError:
            continue
        if address <= expected_pc:
            resolved = (address, fields[2])
        else:
            break
    expected_resolution = (expected_symbol_address, expected_symbol)
    if resolved != expected_resolution:
        raise GateError(
            f"{label}: carrier-fix symbol drift: "
            f"{resolved} != {expected_resolution}"
        )

    disassembly_result = execute(
        f"{label}-disassembly",
        [
            str(LLVM_BIN / "llvm-objdump"),
            "--arch-name=dadao",
            "-d",
            f"--start-address={expected_pc - 0x30:#x}",
            f"--stop-address={expected_pc + 0xc:#x}",
            str(vmlinux),
        ],
    )
    required = (
        f"addi rb8, rb1, {stack_slot_offset}",
        f"stb {store_register}, rb8, 0",
        f"{expected_pc:x}:",
        f"ldo {reload_register}, rb8, 0",
    )
    missing = [
        marker for marker in required
        if marker not in disassembly_result.stdout
    ]
    if missing:
        raise GateError(
            f"{label}: carrier-fix stack-slot proof drift: {missing}"
        )
    return {
        "exception": "EXCP_MALIGN",
        "exception_index": expected_index,
        "pc": f"0x{expected_pc:016x}",
        "symbol": expected_symbol,
        "symbol_address": f"0x{expected_symbol_address:016x}",
        "symbol_offset": f"0x{expected_pc - expected_symbol_address:x}",
        "source": stage["source"],
        "stack_slot_evidence": {
            "offset_from_rb1": stack_slot_offset,
            "store": f"stb {store_register}, rb8, 0",
            "reload": f"ldo {reload_register}, rb8, 0",
        },
        "symbol_log": file_identity(EVIDENCE / f"{label}-symbols.log"),
        "disassembly_log": file_identity(
            EVIDENCE / f"{label}-disassembly.log"
        ),
    }


def run_expected_carrier_failure(
    stage: dict[str, object], image: Path, vmlinux: Path, rom: Path
) -> dict[str, object]:
    label = str(stage["label"])
    stage_dir = EVIDENCE / "carrier-fix" / label
    stage_dir.mkdir(parents=True, exist_ok=True)
    transport = tempfile.TemporaryDirectory(prefix="kl152a_carrier_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    console_path = stage_dir / "console.bin"
    trace_path = stage_dir / "qemu-trace.log"
    runtime_path = stage_dir / "qemu-runtime.log"
    command = [
        str(QEMU),
        "-M",
        "dadao-m1",
        "-S",
        "-global",
        "dadao-cpu.cfx-smon-real=on",
        "-bios",
        str(rom),
        "-kernel",
        str(image),
        "-display",
        "none",
        "-serial",
        f"file:{console_path}",
        "-no-shutdown",
        "-d",
        "int",
        "-D",
        str(trace_path),
        "-qmp",
        f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    greeting = ""
    initial = b""
    final = b""
    status: object = None
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(
                f"{label}: historical scratch is nonzero before cont"
            )
        (stage_dir / "progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise GateError(
                    f"{label}: QEMU exited before expected MALIGN"
                )
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                break
            time.sleep(0.02)
        else:
            raise GateError(f"{label}: expected MALIGN timeout")
        final = dump_oracle(stream, oracle_path)
        expected_oracle = (MARKER_VALUE, 0, *PROGRESS_VALUES[:4], 0)
        if decode_oracle(final) != expected_oracle:
            raise GateError(
                f"{label}: historical oracle drift: {decode_oracle(final)}"
            )
        if (
            not isinstance(status, dict)
            or status.get("status") != "shutdown"
            or status.get("running")
        ):
            raise GateError(
                f"{label}: historical MALIGN did not shut down: {status}"
            )
        (stage_dir / "progress-final.bin").write_bytes(final)
        try:
            qmp_roundtrip(stream, {"execute": "quit"})
        except (GateError, OSError, TimeoutError):
            pass
        sock.close()
    finally:
        if proc.poll() is None:
            proc.kill()
        stdout, stderr = proc.communicate()
        runtime_path.write_text(
            "=== command ===\n"
            + shlex.join(command)
            + "\n=== greeting ===\n"
            + greeting
            + "\n=== stdout ===\n"
            + stdout.decode(errors="replace")
            + "\n=== stderr ===\n"
            + stderr.decode(errors="replace")
        )
        transport.cleanup()

    blocker = analyze_carrier_failure(stage, vmlinux, trace_path)
    return {
        "status": status,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "image": file_identity(stage_dir / "Image"),
        "initial_raw": file_identity(stage_dir / "progress-initial.bin"),
        "final_raw": file_identity(stage_dir / "progress-final.bin"),
        "trace": file_identity(trace_path),
        "console": file_identity(console_path),
        "qemu_runtime": file_identity(runtime_path),
        "observed_failure": blocker,
    }


def build_and_run_carrier_stage(
    stage: dict[str, object], rom: Path
) -> dict[str, object]:
    label = str(stage["label"])
    commit = str(stage["commit"])
    source_parent = ROOT / ".work" / "source"
    build_parent = ROOT / ".work" / "build"
    source_parent.mkdir(parents=True, exist_ok=True)
    build_parent.mkdir(parents=True, exist_ok=True)
    source_path = Path(
        tempfile.mkdtemp(prefix=f"kl152a-{label}-", dir=source_parent)
    )
    shutil.rmtree(source_path)
    output_path = Path(
        tempfile.mkdtemp(prefix=f"kl152a-{label}-", dir=build_parent)
    )
    worktree_added = False
    result: dict[str, object] | None = None
    try:
        execute(
            f"{label}-worktree-add",
            [
                "git",
                "-C",
                str(LINUX_SOURCE),
                "worktree",
                "add",
                "--detach",
                str(source_path),
                commit,
            ],
        )
        worktree_added = True
        identity = execute(
            f"{label}-commit-identity",
            [
                "git",
                "-C",
                str(source_path),
                "show",
                "-s",
                "--format=%H%n%P%n%s",
                "HEAD",
            ],
        ).stdout.splitlines()
        if not identity or identity[0] != commit:
            raise GateError(f"{label}: historical HEAD identity drift")
        dirty = execute(
            f"{label}-status-before",
            ["git", "-C", str(source_path), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(f"{label}: historical worktree dirty")

        make_tree(f"{label}-mrproper", source_path, output_path, "mrproper")
        make_tree(
            f"{label}-defconfig",
            source_path,
            output_path,
            "dadao_defconfig",
        )
        make_tree(
            f"{label}-olddefconfig",
            source_path,
            output_path,
            "olddefconfig",
        )
        build = make_tree(
            f"{label}-image", source_path, output_path, "Image"
        )
        reject_forbidden_diagnostics(build)
        image = output_path / "arch/dadao/boot/Image"
        vmlinux = output_path / "vmlinux"
        if not image.is_file() or not vmlinux.is_file():
            raise GateError(f"{label}: historical Image/vmlinux missing")
        stage_dir = EVIDENCE / "carrier-fix" / label
        stage_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(image, stage_dir / "Image")

        runtime = run_expected_carrier_failure(
            stage, stage_dir / "Image", vmlinux, rom
        )
        dirty_after = execute(
            f"{label}-status-after",
            ["git", "-C", str(source_path), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty_after:
            raise GateError(
                f"{label}: historical worktree dirty after evidence"
            )
        command_logs = [
            file_identity(EVIDENCE / f"{label}-{suffix}.log")
            for suffix in (
                "worktree-add",
                "commit-identity",
                "status-before",
                "mrproper",
                "defconfig",
                "olddefconfig",
                "image",
                "status-after",
            )
        ]
        result = {
            "label": label,
            "linux_head": commit,
            "linux_parent": identity[1] if len(identity) > 1 else "",
            "linux_subject": identity[2] if len(identity) > 2 else "",
            "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
            "command_logs": command_logs,
            **runtime,
        }
    finally:
        cleanup_failures: list[str] = []
        if worktree_added:
            remove = execute(
                f"{label}-worktree-remove",
                [
                    "git",
                    "-C",
                    str(LINUX_SOURCE),
                    "worktree",
                    "remove",
                    "--force",
                    str(source_path),
                ],
                check=False,
            )
            if remove.returncode:
                cleanup_failures.append(
                    f"git worktree remove rc={remove.returncode}"
                )
        for path in (output_path, source_path):
            try:
                if path.exists():
                    shutil.rmtree(path)
            except OSError as exc:
                cleanup_failures.append(f"cannot remove {path}: {exc}")
            if path.exists():
                cleanup_failures.append(f"path remains after cleanup: {path}")
        worktrees = execute(
            f"{label}-worktree-list-after",
            [
                "git",
                "-C",
                str(LINUX_SOURCE),
                "worktree",
                "list",
                "--porcelain",
            ],
            check=False,
        )
        if worktrees.returncode:
            cleanup_failures.append(
                f"git worktree list rc={worktrees.returncode}"
            )
        elif str(source_path) in worktrees.stdout:
            cleanup_failures.append(
                f"temporary worktree remains registered: {source_path}"
            )
        if cleanup_failures:
            raise GateError(
                f"{label}: temporary worktree cleanup failed: "
                + "; ".join(cleanup_failures)
            )
    if result is None:
        raise GateError(f"{label}: carrier-fix evidence was not produced")
    result["worktree_remove_log"] = file_identity(
        EVIDENCE / f"{label}-worktree-remove.log"
    )
    result["worktree_list_after_log"] = file_identity(
        EVIDENCE / f"{label}-worktree-list-after.log"
    )
    return result


def collect_carrier_fix_evidence(rom: Path) -> list[dict[str, object]]:
    return [
        build_and_run_carrier_stage(stage, rom)
        for stage in CARRIER_FIX_STAGES
    ]


def run_progress_guest(
    name: str,
    image: Path,
    rom: Path,
    *,
    serial_mode: str,
    timeout: float = 30.0,
) -> dict[str, object]:
    if serial_mode not in {"file", "none"}:
        raise GateError(f"invalid serial mode: {serial_mode}")
    transport = tempfile.TemporaryDirectory(prefix=f"kl152a_{name}_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    console_path = EVIDENCE / f"{name}-console.bin"
    console_path.unlink(missing_ok=True)
    trace_path = EVIDENCE / f"{name}-qemu-trace.log"
    trace_path.unlink(missing_ok=True)
    serial_arg = f"file:{console_path}" if serial_mode == "file" else "none"
    command = [
        str(QEMU),
        "-M",
        "dadao-m1",
        "-S",
        "-global",
        "dadao-cpu.cfx-smon-real=on",
        "-bios",
        str(rom),
        "-kernel",
        str(image),
        "-display",
        "none",
        "-serial",
        serial_arg,
        "-no-shutdown",
        "-d",
        "int",
        "-D",
        str(trace_path),
        "-qmp",
        f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    greeting = ""
    snapshots: list[dict[str, object]] = []
    marker_running_status: object = None
    final_status: object = None
    initial = b""
    final = b""
    start = time.monotonic()
    last_progress_depth = 0
    try:
        sock, stream, greeting = connect_qmp(proc, qmp_path, 10.0)
        initial = dump_oracle(stream, oracle_path)
        if initial != bytes(ORACLE_SIZE):
            raise GateError(
                f"{name}: scratch nonzero before CPU start: {initial.hex()}"
            )
        (EVIDENCE / f"{name}-progress-initial.bin").write_bytes(initial)
        qmp_roundtrip(stream, {"execute": "cont"})
        last_words: tuple[int, ...] | None = None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                raise GateError(
                    f"{name}: QEMU exited before progress: rc={proc.returncode}"
                )
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
                marker_running_status = qmp_roundtrip(
                    stream, {"execute": "query-status"}
                )
                if (
                    marker_running_status.get("status") != "running"
                    or not marker_running_status.get("running")
                ):
                    raise GateError(
                        f"{name}: KL-149 marker not observed running: "
                        f"{marker_running_status}"
                    )
            if marker not in (0, MARKER_VALUE) or failure != 0:
                raise GateError(
                    f"{name}: KL-149 positive oracle regressed: "
                    f"marker={marker:#x} failure={failure:#x}"
                )
            if not progress_is_ordered(tuple(progress)):
                raise GateError(
                    f"{name}: unordered/invalid progress words: {progress}"
                )
            if any(progress) and marker != MARKER_VALUE:
                raise GateError(
                    f"{name}: progress appeared before KL-149 marker: {words}"
                )
            current_progress_depth = progress_depth(tuple(progress))
            if current_progress_depth < last_progress_depth:
                raise GateError(
                    f"{name}: progress regressed: "
                    f"{current_progress_depth} < {last_progress_depth}"
                )
            last_progress_depth = current_progress_depth
            if tuple(progress) == PROGRESS_VALUES:
                break
            status = qmp_roundtrip(stream, {"execute": "query-status"})
            if status.get("status") == "shutdown":
                registers = qmp_roundtrip(
                    stream,
                    {
                        "execute": "human-monitor-command",
                        "arguments": {"command-line": "info registers"},
                    },
                )
                (EVIDENCE / f"{name}-shutdown-registers.log").write_text(
                    str(registers) + "\n"
                )
                raise GateError(
                    f"{name}: shutdown before all progress words: {words}"
                )
            time.sleep(0.02)
        else:
            raise GateError(f"{name}: progress timeout: {snapshots[-1:]}")
        if marker_running_status is None:
            raise GateError(f"{name}: KL-149 marker was never observed")
        time.sleep(0.2)
        final = dump_oracle(stream, oracle_path)
        final_status = qmp_roundtrip(stream, {"execute": "query-status"})
        expected_final = (MARKER_VALUE, 0, *PROGRESS_VALUES)
        final_words = decode_oracle(final)
        if final_words != expected_final:
            raise GateError(
                f"{name}: final oracle regressed after progress: "
                f"{final_words} != {expected_final}"
            )
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
            "=== command ===\n"
            + shlex.join(command)
            + "\n=== greeting ===\n"
            + greeting
            + "\n=== stdout ===\n"
            + stdout.decode(errors="replace")
            + "\n=== stderr ===\n"
            + stderr.decode(errors="replace")
        )
        transport.cleanup()
    if not final:
        raise GateError(f"{name}: final oracle missing")
    (EVIDENCE / f"{name}-progress-final.bin").write_bytes(final)
    console = console_path.read_bytes() if console_path.exists() else b""
    verdict, counts, positions = console_verdict(console)
    blocker = identify_post_mm_init_blocker(name, trace_path)
    if (
        not isinstance(final_status, dict)
        or final_status.get("status") != "shutdown"
        or final_status.get("running")
    ):
        raise GateError(
            f"{name}: post-mm-init MALIGN did not produce shutdown: "
            f"{final_status}"
        )
    return {
        "command": command,
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "final_words": {
            "kl149_marker": f"0x{decode_oracle(final)[0]:016x}",
            "kl149_failure": f"0x{decode_oracle(final)[1]:016x}",
            **{
                key: f"0x{value:016x}"
                for key, value in zip(
                    PROGRESS_NAMES, decode_oracle(final)[2:], strict=True
                )
            },
        },
        "snapshots": snapshots,
        "kl149_marker_running_status": marker_running_status,
        "post_progress_status": final_status,
        "console_path": str(console_path),
        "console_size": len(console),
        "console_sha256": sha256(console_path) if console_path.exists() else None,
        "console_anchor_counts": counts,
        "console_anchor_positions": positions,
        "console_verdict": verdict,
        "trace_path": str(trace_path),
        "first_post_mm_init_blocker": blocker,
    }


def run_wrong_mode_guest(image: Path, rom: Path) -> dict[str, object]:
    transport = tempfile.TemporaryDirectory(prefix="kl150a_wrong_mode_")
    transport_path = Path(transport.name)
    qmp_path = transport_path / "qmp.sock"
    oracle_path = transport_path / "oracle.bin"
    command = [
        str(QEMU),
        "-M",
        "dadao-m1",
        "-S",
        "-global",
        "dadao-cpu.cfx-smon-real=on",
        "-bios",
        str(rom),
        "-kernel",
        str(image),
        "-display",
        "none",
        "-serial",
        "none",
        "-no-shutdown",
        "-qmp",
        f"unix:{qmp_path},server,nowait",
    ]
    proc = subprocess.Popen(
        command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
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
            "=== command ===\n"
            + shlex.join(command)
            + "\n=== greeting ===\n"
            + greeting
            + "\n=== stdout ===\n"
            + stdout.decode(errors="replace")
            + "\n=== stderr ===\n"
            + stderr.decode(errors="replace")
        )
        transport.cleanup()
    (EVIDENCE / "wrong-mode-progress-final.bin").write_bytes(final)
    return {
        "initial_raw_hex": initial.hex(),
        "final_raw_hex": final.hex(),
        "status": status,
    }


def generate_roms() -> tuple[Path, Path]:
    rom = EVIDENCE / "kl152a-mm-init-handoff.bin"
    wrong_mode = EVIDENCE / "kl152a-mm-init-handoff-wrong-mode.bin"
    execute(
        "handoff-rom",
        [
            sys.executable,
            str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(rom),
        ],
    )
    execute(
        "handoff-rom-wrong-mode",
        [
            sys.executable,
            str(ROOT / "tests/scripts/gen_kl149a_linux_handoff.py"),
            str(wrong_mode),
            "--previous-mode",
            "3",
        ],
    )
    if sha256(rom) != ROM_SHA256:
        raise GateError("positive HBI ROM identity drift")
    if sha256(wrong_mode) != WRONG_MODE_ROM_SHA256:
        raise GateError("wrong-mode HBI ROM identity drift")
    forbidden = b"".join(struct.pack(">Q", value) for value in PROGRESS_VALUES)
    for payload in (rom.read_bytes(), wrong_mode.read_bytes()):
        if any(struct.pack(">Q", value) in payload for value in PROGRESS_VALUES):
            raise GateError("handoff ROM contains a progress value")
        if forbidden in payload:
            raise GateError("handoff ROM pre-fills the progress sequence")
    return rom, wrong_mode


def verify_sources_clean_after() -> None:
    for source_name, source in (
        ("Linux", LINUX_SOURCE),
        ("QEMU", QEMU_SOURCE),
    ):
        dirty = execute(
            f"{source_name.lower()}-status-after",
            ["git", "-C", str(source), "status", "--porcelain=v1"],
        ).stdout.strip()
        if dirty:
            raise GateError(
                f"{source_name} source worktree dirty after gate:\n{dirty}"
            )


def publish_artifact_manifest(
    runner_identity: dict[str, object]
) -> dict[str, object]:
    if ACTIVE_RUN_ID is None:
        raise GateError("artifact publication has no active run id")
    running_path = EVIDENCE / "RUNNING.json"
    if not running_path.is_file() or (EVIDENCE / "FAILED.json").exists():
        raise GateError(
            "manifest publication requires RUNNING and forbids FAILED"
        )
    running = json.loads(running_path.read_text())
    if (
        running.get("state") != "RUNNING"
        or running.get("run_id") != ACTIVE_RUN_ID
    ):
        raise GateError("RUNNING identity does not match active run")
    required = (
        EVIDENCE / "positive-progress-initial.bin",
        EVIDENCE / "positive-progress-final.bin",
        EVIDENCE / "positive-qemu-trace.log",
        EVIDENCE / "positive-console.bin",
        EVIDENCE / "positive-post-mm-init-symbols.log",
        EVIDENCE / "positive-post-mm-init-disassembly.log",
        EVIDENCE / "positive-qemu-runtime.log",
        EVIDENCE / "serial-none-progress-initial.bin",
        EVIDENCE / "serial-none-progress-final.bin",
        EVIDENCE / "serial-none-qemu-trace.log",
        EVIDENCE / "serial-none-post-mm-init-symbols.log",
        EVIDENCE / "serial-none-post-mm-init-disassembly.log",
        EVIDENCE / "serial-none-qemu-runtime.log",
        EVIDENCE / "wrong-mode-progress-initial.bin",
        EVIDENCE / "wrong-mode-progress-final.bin",
        EVIDENCE / "wrong-mode-qemu-runtime.log",
    )
    carrier_required = tuple(
        EVIDENCE / "carrier-fix" / str(stage["label"]) / name
        for stage in CARRIER_FIX_STAGES
        for name in (
            "Image",
            "progress-initial.bin",
            "progress-final.bin",
            "qemu-trace.log",
            "console.bin",
            "qemu-runtime.log",
        )
    )
    missing = [
        str(path) for path in (*required, *carrier_required)
        if not path.is_file()
    ]
    if missing:
        raise GateError(f"key evidence artifacts missing: {missing}")
    excluded_names = {
        "summary.json",
        "artifact-manifest.json",
        "RUNNING.json",
        "FAILED.json",
    }
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
        "task": "KL-152a",
        "run_id": ACTIVE_RUN_ID,
        "scope": (
            "All non-state files in the canonical clean single-run evidence "
            "directory before artifact-manifest.json and summary.json are "
            "published"
        ),
        "cycle_break": (
            "The manifest excludes itself, summary.json, RUNNING.json, and "
            "FAILED.json; summary.json binds this manifest by size and "
            "SHA256 while the external current-state record binds the final "
            "summary"
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
        manifest.get("task") != "KL-152a"
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
        "task": "KL-152a",
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
    if any(
        (EVIDENCE / name).exists()
        for name in ("RUNNING.json", "FAILED.json")
    ):
        raise GateError("transient state survived PASS publication")
    return summary_identity


def main() -> int:
    runner_identity = prepare_single_run_evidence()
    root_identity = verify_root_frozen_identity()
    frozen = verify_kl151_frozen_evidence()
    queues = verify_component_identities()
    source_contract = verify_progress_source_contract()
    qemu = rebuild_and_verify_qemu()
    rom, wrong_mode_rom = generate_roms()
    carrier_fix_evidence = collect_carrier_fix_evidence(rom)
    positive_image = build_linux_image()

    positive = run_progress_guest(
        "positive",
        Path(positive_image["image"]),
        rom,
        serial_mode="file",
    )
    if not positive["console_verdict"]:
        raise GateError(
            "positive console anchors are not unique and ordered: "
            f"counts={positive['console_anchor_counts']} "
            f"positions={positive['console_anchor_positions']}"
        )

    serial_none = run_progress_guest(
        "serial-none",
        Path(positive_image["image"]),
        rom,
        serial_mode="none",
    )
    if serial_none["console_verdict"]:
        raise GateError("-serial none passed the console verdict")
    if serial_none["console_size"] != 0:
        raise GateError("-serial none unexpectedly produced console bytes")
    blocker_identity_keys = (
        "exception",
        "exception_index",
        "pc",
        "symbol",
        "symbol_address",
        "symbol_offset",
        "source",
        "stack_slot_evidence",
    )
    if any(
        serial_none["first_post_mm_init_blocker"][key]
        != positive["first_post_mm_init_blocker"][key]
        for key in blocker_identity_keys
    ):
        raise GateError(
            "post-mm-init blocker differs between console transports"
        )

    wrong_mode = run_wrong_mode_guest(
        Path(positive_image["image"]), wrong_mode_rom
    )
    verify_sources_clean_after()

    counts = {"pass": 3, "fail": 0, "skip": 0}
    summary = {
        "task": "KL-152a",
        "run_id": ACTIVE_RUN_ID,
        "result": "PASS",
        "counts": counts,
        "build_flags": {"ARCH": "dadao", "KCFLAGS": "-O0"},
        "root_identity": root_identity,
        "kl151_frozen_evidence": frozen,
        "component_queues": queues,
        "carrier_fix_evidence": carrier_fix_evidence,
        "source_stage_contract": source_contract,
        "qemu_identity": qemu,
        "linux_positive": positive_image,
        "rom": {
            "path": str(rom),
            "sha256": sha256(rom),
            "wrong_mode_path": str(wrong_mode_rom),
            "wrong_mode_sha256": sha256(wrong_mode_rom),
        },
        "positive_runtime": positive,
        "negative_serial_none": serial_none,
        "negative_wrong_mode": wrong_mode,
        "first_next_blocker": positive["first_post_mm_init_blocker"],
        "runner_identity": runner_identity,
        "evidence_publication": {
            "semantics": (
                "exclusive clean single-run canonical directory with "
                "external atomic current-state authority"
            ),
            "exclusive_lock": {
                "path": str(EVIDENCE_LOCK),
                "mechanism": "fcntl.flock LOCK_EX|LOCK_NB",
                "outside_evidence": True,
                "held_for_entire_run_and_publication": True,
            },
            "current_state": {
                "path": str(EVIDENCE_CURRENT),
                "run_id": ACTIVE_RUN_ID,
                "valid_pass_contract": (
                    "state=PASS, valid_pass=true, matching run_id, and "
                    "matching summary/manifest identities"
                ),
            },
            "old_pass_invalidated_at_start": True,
            "start_publish": (
                "atomic current-state RUNNING invalidates every prior PASS "
                "before canonical evidence replacement"
            ),
            "summary_publish": (
                "manifest and summary use fsync plus atomic os.replace while "
                "RUNNING remains present; artifacts are revalidated before "
                "RUNNING removal and atomic current-state PASS"
            ),
            "failure_summary_policy": (
                "summary.json and manifest absent; FAILED.json and external "
                "current-state FAILED record this run"
            ),
            "forced_termination_policy": (
                "current-state remains RUNNING and no prior PASS is valid "
                "until the final atomic PASS commit"
            ),
            "startup_transient_cleanup": STARTUP_TRANSIENT_CLEANUP,
        },
    }
    current_runner_identity = file_identity(RUNNER)
    if current_runner_identity != runner_identity:
        raise GateError("runner changed while KL-152a gate was executing")
    summary["artifact_manifest"] = publish_artifact_manifest(runner_identity)
    finalize_success(summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("PASS: KL-152a mm_init completion (3/3, FAIL=0, SKIP=0)")
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
            raise SystemExit(f"KL-152a FAIL: {exc}") from exc
        raise
    finally:
        if lock_descriptor is not None:
            release_exclusive_lock(lock_descriptor)
