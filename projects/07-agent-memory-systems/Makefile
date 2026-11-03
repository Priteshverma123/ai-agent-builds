# 07-agent-memory-systems: common tasks. Override the interpreter with `make PYTHON=python3 ...`.
PYTHON ?= python

.PHONY: install test demo lint clean

install:  ## install the package in editable mode with test deps
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

test:  ## run the offline test suite
	$(PYTHON) -m pytest -q

demo:  ## run the one-command teaching demo
	$(PYTHON) demo.py

lint:  ## style check (needs ruff: pip install ruff)
	$(PYTHON) -m ruff check src tests demo.py

clean:  ## remove caches and build artefacts
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p, ignore_errors=True) for p in [*pathlib.Path('.').rglob('__pycache__'), pathlib.Path('.pytest_cache'), pathlib.Path('build'), *pathlib.Path('.').glob('*.egg-info'), *pathlib.Path('src').glob('*.egg-info')]]"
