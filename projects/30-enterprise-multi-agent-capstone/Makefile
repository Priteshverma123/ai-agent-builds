# Enterprise multi-agent capstone. On Windows without make, run the commands after each target by hand.
PYTHON ?= python
PORT   ?= 8000
IMAGE  ?= enterprise-assistant

.PHONY: install test demo evals serve lint docker compose clean

install:  ## pinned runtime + test deps
	$(PYTHON) -m pip install -r requirements.txt

test:     ## fast offline test suite
	$(PYTHON) -m pytest -q

demo:     ## MCP discovery + five traced requests + eval summary
	$(PYTHON) demo.py

evals:    ## full eval report; exit code 1 on any failure
	$(PYTHON) run_evals.py

serve:    ## http://127.0.0.1:$(PORT)/docs
	PYTHONPATH=src $(PYTHON) -m capstone.cli serve --port $(PORT)

lint:     ## needs ruff (pip install ruff)
	$(PYTHON) -m ruff check src tests

docker:   ## build and run the API container on :8000
	docker build -t $(IMAGE) .
	docker run --rm -p 8000:8000 $(IMAGE)

compose:  ## API + traces volume; eval gate: docker compose --profile ci run --rm evals
	docker compose up --build

clean:
	$(PYTHON) -c "import pathlib, shutil; [shutil.rmtree(p) for p in pathlib.Path('.').rglob('*') if p.name in ('__pycache__', '.pytest_cache') and p.is_dir()]"
