# 14 · Human-in-the-Loop Approvals. Run `make help` for targets.
PYTHON ?= python
IMAGE  ?= exe404/14-human-in-the-loop-approvals
RUN    ?=

.PHONY: help install test demo pending audit lint docker clean

help:          ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:       ## install runtime + dev deps
	$(PYTHON) -m pip install -r requirements.txt

test:          ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:          ## the scripted end-to-end approval story
	$(PYTHON) demo.py

pending:       ## list runs waiting for a human
	$(PYTHON) demo.py pending

audit:         ## print and verify the hash-chained audit log
	$(PYTHON) demo.py audit

lint:          ## style check (needs ruff: pip install ruff)
	$(PYTHON) -m ruff check src tests demo.py

docker:        ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:         ## remove caches and the local run state
	rm -rf .pytest_cache .hitl_state build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
