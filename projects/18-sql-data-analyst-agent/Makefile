# 18 · SQL Data Analyst Agent. Run `make help` for targets.
PYTHON ?= python
IMAGE  ?= exe404/18-sql-data-analyst-agent
Q      ?= How many customers do we have?

.PHONY: help install test demo ask lint docker clean

help:          ## list targets
	@grep -E '^[a-z]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

install:       ## install runtime + dev deps
	$(PYTHON) -m pip install -r requirements.txt

test:          ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:          ## ask the demo question set (one must be refused)
	$(PYTHON) demo.py

ask:           ## ask one question with the chart JSON (make ask Q="...")
	$(PYTHON) demo.py --json "$(Q)"

lint:          ## style check (needs ruff: pip install ruff)
	$(PYTHON) -m ruff check src tests demo.py

docker:        ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:         ## remove caches
	rm -rf .pytest_cache build dist *.egg-info
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
