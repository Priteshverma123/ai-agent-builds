# SRE incident agent. On Windows without make, run the commands after each target by hand.
PYTHON ?= python
IMAGE  ?= sre-incident-agent

.PHONY: install test demo interactive lint docker clean

install:      ## pinned deps (httpx only matters with a real LLM)
	$(PYTHON) -m pip install -r requirements.txt

test:         ## fast offline test suite
	$(PYTHON) -m pytest -q

demo:         ## scripted on-call answers, writes out/postmortem.md
	$(PYTHON) demo.py

interactive:  ## you are the on-call: approve or deny each mutating step
	$(PYTHON) demo.py --interactive

lint:         ## needs ruff (pip install ruff)
	$(PYTHON) -m ruff check src tests

docker:       ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('*') if p.name in ('__pycache__', '.pytest_cache', 'out') and p.is_dir()]"
