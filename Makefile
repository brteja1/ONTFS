PYTHON ?= python3
PIP := $(PYTHON) -m pip

.PHONY: deps deps-mcp deps-shacl deps-embed deps-all

# Install ONTFS and core dependencies only; optional extras remain opt-in.
deps:
	$(PIP) install -e .

deps-mcp:
	$(PIP) install -e '.[mcp]'

deps-shacl:
	$(PIP) install -e '.[shacl]'

deps-embed:
	$(PIP) install -e '.[embed]'

deps-all:
	$(PIP) install -e '.[mcp,shacl,embed]'
