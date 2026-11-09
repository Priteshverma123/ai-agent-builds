"""AST checks on the full post-change file, reported only where they touch changed lines.

Parsing the whole file (not the hunk) gives real structure: we know a string is an f-string that
flows into `.execute()`, not just that a line "looks like SQL". Filtering to changed lines keeps
the review about *this* change; old problems belong in a separate clean-up, not in this PR.
"""

from __future__ import annotations

import ast

from ..context import ChangedFile, ReviewContext
from ..findings import Finding, Severity

COMPLEXITY_LIMIT = 8
BRANCHES = (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.IfExp, ast.BoolOp, ast.comprehension, ast.Match)


def _is_dynamic_string(node: ast.AST) -> bool:
    """f-strings, "..." % x, "...".format(x) and "..." + x all build strings from data."""
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(v, ast.FormattedValue) for v in node.values)
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mod, ast.Add)):
        return True
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr == "format")


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        base = func.value.id if isinstance(func.value, ast.Name) else "?"
        return f"{base}.{func.attr}"
    return ""


class _Visitor(ast.NodeVisitor):
    def __init__(self, f: ChangedFile) -> None:
        self.f = f
        self.findings: list[Finding] = []
        self.assignments: dict[str, ast.AST] = {}  # variable -> value, to follow `q = f"..."; execute(q)`

    def report(self, node: ast.AST, rule: str, sev: Severity, conf: float, msg: str, fix: str) -> None:
        line = getattr(node, "lineno", 0)
        if line in self.f.added:
            self.findings.append(Finding(rule, sev, conf, self.f.path, line, msg, fix))

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                self.assignments[target.id] = node.value
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        if name in ("eval", "exec"):
            self.report(node, "eval-exec", Severity.CRITICAL, 0.9, f"{name}() runs arbitrary code from its input.",
                        "Parse the input explicitly (ast.literal_eval or a small grammar).")
        elif name in ("pickle.loads", "pickle.load", "marshal.loads"):
            self.report(node, "unsafe-deserialization", Severity.HIGH, 0.85,
                        f"{name}() on untrusted data allows remote code execution.", "Use JSON or a signed format.")
        elif name == "yaml.load" and "Loader" not in kwargs:
            self.report(node, "unsafe-yaml", Severity.HIGH, 0.85, "yaml.load without a safe Loader.",
                        "Use yaml.safe_load().")
        elif name.startswith("subprocess.") and isinstance(kwargs.get("shell"), ast.Constant) \
                and kwargs["shell"].value is True:
            self.report(node, "shell-injection", Severity.HIGH, 0.8, "subprocess with shell=True and a built command.",
                        "Pass an argument list and drop shell=True.")
        elif name.endswith((".execute", ".executemany")) and node.args:
            query = node.args[0]
            if isinstance(query, ast.Name):
                query = self.assignments.get(query.id, query)
            if _is_dynamic_string(query):
                self.report(node, "sql-injection", Severity.HIGH, 0.9, "SQL built from a formatted string.",
                            "Use placeholders: conn.execute('... WHERE status = ?', (status,)).")
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for default in node.args.defaults + node.args.kw_defaults:
            if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                self.report(default, "mutable-default", Severity.MEDIUM, 0.9,
                            f"Mutable default argument in {node.name}(); it is shared between calls.",
                            "Default to None and create the list/dict inside the function.")
        complexity = 1 + sum(isinstance(n, BRANCHES) for n in ast.walk(node))
        span = range(node.lineno, (node.end_lineno or node.lineno) + 1)
        if complexity > COMPLEXITY_LIMIT and any(line in self.f.added for line in span):
            self.findings.append(Finding("complexity", Severity.MEDIUM, 0.6, self.f.path, node.lineno,
                                         f"{node.name}() has complexity {complexity} (limit {COMPLEXITY_LIMIT}).",
                                         "Split it into smaller functions."))
        saved = dict(self.assignments)
        self.generic_visit(node)
        self.assignments = saved

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        swallowed = all(isinstance(stmt, ast.Pass) for stmt in node.body)
        if node.type is None or swallowed:
            what = "Bare except" if node.type is None else "Exception swallowed with pass"
            self.report(node, "swallowed-exception", Severity.MEDIUM, 0.75, f"{what} hides real errors.",
                        "Catch the specific exception and log or re-raise it.")
        self.generic_visit(node)


def check_python(ctx: ReviewContext) -> list[Finding]:
    findings = []
    for f in ctx.files:
        if not f.is_python or f.new_text is None:
            continue
        try:
            tree = ast.parse(f.new_text)
        except SyntaxError as exc:
            line = exc.lineno or 1
            findings.append(Finding("syntax-error", Severity.CRITICAL, 1.0, f.path, line,
                                    f"File does not parse: {exc.msg}.", "Fix the syntax error."))
            continue
        visitor = _Visitor(f)
        visitor.visit(tree)
        findings.extend(visitor.findings)
    return findings
