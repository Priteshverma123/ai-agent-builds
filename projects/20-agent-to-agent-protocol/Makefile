# Common tasks. On Windows use `make` from Git Bash / WSL, or run the commands directly.
PYTHON ?= python

.PHONY: install test demo lint serve docker clean

install:  ## install runtime deps and this package (editable, adds the `a2a-demo` command)
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

test:  ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:  ## run the one-command teaching demo
	$(PYTHON) demo.py

lint:  ## style check (needs `pip install ruff`)
	$(PYTHON) -m ruff check src tests

serve:  ## run the HTTP service locally
	PYTHONPATH=src $(PYTHON) -m a2a_local --serve fx --port 8001

docker:  ## build and run the demo in a container
	docker build -t  .
	docker run --rm 

clean:  ## remove caches and build artefacts
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for pat in ('**/__pycache__', '.pytest_cache', '.ruff_cache', 'build', 'dist', '**/*.egg-info') for p in pathlib.Path('.').glob(pat)]"
