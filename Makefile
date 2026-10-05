PYTHON ?= python3
PIP := $(PYTHON) -m pip

.PHONY: deps

# Install ONTFS and every declared optional dependency group.
deps:
	$(PIP) install -e '.[mcp,shacl,embed]'
