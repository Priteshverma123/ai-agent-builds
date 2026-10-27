# Common tasks. On Windows without `make`, run the command under each target by hand.
PY ?= python

.PHONY: install test demo ask lint docker clean

install:  ## install the package (editable) with test deps
	$(PY) -m pip install -e ".[dev]"

test:  ## run the offline test suite
	$(PY) -m pytest -q

demo:  ## run the one-command demo
	$(PY) demo.py

ask:  ## ask your own question, e.g. make ask Q="How much taller is Everest than K2?"
	$(PY) demo.py "$(Q)"

lint:  ## style check (ruff is optional; install it yourself)
	$(PY) -m ruff check src tests

docker:  ## build and run the demo in a container
	docker build -t react-agent . && docker run --rm react-agent

clean:  ## remove caches
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p) for p in list(pathlib.Path('.').rglob('*')) if p.is_dir() and p.name in ('__pycache__', '.pytest_cache', '.ruff_cache')]"
