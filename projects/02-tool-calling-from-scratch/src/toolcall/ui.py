"""Plain-ASCII terminal boxes, so the trace looks good in any terminal (and on video)."""

import textwrap

WIDTH = 78


def banner(text: str) -> str:
    edge = "+" + "=" * (WIDTH - 2) + "+"
    return f"{edge}\n| {text:<{WIDTH - 4}} |\n{edge}"


def box(title: str, rows: list[tuple[str, str]]) -> str:
    """Draw a titled box. Each row is (label, text); long text wraps under itself."""
    top = f"+-- {title} ".ljust(WIDTH - 1, "-") + "+"
    label_width = max((len(label) for label, _ in rows), default=0)
    inner = WIDTH - 4
    lines = [top]
    for label, text in rows:
        prefix = f"{label:<{label_width}} : " if label else " " * (label_width + 3)
        wrapped = textwrap.wrap(text, inner - len(prefix)) or [""]
        for i, chunk in enumerate(wrapped):
            lead = prefix if i == 0 else " " * len(prefix)
            lines.append(f"| {lead + chunk:<{inner}} |")
    lines.append("+" + "-" * (WIDTH - 2) + "+")
    return "\n".join(lines)
