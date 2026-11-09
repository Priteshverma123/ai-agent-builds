# 16 · Agent Tracing & Observability. Run `make help` for targets.
PYTHON ?= python
IMAGE  ?= exe404/16-agent-tracing-observability

.PHONY: help install test demo view lint docker clean

help:          ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:       ## install runtime + dev deps
	$(PYTHON) -m pip install -r requirements.txt

test:          ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:          ## trace the example questions, write out/trace.jsonl + out/trace.html
	$(PYTHON) demo.py

view:          ## re-render an existing trace without running the agent
	$(PYTHON) demo.py --view out/trace.jsonl

lint:          ## style check (needs ruff: pip install ruff)
	$(PYTHON) -m ruff check src tests demo.py

docker:        ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:         ## remove caches and generated traces
	rm -rf .pytest_cache out build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
