"""Command line.

    python demo.py                                   # story: v1 vs baseline, then v2 vs baseline
    python demo.py run --agent v2 --baseline examples/baseline.json   # CI mode: exits 0 / 1 / 2
    python demo.py run --agent v1 --save-baseline examples/baseline.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .agent import SupportAgent
from .compare import Exit, GateResult, gate
from .config import load_settings
from .llm import MockJudgeLLM, MockSupportLLM, llm_from_env
from .report import banner, markdown, results_table, summary
from .runner import RunResult, run_suite
from .suite import load_suite

ROOT = Path(__file__).resolve().parents[2]


def evaluate(agent_version: str, suite_path: Path, baseline_path: Path | None, trials: int = 1,
             out_dir: Path | None = None) -> tuple[RunResult, GateResult]:
    suite = load_suite(suite_path)
    agent = SupportAgent(llm_from_env(MockSupportLLM(agent_version)), max_steps=load_settings().max_steps)
    run = run_suite(suite, agent, judge=MockJudgeLLM(), trials=trials)
    baseline = None
    if baseline_path and baseline_path.exists():
        baseline = RunResult.from_dict(json.loads(baseline_path.read_text(encoding="utf-8")))
    result = gate(run, baseline, suite.pass_threshold)
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"results-{agent_version}.json").write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")
        (out_dir / f"report-{agent_version}.md").write_text(markdown(run, result), encoding="utf-8")
    return run, result


def show(title: str, run: RunResult, result: GateResult) -> None:
    print(banner(title))
    print(results_table(run, result))
    print(summary(run, result))
    print()


def _display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix() if path.is_relative_to(ROOT) else str(path)


def story() -> None:
    settings = load_settings()
    out = settings.out_dir
    run, result = evaluate("v1", settings.suite, settings.baseline, settings.trials, out_dir=out)
    show("v1 (released) vs baseline", run, result)
    run, result = evaluate("v2", settings.suite, settings.baseline, settings.trials, out_dir=out)
    show("v2 (new prompt: 'friendlier') vs baseline", run, result)
    print(f"  reports written to {_display(out)}/  |  in CI, `python demo.py run --agent v2` would exit "
          f"{int(result.exit)}")


def main(argv: list[str] | None = None) -> None:
    settings = load_settings()
    parser = argparse.ArgumentParser(description="Agent evals harness")
    sub = parser.add_subparsers(dest="cmd")
    run_cmd = sub.add_parser("run", help="evaluate one agent version and exit with the gate code")
    run_cmd.add_argument("--agent", choices=["v1", "v2"], default="v1")
    run_cmd.add_argument("--suite", type=Path, default=settings.suite)
    run_cmd.add_argument("--baseline", type=Path, default=settings.baseline)
    run_cmd.add_argument("--no-baseline", action="store_true", help="only check the absolute threshold")
    run_cmd.add_argument("--save-baseline", type=Path, help="write this run as the new baseline")
    run_cmd.add_argument("--trials", type=int, default=settings.trials, help="repeat each case to detect flaky behaviour")
    run_cmd.add_argument("--out", type=Path, default=settings.out_dir)
    args = parser.parse_args(argv)

    if args.cmd is None:
        story()
        return
    baseline = None if args.no_baseline or args.save_baseline else args.baseline
    run, result = evaluate(args.agent, args.suite, baseline, args.trials, args.out)
    show(f"{args.agent} on {args.suite.name}", run, result)
    if args.save_baseline:
        args.save_baseline.write_text(json.dumps(run.to_dict(), indent=2), encoding="utf-8")
        print(f"  baseline saved to {args.save_baseline}")
        sys.exit(int(Exit.OK))
    sys.exit(int(result.exit))
