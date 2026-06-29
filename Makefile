PYTHON ?= python3

.DEFAULT_GOAL := help

.PHONY: help manifest-check doctor status fetch apply-series prepare check check-wiki-drift docker-image clean-work

help:
	@echo "DADAO-0628 greenfield orchestration"
	@echo ""
	@echo "  make manifest-check  Validate specification/component/reference locks"
	@echo "  make doctor          Check host or container build prerequisites"
	@echo "  make status          Show locked components and legacy references"
	@echo "  make fetch           Fetch enabled components at exact commits"
	@echo "  make apply-series    Apply ordered patch series to fetched sources"
	@echo "  make prepare         Fetch and apply enabled components"
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

check: manifest-check validate-encoding validate-vectors check-wiki-drift
	@$(PYTHON) -m compileall -q scripts
	@echo "repository checks: PASS"

check-wiki-drift:
	@$(PYTHON) scripts/check_wiki_drift.py

validate-encoding:
	@$(PYTHON) scripts/validate_encoding.py tools/opcodes.yaml

validate-vectors:
	@$(PYTHON) scripts/validate_vectors.py

docker-image:
	docker build -t dadao-0628-dev:local containers/dev

clean-work:
	@$(PYTHON) scripts/clean_work.py
