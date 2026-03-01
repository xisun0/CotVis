PYTHON ?= python3
ARGS ?=

.PHONY: setup run run-web sample-wav setup-local commit-help

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .

run:
	$(PYTHON) -m realtime_asr.cli $(ARGS)

run-web:
	$(PYTHON) -m realtime_asr.cli --serve-ui $(ARGS)

sample-wav:
	mkdir -p examples
	say -v Samantha -f examples/sample_script.txt -o examples/sample.aiff
	afconvert -f WAVE -d LEI16@16000 -c 1 examples/sample.aiff examples/sample.wav
	rm -f examples/sample.aiff
	@echo "Generated examples/sample.wav"

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
