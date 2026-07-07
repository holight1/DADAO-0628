PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help manifest-check doctor status fetch apply-series prepare build-qemu build-mc check check-wiki-drift check-wiki-refs check-wiki-refs-abi docker-image clean-work lint check-issues check-trans check-qfc check-lit-bytes check-codegen-abi

help:
	@echo "DADAO-0628 greenfield orchestration"
	@echo ""
	@echo "  make manifest-check  Validate specification/component/reference locks"
	@echo "  make doctor          Check host or container build prerequisites"
	@echo "  make status          Show locked components and legacy references"
	@echo "  make fetch           Fetch enabled components at exact commits"
	@echo "  make apply-series    Apply ordered patch series to fetched sources"
	@echo "  make prepare         Fetch and apply enabled components"
	@echo "  make build-qemu      Configure and compile QEMU (Phase 3)"
	@echo "  make build-mc        Build LLVM MC components for DADAO (Phase 2)"
	@echo "  make check           Run repository-level structural checks"
	@echo "  make docker-image    Build the reproducible development image"
	@echo "  make clean-work      Remove generated .work content only"

manifest-check:
	@$(PYTHON) scripts/manifest_check.py

doctor:
	@$(PYTHON) scripts/doctor.py

status:
	@$(PYTHON) scripts/status.py

fetch: manifest-check
	@$(PYTHON) scripts/fetch.py

apply-series: manifest-check
	@$(PYTHON) scripts/apply_series.py

prepare: fetch apply-series

check: manifest-check validate-encoding validate-vectors check-wiki-drift check-wiki-refs check-wiki-refs-abi check-issues
	@$(PYTHON) -m compileall -q scripts
	@echo "repository checks: PASS"

QEMU_SRC   ?= .work/qemu
QEMU_BUILD ?= .work/build/qemu

build-qemu: manifest-check
	cd $(QEMU_SRC) && ./configure \
	  --target-list=dadao-softmmu \
	  --enable-tcg \
	  --disable-werror
	$(MAKE) -C $(QEMU_SRC) -j$$(nproc)
	@echo "build-qemu: PASS"

LLVM_BUILD ?= .work/build/llvm
LLVM_SRC   ?= .work/llvm/llvm

build-mc: manifest-check
	cmake -G Ninja -B $(LLVM_BUILD) -S $(LLVM_SRC) \
	  -DLLVM_TARGETS_TO_BUILD=DADAO \
	  -DLLVM_ENABLE_PROJECTS="" \
	  -DCMAKE_BUILD_TYPE=RelWithDebInfo \
	  -DLLVM_ENABLE_ASSERTIONS=ON
	ninja -C $(LLVM_BUILD) llvm-mc llvm-objdump
	@echo "build-mc: PASS"

check-wiki-drift:
	@$(PYTHON) scripts/check_wiki_drift.py

check-wiki-refs:
	@$(PYTHON) scripts/check_wiki_refs.py

# C1 (ADR-0009 CodeGen/ABI branch): wiki->spec audit of contracts/abi/spec.md.
# DL-040c closed the first-round backlog (Check-2 refined for chapter-level
# citations + code-fence/appendix/table shape; residuals tagged/cited). Now
# fail-closed and part of `make check`, alongside check-wiki-refs (ISA).
check-wiki-refs-abi:
	@$(PYTHON) scripts/check_wiki_refs.py --profile abi

validate-encoding:
	@$(PYTHON) scripts/validate_encoding.py tools/opcodes.yaml

validate-vectors:
	@$(PYTHON) scripts/validate_vectors.py

docker-image:
	docker build -t dadao-0628-dev:local containers/dev

check-qfc:
	@$(PYTHON) scripts/check_qfc_coverage.py

check-lit-bytes:
	@$(PYTHON) scripts/check_lit_bytes.py

lint: check-issues check-trans check-qfc check-lit-bytes

check-issues:
	@$(PYTHON) scripts/check_issues.py

check-trans:
	@$(PYTHON) scripts/check_qemu_trans.py

clean-work:
	@$(PYTHON) scripts/clean_work.py

# C3 (ADR-0009 CodeGen/ABI branch): read-only backend-vs-abi.yaml conformance.
# INTENTIONALLY standalone — NOT part of `make check`. The Phase-5 CodeGen spike
# is WIP; this target EXPOSES divergence, it must not block repository checks.
check-codegen-abi:
	@$(PYTHON) scripts/check_codegen_abi.py
