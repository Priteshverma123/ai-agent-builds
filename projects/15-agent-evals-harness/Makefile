# 15 · Agent Evals Harness. Run `make help` for targets.
PYTHON ?= python
IMAGE  ?= exe404/15-agent-evals-harness
AGENT  ?= v1

.PHONY: help install test demo eval baseline lint docker clean

help:          ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:       ## install runtime + dev deps
	$(PYTHON) -m pip install -r requirements.txt

test:          ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:          ## story: v1 vs baseline, then v2 vs baseline
	$(PYTHON) demo.py

eval:          ## CI gate for one version, exits 0/1/2 (make eval AGENT=v2)
	$(PYTHON) demo.py run --agent $(AGENT)

baseline:      ## save the current version's results as the new baseline
	$(PYTHON) demo.py run --agent $(AGENT) --save-baseline examples/baseline.json

lint:          ## style check (needs ruff: pip install ruff)
	$(PYTHON) -m ruff check src tests demo.py

docker:        ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:         ## remove caches and generated reports
	rm -rf .pytest_cache out build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
