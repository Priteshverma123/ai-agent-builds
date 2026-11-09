import json
import shutil

from intake.cli import main, run_pipeline
from intake.config import ClientConfig
from intake.domain.models import Status
from intake.services.evaluate import evaluate, load_golden

from conftest import EXAMPLES

MASTER = EXAMPLES / "master"
CLIENT = EXAMPLES / "clients" / "northwind.json"


def statuses(run) -> dict[str, str]:
    return {r.doc_id: r.status.value for r in run.results}


def test_end_to_end_run_writes_erp_exceptions_and_report(tmp_path):
    run = run_pipeline(EXAMPLES / "inbox", CLIENT, MASTER, tmp_path, provider="mock")
    assert [r.doc_id for r in run.by_status(Status.APPROVED)] == ["INV-1001.txt", "INV-1004.json"]

    erp = [json.loads(line) for line in (tmp_path / "erp_invoices.jsonl").read_text().splitlines()]
    assert erp[0]["DocumentNo"] == "A-88121" and erp[0]["DocumentDate"] == "02.10.2026"
    assert erp[0]["GLAccount"] == "5100-MRO" and len(erp[0]["Lines"]) == 2

    csv_lines = (tmp_path / "erp_invoice_lines.csv").read_text().splitlines()
    assert csv_lines[0].startswith("VendorAccount,DocumentNo") and len(csv_lines) == 5

    queue = [json.loads(line) for line in (tmp_path / "exceptions.jsonl").read_text().splitlines()]
    owners = {q["doc_id"]: q["owner"] for q in queue}
    assert owners["INV-1002.txt"] == "buyer" and owners["INV-1003.txt"] == "receiving"
    assert "2 / 9 (22%)" in (tmp_path / "run_report.md").read_text()


def test_golden_set_meets_acceptance(tmp_path, cfg):
    run = run_pipeline(EXAMPLES / "inbox", CLIENT, MASTER, tmp_path, provider="mock")
    report = evaluate(run.results, load_golden(EXAMPLES / "golden" / "expected.json"), cfg.acceptance)
    assert report.passed and report.mismatches == []


def test_eval_catches_a_regression(tmp_path, cfg):
    run = run_pipeline(EXAMPLES / "inbox", CLIENT, MASTER, tmp_path, provider="mock")
    golden = load_golden(EXAMPLES / "golden" / "expected.json")
    golden["INV-1001.txt"]["fields"]["total"] = 999.0           # one wrong field is still >= 98%...
    golden["INV-1004.json"]["fields"]["po_number"] = "PO-0000"   # ...two are not
    report = evaluate(run.results, golden, cfg.acceptance)
    assert report.metrics["field_accuracy"] < 1.0 and not report.passed
    assert "INV-1001.txt: total 200.09 != 999.0" in report.mismatches


def test_onboarding_a_different_client_is_config_only(tmp_path):
    """A looser client: 10% price tolerance and no PO requirement. Same code, different outcomes."""
    raw = json.loads(CLIENT.read_text())
    raw["tolerances"]["price_pct"] = 0.10
    raw["require_po"] = False
    raw["erp_mapping"]["date_format"] = "%Y%m%d"
    client = tmp_path / "loose.json"
    client.write_text(json.dumps(raw))
    run = run_pipeline(EXAMPLES / "inbox", client, MASTER, tmp_path / "out", provider="mock")
    assert statuses(run)["INV-1002.txt"] == "approved"
    inv_1005 = next(r for r in run.results if r.doc_id == "INV-1005.txt")
    assert [i.code for i in inv_1005.blocking] == ["UNKNOWN_VENDOR"]
    erp = (tmp_path / "out" / "erp_invoices.jsonl").read_text()
    assert '"DocumentDate": "20261002"' in erp


def test_same_invoice_twice_in_one_batch_is_paid_once(tmp_path):
    inbox = tmp_path / "inbox"
    shutil.copytree(EXAMPLES / "inbox", inbox)
    shutil.copy(inbox / "INV-1001.txt", inbox / "INV-1001b.txt")
    run = run_pipeline(inbox, CLIENT, MASTER, tmp_path / "out", provider="mock")
    second = next(r for r in run.results if r.doc_id == "INV-1001b.txt")
    assert [i.code for i in second.blocking] == ["DUPLICATE_INVOICE"]
    assert len(run.erp_records) == 2


def test_cli_eval_exit_code(tmp_path, capsys):
    assert main(["eval", "--out", str(tmp_path), "--provider", "mock"]) == 0
    assert "ACCEPTANCE: PASS" in capsys.readouterr().out
    assert ClientConfig.load(CLIENT).acceptance.decision_accuracy == 1.0
