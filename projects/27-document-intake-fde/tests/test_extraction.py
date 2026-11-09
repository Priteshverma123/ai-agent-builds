from intake.adapters.llm import LABELS, MockLLM
from intake.adapters.storage import RawDocument
from intake.domain.models import DocType, DocumentResult
from intake.services.extraction import classify, extract, normalize_dates

from conftest import EXAMPLES


def raw(name: str) -> RawDocument:
    return RawDocument(name, (EXAMPLES / "inbox" / name).read_text(encoding="utf-8"))


def test_mock_classifies_by_keyword_votes():
    llm = MockLLM()
    assert llm.classify(raw("INV-1001.txt").text, LABELS)["label"] == "invoice"
    assert llm.classify(raw("PO-5003.txt").text, LABELS)["label"] == "purchase_order"
    assert llm.classify(raw("GRN-7003.txt").text, LABELS)["label"] == "goods_receipt"
    assert llm.classify(raw("newsletter.txt").text, LABELS) == {
        "label": "unknown", "confidence": 0.0, "rationale": "no document keywords"}


def test_text_invoice_extracts_into_schema(cfg):
    result = DocumentResult(doc_id="INV-1003.txt")
    inv = extract(raw("INV-1003.txt"), DocType.INVOICE, MockLLM(), cfg, result)
    assert inv.invoice_number == "IN-2231" and inv.vendor_tax_id == "77-1200345"
    assert inv.total == 1054.70 and inv.tax == 59.70  # "1,054.70" parsed
    assert [(l.sku, l.quantity) for l in inv.lines] == [("SENS-T1", 100), ("CABLE-2M", 50)]
    assert result.extraction_confidence == 1.0


def test_us_dates_are_normalised_by_client_config(cfg):
    inv = extract(raw("INV-1002.txt"), DocType.INVOICE, MockLLM(), cfg, DocumentResult(doc_id="x"))
    assert str(inv.invoice_date) == "2026-10-05" and str(inv.due_date) == "2026-11-04"
    assert normalize_dates({"invoice_date": "31.12.2026"}, ["%d.%m.%Y"]) == {"invoice_date": "2026-12-31"}


def test_json_documents_skip_the_llm(cfg):
    class ExplodingLLM:
        name = "boom"

        def classify(self, *a):
            raise AssertionError("LLM must not be called for JSON")

        extract = classify

    result = DocumentResult(doc_id="INV-1004.json")
    doc_type = classify(raw("INV-1004.json"), ExplodingLLM(), cfg, result)
    inv = extract(raw("INV-1004.json"), doc_type, ExplodingLLM(), cfg, result)
    assert doc_type is DocType.INVOICE and inv.po_number == "PO-5004"


def test_repair_retry_sends_validation_errors_back(cfg):
    class LearningLLM(MockLLM):
        name = "learning"

        def __init__(self):
            self.feedback = []

        def extract(self, text, doc_type, schema, feedback=None):
            self.feedback.append(feedback)
            data = super().extract(text, doc_type, schema)
            return data if feedback else {k: v for k, v in data.items() if k != "total"}

    llm = LearningLLM()
    result = DocumentResult(doc_id="INV-1001.txt")
    inv = extract(raw("INV-1001.txt"), DocType.INVOICE, llm, cfg, result)
    assert inv is not None and inv.total == 200.09
    assert llm.feedback[0] is None and "total: Field required" in llm.feedback[1]
    assert [e.ok for e in result.trace] == [False, True]


def test_unreadable_scan_becomes_extraction_failed(cfg):
    result = DocumentResult(doc_id="scan_0042.txt")
    assert extract(raw("scan_0042.txt"), DocType.INVOICE, MockLLM(), cfg, result) is None
    assert [i.code for i in result.issues] == ["EXTRACTION_FAILED"]


def test_low_classification_confidence_is_flagged(cfg):
    class UnsureLLM(MockLLM):
        def classify(self, text, labels):
            return {"label": "invoice", "confidence": 0.55, "rationale": "smudged header"}

    result = DocumentResult(doc_id="x.txt")
    classify(RawDocument("x.txt", "???"), UnsureLLM(), cfg, result)
    assert [i.code for i in result.issues] == ["LOW_CONFIDENCE"]
