.DEFAULT_GOAL := deps
PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: deps deps-mcp deps-shacl deps-embed deps-all

# Bootstrap a project-local environment so installs do not modify an
# externally-managed system Python (PEP 668).
$(VENV_PYTHON):
	$(PYTHON) -m venv $(VENV)

# Install ONTFS and core dependencies only; optional extras remain opt-in.
deps: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install -e .

deps-mcp: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install -e '.[mcp]'

deps-shacl: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install -e '.[shacl]'

deps-embed: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install -e '.[embed]'

deps-all: $(VENV_PYTHON)
	$(VENV_PYTHON) -m pip install -e '.[mcp,shacl,embed]'
