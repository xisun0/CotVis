PYTHON ?= python3
ARGS ?=
DEMO_PORT ?= 8765
DEMO_TAIL_SEC ?= 8

.PHONY: setup setup-llm run run-web demo test-asr test-nlp sample-wav setup-local commit-help

setup:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e .

setup-llm:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[llm]"

run:
	$(PYTHON) -m realtime_asr.cli $(ARGS)

run-web:
	$(PYTHON) -m realtime_asr.cli --serve-ui $(ARGS)

demo: sample-wav
	@echo "Starting CotVis demo on http://127.0.0.1:$(DEMO_PORT)"
	@set -e; \
	$(PYTHON) -m realtime_asr.cli --serve-ui --open-browser --ui-port $(DEMO_PORT) $(ARGS) > /tmp/cotvis_demo.log 2>&1 & \
	ASR_PID=$$!; \
	cleanup() { kill $$ASR_PID >/dev/null 2>&1 || true; }; \
	trap cleanup EXIT INT TERM; \
	sleep 3; \
	afplay examples/sample.wav; \
	sleep $(DEMO_TAIL_SEC); \
	cleanup; \
	trap - EXIT INT TERM; \
	echo "Demo finished. Recent output:"; \
	tail -n 40 /tmp/cotvis_demo.log

test-asr: demo

test-nlp:
	$(PYTHON) -m realtime_asr.simulate_transcript --serve-ui --open-browser $(ARGS)

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
