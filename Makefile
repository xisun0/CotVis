PYTHON ?= python3

.PHONY: setup run

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .

run:
	$(PYTHON) -m realtime_asr.cli
