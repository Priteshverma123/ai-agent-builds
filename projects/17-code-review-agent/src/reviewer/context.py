"""Everything the checks need about one change: per file, the diff, the new text and changed lines."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .diff import FileDiff, apply_patch, parse_diff


@dataclass
class ChangedFile:
    diff: FileDiff
    new_text: str | None  # full post-change file, when it can be rebuilt
    added: dict[int, str]

    @property
    def path(self) -> str:
        return self.diff.path

    @property
    def is_python(self) -> bool:
        return self.path.endswith(".py")

    @property
    def is_test(self) -> bool:
        name = Path(self.path).name
        return name.startswith("test_") or name.endswith("_test.py") or "/tests/" in f"/{self.path}"


@dataclass
class ReviewContext:
    files: list[ChangedFile]

    @classmethod
    def from_diff(cls, diff_text: str, base_dir: Path | None = None) -> "ReviewContext":
        files = []
        for fd in parse_diff(diff_text):
            if fd.new_path is None:  # deleted files have nothing to review
                continue
            new_text = None
            if fd.is_new:
                new_text = "\n".join(text for _, text in sorted(fd.added().items())) + "\n"
            elif base_dir and (base_dir / fd.old_path).exists():  # type: ignore[operator]
                new_text = apply_patch((base_dir / fd.old_path).read_text(encoding="utf-8"), fd)  # type: ignore[operator]
            files.append(ChangedFile(fd, new_text, fd.added()))
        return cls(files)

    def file(self, path: str) -> ChangedFile | None:
        return next((f for f in self.files if f.path == path), None)
