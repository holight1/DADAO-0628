#!/usr/bin/env python3
"""Fail-closed KL-145a K2 closure matrix.

This runner intentionally validates explicit pass/fail counts and semantic
markers rather than treating subprocess exit code zero as evidence.  It does
not build, fetch, enable, or modify Linux; the final static gate requires the
manifest's Linux component to remain disabled.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / ".work" / "evidence" / "kl145a-k2-closure"
SUMMARY = EVIDENCE / "summary.json"
QEMU_TREE = ROOT / ".work" / "source" / "qemu"
GEM5_TREE = Path("/home/holight/DADAO-gem5")
QEMU_BIN = QEMU_TREE / "build" / "qemu-system-dadao"
GEM5_BIN = GEM5_TREE / "build" / "DADAO" / "gem5.opt"
TIMEOUT = 900


@dataclass
class GateResult:
    name: str
    command: list[str]
    returncode: int | None
    duration_seconds: float
    checks: list[str]
    verdict: str
    reason: str
    log: str


Check = Callable[[str], tuple[bool, str]]


def exact_count(pattern: str, expected: int, description: str) -> Check:
    regex = re.compile(pattern, re.MULTILINE)

    def check(output: str) -> tuple[bool, str]:
        actual = len(regex.findall(output))
        return actual == expected, f"{description}: {actual}/{expected}"

    return check


def contains(text: str, description: str) -> Check:
    def check(output: str) -> tuple[bool, str]:
        return text in output, f"{description}: {'present' if text in output else 'missing'}"

    return check


def absent(text: str, description: str) -> Check:
    def check(output: str) -> tuple[bool, str]:
        return text not in output, (
            f"{description}: {'absent' if text not in output else 'present'}")

    return check


def ordered_rounds(pattern: str, rounds: int, description: str) -> Check:
    regex = re.compile(pattern, re.MULTILINE)
    expected = [(index, rounds) for index in range(1, rounds + 1)]

    def check(output: str) -> tuple[bool, str]:
        actual = [
            (int(match.group(1)), int(match.group(2)))
            for match in regex.finditer(output)
        ]
        return actual == expected, (
            f"{description}: {actual if actual != expected else '1..' + str(rounds)}")

    return check


def run_gate(name: str, command: list[str], checks: list[Check],
             accepted_returncodes: tuple[int, ...] = (0,)) -> GateResult:
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    log_path = EVIDENCE / f"{name}.log"
    start = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=TIMEOUT,
            check=False,
        )
        output = completed.stdout
        returncode: int | None = completed.returncode
        execution_reason = ""
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or ""
        output = raw.decode() if isinstance(raw, bytes) else raw
        returncode = None
        execution_reason = f"timeout after {TIMEOUT}s"
    except OSError as exc:
        output = f"launch error: {exc}\n"
        returncode = None
        execution_reason = f"launch error: {exc}"
    log_path.write_text(output, encoding="utf-8")

    details: list[str] = []
    failures: list[str] = []
    if execution_reason:
        failures.append(execution_reason)
    if returncode not in accepted_returncodes:
        failures.append(f"returncode={returncode}")
    for check in checks:
        ok, detail = check(output)
        details.append(detail)
        if not ok:
            failures.append(detail)
    verdict = "PASS" if not failures else "FAIL"
    return GateResult(
        name=name,
        command=command,
        returncode=returncode,
        duration_seconds=round(time.monotonic() - start, 3),
        checks=details,
        verdict=verdict,
        reason="; ".join(failures),
        log=str(log_path.relative_to(ROOT)),
    )


def k2_scenario_checks(rounds: int, negative_marker: str, final_marker: str) -> list[Check]:
    return [
        ordered_rounds(
            r"^round ([0-9]+)/([0-9]+): "
            r"qemu=PASS gem5=PASS oracle=PASS cross=PASS$",
            rounds, "ordered dual-backend positive rounds"),
        exact_count(
            rf"^{re.escape(negative_marker)} "
            r"\(qemu=FAIL/status=FAIL/mismatch=[1-9][0-9]* "
            r"gem5=FAIL/status=FAIL/mismatch=[1-9][0-9]*\) as required$",
            1, "bound dual-backend nonzero-mismatch negative"),
        exact_count(
            r"^post-restore round: PASS$", 1, "post-restore positive"),
        exact_count(
            rf"^{re.escape(final_marker)}$", 1, "scenario terminal PASS"),
        absent("HARNESS-ERROR", "harness errors"),
        absent("unexpected", "unexpected-result marker"),
        absent("SKIP", "scenario-level SKIP"),
    ]


def backend_binding_gate() -> GateResult:
    start = time.monotonic()
    checks: list[str] = []
    failures: list[str] = []
    override_names = ("QEMU_DADAO", "GEM5_OPT", "GEM5_FS", "K2_FS_CFG")
    active = [name for name in override_names if name in os.environ]
    checks.append(
        "backend/config overrides: absent"
        if not active else "backend/config overrides: " + ", ".join(active))
    if active:
        failures.append("closure forbids backend/config overrides")

    bindings = (
        ("qemu", QEMU_BIN, QEMU_TREE),
        ("gem5", GEM5_BIN, GEM5_TREE),
    )
    for label, binary, tree in bindings:
        try:
            resolved_binary = binary.resolve(strict=True)
            resolved_tree = tree.resolve(strict=True)
            bound = resolved_binary.is_relative_to(resolved_tree)
            executable = os.access(resolved_binary, os.X_OK)
        except OSError as exc:
            bound = executable = False
            resolved_binary = binary
            failures.append(f"{label} binary resolution error: {exc}")
        checks.append(
            f"{label} binary: {'bound+executable' if bound and executable else 'invalid'} "
            f"({resolved_binary})")
        if not bound or not executable:
            failures.append(f"{label} binary is not bound to expected source tree")

    return GateResult(
        name="backend-binding",
        command=[],
        returncode=0 if not failures else 1,
        duration_seconds=round(time.monotonic() - start, 3),
        checks=checks,
        verdict="PASS" if not failures else "FAIL",
        reason="; ".join(failures),
        log="",
    )


def static_readiness_gate() -> GateResult:
    start = time.monotonic()
    checks: list[str] = []
    failures: list[str] = []

    with (ROOT / "manifests" / "components.lock.toml").open("rb") as stream:
        manifest = tomllib.load(stream)
    linux = [
        component for component in manifest.get("component", [])
        if component.get("name") == "linux"
    ]
    linux_disabled = (
        len(linux) == 1
        and linux[0].get("enabled") is False
        and linux[0].get("commit") == ""
    )
    checks.append(
        "linux component: disabled and unpinned"
        if linux_disabled else "linux component: NOT disabled/unpinned")
    if not linux_disabled:
        failures.append("Linux manifest boundary changed")

    arch_path = ROOT / "arch" / "dadao"
    checks.append(
        f"root arch/dadao: {'absent' if not arch_path.exists() else 'present'}")
    if arch_path.exists():
        failures.append("K3 path exists: arch/dadao")

    linux_source = ROOT / ".work" / "source" / "linux"
    checks.append(
        ".work/source/linux: "
        + ("absent" if not linux_source.exists() else "present"))
    if linux_source.exists():
        failures.append("Linux source tree was fetched before K3")

    patch_series_value = linux[0].get("patch_series", "") if len(linux) == 1 else ""
    expected_series_value = "components/linux/patches/series"
    series_binding_ok = patch_series_value == expected_series_value
    checks.append(
        "Linux patch_series manifest binding: "
        + ("frozen" if series_binding_ok else repr(patch_series_value)))
    if not series_binding_ok:
        failures.append("Linux patch_series manifest binding changed")
    series = ROOT / patch_series_value if patch_series_value else ROOT / "__missing__"
    try:
        resolved_series = series.resolve(strict=True)
        series_in_repo = resolved_series.is_relative_to(ROOT.resolve())
        series_is_file = resolved_series.is_file()
    except OSError:
        resolved_series = series
        series_in_repo = series_is_file = False
    if not series_in_repo or not series_is_file:
        failures.append("Linux patch series file missing or outside repository")
    active_series = []
    if series_is_file:
        active_series = [
            line.strip()
            for line in resolved_series.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
    patch_payloads = (
        [
            path for path in resolved_series.parent.rglob("*")
            if path.is_file() and path != resolved_series
        ]
        if series_is_file else []
    )
    patches_empty = (
        series_binding_ok and series_is_file
        and not active_series and not patch_payloads
    )
    checks.append(
        "Linux patch series: empty"
        if patches_empty else "Linux patch series: active/non-empty")
    if not patches_empty:
        failures.append("Linux patch payload exists before K3")

    for label, tree in (("qemu", QEMU_TREE), ("gem5", GEM5_TREE)):
        try:
            completed = subprocess.run(
                ["git", "status", "--short"],
                cwd=tree,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            clean = completed.returncode == 0 and completed.stdout == ""
            detail = completed.stdout.strip()
        except OSError as exc:
            clean = False
            detail = str(exc)
        checks.append(f"{label} component worktree: {'clean' if clean else 'dirty'}")
        if not clean:
            failures.append(f"{label} component dirty/error: {detail}")

    return GateResult(
        name="k3-readiness-boundary",
        command=[],
        returncode=0 if not failures else 1,
        duration_seconds=round(time.monotonic() - start, 3),
        checks=checks,
        verdict="PASS" if not failures else "FAIL",
        reason="; ".join(failures),
        log="",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rounds", type=int, default=10,
        help="positive rounds for KL-141a..144a; closure requires 10")
    args = parser.parse_args()
    if args.rounds != 10:
        parser.error("KL-145a closure evidence requires exactly --rounds 10")
    rounds = args.rounds

    gates: list[tuple[str, list[str], list[Check]]] = [
        (
            "kl140a-oracle",
            [sys.executable, "tests/scripts/run_kl140a_k2_report_selftest.py",
             "--rounds", "10"],
            [
                ordered_rounds(
                    r"^round ([0-9]+)/([0-9]+): 70/70 checks passed$",
                    10, "ordered 70/70 oracle self-test rounds"),
                exact_count(
                    r"^PASS: k2_report schema/codec/oracle/dual-backend "
                    r"self-test \(fail-closed; no backend log consulted\)$",
                    1, "KL-140a terminal PASS"),
                absent("SKIP", "KL-140a SKIP"),
            ],
        ),
        (
            "kl141a-cooperative",
            [sys.executable, "tests/scripts/run_kl141a_coop_switch.py",
             "--rounds", str(rounds)],
            k2_scenario_checks(
                rounds,
                "negative mutation(rd40@t7): dual=FAIL",
                "PASS: KL-141a cooperative context switch dual-backend oracle"),
        ),
        (
            "kl142a-trap",
            [sys.executable, "tests/scripts/run_kl142a_preemptive_trap.py",
             "--rounds", str(rounds)],
            k2_scenario_checks(
                rounds,
                "negative mutation(rd17): dual=FAIL",
                "PASS: KL-142a preemptive trap full-context dual-backend oracle"),
        ),
        (
            "kl143a-address-space",
            [sys.executable, "tests/scripts/run_kl143a_address_space_switch.py",
             "--rounds", str(rounds)],
            k2_scenario_checks(
                rounds,
                "negative omit-invalidate@6: dual=FAIL",
                "PASS: KL-143a PTBR/address-space switch dual-backend oracle"),
        ),
        (
            "kl144a-integrated",
            [sys.executable, "tests/scripts/run_kl144a_timer_scheduler.py",
             "--rounds", str(rounds)],
            k2_scenario_checks(
                rounds,
                "negative omit-invalidate: dual=FAIL",
                "PASS: KL-144a integrated timer-driven scheduler"),
        ),
        (
            "kl139a-k1-k2",
            [sys.executable, "tests/scripts/run_kl139a_k1_k2_integration.py",
             "--rounds", "3"],
            [
                ordered_rounds(
                    r"^round ([0-9]+)/([0-9]+): qemu=139 gem5=139$",
                    3, "ordered K1->K2 rounds"),
                exact_count(
                    r"^PASS: one shared bare-metal image; .+$",
                    1, "KL-139a terminal PASS"),
                absent("HARNESS-ERROR", "harness errors"),
                absent("SKIP", "KL-139a SKIP"),
            ],
        ),
        (
            "lit-e2e",
            [str(ROOT / ".work" / "build" / "llvm" / "bin" / "llvm-lit"),
             "-sv", "tests/lit/E2E/"],
            [
                contains("Total Discovered Tests: 81", "lit discovered count"),
                contains("Passed: 81 (100.00%)", "lit explicit pass count"),
                absent("Failed:", "lit failures"),
                absent("Unsupported:", "lit unsupported tests"),
            ],
        ),
        (
            "ordinary-differential",
            [sys.executable, "tools/run_differential.py"],
            [
                contains(
                    "AGREE(3-way)=200  AGREE(interp+QEMU, gem5-SKIP)=2  "
                    "DIVERGE=0  HARNESS=0  QEMU-SKIP=0",
                    "three-way exact summary"),
                contains(
                    "AGREE(4-way)=200  Sail-SKIP(out-of-slice)=2  "
                    "SAIL-DIVERGE=0",
                    "four-way exact summary"),
            ],
        ),
        (
            "manifest",
            [sys.executable, "scripts/manifest_check.py"],
            [contains("manifest validation: PASS", "manifest PASS")],
        ),
        (
            "issues",
            [sys.executable, "scripts/check_issues.py"],
            [
                contains("ISSUE REGISTRY: PASS", "issue registry PASS"),
                contains("Open:   24", "open issue count"),
                contains("Closed: 43", "closed issue count"),
            ],
        ),
        (
            "wiki-refs",
            [sys.executable, "scripts/check_wiki_refs.py"],
            [
                contains("Check 1 DANGLING:    0", "zero dangling refs"),
                contains("OVERALL: PASS", "wiki refs PASS"),
            ],
        ),
        (
            "wiki-drift",
            [sys.executable, "scripts/check_wiki_drift.py"],
            [contains(
                "wiki drift check: PASS (3 contract(s) verified)",
                "wiki drift PASS")],
        ),
    ]

    binding = backend_binding_gate()
    results: list[GateResult] = [binding]
    print(
        f"[{binding.verdict}] {binding.name}"
        + (f": {binding.reason}" if binding.reason else ""),
        flush=True,
    )
    if binding.verdict == "PASS":
        for name, command, checks in gates:
            print(f"[RUN] {name}", flush=True)
            result = run_gate(name, command, checks)
            results.append(result)
            print(
                f"[{result.verdict}] {name} ({result.duration_seconds:.3f}s)"
                + (f": {result.reason}" if result.reason else ""),
                flush=True,
            )
            # Evidence must be complete, but once a foundational K2 scenario
            # is broken there is no value in later expensive gates.
            if result.verdict != "PASS":
                break

    if (all(result.verdict == "PASS" for result in results)
            and len(results) == len(gates) + 1):
        print("[RUN] known-make-check-debt", flush=True)
        known_debt = run_gate(
            "known-make-check-debt",
            ["make", "check"],
            [
                exact_count(
                    r"^COVERAGE MISSING: ", 5,
                    "known privileged vector coverage count"),
                *[
                    contains(
                        f"COVERAGE MISSING: {instruction}",
                        f"known {instruction} coverage debt")
                    for instruction in (
                        "ldmo-ra", "stmo-ra", "cfx2rd", "cfx2rc", "escape")
                ],
                contains(
                    "make: *** [Makefile:138: validate-vectors] Error 1",
                    "known validate-vectors stop"),
            ],
            accepted_returncodes=(2,),
        )
        results.append(known_debt)
        print(
            f"[{known_debt.verdict}] {known_debt.name} "
            f"({known_debt.duration_seconds:.3f}s)"
            + (f": {known_debt.reason}" if known_debt.reason else ""),
            flush=True,
        )

    if (all(result.verdict == "PASS" for result in results)
            and len(results) == len(gates) + 2):
        readiness = static_readiness_gate()
        results.append(readiness)
        print(
            f"[{readiness.verdict}] {readiness.name}"
            + (f": {readiness.reason}" if readiness.reason else ""),
            flush=True,
        )

    complete = len(results) == len(gates) + 3
    passed = complete and all(result.verdict == "PASS" for result in results)
    payload = {
        "schema_version": 1,
        "task": "KL-145a",
        "verdict": "PASS" if passed else "FAIL",
        "expected_gate_count": len(gates) + 3,
        "observed_gate_count": len(results),
        "results": [asdict(result) for result in results],
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"summary: {SUMMARY.relative_to(ROOT)}")
    if not passed:
        print("FAIL: KL-145a K2 closure matrix is incomplete or failing")
        return 1
    print(
        "PASS: KL-145a K2 closure complete; Linux remains disabled; "
        "stop before K3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
