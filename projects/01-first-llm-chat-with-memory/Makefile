# Common tasks. On Windows without `make`, run the command under each target by hand.
PY ?= python

.PHONY: install test demo chat lint docker clean

install:  ## install the package (editable) with test deps
	$(PY) -m pip install -e ".[dev]"

test:  ## run the offline test suite
	$(PY) -m pytest -q

demo:  ## run the one-command demo
	$(PY) demo.py

chat:  ## chat interactively with a 200-token window
	$(PY) demo.py --chat --budget 200

lint:  ## style check (ruff is optional; install it yourself)
	$(PY) -m ruff check src tests

docker:  ## build and run the demo in a container
	docker build -t chat-memory . && docker run --rm chat-memory

clean:  ## remove caches
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p) for p in list(pathlib.Path('.').rglob('*')) if p.is_dir() and p.name in ('__pycache__', '.pytest_cache', '.ruff_cache')]"
