#!/usr/bin/env python3
"""Run the pinned Embench-IoT inventory as a fail-closed DADAO sweep.

Each of the exactly 19 pinned benchmarks is freshly compiled at -O0 and -O2,
linked with this project's musl crt1.o/libc.a, converted to a flat binary for
QEMU, and run as the same ELF under gem5 SE.  Embench support/main.c returns
zero only when verify_benchmark() succeeds, so backend exit code zero is PASS.

The sweep always writes JSON (and, when requested, Markdown), but exits
non-zero if preflight fails, any result is missing, or any result is not PASS.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
import tomllib
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "manifests/components.lock.toml"
SCHEMA_VERSION = 2
FINGERPRINT_VERSION = 1
LOG_RECORD_PREFIX = "EMBENCH_SWEEP_RECORD="

INVENTORY = (
    "aha-mont64",
    "crc32",
    "depthconv",
    "edn",
    "huffbench",
    "matmult-int",
    "md5sum",
    "nettle-aes",
    "nettle-sha256",
    "nsichneu",
    "picojpeg",
    "qrduino",
    "sglib-combined",
    "slre",
    "statemate",
    "tarfind",
    "ud",
    "wikisort",
    "xgboost",
)
OPTIMIZATIONS = ("O0", "O2")
BACKEND_STATES = ("PASS", "FAIL", "TIMEOUT", "NOT_RUN")
FINAL_STATUSES = {
    "PASS",
    "FAIL_COMPILE",
    "FAIL_LINK",
    "FAIL_QEMU",
    "FAIL_GEM5",
    "TIMEOUT_QEMU",
    "TIMEOUT_GEM5",
}
FAULT_CODES = {
    0x81: "MALIGN",
    0x82: "ILLI",
    0x83: "UNDI",
    0x84: "RASOF",
    0x85: "RASUF",
    0x8F: "UNMAPPED",
}


class PreflightError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def rel(path: Path) -> str:
    try:
        return str(path.absolute().relative_to(ROOT.absolute()))
    except ValueError:
        return str(path.absolute())


def command_text(command: list[str]) -> str:
    return shlex.join(command)


def run_command(
    command: list[str], timeout: float, log_path: Path
) -> dict[str, Any]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = completed.stdout
        result = {
            "attempted": True,
            "timed_out": False,
            "returncode": completed.returncode,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "log": rel(log_path),
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode("utf-8", "replace")
        result = {
            "attempted": True,
            "timed_out": True,
            "returncode": None,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "command": command,
            "log": rel(log_path),
        }
    record = {
        "command": command,
        "returncode": result["returncode"],
        "timed_out": result["timed_out"],
    }
    log_path.write_text(
        f"$ {command_text(command)}\n\n{output.rstrip()}\n\n"
        f"{LOG_RECORD_PREFIX}{json.dumps(record, sort_keys=True)}\n",
        encoding="utf-8",
    )
    return result


def git_head(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True
    ).strip()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_digest(value: Any) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def file_identity(path: Path) -> dict[str, Any]:
    return {
        "path": rel(path),
        "sha256": sha256(path),
        "size": path.stat().st_size,
    }


def directory_identity(path: Path) -> dict[str, Any]:
    files = []
    for item in sorted(
        (entry for entry in path.rglob("*") if entry.is_file()),
        key=lambda entry: entry.relative_to(path).as_posix(),
    ):
        files.append(
            {
                "path": item.relative_to(path).as_posix(),
                "sha256": sha256(item),
                "size": item.stat().st_size,
            }
        )
    return {
        "path": rel(path),
        "files": len(files),
        "sha256": canonical_digest(files),
    }


def tool_identity(path: Path) -> dict[str, Any]:
    identity = file_identity(path)
    identity["executable"] = os.access(path, os.X_OK)
    return identity


def git_tree(path: Path, revision: str = "HEAD") -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", f"{revision}^{{tree}}"],
        text=True,
    ).strip()


def stable_patch_id(data: bytes, label: str) -> str:
    completed = subprocess.run(
        ["git", "patch-id", "--stable"],
        input=data,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    records = completed.stdout.decode("utf-8", "replace").splitlines()
    if len(records) != 1 or len(records[0].split()) < 1:
        raise PreflightError(f"cannot derive one stable patch-id for {label}")
    return records[0].split()[0]


def patch_file_identity(path: Path) -> dict[str, Any]:
    identity = file_identity(path)
    identity["patch_id"] = stable_patch_id(path.read_bytes(), rel(path))
    return identity


def commit_patch_id(source: Path, commit: str) -> str:
    patch = subprocess.check_output(
        [
            "git",
            "-C",
            str(source),
            "show",
            "--binary",
            "--full-index",
            "--pretty=format:",
            commit,
        ]
    )
    return stable_patch_id(patch, commit)


def load_component(name: str) -> tuple[dict[str, Any], Path, list[str]]:
    with MANIFEST.open("rb") as stream:
        manifest = tomllib.load(stream)
    matches = [
        component
        for component in manifest.get("component", [])
        if component.get("name") == name
    ]
    if len(matches) != 1:
        raise PreflightError(
            f"manifest must contain exactly one {name!r} component"
        )
    component = matches[0]
    if not component.get("enabled"):
        raise PreflightError(f"manifest component {name!r} is not enabled")
    series_path = ROOT / component["patch_series"]
    if not series_path.is_file():
        raise PreflightError(f"missing patch series: {rel(series_path)}")
    patches = [
        line.strip()
        for line in series_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    return component, series_path, patches


def check_component_checkout(
    source: Path,
    component: dict[str, Any],
    series_path: Path,
    patches: list[str],
    source_mode: str,
) -> dict[str, Any]:
    if not (source / ".git").exists():
        raise PreflightError(f"missing Embench git checkout: {rel(source)}")
    dirty = subprocess.check_output(
        ["git", "-C", str(source), "status", "--porcelain=v1"], text=True
    )
    if dirty:
        raise PreflightError(f"Embench checkout is dirty: {rel(source)}")
    head = git_head(source)
    pin = component["commit"]
    patch_records = []
    for item in patches:
        patch_path = ROOT / "components" / component["name"] / "patches" / item
        if not patch_path.is_file():
            raise PreflightError(f"missing component patch: {rel(patch_path)}")
        patch_records.append(
            {"name": item, **patch_file_identity(patch_path)}
        )

    if source_mode == "unpatched":
        if head != pin:
            raise PreflightError(
                f"unpatched Embench HEAD {head} does not equal pin {pin}"
            )
        commits = []
        commit_patch_ids = []
    elif not patches:
        if head != pin:
            raise PreflightError(
                f"Embench HEAD {head} does not equal empty-series pin {pin}"
            )
        commits = []
        commit_patch_ids = []
    else:
        ancestor = subprocess.run(
            ["git", "-C", str(source), "merge-base", "--is-ancestor", pin, head],
            check=False,
        ).returncode
        commits = subprocess.check_output(
            [
                "git",
                "-C",
                str(source),
                "rev-list",
                "--reverse",
                f"{pin}..{head}",
            ],
            text=True,
        ).splitlines()
        if ancestor != 0 or len(commits) != len(patches):
            raise PreflightError(
                "Embench checkout does not match manifest pin plus patch series"
            )
        commit_patch_ids = [
            commit_patch_id(source, commit) for commit in commits
        ]
        expected_patch_ids = [
            record["patch_id"] for record in patch_records
        ]
        if commit_patch_ids != expected_patch_ids:
            raise PreflightError(
                "Embench checkout commits do not match declared series patch-id order"
            )

    return {
        "mode": source_mode,
        "repository": component["repository"],
        "pin": pin,
        "head": head,
        "tree": git_tree(source),
        "series": {
            **file_identity(series_path),
            "entries": patch_records,
        },
        "commits": commits,
        "commit_patch_ids": commit_patch_ids,
    }


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    if len(INVENTORY) != 19 or len(set(INVENTORY)) != 19:
        raise PreflightError("hard-coded benchmark inventory is not exactly 19")

    source = args.source.resolve()
    component, series_path, patches = load_component("embench")
    checkout = check_component_checkout(
        source, component, series_path, patches, args.source_mode
    )

    src_root = source / "src"
    discovered = sorted(path.name for path in src_root.iterdir() if path.is_dir())
    if discovered != sorted(INVENTORY):
        missing = sorted(set(INVENTORY) - set(discovered))
        extra = sorted(set(discovered) - set(INVENTORY))
        raise PreflightError(
            f"Embench inventory mismatch: missing={missing}, extra={extra}"
        )

    required = {
        "clang": args.clang,
        "ld.lld": args.lld,
        "llvm-objcopy": args.objcopy,
        "qemu": args.qemu,
        "gem5": args.gem5,
        "gem5_se": args.gem5_se,
        "trampoline": ROOT / "tests/scripts/trampoline.bin",
        "linker_script": ROOT / "tests/scripts/dadao.ld",
        "crt1": args.musl_build / "lib/crt1.o",
        "libc": args.musl_build / "lib/libc.a",
        "board_glue": ROOT / "tests/embench/boardsupport.c",
        "support_main": source / "support/main.c",
        "support_beebsc": source / "support/beebsc.c",
        "sweep_script": Path(__file__).resolve(),
    }
    missing = [f"{name}={rel(path)}" for name, path in required.items() if not path.is_file()]
    if missing:
        raise PreflightError("missing required tools/artifacts: " + ", ".join(missing))
    for name in ("clang", "ld.lld", "llvm-objcopy", "qemu", "gem5"):
        if not os.access(required[name], os.X_OK):
            raise PreflightError(f"required tool is not executable: {name}")

    include_dirs = (
        args.musl_source / "arch/dadao",
        args.musl_source / "arch/generic",
        args.musl_source / "include",
        args.musl_build / "obj/include",
        source / "support",
    )
    missing_includes = [rel(path) for path in include_dirs if not path.is_dir()]
    if missing_includes:
        raise PreflightError(
            "missing include directories: " + ", ".join(missing_includes)
        )

    source_heads = {}
    for name, path in (
        ("embench", source),
        ("llvm", ROOT / ".work/source/llvm"),
        ("qemu", ROOT / ".work/source/qemu"),
        ("gem5", ROOT / ".work/source/gem5"),
        ("musl", ROOT / ".work/source/musl"),
    ):
        source_heads[name] = git_head(path)

    files = {
        name: file_identity(required[name])
        for name in (
            "sweep_script",
            "board_glue",
            "linker_script",
            "trampoline",
            "gem5_se",
            "support_main",
            "support_beebsc",
        )
    }
    tools = {
        name: tool_identity(required[name])
        for name in ("clang", "ld.lld", "llvm-objcopy", "qemu", "gem5")
    }
    musl = {
        "source_head": source_heads["musl"],
        "crt1": file_identity(required["crt1"]),
        "libc": file_identity(required["libc"]),
        "include_directories": [
            directory_identity(path) for path in include_dirs
        ],
    }
    contracts = {
        "compile": {
            "target": "dadao",
            "standard": "c99",
            "flags": ["-nostdinc"],
            "optimizations": list(OPTIMIZATIONS),
            "defines": ["WARMUP_HEAT=0", "GLOBAL_SCALE_FACTOR=1"],
            "separate_translation_units": True,
        },
        "link": {
            "script": files["linker_script"],
            "static_musl": True,
            "group_archives": True,
        },
        "qemu": {
            "machine": "dadao-m1",
            "arguments": ["-nographic", "-bios", "<trampoline>", "-kernel", "<binary>"],
        },
        "gem5": {
            "arguments": ["<gem5-se>", "<elf>"],
        },
        "timeouts_seconds": {
            "compile": args.compile_timeout,
            "link_and_objcopy": args.link_timeout,
            "qemu": args.qemu_timeout,
            "gem5": args.gem5_timeout,
        },
    }
    identity = {
        "fingerprint_version": FINGERPRINT_VERSION,
        "result_schema_version": SCHEMA_VERSION,
        "inventory": list(INVENTORY),
        "optimizations": list(OPTIMIZATIONS),
        "component": checkout,
        "source_heads": source_heads,
        "files": files,
        "tools": tools,
        "musl": musl,
        "contracts": contracts,
        "output": {
            "source": rel(args.source),
            "out": rel(args.out),
            "json": rel(args.json_path),
        },
    }
    fingerprint = {
        "algorithm": "sha256",
        "digest": canonical_digest(identity),
        "identity": identity,
    }
    return {
        "component": {
            "repository": component["repository"],
            "pin": component["commit"],
            "head": source_heads["embench"],
            "tree": checkout["tree"],
            "source_mode": args.source_mode,
            "patch_series": rel(series_path),
            "patches": patches,
            "series_sha256": checkout["series"]["sha256"],
            "patch_identities": checkout["series"]["entries"],
            "commit_patch_ids": checkout["commit_patch_ids"],
        },
        "source_heads": source_heads,
        "tools": tools,
        "musl": musl,
        "execution_fingerprint": fingerprint,
        "paths": {
            "gem5_se": rel(args.gem5_se),
            "musl_crt1": rel(required["crt1"]),
            "musl_libc": rel(required["libc"]),
            "trampoline": rel(required["trampoline"]),
            "linker_script": rel(required["linker_script"]),
            "board_glue": rel(required["board_glue"]),
        },
    }


def not_run(reason: str) -> dict[str, Any]:
    return {
        "attempted": False,
        "timed_out": False,
        "returncode": None,
        "state": "NOT_RUN",
        "reason": reason,
    }


def source_files(source: Path, benchmark: str) -> list[Path]:
    benchmark_sources = sorted((source / "src" / benchmark).glob("*.c"))
    if not benchmark_sources:
        raise PreflightError(f"{benchmark}: zero benchmark source files")
    return [
        source / "support/main.c",
        source / "support/beebsc.c",
        ROOT / "tests/embench/boardsupport.c",
        *benchmark_sources,
    ]


def compile_benchmark(
    args: argparse.Namespace, optimization: str, benchmark: str, build_dir: Path
) -> tuple[list[Path] | None, list[dict[str, Any]], dict[str, Any] | None]:
    objects = []
    records = []
    for index, source_file in enumerate(source_files(args.source, benchmark)):
        obj = build_dir / f"{index:02d}-{source_file.stem}.o"
        command = [
            str(args.clang),
            "--target=dadao",
            "-std=c99",
            "-nostdinc",
            f"-{optimization}",
            "-DWARMUP_HEAT=0",
            "-DGLOBAL_SCALE_FACTOR=1",
            "-I",
            str(args.musl_source / "arch/dadao"),
            "-I",
            str(args.musl_source / "arch/generic"),
            "-I",
            str(args.musl_source / "include"),
            "-I",
            str(args.musl_build / "obj/include"),
            "-I",
            str(args.source / "support"),
            "-I",
            str(args.source / "src" / benchmark),
            "-c",
            str(source_file),
            "-o",
            str(obj),
        ]
        log_path = build_dir / f"compile-{index:02d}-{source_file.stem}.log"
        run = run_command(command, args.compile_timeout, log_path)
        record = {
            "source": rel(source_file),
            "object": None,
            "run": run,
        }
        records.append(record)
        if run["timed_out"] or run["returncode"] != 0:
            return None, records, {
                "failed_source": rel(source_file),
                "timed_out": run["timed_out"],
                "returncode": run["returncode"],
            }
        record["object"] = file_identity(obj)
        objects.append(obj)
    return objects, records, None


def sweep_one(
    args: argparse.Namespace, optimization: str, benchmark: str, opt_dir: Path
) -> dict[str, Any]:
    build_dir = opt_dir / benchmark
    build_dir.mkdir(parents=True)
    result: dict[str, Any] = {
        "benchmark": benchmark,
        "optimization": optimization,
        "status": None,
        "build": {},
        "qemu": not_run("build not completed"),
        "gem5": not_run("build not completed"),
    }

    objects, compile_records, failure = compile_benchmark(
        args, optimization, benchmark, build_dir
    )
    if failure:
        result["status"] = "FAIL_COMPILE"
        result["build"] = {
            "stage": "compile",
            "compile": compile_records,
            **failure,
        }
        return result

    elf = build_dir / f"{benchmark}.elf"
    binary = build_dir / f"{benchmark}.bin"
    link_command = [
        str(args.lld),
        "-T",
        str(ROOT / "tests/scripts/dadao.ld"),
        "--start-group",
        str(args.musl_build / "lib/crt1.o"),
        *(str(obj) for obj in objects),
        str(args.musl_build / "lib/libc.a"),
        "--end-group",
        "-o",
        str(elf),
    ]
    link = run_command(link_command, args.link_timeout, build_dir / "link.log")
    result["build"] = {
        "stage": "link",
        "compile_objects": len(objects),
        "compile": compile_records,
        "link": link,
    }
    if link["timed_out"] or link["returncode"] != 0:
        result["status"] = "FAIL_LINK"
        result["qemu"] = not_run("link failed")
        result["gem5"] = not_run("link failed")
        return result

    objcopy_command = [
        str(args.objcopy),
        "-O",
        "binary",
        str(elf),
        str(binary),
    ]
    objcopy = run_command(
        objcopy_command, args.link_timeout, build_dir / "objcopy.log"
    )
    result["build"]["objcopy"] = objcopy
    if objcopy["timed_out"] or objcopy["returncode"] != 0:
        result["status"] = "FAIL_LINK"
        result["build"]["stage"] = "objcopy"
        result["qemu"] = not_run("objcopy failed")
        result["gem5"] = not_run("objcopy failed")
        return result
    result["build"]["elf"] = file_identity(elf)
    result["build"]["binary"] = file_identity(binary)

    qemu_command = [
        str(args.qemu),
        "-M",
        "dadao-m1",
        "-nographic",
        "-bios",
        str(ROOT / "tests/scripts/trampoline.bin"),
        "-kernel",
        str(binary),
    ]
    qemu = run_command(qemu_command, args.qemu_timeout, build_dir / "qemu.log")
    qemu["state"] = (
        "TIMEOUT"
        if qemu["timed_out"]
        else ("PASS" if qemu["returncode"] == 0 else "FAIL")
    )
    result["qemu"] = qemu

    gem5_command = [str(args.gem5), str(args.gem5_se), str(elf)]
    gem5 = run_command(gem5_command, args.gem5_timeout, build_dir / "gem5.log")
    gem5["state"] = (
        "TIMEOUT"
        if gem5["timed_out"]
        else ("PASS" if gem5["returncode"] == 0 else "FAIL")
    )
    result["gem5"] = gem5

    if qemu["timed_out"]:
        result["status"] = "TIMEOUT_QEMU"
    elif qemu["returncode"] != 0:
        result["status"] = "FAIL_QEMU"
    elif gem5["timed_out"]:
        result["status"] = "TIMEOUT_GEM5"
    elif gem5["returncode"] != 0:
        result["status"] = "FAIL_GEM5"
    else:
        result["status"] = "PASS"
    return result


def summarize(results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    summary = {}
    for optimization in OPTIMIZATIONS:
        selected = [
            result
            for result in results
            if result.get("optimization") == optimization
        ]
        primary_counts = Counter(
            result["status"]
            for result in selected
        )
        summary[optimization] = {
            "total": len(selected),
            "primary_status": {
                status: primary_counts.get(status, 0)
                for status in sorted(FINAL_STATUSES)
            },
            "backends": {
                backend: {
                    state: sum(
                        result.get(backend, {}).get("state") == state
                        for result in selected
                    )
                    for state in BACKEND_STATES
                }
                for backend in ("qemu", "gem5")
            },
        }
    return summary


def recorded_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def validate_file_record(record: Any, context: str) -> list[str]:
    if not isinstance(record, dict):
        return [f"{context}: missing file identity"]
    path_value = record.get("path")
    if not isinstance(path_value, str):
        return [f"{context}: invalid path"]
    path = recorded_path(path_value)
    if not path.is_file():
        return [f"{context}: referenced file is missing: {path_value}"]
    errors = []
    if record.get("size") != path.stat().st_size:
        errors.append(f"{context}: size drift for {path_value}")
    if record.get("sha256") != sha256(path):
        errors.append(f"{context}: sha256 drift for {path_value}")
    return errors


def validate_run_evidence(run: Any, context: str) -> list[str]:
    if not isinstance(run, dict):
        return [f"{context}: missing run record"]
    errors = []
    if run.get("attempted") is not True:
        errors.append(f"{context}: run was not attempted")
        return errors
    timed_out = run.get("timed_out")
    returncode = run.get("returncode")
    command = run.get("command")
    if not isinstance(timed_out, bool):
        errors.append(f"{context}: timed_out is not boolean")
    if timed_out and returncode is not None:
        errors.append(f"{context}: timeout must have null returncode")
    if not timed_out and not isinstance(returncode, int):
        errors.append(f"{context}: non-timeout run must have integer returncode")
    if not isinstance(command, list) or not all(
        isinstance(item, str) for item in command
    ):
        errors.append(f"{context}: invalid command")
    log_value = run.get("log")
    if not isinstance(log_value, str):
        errors.append(f"{context}: invalid log path")
        return errors
    log_path = recorded_path(log_value)
    if not log_path.is_file():
        errors.append(f"{context}: referenced log is missing: {log_value}")
        return errors
    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not lines or not lines[-1].startswith(LOG_RECORD_PREFIX):
        errors.append(f"{context}: log lacks machine-readable exit record")
        return errors
    try:
        footer = json.loads(lines[-1][len(LOG_RECORD_PREFIX):])
    except json.JSONDecodeError:
        errors.append(f"{context}: malformed log exit record")
        return errors
    expected = {
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
    }
    if footer != expected:
        errors.append(f"{context}: log exit record disagrees with JSON")
    return errors


def validate_backend(backend: Any, context: str) -> list[str]:
    if not isinstance(backend, dict):
        return [f"{context}: missing backend record"]
    errors = []
    attempted = backend.get("attempted")
    state = backend.get("state")
    timed_out = backend.get("timed_out")
    returncode = backend.get("returncode")
    if attempted is False:
        if state != "NOT_RUN" or timed_out is not False or returncode is not None:
            errors.append(
                f"{context}: NOT_RUN requires attempted=false, "
                "timed_out=false, returncode=null"
            )
        return errors
    if attempted is not True:
        return [f"{context}: attempted is not boolean"]
    errors.extend(validate_run_evidence(backend, context))
    expected_state = (
        "TIMEOUT"
        if timed_out
        else ("PASS" if returncode == 0 else "FAIL")
    )
    if state != expected_state:
        errors.append(
            f"{context}: state={state!r}, expected {expected_state!r}"
        )
    return errors


def derive_primary_status(result: dict[str, Any]) -> str | None:
    qemu = result.get("qemu", {})
    gem5 = result.get("gem5", {})
    if qemu.get("state") == "NOT_RUN" and gem5.get("state") == "NOT_RUN":
        stage = result.get("build", {}).get("stage")
        if stage == "compile":
            return "FAIL_COMPILE"
        if stage in ("link", "objcopy"):
            return "FAIL_LINK"
        return None
    if qemu.get("attempted") is not True or gem5.get("attempted") is not True:
        return None
    if qemu.get("state") == "TIMEOUT":
        return "TIMEOUT_QEMU"
    if qemu.get("state") == "FAIL":
        return "FAIL_QEMU"
    if gem5.get("state") == "TIMEOUT":
        return "TIMEOUT_GEM5"
    if gem5.get("state") == "FAIL":
        return "FAIL_GEM5"
    if qemu.get("state") == "PASS" and gem5.get("state") == "PASS":
        return "PASS"
    return None


def validate_result_evidence(result: dict[str, Any], context: str) -> list[str]:
    errors = []
    build = result.get("build")
    if not isinstance(build, dict):
        return [f"{context}: missing build record"]
    compile_records = build.get("compile")
    if not isinstance(compile_records, list) or not compile_records:
        errors.append(f"{context}: missing compile evidence")
    else:
        for index, record in enumerate(compile_records):
            item_context = f"{context}/compile[{index}]"
            if not isinstance(record, dict):
                errors.append(f"{item_context}: invalid record")
                continue
            source = record.get("source")
            if not isinstance(source, str) or not recorded_path(source).is_file():
                errors.append(f"{item_context}: source path is missing")
            run = record.get("run")
            errors.extend(validate_run_evidence(run, item_context))
            if (
                isinstance(run, dict)
                and not run.get("timed_out")
                and run.get("returncode") == 0
            ):
                errors.extend(
                    validate_file_record(
                        record.get("object"), f"{item_context}/object"
                    )
                )

    stage = build.get("stage")
    if stage in ("link", "objcopy") and "link" in build:
        errors.extend(validate_run_evidence(build["link"], f"{context}/link"))
    if stage == "objcopy" or "objcopy" in build:
        errors.extend(
            validate_run_evidence(build.get("objcopy"), f"{context}/objcopy")
        )
    if result.get("qemu", {}).get("attempted") is True:
        errors.extend(validate_file_record(build.get("elf"), f"{context}/elf"))
        errors.extend(
            validate_file_record(build.get("binary"), f"{context}/binary")
        )
    return errors


def validate_results(
    results: Any, *, require_complete: bool, verify_evidence: bool
) -> list[str]:
    errors = []
    if not isinstance(results, list):
        return ["results is not a list"]
    expected = {
        (optimization, benchmark)
        for optimization in OPTIMIZATIONS
        for benchmark in INVENTORY
    }
    keys = [
        (result.get("optimization"), result.get("benchmark"))
        for result in results
        if isinstance(result, dict)
    ]
    actual = set(keys)
    if len(keys) != len(results):
        errors.append("one or more results are not objects")
    if len(actual) != len(keys):
        errors.append("result matrix contains duplicate keys")
    if not actual.issubset(expected):
        errors.append("result matrix contains unexpected keys")
    if require_complete and (actual != expected or len(results) != len(expected)):
        errors.append(
            f"result matrix incomplete: expected={len(expected)} actual={len(results)}"
        )
    invalid = [
        f"{result.get('optimization')}/{result.get('benchmark')}={result.get('status')}"
        for result in results
        if isinstance(result, dict)
        and result.get("status") not in FINAL_STATUSES
    ]
    if invalid:
        errors.append("invalid statuses: " + ", ".join(invalid))
    for result in results:
        if not isinstance(result, dict):
            continue
        context = (
            f"{result.get('optimization')}/{result.get('benchmark')}"
        )
        errors.extend(validate_backend(result.get("qemu"), f"{context}/qemu"))
        errors.extend(validate_backend(result.get("gem5"), f"{context}/gem5"))
        expected_status = derive_primary_status(result)
        if result.get("status") != expected_status:
            errors.append(
                f"{context}: primary status {result.get('status')!r} "
                f"does not match backend/build evidence {expected_status!r}"
            )
        if verify_evidence:
            errors.extend(validate_result_evidence(result, context))
    for optimization in OPTIMIZATIONS:
        count = sum(
            isinstance(result, dict)
            and result.get("optimization") == optimization
            for result in results
        )
        if require_complete and count != 19:
            errors.append(f"{optimization} result count is {count}, expected 19")
        if not require_complete and count > 19:
            errors.append(f"{optimization} result count exceeds 19")
    return errors


def diagnosis(result: dict[str, Any]) -> str:
    status = result["status"]
    if status == "PASS":
        return "verify_benchmark true on both backends"
    if status == "FAIL_COMPILE":
        build = result["build"]
        records = build.get("compile", [])
        run = records[-1].get("run", {}) if records else {}
        timeout = " timeout" if run.get("timed_out") else ""
        return (
            f"compile{timeout}: {build.get('failed_source')}, "
            f"rc={run.get('returncode')}"
        )
    if status == "FAIL_LINK":
        build = result["build"]
        stage = build.get("stage", "link")
        run = build.get(stage, build.get("link", {}))
        return f"{stage}: rc={run.get('returncode')}"
    qemu = result["qemu"]
    gem5 = result["gem5"]
    if status == "TIMEOUT_QEMU":
        return f"QEMU exceeded {qemu.get('elapsed_seconds')}s"
    if status == "TIMEOUT_GEM5":
        return f"gem5 exceeded {gem5.get('elapsed_seconds')}s"
    if status == "FAIL_QEMU":
        code = qemu.get("returncode")
        detail = FAULT_CODES.get(code, "nonzero verify/runtime exit")
        return f"QEMU rc={code} ({detail}); gem5 rc={gem5.get('returncode')}"
    if status == "FAIL_GEM5":
        code = gem5.get("returncode")
        detail = FAULT_CODES.get(code, "nonzero verify/runtime exit")
        return f"gem5 rc={code} ({detail}); QEMU rc={qemu.get('returncode')}"
    return "unclassified"


def backend_cell(backend: dict[str, Any]) -> str:
    state = backend.get("state", "NOT_RUN")
    if state == "TIMEOUT":
        return f"TIMEOUT ({backend.get('elapsed_seconds')}s)"
    if state == "NOT_RUN":
        return f"NOT_RUN ({backend.get('reason', 'prior stage failed')})"
    return f"{state} (rc={backend.get('returncode')})"


def render_report(payload: dict[str, Any], path: Path) -> None:
    metadata = payload.get("metadata", {})
    lines = [
        "# ML-032a: Embench-IoT 19 项功能测试报告",
        "",
        f"生成时间（UTC）：`{metadata.get('finished_at', utc_now())}`。",
        "",
        "## 范围与判定契约",
        "",
        "本报告只陈述锁定 Embench source、当前 DADAO 工具链和两个功能模型下的"
        " correctness 结果，不是 Embench speed/size 分数，也不是跨后端或硬件性能结论。",
        "`WARMUP_HEAT=0`、`GLOBAL_SCALE_FACTOR=1`；每项仍执行一次 `benchmark()`，"
        "随后由 upstream `verify_benchmark()` 判定，`support/main.c` 仅在验证为真时返回 0。",
        "",
        "每个源文件、`support/main.c`、`support/beebsc.c` 与项目内"
        " `tests/embench/boardsupport.c` 分别编译；随后以项目 musl"
        " `crt1.o`/`libc.a` 静态链接。同一 ELF 交给 gem5 SE，objcopy 后 flat binary"
        " 交给 QEMU `dadao-m1`。工具缺失、未运行、超时和任一非零退出均不会计为 PASS。",
        "",
        "## 锁定输入与工具",
        "",
        "| 项 | 身份 |",
        "|---|---|",
    ]
    component = metadata.get("component", {})
    lines.append(
        f"| Embench | `{component.get('repository')}` @ `{component.get('head')}`; "
        f"pin `{component.get('pin')}`; tree `{component.get('tree')}`; "
        f"mode `{component.get('source_mode')}`; "
        f"patches `{len(component.get('patches', []))}` |"
    )
    for name, head in metadata.get("source_heads", {}).items():
        if name != "embench":
            lines.append(f"| {name} source HEAD | `{head}` |")
    for name, identity in metadata.get("tools", {}).items():
        lines.append(
            f"| {name} | `{identity.get('path')}`; sha256 `{identity.get('sha256')}` |"
        )
    for name, value in metadata.get("paths", {}).items():
        lines.append(f"| {name} | `{value}` |")
    fingerprint = metadata.get("execution_fingerprint", {})
    lines.append(
        f"| execution fingerprint | `{fingerprint.get('digest')}` "
        f"({fingerprint.get('algorithm')}) |"
    )
    musl = metadata.get("musl", {})
    for name in ("crt1", "libc"):
        identity = musl.get(name, {})
        lines.append(
            f"| musl {name} | `{identity.get('path')}`; "
            f"sha256 `{identity.get('sha256')}` |"
        )

    patches = component.get("patches", [])
    lines.append(
        f"- series sha256：`{component.get('series_sha256')}`；"
        f"checkout commit patch-id：`{component.get('commit_patch_ids', [])}`。"
    )
    lines.extend(["", "## 组件 patch series", ""])
    if patches:
        for patch in patches:
            lines.append(f"- `{patch}`")
            if patch == "0001-md5sum-decode-message-words-as-little-endian.patch":
                lines.extend(
                    [
                        "  - 将消息 bit length 从 host-native `memcpy` 改为 4 个"
                        "显式 little-endian byte store。",
                        "  - 将消息块的 native `uint32_t *` load 改为 16 个"
                        "显式 little-endian word decode。",
                        "  - benchmark 输入、算法轮次与 `RESULT` 均未修改。",
                    ]
                )
    else:
        lines.append("- 空 series；运行 pinned upstream 原始 source。")

    lines.extend(["", "## 执行命令", ""])
    lines.append(
        f"`{metadata.get('invocation', 'python3 tests/scripts/embench_sweep.py')}`"
    )
    timeouts = metadata.get("timeouts_seconds", {})
    lines.extend(
        [
            "",
            "编译契约：`clang --target=dadao -std=c99 -nostdinc "
            "-O{0,2} -DWARMUP_HEAT=0 -DGLOBAL_SCALE_FACTOR=1` 加 musl/support/"
            "benchmark include；链接契约：`ld.lld -T tests/scripts/dadao.ld "
            "--start-group crt1.o <objects> libc.a --end-group`。",
            "",
            "每项有界 timeout（秒）："
            f"compile `{timeouts.get('compile')}`、link/objcopy "
            f"`{timeouts.get('link')}`、QEMU `{timeouts.get('qemu')}`、"
            f"gem5 `{timeouts.get('gem5')}`。每完成一项即写 JSON/Markdown"
            " checkpoint；中断中的项目不会记录为 PASS。",
            "",
            "## 汇总",
            "",
            "下表统计 QEMU 优先的 primary status；它用于保持单一总状态，"
            "不是后端失败计数。",
            "",
            "| 优化 | PRIMARY_PASS | PRIMARY_FAIL_COMPILE | PRIMARY_FAIL_LINK | "
            "PRIMARY_FAIL_QEMU | PRIMARY_FAIL_GEM5 | PRIMARY_TIMEOUT_QEMU | "
            "PRIMARY_TIMEOUT_GEM5 | TOTAL |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for optimization in OPTIMIZATIONS:
        summary = payload.get("summary", {}).get(optimization, {})
        primary = summary.get("primary_status", {})
        lines.append(
            f"| -{optimization} | {primary.get('PASS', 0)} | "
            f"{primary.get('FAIL_COMPILE', 0)} | "
            f"{primary.get('FAIL_LINK', 0)} | "
            f"{primary.get('FAIL_QEMU', 0)} | "
            f"{primary.get('FAIL_GEM5', 0)} | "
            f"{primary.get('TIMEOUT_QEMU', 0)} | "
            f"{primary.get('TIMEOUT_GEM5', 0)} | "
            f"{summary.get('total', 0)} |"
        )

    lines.extend(
        [
            "",
            "### 独立 backend 汇总",
            "",
            "| 优化 | backend | PASS | FAIL | TIMEOUT | NOT_RUN | TOTAL |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
    )
    for optimization in OPTIMIZATIONS:
        summary = payload.get("summary", {}).get(optimization, {})
        for backend in ("qemu", "gem5"):
            counts = summary.get("backends", {}).get(backend, {})
            total = sum(counts.get(state, 0) for state in BACKEND_STATES)
            lines.append(
                f"| -{optimization} | {backend} | "
                f"{counts.get('PASS', 0)} | {counts.get('FAIL', 0)} | "
                f"{counts.get('TIMEOUT', 0)} | "
                f"{counts.get('NOT_RUN', 0)} | {total} |"
            )

    lines.extend(
        [
            "",
            "## 逐项结果",
            "",
            "| 优化 | benchmark | primary status（QEMU 优先） | QEMU | gem5 | 初步诊断 |",
            "|---|---|---|---|---|---|",
        ]
    )
    for result in payload.get("results", []):
        lines.append(
            f"| -{result['optimization']} | `{result['benchmark']}` | "
            f"{result['status']} | {backend_cell(result['qemu'])} | "
            f"{backend_cell(result['gem5'])} | {diagnosis(result)} |"
        )

    validation_errors = payload.get("validation_errors", [])
    fatal_errors = payload.get("fatal_errors", [])
    failures = [
        result for result in payload.get("results", []) if result["status"] != "PASS"
    ]
    lines.extend(["", "## 失败与遗留风险", ""])
    if fatal_errors:
        for error in fatal_errors:
            lines.append(f"- FATAL: {error}")
    if validation_errors:
        for error in validation_errors:
            lines.append(f"- RESULT_VALIDATION: {error}")
    if failures:
        for result in failures:
            lines.append(
                f"- `-{result['optimization']} {result['benchmark']}`: "
                f"{result['status']} — {diagnosis(result)}。详细日志见 JSON 中路径。"
            )
    if not fatal_errors and not validation_errors and not failures:
        lines.append(
            "- 无功能失败。结论严格限于当前 pin、当前构建产物和当前功能模型；"
            "本 sweep 不覆盖性能、时序、并发、动态链接或完整 libc 能力。"
        )
    lines.append(
        "- 上游 pin 的 `xgboost/verify_benchmark()` 使用"
        " `SAMPLES_IN_FILE * (LOCAL_SCALE_FACTOR, GLOBAL_SCALE_FACTOR / 12)`；"
        "在本任务规定的 `GLOBAL_SCALE_FACTOR=1` 下阈值为 0。故 xgboost 的 PASS"
        " 只证明 body 已执行且 upstream verifier 返回真，不能单独证明预测准确率；"
        "本任务未修改 verifier/expected value。"
    )
    lines.extend(
        [
            "",
            f"机器可读证据：`{metadata.get('json_path', '')}`；产物与日志目录"
            f" `{metadata.get('execution_fingerprint', {}).get('identity', {}).get('output', {}).get('out', '')}`"
            "（不提交大产物）。",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_checkpoint(
    payload: dict[str, Any],
    json_path: Path,
    report_path: Path | None,
    *,
    require_complete: bool,
) -> None:
    payload["summary"] = summarize(payload["results"])
    payload["validation_errors"] = validate_results(
        payload["results"],
        require_complete=require_complete,
        verify_evidence=True,
    )
    payload["metadata"]["updated_at"] = utc_now()
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    if report_path:
        render_report(payload, report_path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source", type=Path, default=ROOT / ".work/source/embench"
    )
    parser.add_argument(
        "--out", type=Path, default=ROOT / ".work/embench-sweep"
    )
    parser.add_argument("--json", type=Path, default=None)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="keep checkpointed results/artifacts and run only missing matrix entries",
    )
    parser.add_argument(
        "--source-mode",
        choices=("patched", "unpatched"),
        default="patched",
        help="validate manifest pin+series (patched) or exact pin (unpatched)",
    )
    parser.add_argument(
        "--clang", type=Path, default=ROOT / ".work/build/llvm/bin/clang"
    )
    parser.add_argument(
        "--lld", type=Path, default=ROOT / ".work/build/llvm/bin/ld.lld"
    )
    parser.add_argument(
        "--objcopy",
        type=Path,
        default=ROOT / ".work/build/llvm/bin/llvm-objcopy",
    )
    parser.add_argument(
        "--qemu",
        type=Path,
        default=ROOT / ".work/source/qemu/build/qemu-system-dadao",
    )
    parser.add_argument(
        "--gem5",
        type=Path,
        default=ROOT / ".work/source/gem5/build/DADAO/gem5.opt",
    )
    parser.add_argument(
        "--gem5-se",
        type=Path,
        default=ROOT / ".work/source/gem5/tests/dadao/dadao_se.py",
    )
    parser.add_argument(
        "--musl-source", type=Path, default=ROOT / ".work/source/musl"
    )
    parser.add_argument(
        "--musl-build", type=Path, default=ROOT / ".work/build/musl"
    )
    parser.add_argument("--compile-timeout", type=float, default=120.0)
    parser.add_argument("--link-timeout", type=float, default=60.0)
    parser.add_argument("--qemu-timeout", type=float, default=60.0)
    parser.add_argument("--gem5-timeout", type=float, default=180.0)
    return parser.parse_args()


def resume_validation_errors(
    payload: Any,
    current_fingerprint: dict[str, Any],
    json_path: Path,
) -> list[str]:
    if not isinstance(payload, dict):
        return ["checkpoint root is not an object"]
    errors = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        errors.append(
            f"checkpoint schema={payload.get('schema_version')!r}, "
            f"expected {SCHEMA_VERSION}"
        )
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        return [*errors, "checkpoint metadata is missing"]
    stored = metadata.get("execution_fingerprint")
    if not isinstance(stored, dict):
        errors.append("checkpoint execution fingerprint is missing")
    else:
        identity = stored.get("identity")
        digest = stored.get("digest")
        if not isinstance(identity, dict) or not isinstance(digest, str):
            errors.append("checkpoint execution fingerprint is malformed")
        elif canonical_digest(identity) != digest:
            errors.append("checkpoint execution fingerprint digest is corrupt")
        if stored != current_fingerprint:
            errors.append(
                "execution fingerprint drift: "
                f"stored={stored.get('digest')} "
                f"current={current_fingerprint.get('digest')}"
            )
    if metadata.get("json_path") != rel(json_path):
        errors.append(
            "checkpoint json_path does not match requested JSON path"
        )
    if errors:
        return errors
    results = payload.get("results")
    errors.extend(
        validate_results(
            results,
            require_complete=False,
            verify_evidence=True,
        )
    )
    if isinstance(results, list) and payload.get("summary") != summarize(results):
        errors.append("checkpoint summary disagrees with result records")
    return errors


def main() -> int:
    args = parse_args()
    args.source = args.source.resolve()
    args.out = args.out.resolve()
    # Do not resolve executable symlinks: ld.lld selects its driver mode from
    # argv[0], while its resolved target is the generic `lld` multiplexer.
    args.clang = args.clang.absolute()
    args.lld = args.lld.absolute()
    args.objcopy = args.objcopy.absolute()
    args.qemu = args.qemu.absolute()
    args.gem5 = args.gem5.absolute()
    args.gem5_se = args.gem5_se.resolve()
    args.musl_source = args.musl_source.resolve()
    args.musl_build = args.musl_build.resolve()
    json_path = (args.json or (args.out / "results.json")).resolve()
    args.json_path = json_path
    report_path = args.report.resolve() if args.report else None
    invocation = command_text([sys.executable, *sys.argv])

    try:
        current_metadata = preflight(args)
    except (PreflightError, OSError, subprocess.SubprocessError, ValueError) as exc:
        if args.resume:
            print(
                f"resume refused before checkpoint write: {exc}",
                file=sys.stderr,
            )
            return 2
        payload = {
            "schema_version": SCHEMA_VERSION,
            "metadata": {
                "started_at": utc_now(),
                "invocation": invocation,
                "json_path": rel(json_path),
                "inventory": list(INVENTORY),
                "optimizations": list(OPTIMIZATIONS),
                "timeouts_seconds": {
                    "compile": args.compile_timeout,
                    "link": args.link_timeout,
                    "qemu": args.qemu_timeout,
                    "gem5": args.gem5_timeout,
                },
            },
            "results": [],
            "summary": {},
            "fatal_errors": [],
            "validation_errors": [],
        }
        payload["fatal_errors"].append(str(exc))
        args.out.mkdir(parents=True, exist_ok=True)
        payload["metadata"]["finished_at"] = utc_now()
        write_checkpoint(
            payload,
            json_path,
            report_path,
            require_complete=True,
        )
        return 1

    if args.resume:
        if not json_path.is_file():
            print(
                f"resume refused: checkpoint does not exist: {json_path}",
                file=sys.stderr,
            )
            return 2
        try:
            payload = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(
                f"resume refused: cannot read checkpoint: {exc}",
                file=sys.stderr,
            )
            return 2
        resume_errors = resume_validation_errors(
            payload,
            current_metadata["execution_fingerprint"],
            json_path,
        )
        if resume_errors:
            print("resume refused; checkpoint was not modified:", file=sys.stderr)
            for error in resume_errors:
                print(f"  - {error}", file=sys.stderr)
            return 2
        history = payload["metadata"].setdefault("resume_history", [])
        history.append(
            {
                "at": utc_now(),
                "invocation": invocation,
                "fingerprint": current_metadata["execution_fingerprint"]["digest"],
                "reused_results": len(payload["results"]),
                "prior_fatal_errors": payload.get("fatal_errors", []),
            }
        )
        payload["fatal_errors"] = []
        payload["validation_errors"] = []
        complete_resume = len(payload["results"]) == (
            len(INVENTORY) * len(OPTIMIZATIONS)
        )
    else:
        complete_resume = False
        payload = {
            "schema_version": SCHEMA_VERSION,
            "metadata": {
                "started_at": utc_now(),
                "invocation": invocation,
                "json_path": rel(json_path),
                "inventory": list(INVENTORY),
                "optimizations": list(OPTIMIZATIONS),
                "timeouts_seconds": {
                    "compile": args.compile_timeout,
                    "link": args.link_timeout,
                    "qemu": args.qemu_timeout,
                    "gem5": args.gem5_timeout,
                },
                **current_metadata,
            },
            "results": [],
            "summary": {},
            "fatal_errors": [],
            "validation_errors": [],
        }

    args.out.mkdir(parents=True, exist_ok=True)
    interrupted = False
    try:
        completed = {
            (result["optimization"], result["benchmark"])
            for result in payload["results"]
        }
        for optimization in OPTIMIZATIONS:
            opt_dir = args.out / optimization
            if opt_dir.exists() and not args.resume:
                shutil.rmtree(opt_dir)
            opt_dir.mkdir(parents=True, exist_ok=True)
            for index, benchmark in enumerate(INVENTORY, start=1):
                if (optimization, benchmark) in completed:
                    print(
                        f"[{optimization} {index:02d}/19] {benchmark}: "
                        "checkpoint exists",
                        file=sys.stderr,
                        flush=True,
                    )
                    continue
                build_dir = opt_dir / benchmark
                if build_dir.exists():
                    suffix = datetime.now().strftime("%Y%m%d-%H%M%S")
                    preserved = opt_dir / f"{benchmark}.interrupted-{suffix}"
                    build_dir.rename(preserved)
                    print(
                        f"  preserved interrupted artifacts as {preserved}",
                        file=sys.stderr,
                        flush=True,
                    )
                print(
                    f"[{optimization} {index:02d}/19] {benchmark}",
                    file=sys.stderr,
                    flush=True,
                )
                result = sweep_one(
                    args, optimization, benchmark, opt_dir
                )
                payload["results"].append(result)
                print(
                    f"  {result['status']} "
                    f"(qemu={result['qemu'].get('state')}, "
                    f"gem5={result['gem5'].get('state')})",
                    file=sys.stderr,
                    flush=True,
                )
                write_checkpoint(
                    payload,
                    json_path,
                    report_path,
                    require_complete=False,
                )
    except (PreflightError, OSError, subprocess.SubprocessError, ValueError) as exc:
        payload["fatal_errors"].append(str(exc))
    except KeyboardInterrupt:
        interrupted = True
        payload["fatal_errors"].append(
            "sweep interrupted; in-flight entry is not recorded as PASS"
        )

    if args.resume:
        payload["metadata"]["last_resume_finished_at"] = utc_now()
    else:
        payload["metadata"]["finished_at"] = utc_now()
    write_checkpoint(
        payload,
        json_path,
        # A complete resume is evidence validation/reuse only.  Do not
        # regenerate an existing report: the durable ML-032a report may have
        # hand-reviewed appendices that are intentionally outside the generic
        # renderer.  Partial resumes still render after adding new results.
        None if complete_resume else report_path,
        require_complete=True,
    )
    if complete_resume and report_path:
        print(
            "REPORT: unchanged (complete resume reused all results)",
            file=sys.stderr,
        )

    for optimization in OPTIMIZATIONS:
        counts = payload["summary"].get(optimization, {})
        primary = counts.get("primary_status", {})
        print(
            f"{optimization} primary: "
            + " ".join(
                f"{status}={primary.get(status, 0)}"
                for status in sorted(FINAL_STATUSES)
            )
            + f" TOTAL={counts.get('total', 0)}",
            file=sys.stderr,
        )
        for backend in ("qemu", "gem5"):
            backend_counts = counts.get("backends", {}).get(backend, {})
            print(
                f"{optimization} {backend}: "
                + " ".join(
                    f"{state}={backend_counts.get(state, 0)}"
                    for state in BACKEND_STATES
                ),
                file=sys.stderr,
            )
    print(f"JSON: {json_path}", file=sys.stderr)
    if report_path and not complete_resume:
        print(f"REPORT: {report_path}", file=sys.stderr)

    all_pass = (
        not payload["fatal_errors"]
        and not payload["validation_errors"]
        and len(payload["results"]) == 38
        and all(result["status"] == "PASS" for result in payload["results"])
    )
    if interrupted:
        return 130
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
