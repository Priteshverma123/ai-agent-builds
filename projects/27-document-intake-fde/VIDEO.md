# VIDEO hooks · 27 Document Intake Pipeline (FDE)

- **hook:** 18 documents in, two payments out, and every hold explained.
- **demo_cmd:** `python run.py demo`
- **demo_output:**
  ```
  +-- INV-1002.txt [EXCEPTION] ------------------------------------------------------------------+
  |  extract   mock LLM: GX-30417, 2 line(s), total 226.80 (100% of required fields)             |
  |  vendor    V-002 Globex Office Products (matched by name)                                    |
  | !match     PO-5002 + GRN-7002: PRICE_VARIANCE: PAPER-A4: billed 4.10 vs PO 3.80 (+7.9%)      |
  | !decide    EXCEPTION -> buyer: PRICE_VARIANCE                                                |
  == Run summary ==
    straight-through (posted to ERP)   2  (22%)  USD 456.89
    INV-1008.txt                     -> ap_clerk: DUPLICATE_INVOICE
    ACCEPTANCE: PASS
  ```
- **diagram:** `Inbox` → `Classify + Extract (LLM → pydantic)` → `Rules + 3-way match` → `ERP export / Exceptions queue` → `Report + golden eval`
- **real_world:** A manufacturer's AP team receives 4,000 supplier invoices a month. Clean ones post to the ERP automatically, and price, quantity and duplicate problems go to the buyer, receiving or AP, each with a reason.
- **try_it:** Copy `northwind.json` to a new client with European dates and a 5% price tolerance, then make `python run.py eval` pass for it.
- **flow_steps:**
  1. `cli.py` reads `Settings` and the client's `ClientConfig` (`config.py`), then `storage.load_inbox()` loads all 18 files from the inbox.
  2. Pass 1 in `services/pipeline.py`: `classify()` and `extract()` in `services/extraction.py` ask the LLM for JSON and validate it with pydantic, retrying once with the exact errors.
  3. Pass 2: every invoice is matched to a vendor by `VendorMaster.resolve()` and checked by `validate_invoice()` in `domain/rules.py` (totals, tax, dates, duplicates).
  4. `three_way_match()` in `domain/matching.py` compares the invoice with its PO and goods receipt: INV-1002 is billed 7.9% above the PO price.
  5. `_decide()` approves clean invoices for the ERP and sends each problem to its owner (buyer, receiving, AP) via `owner_for()`; `OutputWriter` writes the files.
  6. `evaluate()` in `services/evaluate.py` scores the run against the golden set and prints ACCEPTANCE: PASS.

