# Customer support agent. On Windows without make, run the commands after each target by hand.
PYTHON ?= python
PORT   ?= 8000
IMAGE  ?= support-agent

.PHONY: install test demo evals serve lint docker clean

install:  ## pinned runtime + test deps
	$(PYTHON) -m pip install -r requirements.txt

test:     ## fast offline test suite
	$(PYTHON) -m pytest -q

demo:     ## five scripted conversations over real HTTP, rendered from traces
	$(PYTHON) run.py demo

evals:    ## 14-case eval gate; exit code 1 on any failure
	$(PYTHON) run.py evals

serve:    ## http://127.0.0.1:$(PORT)/docs
	SUPPORT_TODAY=2026-10-20 $(PYTHON) run.py serve --port $(PORT)

lint:     ## needs ruff (pip install ruff)
	$(PYTHON) -m ruff check src tests

docker:   ## build and run the API container on :8000
	docker build -t $(IMAGE) .
	docker run --rm -p 8000:8000 $(IMAGE)

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('*') if p.name in ('__pycache__', '.pytest_cache') and p.is_dir()]"
