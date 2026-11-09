# Architecture · 27 Document Intake Pipeline (FDE)

## Components

| Layer | Component | File | Responsibility |
|---|---|---|---|
| entry | `main`, `run_pipeline`, `render_*` | `src/intake/cli.py` | `demo` / `run` / `eval` subcommands; wires settings, adapters and the pipeline. |
| config | `Settings` | `src/intake/config.py` | Env settings: `LLM_PROVIDER`, `LLM_MODEL`, default paths (`INTAKE_*`). |
| config | `ClientConfig` | `src/intake/config.py` | Per-client JSON: tolerances, date formats, routing, ERP mapping, acceptance targets. |
| service | `IntakePipeline.run` | `src/intake/services/pipeline.py` | Pass 1 classify + extract; pass 2 vendor, rules, 3-way match, decide. |
| service | `classify`, `extract` | `src/intake/services/extraction.py` | LLM → JSON → date normalisation → pydantic, with one repair retry carrying the validation errors. |
| service | `render_markdown`, `stats` | `src/intake/services/report.py` | Run report and STP numbers. |
| service | `evaluate`, `load_golden` | `src/intake/services/evaluate.py` | Golden-set metrics against the client's acceptance targets. |
| domain | `validate_invoice` + rules | `src/intake/domain/rules.py` | Line math, subtotal/total, tax rate, dates, known vendor, PO required, duplicates. |
| domain | `three_way_match` | `src/intake/domain/matching.py` | Invoice vs PO vs goods receipts: price variance, over-billed quantity, vendor mismatch. |
| domain | `VendorMaster.resolve` | `src/intake/domain/vendors.py` | Tax id → exact name → fuzzy name. |
| domain | models | `src/intake/domain/models.py` | `Invoice`, `PurchaseOrder`, `GoodsReceipt`, `Issue`, `DocumentResult` (with its trace). |
| adapter | `MockLLM`, `AnthropicLLM`, `OpenAILLM`, `build_llm` | `src/intake/adapters/llm.py`, `providers.py` | The extractor port and implementations. |
| adapter | `load_inbox`, `OutputWriter`, `to_erp_record` | `src/intake/adapters/storage.py` | Read inbox and master data; write ERP JSONL/CSV, exceptions queue, report. |

## Data flow

Inbox files → `RawDocument` → `classify` (JSON documents declare their type; text documents go to the LLM) →
`extract` (validated pydantic model or `EXTRACTION_FAILED`) → after **all** documents are parsed, POs and GRNs are
indexed by PO number → each invoice gets vendor resolution, `validate_invoice` and `three_way_match` →
`_decide` sets `APPROVED` / `EXCEPTION` (with owner from `ClientConfig.exception_routing`) / `REFERENCE` →
`write_outputs` writes ERP records, the exceptions queue and the report → `evaluate` compares with the golden set.

## One full request: an invoice with a price variance

```mermaid
sequenceDiagram
    autonumber
    participant CLI as cli.main("demo")
    participant S as Settings / ClientConfig
    participant P as IntakePipeline.run
    participant X as extraction.classify / extract
    participant LLM as MockLLM
    participant V as VendorMaster
    participant R as rules.validate_invoice
    participant M as matching.three_way_match
    participant W as OutputWriter
    participant E as evaluate

    CLI->>S: Settings.from_env(); ClientConfig.load(northwind.json)
    CLI->>P: run(load_inbox(inbox))
    loop pass 1: every document
        P->>X: classify(raw)
        X->>LLM: classify(text, LABELS)
        LLM-->>X: {"label": "invoice", "confidence": 0.97}
        P->>X: extract(raw, INVOICE)
        X->>LLM: extract(text, schema)
        X->>X: normalize_dates + Invoice.model_validate (1 repair retry)
    end
    Note over P: index POs + GRNs by po_number<br/>(a PO arriving after its invoice still matches)
    P->>V: resolve("Globex Office Products", tax_id)
    P->>R: validate_invoice(INV-1002, RuleContext)
    R-->>P: all rules passed
    P->>M: three_way_match(INV-1002, PO-5002, [GRN-7002])
    M-->>P: PRICE_VARIANCE PAPER-A4 +7.9% (> 2% tolerance)
    P->>P: _decide -> EXCEPTION, owner = buyer
    CLI->>W: write_outputs: erp_invoices.jsonl, erp_invoice_lines.csv, exceptions.jsonl, run_report.md
    CLI->>E: evaluate(results, golden, acceptance)
    E-->>CLI: ACCEPTANCE: PASS
```

## Design decisions

- **The model only reads.** LLM output is used for classification and extraction; every approve/hold decision is
  deterministic code in `domain/`, so it can be explained to an auditor and unit-tested.
- **Validation is the contract.** Pydantic schemas define what "extracted" means; one repair retry sends the exact
  validation errors back to the model, then the document goes to the exceptions queue instead of guessing.
- **Two passes.** Matching runs after the whole batch is parsed, so document order in the inbox does not matter.
- **Client config, not code.** Onboarding a customer is a JSON file (`ClientConfig`); environment `Settings` hold
  only process concerns (provider, model, paths). CLI flags override both.
- **Golden-set acceptance.** The numbers the customer signed off on are in the client file; `run.py eval` exits 1
  if any metric falls below its target, so it can gate a deploy.

## Failure modes and how they are handled

| Failure | Handling |
|---|---|
| Not a business document (newsletter) | `UNCLASSIFIED` → exceptions queue. |
| Low classification confidence | `LOW_CONFIDENCE` → exceptions queue. |
| Malformed / incomplete extraction | One repair retry with validation feedback, then `EXTRACTION_FAILED`. |
| Unknown vendor | `known_vendor` rule raises an error issue → routed per client config. |
| Price / quantity mismatch vs PO / GRN | `three_way_match` issues → buyer or receiving. |
| Already-posted or in-batch duplicate | `not_duplicate` against `posted_invoices.json` + invoices approved earlier in the run. |
| Arithmetic or tax errors | `line_math`, `subtotal_matches_lines`, `total_matches`, `tax_rate` with client tolerances. |
| Model refusal (Anthropic) | Treated as an empty extraction → validation fails → exceptions queue. |

## How to extend

- **New rule:** write `def my_rule(inv, ctx) -> list[Issue]` in `domain/rules.py` and add it to `validate_invoice`.
- **New document type:** add a pydantic model, a `DocType`, a `SCHEMAS` entry, and teach `MockLLM` to extract it.
- **New client:** copy `examples/clients/northwind.json`, adjust it, add a golden file, run `python run.py eval --client ...`.
- **Real ERP:** replace `OutputWriter.write_erp` with an API client; keep `to_erp_record` as the mapping layer.
