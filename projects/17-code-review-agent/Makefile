# 17 · Code Review Agent. Run `make help` for targets.
PYTHON ?= python
IMAGE  ?= exe404/17-code-review-agent

.PHONY: help install test demo review-md ci lint docker clean

help:          ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:       ## install runtime + dev deps
	$(PYTHON) -m pip install -r requirements.txt

test:          ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:          ## review examples/change.diff with the full trace
	$(PYTHON) demo.py

review-md:     ## write the review as a PR comment to review.md
	$(PYTHON) demo.py --format markdown > review.md

ci:            ## CI gate: exit 1 if any HIGH or CRITICAL finding
	$(PYTHON) demo.py --fail-on high

lint:          ## style check (needs ruff: pip install ruff)
	$(PYTHON) -m ruff check src tests demo.py

docker:        ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:         ## remove caches and generated reports
	rm -rf .pytest_cache review.md build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
