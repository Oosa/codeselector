"""
Base parser contract for CodeSelector language plugins.

Every language parser must:
  1. Subclass BaseParser
  2. Declare EXTENSIONS — the file suffixes it handles
  3. Implement collect() — return list[Entity] for a given file

Parsers are thin: they only collect raw entities.
All query matching / filtering / scope resolution stays in codeselector.py.

Entity extras (stored as __dict__ keys with _ prefix):
  _ext          str   — file extension without dot
  _lang         str   — "python" | "js" | "ts" | "php" | "css" | "scss"
  _is_async     bool  — func is async
  _args_count   int   — number of declared parameters
  _has_docstring bool — func/class has a leading doc comment
  _is_public    bool  — name does not start with _ (or # for private in JS/PHP)
  _module       str   — import module name
  _method       str   — short method name from a call (obj.method → method)
  _decorator_names list[str]  — decorator / annotation names on a func/class
  _visibility   str   — "public" | "private" | "protected" | "static" (PHP/JS)
  _return_type  str   — declared return type annotation (TS/PHP)
  _selector     str   — CSS selector string (css entities)
  _properties   list  — list of CSS property names inside a rule
"""

from __future__ import annotations
import os
import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Entity  (shared with codeselector.py — imported from here)
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    """A single code entity extracted from a source file."""
    file: str
    entity_type: str        # file|dir|class|func|var|call|import|decorator|
                            # rule|selector|mixin|prop  (CSS extras)
    entity_name: str
    parent_class: str | None
    line_start: int
    line_end: int
    node: Any = field(default=None, repr=False)
    source_lines: list[str] = field(default=None, repr=False)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self, modifier: str = "code") -> dict:
        base = {
            "file": self.file,
            "entity_type": self.entity_type,
            "entity_name": self.entity_name,
            "parent_class": self.parent_class,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }
        if modifier == "name":
            base["content"] = self.entity_name
        elif modifier == "lines":
            base["content"] = f"{self.line_start}-{self.line_end}"
        elif modifier == "loc":
            base["content"] = f"{self.file}:{self.line_start}-{self.line_end}"
        elif modifier == "count":
            pass
        elif modifier == "args":
            base["content"] = self.__dict__.get("_args_list", [])
        elif modifier == "docstring":
            base["content"] = self.__dict__.get("_docstring", "")
        else:
            base["content"] = self._extract_code()
        return base

    def _extract_code(self) -> str:
        if self.source_lines and self.line_start and self.line_end:
            lines = self.source_lines[self.line_start - 1: self.line_end]
            return "".join(lines).rstrip()
        return ""


# ---------------------------------------------------------------------------
# Helpers shared by all regex-based parsers
# ---------------------------------------------------------------------------

def read_file_safe(path: str) -> tuple[str | None, list[str]]:
    """Read a source file; return (source, lines) or (None, []) on error."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            src = fh.read()
        return src, src.splitlines(keepends=True)
    except OSError:
        return None, []


def make_file_entity(file_path: str, source_lines: list[str], lang: str) -> Entity:
    """Produce the top-level file Entity for any language."""
    ext = os.path.splitext(file_path)[1].lstrip(".")
    name = os.path.splitext(os.path.basename(file_path))[0]
    e = Entity(
        file=file_path, entity_type="file",
        entity_name=name, parent_class=None,
        line_start=1, line_end=max(1, len(source_lines)),
        node=None, source_lines=source_lines,
    )
    e.__dict__["_ext"]  = ext
    e.__dict__["_lang"] = lang
    return e


def end_of_block(lines: list[str], open_line: int, open_ch: str = "{", close_ch: str = "}") -> int:
    """
    Walk forward from open_line (1-based) and return the 1-based line number
    of the matching closing brace/bracket.

    We start counting from open_line and treat the first { as depth=1.
    Returns the line where depth reaches 0 again (closing brace).
    Falls back to len(lines) if never closed.
    """
    depth = 0
    started = False
    for i, raw in enumerate(lines[open_line - 1:], start=open_line):
        opens  = raw.count(open_ch)
        closes = raw.count(close_ch)
        # Ignore braces inside strings — heuristic: skip lines that look like CSS string values
        depth += opens - closes
        if opens > 0:
            started = True
        if started and depth <= 0:
            return i
    return len(lines)


def strip_comments_js(source: str) -> str:
    """Replace JS/TS comments with spaces — preserves line numbers and offsets."""
    def _blank_block(m):
        text = m.group(0)
        return re.sub(r"[^\n]", " ", text)
    source = re.sub(r"/\*.*?\*/", _blank_block, source, flags=re.DOTALL)
    source = re.sub(r"//[^\n]*", lambda m: " " * len(m.group(0)), source)
    return source


def strip_comments_php(source: str) -> str:
    source = re.sub(r"//[^\n]*", "", source)
    source = re.sub(r"#[^\n]*", "", source)
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    return source


def line_of_offset(source: str, offset: int) -> int:
    """Return 1-based line number for a character offset in source."""
    return source[:offset].count("\n") + 1


# ---------------------------------------------------------------------------
# BaseParser
# ---------------------------------------------------------------------------

class BaseParser:
    """
    Abstract base for all language parsers.

    Subclasses set EXTENSIONS and implement collect().
    They may override individual _collect_* helpers.
    """
    EXTENSIONS: list[str] = []   # e.g. [".js", ".mjs"]
    LANG: str = "unknown"

    # ------------------------------------------------------------------
    # Public interface used by the registry / codeselector
    # ------------------------------------------------------------------

    def can_parse(self, file_path: str) -> bool:
        ext = os.path.splitext(file_path)[1].lower()
        return ext in self.EXTENSIONS

    def collect(self, file_path: str) -> list[Entity]:
        """
        Parse file_path and return all Entity objects found.
        Always includes at least the file Entity itself.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Stubs — override in subclasses as needed
    # ------------------------------------------------------------------

    def _collect_functions(self, file_path, src, lines) -> list[Entity]:
        return []

    def _collect_classes(self, file_path, src, lines) -> list[Entity]:
        return []

    def _collect_vars(self, file_path, src, lines) -> list[Entity]:
        return []

    def _collect_imports(self, file_path, src, lines) -> list[Entity]:
        return []

    def _collect_calls(self, file_path, src, lines) -> list[Entity]:
        return []

    def _collect_decorators(self, file_path, src, lines) -> list[Entity]:
        return []

    # CSS extras
    def _collect_rules(self, file_path, src, lines) -> list[Entity]:
        return []

    def _collect_mixins(self, file_path, src, lines) -> list[Entity]:
        return []
