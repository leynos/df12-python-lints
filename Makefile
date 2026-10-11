MDLINT ?= markdownlint-cli2
NIXIE ?= nixie
export PATH := $(HOME)/.local/bin:$(HOME)/.bun/bin:$(PATH)
# Every uv call goes through the vendored helper, which cleans the environment,
# uses the global uv cache, runs offline first and goes online at most once. See
# https://github.com/leynos/shared-actions/tree/main/uv_gate for the contract.
# The one exception is typos-config-builder at a release tag, which the spelling
# baseline requires to be called directly.
UV_GATE ?= python3 scripts/uv_gate.py
UV ?= $(shell command -v uv 2>/dev/null || printf '%s/.local/bin/uv' "$$HOME")
# The helper finds uv on PATH, so a caller's UV=/path/to/uv is honoured by putting
# that uv's directory first on PATH for every recipe.
export PATH := $(if $(findstring /,$(UV)),$(patsubst %/,%,$(dir $(UV))):)$(PATH)
# A UV given on the command line or in the environment must be uv itself or an executable
# file named uv: the helper finds uv on PATH by that name and would otherwise use another.
UV_SELECTION_CHECK := $(if $(filter command line environment,$(origin UV)),$(if $(filter uv,$(UV)),,$(if $(findstring /,$(UV)),$(if $(shell test -f '$(UV)' -a -x '$(UV)' && printf y),$(if $(filter uv,$(notdir $(UV))),,$(error UV=$(UV) must be named uv)),$(error UV=$(UV) is not an executable file)),$(error UV=$(UV) must be uv or a path to an executable file named uv))))

USER_CARGO := $(HOME)/.cargo/bin/cargo
USER_WHITAKER := $(HOME)/.local/bin/whitaker
USER_BIN_PATH := $(HOME)/.cargo/bin:$(HOME)/.local/bin:$(HOME)/.bun/bin
TOOLS = $(MDLINT) $(MDTABLEFIX)
VENV_TOOLS = pytest
export PYO3_USE_ABI3_FORWARD_COMPATIBILITY := 1
TYPOS_CONFIG_BUILDER_VERSION ?= v0.1.3
TYPOS_CONFIG_BUILDER = env $(UV) tool run --python 3.14 --from \
	"git+https://github.com/leynos/typos-config-builder.git@$(TYPOS_CONFIG_BUILDER_VERSION)" \
	typos-config-builder
WITH_ACT ?= 0
ACT_TEST_ENV = $(if $(filter 1 true yes on,$(WITH_ACT)),RUN_ACT_VALIDATION=1,)
PYTEST_XDIST_WORKERS ?= auto
PYTHON_TARGETS ?= df12_python_lints tests
PYLINT_PYTHON ?= pypy@3.12
PYLINT_VERSION ?= 4.0.9
PYLINT_TARGETS ?= $(PYTHON_TARGETS)
PYLINT = $(UV_GATE) tool --managed-python --python $(PYLINT_PYTHON) --from 'pylint==$(PYLINT_VERSION)' -- pylint


# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.1 or later; CI pins the version at its
# install-mdtablefix step.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences

.PHONY: prepare help all audit clean build build-release crosshair lint lint-python fmt check-fmt \
        markdownlint nixie spelling test typecheck $(TOOLS) $(VENV_TOOLS)

prepare: ## Install the locked development environment, offline first
	$(UV_GATE) prepare --group dev

.DEFAULT_GOAL := all

all: build check-fmt lint typecheck test
	+$(MAKE) spelling

define ensure_uv
	@command -v $(UV) >/dev/null 2>&1 || { \
	  printf "Error: uv is required, but '%s' was not found or is not executable\n" "$(UV)" >&2; \
	  exit 1; \
	}
endef

.venv: pyproject.toml prepare
	$(call ensure_uv)

build: .venv prepare ## Build virtual-env and install deps

build-release: prepare ## Build artefacts (sdist & wheel)
	$(call ensure_uv)
	$(UV_GATE) run -- python -m build --sdist --wheel

clean: ## Remove build artifacts
	rm -rf build dist *.egg-info \
	  .mypy_cache .pytest_cache .coverage coverage.* \
	  lcov.info htmlcov .venv .uv-cache .uv-tools \
	  .typos-oxendict-base.json .typos-oxendict-base.toml
	find . -type d -name '__pycache__' -print0 | xargs -0 -r rm -rf

define ensure_tool
	@command -v $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required, but not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

define ensure_tool_venv
	@$(UV_GATE) run -- which $(1) >/dev/null 2>&1 || { \
	  printf "Error: '%s' is required in the virtualenv, but is not installed\n" "$(1)" >&2; \
	  exit 1; \
	}
endef

ifneq ($(strip $(TOOLS)),)
$(TOOLS): ## Verify required CLI tools
	$(call ensure_tool,$@)
endif


ifneq ($(strip $(VENV_TOOLS)),)
.PHONY: $(VENV_TOOLS)
$(VENV_TOOLS): build ## Verify required CLI tools in venv
	$(call ensure_tool_venv,$@)
endif


fmt: build $(MDTABLEFIX) $(MDLINT) ## Format sources
	$(UV_GATE) run -- ruff format $(PYTHON_TARGETS)
	$(UV_GATE) run -- ruff check --select I --fix $(PYTHON_TARGETS)
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	$(MDLINT) --fix "**/*.md"

	$(MDFORMAT_ALL)

check-fmt: build $(MDTABLEFIX) ## Verify formatting
	$(UV_GATE) run -- ruff format --check $(PYTHON_TARGETS)
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)


lint: lint-python ## Run linters

lint-python: build ## Run Python linters
	$(UV_GATE) run -- ruff check $(PYTHON_TARGETS)
	$(UV_GATE) run -- interrogate --fail-under 100 $(PYTHON_TARGETS)
	$(PYLINT) $(PYLINT_TARGETS)


typecheck: build ## Run typechecking
	$(UV_GATE) run -- ty --version
	$(UV_GATE) run -- ty check $(PYTHON_TARGETS)

audit: build ## Audit dependencies for known vulnerabilities
	$(UV_GATE) run -- pip-audit


markdownlint: $(MDLINT) ## Lint Markdown files and spelling
	env -u NO_COLOR $(MDLINT) '**/*.md'
	+$(MAKE) spelling

spelling: ## Enforce en-GB-oxendict spelling
	$(TYPOS_CONFIG_BUILDER) gate --repository .

nixie: ## Validate Mermaid diagrams
	$(call ensure_tool,$(NIXIE))
	$(NIXIE) --no-sandbox

test: build $(VENV_TOOLS) ## Run tests
	$(ACT_TEST_ENV) $(UV_GATE) run -- pytest -v -n $(PYTEST_XDIST_WORKERS)

crosshair: build ## Model-check pure kernels with CrossHair
	RUN_CROSSHAIR=1 $(UV_GATE) run -- pytest -v tests/test_crosshair.py


help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":.*##"; printf "Available targets:\n"} {gsub(/^[[:space:]]+/, "", $$2); printf "  %-20s %s\n", $$1, $$2}'
