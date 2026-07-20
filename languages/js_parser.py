"""
JavaScript / TypeScript language parser for CodeSelector.
Handles: .js  .mjs  .cjs  .ts  .tsx

Uses regex-based parsing — covers the 95% case without a full AST.
Entities extracted:
  func      — function foo(), const foo = () =>, async function, method shorthand
  class     — class Foo, class Foo extends Bar
  var       — const / let / var declarations
  import    — import ... from, require(...)
  call      — function/method calls
  decorator — @Decorator (TS decorators)
  export    — exported symbols (stored as extra attr _exported=true on existing entity)
"""

from __future__ import annotations
import os
import re
from .base import (
    BaseParser, Entity, read_file_safe, make_file_entity,
    end_of_block, strip_comments_js, line_of_offset,
)

# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------

# Functions
_RX_FUNC_DECL     = re.compile(r'^[ \t]*(export\s+)?(default\s+)?(async\s+)?function\s*\*?\s+(\w+)\s*\(([^)]*)\)', re.M)
_RX_FUNC_ARROW    = re.compile(r'^[ \t]*(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\(([^)]*)\)\s*=>', re.M)
_RX_FUNC_ARROW_1  = re.compile(r'^[ \t]*(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?(\w+)\s*=>', re.M)
_RX_METHOD        = re.compile(r'^[ \t]*(static\s+)?(async\s+)?(get\s+|set\s+)?([\w$]+)\s*\(([^)]*)\)\s*(?::\s*[\w<>\[\]|&?]+\s*)?\{', re.M)

# Classes
_RX_CLASS         = re.compile(r'^[ \t]*(export\s+)?(default\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?\s*\{', re.M)

# Variables (const/let/var at statement level)
_RX_VAR           = re.compile(r'^[ \t]*(export\s+)?(const|let|var)\s+(\w+)\s*=', re.M)

# Imports
_RX_IMPORT_FROM   = re.compile(r"^[ \t]*import\s+(?:type\s+)?(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)(?:\s*,\s*(?:\{[^}]*\}|\w+))*\s+from\s+['\"]([^'\"]+)['\"]", re.M)
_RX_IMPORT_BARE   = re.compile(r"^[ \t]*import\s+['\"]([^'\"]+)['\"]", re.M)
_RX_REQUIRE       = re.compile(r"(?:const|let|var)\s+(?:\{[^}]*\}|\w+)\s*=\s*require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", re.M)

# Calls
_RX_CALL          = re.compile(r'(\b[\w$]+(?:\.[\w$]+)*)\s*\(', re.M)

# TS Decorators
_RX_DECORATOR     = re.compile(r'^[ \t]*@([\w.]+)', re.M)

# TS type annotations — return type
_RX_RETURN_TYPE   = re.compile(r'\)\s*:\s*([\w<>\[\]|&?]+)')

# Named import symbols
_RX_IMPORT_NAMES  = re.compile(r"import\s+(?:type\s+)?\{([^}]+)\}\s+from\s+['\"]([^'\"]+)['\"]", re.M)


class JSParser(BaseParser):
    EXTENSIONS = [".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"]
    LANG = "js"

    def collect(self, file_path: str) -> list[Entity]:
        source, lines = read_file_safe(file_path)
        if source is None:
            return []

        # Mark .ts files
        ext = os.path.splitext(file_path)[1].lower()
        lang = "ts" if ext in (".ts", ".tsx") else "js"

        entities: list[Entity] = [make_file_entity(file_path, lines, lang)]
        entities[-1].__dict__["_lang"] = lang

        clean = strip_comments_js(source)

        entities.extend(self._collect_classes(file_path, clean, lines, lang))
        entities.extend(self._collect_functions(file_path, clean, lines, lang))
        entities.extend(self._collect_vars_only(file_path, clean, lines, lang))
        entities.extend(self._collect_imports(file_path, clean, lines, lang))
        entities.extend(self._collect_calls_js(file_path, clean, lines, lang))
        entities.extend(self._collect_decorators_js(file_path, source, lines, lang))
        return entities

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _collect_classes(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        # Track class ranges so we can assign parent_class to methods
        for m in _RX_CLASS.finditer(src):
            name = m.group(3)
            ln   = line_of_offset(src, m.start())
            end  = end_of_block(lines, ln)
            e = Entity(
                file=file_path, entity_type="class",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=end,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"]       = lang
            e.__dict__["_exported"]   = bool(m.group(1))
            e.__dict__["_extends"]    = m.group(4) or ""
            e.__dict__["_has_docstring"] = False
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Functions
    # ------------------------------------------------------------------

    def _collect_functions(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        seen_offsets: set[int] = set()

        # function declarations
        for m in _RX_FUNC_DECL.finditer(src):
            off = m.start()
            if off in seen_offsets:
                continue
            seen_offsets.add(off)
            name      = m.group(4)
            is_async  = bool(m.group(3))
            params    = self._parse_params(m.group(5))
            ln        = line_of_offset(src, off)
            end       = end_of_block(lines, ln)
            parent    = self._find_parent_class(src, off, lines)
            e = self._make_func(file_path, name, params, is_async, ln, end, parent, lines, lang)
            e.__dict__["_exported"] = bool(m.group(1))
            entities.append(e)

        # arrow functions with parens: const foo = async (a, b) =>
        for m in _RX_FUNC_ARROW.finditer(src):
            off = m.start()
            if off in seen_offsets:
                continue
            seen_offsets.add(off)
            name     = m.group(3)
            is_async = bool(m.group(4))
            params   = self._parse_params(m.group(5))
            ln       = line_of_offset(src, off)
            end      = end_of_block(lines, ln)
            parent   = self._find_parent_class(src, off, lines)
            e = self._make_func(file_path, name, params, is_async, ln, end, parent, lines, lang)
            e.__dict__["_exported"] = bool(m.group(1))
            entities.append(e)

        # arrow functions with single arg: const foo = x =>
        for m in _RX_FUNC_ARROW_1.finditer(src):
            off = m.start()
            if off in seen_offsets:
                continue
            seen_offsets.add(off)
            name     = m.group(3)
            is_async = bool(m.group(4))
            params   = [m.group(5)]
            ln       = line_of_offset(src, off)
            end      = end_of_block(lines, ln)
            parent   = self._find_parent_class(src, off, lines)
            e = self._make_func(file_path, name, params, is_async, ln, end, parent, lines, lang)
            e.__dict__["_exported"] = bool(m.group(1))
            entities.append(e)

        # Class method shorthand
        for m in _RX_METHOD.finditer(src):
            off  = m.start()
            name = m.group(4)
            # Skip keywords that look like methods
            if name in ("if", "for", "while", "switch", "catch", "function",
                        "class", "return", "else", "try"):
                continue
            if off in seen_offsets:
                continue
            seen_offsets.add(off)
            is_async = bool(m.group(2))
            params   = self._parse_params(m.group(5))
            ln       = line_of_offset(src, off)
            end      = end_of_block(lines, ln)
            parent   = self._find_parent_class(src, off, lines)
            if parent is None:
                continue   # method-like outside class → skip to avoid noise
            e = self._make_func(file_path, name, params, is_async, ln, end, parent, lines, lang)
            e.__dict__["_static"] = bool(m.group(1))
            entities.append(e)

        return entities

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _collect_vars_only(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        seen: set[str] = set()
        for m in _RX_VAR.finditer(src):
            name = m.group(3)
            if name in seen:
                continue
            # Skip if this looks like a function declaration
            rest = src[m.end():m.end() + 30].lstrip()
            if rest.startswith("function") or rest.startswith("(") or rest.startswith("async"):
                continue
            seen.add(name)
            ln = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="var",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"]     = lang
            e.__dict__["_exported"] = bool(m.group(1))
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _collect_imports(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []

        # import { a, b } from 'mod'  →  emit one entity per name
        for m in _RX_IMPORT_NAMES.finditer(src):
            module = m.group(2)
            names_raw = m.group(1)
            ln = line_of_offset(src, m.start())
            for part in names_raw.split(","):
                name = part.strip().split(" as ")[-1].strip()
                if name:
                    e = self._make_import(file_path, name, module, ln, lines, lang)
                    entities.append(e)

        # import Foo from 'mod'  or  import * as Foo from 'mod'
        for m in _RX_IMPORT_FROM.finditer(src):
            module = m.group(1)
            ln = line_of_offset(src, m.start())
            # simple default import name
            raw = m.group(0)
            name_m = re.search(r"import\s+(?:type\s+)?(\w+)", raw)
            if name_m and name_m.group(1) not in ("type", "as", "from"):
                name = name_m.group(1)
                e = self._make_import(file_path, name, module, ln, lines, lang)
                entities.append(e)

        # import 'side-effect'
        for m in _RX_IMPORT_BARE.finditer(src):
            module = m.group(1)
            ln = line_of_offset(src, m.start())
            e = self._make_import(file_path, module, module, ln, lines, lang)
            entities.append(e)

        # require('mod')
        for m in _RX_REQUIRE.finditer(src):
            module = m.group(1)
            ln = line_of_offset(src, m.start())
            e = self._make_import(file_path, module, module, ln, lines, lang)
            entities.append(e)

        return entities

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _collect_calls_js(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        skip_kw = {"if", "for", "while", "switch", "catch", "function",
                   "class", "return", "typeof", "instanceof", "new", "import", "require"}
        for m in _RX_CALL.finditer(src):
            raw  = m.group(1)
            name = raw.strip()
            base = name.split(".")[0]
            if base in skip_kw:
                continue
            ln = line_of_offset(src, m.start())
            method = name.split(".")[-1] if "." in name else ""
            e = Entity(
                file=file_path, entity_type="call",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_method"] = method
            e.__dict__["_lang"]   = lang
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Decorators (TypeScript)
    # ------------------------------------------------------------------

    def _collect_decorators_js(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        for m in _RX_DECORATOR.finditer(src):
            name = m.group(1)
            ln   = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="decorator",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"] = lang
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_func(self, file_path, name, params, is_async, ln, end, parent, lines, lang) -> Entity:
        e = Entity(
            file=file_path, entity_type="func",
            entity_name=name, parent_class=parent,
            line_start=ln, line_end=end,
            node=None, source_lines=lines,
        )
        e.__dict__["_is_async"]      = is_async
        e.__dict__["_args_count"]    = len(params)
        e.__dict__["_args_list"]     = params
        e.__dict__["_has_docstring"] = False
        e.__dict__["_is_public"]     = not name.startswith("_") and not name.startswith("#")
        e.__dict__["_lang"]          = lang
        return e

    def _make_import(self, file_path, name, module, ln, lines, lang) -> Entity:
        e = Entity(
            file=file_path, entity_type="import",
            entity_name=name, parent_class=None,
            line_start=ln, line_end=ln,
            node=None, source_lines=lines,
        )
        e.__dict__["_module"] = module
        e.__dict__["_lang"]   = lang
        return e

    def _parse_params(self, raw: str) -> list[str]:
        """Split a raw parameter string into a clean list."""
        params = []
        for part in raw.split(","):
            p = part.strip()
            # strip TS type: name: Type = default → name
            p = re.split(r"[=:]", p)[0].strip()
            # strip destructuring, rest, defaults
            p = p.lstrip("...").strip("{").strip()
            if p:
                params.append(p)
        return params

    def _find_parent_class(self, src: str, offset: int, lines: list[str]) -> str | None:
        """Walk backward in source to find enclosing class name, if any."""
        before = src[:offset]
        # Find the last class declaration before this offset
        matches = list(_RX_CLASS.finditer(before))
        if not matches:
            return None
        last = matches[-1]
        class_name = last.group(3)
        class_line = line_of_offset(src, last.start())
        class_end  = end_of_block(lines, class_line)
        this_line  = line_of_offset(src, offset)
        if class_line <= this_line <= class_end:
            return class_name
        return None
