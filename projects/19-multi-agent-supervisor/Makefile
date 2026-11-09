# Common tasks. On Windows use `make` from Git Bash / WSL, or run the commands directly.
PYTHON ?= python

.PHONY: install test demo lint docker clean

install:  ## install runtime deps and this package (editable, adds the `multi-agent-supervisor` command)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

test:  ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:  ## run the one-command teaching demo
	$(PYTHON) demo.py

lint:  ## style check (needs `pip install ruff`)
	$(PYTHON) -m ruff check src tests

docker:  ## build and run the demo in a container
	docker build -t 19-multi-agent-supervisor .
	docker run --rm 19-multi-agent-supervisor

clean:  ## remove caches and build artefacts
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for pat in ('**/__pycache__', '.pytest_cache', '.ruff_cache', 'build', 'dist', '**/*.egg-info') for p in pathlib.Path('.').glob(pat)]"
