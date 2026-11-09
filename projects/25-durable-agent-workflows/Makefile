# Durable agent workflows. On Windows without make, run the commands after each target by hand.
PYTHON ?= python
IMAGE  ?= durable-agent-workflows

.PHONY: install test demo lint docker clean

install:  ## install pinned dev deps (runtime is stdlib only)
	$(PYTHON) -m pip install -r requirements.txt

test:     ## fast offline test suite
	$(PYTHON) -m pytest -q

demo:     ## kill a worker mid-job, resume it, prove exactly-once effects
	$(PYTHON) demo.py

lint:     ## needs ruff (pip install ruff)
	$(PYTHON) -m ruff check src tests

docker:   ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('*') if p.name in ('__pycache__', '.pytest_cache') and p.is_dir()]"
