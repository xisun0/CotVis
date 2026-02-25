PYTHON ?= python3
ARGS ?=

.PHONY: setup run setup-local commit-help

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .

run:
	$(PYTHON) -m realtime_asr.cli $(ARGS)

setup-local:
	git config commit.template .gitmessage.txt
	@echo "Configured local git commit template: .gitmessage.txt"

commit-help:
	@echo "Commit title format:"
	@echo "  <type>(<scope>): <short summary>"
	@echo ""
	@echo "Examples:"
	@echo "  feat(asr): add macOS speech streaming callback"
	@echo "  feat(cli): print top terms every 2 seconds"
	@echo "  fix(context): avoid double counting final transcript text"
	@echo "  docs(docs): add troubleshooting for missing mic permission"
