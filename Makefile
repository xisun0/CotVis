PYTHON ?= python
ARGS ?=

.PHONY: setup run speak legacy-run test setup-local commit-help

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .

run:
	PYTHONPATH=src $(PYTHON) -m codex_speak $(ARGS)

speak:
	PYTHONPATH=src $(PYTHON) -m codex_speak $(ARGS)

legacy-run:
	PYTHONPATH=src $(PYTHON) -m realtime_asr.cli $(ARGS)

test:
	PYTHONPATH=src $(PYTHON) -m pytest tests

setup-local:
	git config commit.template .gitmessage.txt
	@echo "Configured local git commit template: .gitmessage.txt"

commit-help:
	@echo "Commit title format:"
	@echo "  <type>(<scope>): <short summary>"
	@echo ""
	@echo "Examples:"
	@echo "  feat(cli): add Markdown review session bootstrap"
	@echo "  feat(context): add sentence locator for review flow"
	@echo "  docs(docs): add voice review CLI setup notes"
