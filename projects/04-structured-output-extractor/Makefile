# Common tasks. On Windows without `make`, run the command under each target by hand.
PY ?= python

.PHONY: install test demo extract lint docker clean

install:  ## install the package (editable) with test deps
	$(PY) -m pip install -e ".[dev]"

test:  ## run the offline test suite
	$(PY) -m pytest -q

demo:  ## run the one-command demo
	$(PY) demo.py

extract:  ## extract from your own file, e.g. make extract FILE=mail.txt SCHEMA=ticket
	$(PY) demo.py $(FILE) --schema $(SCHEMA)

lint:  ## style check (ruff is optional; install it yourself)
	$(PY) -m ruff check src tests

docker:  ## build and run the demo in a container
	docker build -t structured-extractor . && docker run --rm structured-extractor

clean:  ## remove caches
	$(PY) -c "import pathlib, shutil; [shutil.rmtree(p) for p in list(pathlib.Path('.').rglob('*')) if p.is_dir() and p.name in ('__pycache__', '.pytest_cache', '.ruff_cache')]"
