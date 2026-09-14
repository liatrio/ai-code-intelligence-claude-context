# Convenience targets over setup.py. Every real behaviour lives in
# setup.py; this file exists so operators can type `make check` instead
# of the full python3 invocation, and so CI matches local usage.

PY := python3
SETUP := $(PY) setup.py

.PHONY: check install index status clean harness harness-gratibot help

help:
	@echo "Targets:"
	@echo "  make check                      # verify environment prerequisites"
	@echo "  make install                    # npm + docker compose up + ollama pull"
	@echo "  make index FIXTURE=/abs/path    # index a fixture through the MCP server"
	@echo "  make status                     # report stack state without side effects"
	@echo "  make clean                      # stop Milvus, remove .cache/ and ./volumes/"
	@echo "  make harness FIXTURE=/abs/path  # two-arm 5-prompt harness against a fixture"
	@echo "  make harness-gratibot           # convenience: harness against ~/liatrio/repos/gratibot"

check:
	$(SETUP) --check

install:
	$(SETUP) --install

index:
	@if [ -z "$(FIXTURE)" ]; then echo "FIXTURE=/abs/path required"; exit 1; fi
	$(SETUP) --index --fixture $(FIXTURE)

status:
	$(SETUP) --status

clean:
	$(SETUP) --clean

harness:
	@if [ -z "$(FIXTURE)" ]; then echo "FIXTURE=/abs/path required"; exit 1; fi
	$(PY) run-prompts.py --fixture $(FIXTURE)

harness-gratibot:
	$(PY) run-prompts.py --fixture $(HOME)/liatrio/repos/gratibot
