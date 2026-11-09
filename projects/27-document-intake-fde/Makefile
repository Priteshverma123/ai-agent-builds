# Document intake pipeline. On Windows without make, run the commands after each target by hand.
PYTHON ?= python
IMAGE  ?= document-intake

.PHONY: install test demo run eval lint docker clean

install:  ## pinned runtime + test deps
	$(PYTHON) -m pip install -r requirements.txt

test:     ## fast offline test suite
	$(PYTHON) -m pytest -q

demo:     ## trace for every document + run summary + golden-set acceptance
	$(PYTHON) run.py demo

run:      ## batch mode: writes out/ and prints the summary
	$(PYTHON) run.py run

eval:     ## acceptance gate only; exit code 1 if below target
	$(PYTHON) run.py eval

lint:     ## needs ruff (pip install ruff)
	$(PYTHON) -m ruff check src tests

docker:   ## build and run the demo in a container
	docker build -t $(IMAGE) .
	docker run --rm $(IMAGE)

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('*') if p.name in ('__pycache__', '.pytest_cache', 'out') and p.is_dir()]"
