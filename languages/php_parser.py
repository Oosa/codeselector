"""
PHP language parser for CodeSelector.
Handles: .php

Extracts:
  func       — function foo(...)  and  fn($x) => expr
  class      — class, abstract class, interface, trait
  var        — $variable assignments at statement level
  import     — require / require_once / include / use Namespace
  call       — function/method calls
  decorator  — PHP 8 Attributes  #[Attribute]
  property   — class property declarations (public/protected/private $prop)

PHP visibility keywords are stored in _visibility extra.
"""

from __future__ import annotations
import os
import re
from .base import (
    BaseParser, Entity, read_file_safe, make_file_entity,
    end_of_block, strip_comments_php, line_of_offset,
)

# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------

# Functions
_RX_FUNC = re.compile(
    r'^[ \t]*((?:(?:public|protected|private|static|abstract|final)\s+)*)'
    r'function\s+(&\s*)?(\w+)\s*\(([^)]*)\)',
    re.M,
)

# Anonymous / arrow functions assigned to variable
_RX_FUNC_VAR = re.compile(
    r'^[ \t]*(\$\w+)\s*=\s*(?:static\s+)?function\s*\(([^)]*)\)',
    re.M,
)

# Classes / interfaces / traits / abstract classes
_RX_CLASS = re.compile(
    r'^[ \t]*(abstract\s+|final\s+)?(?:class|interface|trait)\s+(\w+)'
    r'(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w, \\]+)?\s*\{',
    re.M,
)

# Properties
_RX_PROP = re.compile(
    r'^[ \t]*((?:(?:public|protected|private|static|readonly)\s+)+)(?:\?\w+\s+)?(\$\w+)',
    re.M,
)

# Variable assignments  $foo = ...
_RX_VAR = re.compile(r'^\s*(\$\w+)\s*=(?!=)', re.M)

# Imports / use
_RX_USE       = re.compile(r'^[ \t]*use\s+([\w\\]+(?:\s*,\s*[\w\\]+)*)\s*;', re.M)
_RX_REQUIRE   = re.compile(r"(?:require|include)(?:_once)?\s*\(?['\"]([^'\"]+)['\"]", re.M)

# Calls
_RX_CALL = re.compile(r'(\b[\w\\]+(?:::[\w]+|->[\w]+)*)\s*\(', re.M)

# PHP 8 Attributes
_RX_ATTR = re.compile(r'^[ \t]*#\[\s*([\w\\]+)', re.M)


class PHPParser(BaseParser):
    EXTENSIONS = [".php"]
    LANG = "php"

    def collect(self, file_path: str) -> list[Entity]:
        source, lines = read_file_safe(file_path)
        if source is None:
            return []

        entities: list[Entity] = [make_file_entity(file_path, lines, self.LANG)]
        clean = strip_comments_php(source)

        entities.extend(self._collect_classes(file_path, clean, lines))
        entities.extend(self._collect_functions(file_path, clean, lines))
        entities.extend(self._collect_properties(file_path, clean, lines))
        entities.extend(self._collect_vars(file_path, clean, lines))
        entities.extend(self._collect_imports(file_path, clean, lines))
        entities.extend(self._collect_calls_php(file_path, clean, lines))
        entities.extend(self._collect_attributes(file_path, source, lines))
        return entities

    # ------------------------------------------------------------------
    # Classes
    # ------------------------------------------------------------------

    def _collect_classes(self, file_path, src, lines) -> list[Entity]:
        entities = []
        for m in _RX_CLASS.finditer(src):
            name     = m.group(2)
            modifier = (m.group(1) or "").strip()
            ln       = line_of_offset(src, m.start())
            end      = end_of_block(lines, ln)
            e = Entity(
                file=file_path, entity_type="class",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=end,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"]        = self.LANG
            e.__dict__["_modifier"]    = modifier          # abstract | final | ""
            e.__dict__["_extends"]     = m.group(3) or ""
            e.__dict__["_has_docstring"] = False
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Functions / Methods
    # ------------------------------------------------------------------

    def _collect_functions(self, file_path, src, lines) -> list[Entity]:
        entities = []
        seen: set[int] = set()

        # Named functions and methods
        for m in _RX_FUNC.finditer(src):
            off  = m.start()
            if off in seen:
                continue
            seen.add(off)
            modifiers = m.group(1).lower()
            name      = m.group(3)
            params    = self._parse_params(m.group(4))
            ln        = line_of_offset(src, off)
            end       = end_of_block(lines, ln)
            parent    = self._find_parent_class(src, off, lines)

            e = self._make_func(file_path, name, params, modifiers, ln, end, parent, lines)
            entities.append(e)

        # $foo = function(...) — anonymous assigned to variable
        for m in _RX_FUNC_VAR.finditer(src):
            off = m.start()
            if off in seen:
                continue
            seen.add(off)
            name   = m.group(1)           # $varName
            params = self._parse_params(m.group(2))
            ln     = line_of_offset(src, off)
            end    = end_of_block(lines, ln)
            parent = self._find_parent_class(src, off, lines)
            e = self._make_func(file_path, name, params, "", ln, end, parent, lines)
            entities.append(e)

        return entities

    # ------------------------------------------------------------------
    # Class properties
    # ------------------------------------------------------------------

    def _collect_properties(self, file_path, src, lines) -> list[Entity]:
        entities = []
        for m in _RX_PROP.finditer(src):
            modifiers = m.group(1).lower().strip()
            name      = m.group(2)                  # $propName
            ln        = line_of_offset(src, m.start())
            parent    = self._find_parent_class(src, m.start(), lines)
            e = Entity(
                file=file_path, entity_type="var",
                entity_name=name, parent_class=parent,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"]       = self.LANG
            e.__dict__["_visibility"] = self._visibility(modifiers)
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Variables
    # ------------------------------------------------------------------

    def _collect_vars(self, file_path, src, lines) -> list[Entity]:
        entities = []
        seen: set[str] = set()
        for m in _RX_VAR.finditer(src):
            name = m.group(1)
            if name in seen:
                continue
            seen.add(name)
            ln = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="var",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"] = self.LANG
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _collect_imports(self, file_path, src, lines) -> list[Entity]:
        entities = []
        for m in _RX_USE.finditer(src):
            for part in m.group(1).split(","):
                ns = part.strip()
                name = ns.split("\\")[-1]
                ln = line_of_offset(src, m.start())
                e = Entity(
                    file=file_path, entity_type="import",
                    entity_name=name, parent_class=None,
                    line_start=ln, line_end=ln,
                    node=None, source_lines=lines,
                )
                e.__dict__["_module"] = ns
                e.__dict__["_lang"]   = self.LANG
                entities.append(e)
        for m in _RX_REQUIRE.finditer(src):
            module = m.group(1)
            ln = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="import",
                entity_name=os.path.basename(module),
                parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_module"] = module
            e.__dict__["_lang"]   = self.LANG
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Calls
    # ------------------------------------------------------------------

    def _collect_calls_php(self, file_path, src, lines) -> list[Entity]:
        entities = []
        skip = {"if", "for", "foreach", "while", "switch", "catch",
                "function", "class", "return", "echo", "print",
                "elseif", "list", "array", "match"}
        for m in _RX_CALL.finditer(src):
            raw  = m.group(1)
            # resolve -> and :: to short method name
            if "->" in raw:
                method = raw.split("->")[-1]
            elif "::" in raw:
                method = raw.split("::")[-1]
            else:
                method = raw
            base = raw.split("->")[0].split("::")[0].lstrip("$")
            if base in skip:
                continue
            ln = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="call",
                entity_name=raw, parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_method"] = method
            e.__dict__["_lang"]   = self.LANG
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # PHP 8 Attributes  #[Attribute]
    # ------------------------------------------------------------------

    def _collect_attributes(self, file_path, src, lines) -> list[Entity]:
        entities = []
        for m in _RX_ATTR.finditer(src):
            name = m.group(1)
            ln   = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="decorator",
                entity_name=name, parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"] = self.LANG
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _make_func(self, file_path, name, params, modifiers, ln, end, parent, lines) -> Entity:
        e = Entity(
            file=file_path, entity_type="func",
            entity_name=name, parent_class=parent,
            line_start=ln, line_end=end,
            node=None, source_lines=lines,
        )
        e.__dict__["_lang"]        = self.LANG
        e.__dict__["_args_count"]  = len(params)
        e.__dict__["_args_list"]   = params
        e.__dict__["_visibility"]  = self._visibility(modifiers)
        e.__dict__["_is_async"]    = False
        e.__dict__["_is_public"]   = "private" not in modifiers and "protected" not in modifiers
        e.__dict__["_has_docstring"] = False
        e.__dict__["_static"]      = "static" in modifiers
        return e

    def _visibility(self, modifiers: str) -> str:
        if "private" in modifiers:
            return "private"
        if "protected" in modifiers:
            return "protected"
        if "public" in modifiers:
            return "public"
        return "public"   # PHP default

    def _parse_params(self, raw: str) -> list[str]:
        params = []
        for part in raw.split(","):
            p = part.strip()
            # strip type hints:  int $foo = 0  →  $foo
            tokens = p.split()
            for tok in reversed(tokens):
                if tok.startswith("$"):
                    p = tok.rstrip(")")
                    break
            else:
                p = tokens[-1] if tokens else ""
            if p:
                params.append(p)
        return params

    def _find_parent_class(self, src: str, offset: int, lines: list[str]) -> str | None:
        before = src[:offset]
        matches = list(_RX_CLASS.finditer(before))
        if not matches:
            return None
        last = matches[-1]
        ln   = line_of_offset(src, last.start())
        end  = end_of_block(lines, ln)
        this = line_of_offset(src, offset)
        if ln <= this <= end:
            return last.group(2)
        return None
