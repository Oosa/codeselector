"""
CSS / SCSS language parser for CodeSelector.
Handles: .css  .scss  .less

Entity mapping:
  class     →  CSS selector that contains a class  (.btn, .card-header)
  func      →  @mixin name(...)  /  @function name(...)  (SCSS)
  var       →  CSS custom property  --foo: val  /  $var: val (SCSS)
  import    →  @import "..."  /  @use "..." / @forward "..."
  rule      →  full selector block  (tag, id, compound)
  decorator →  @keyframes name  /  @media ...  /  @supports ...

The entity_name for a rule / class is the selector string (normalised).
"""

from __future__ import annotations
import re
from .base import (
    BaseParser, Entity, read_file_safe, make_file_entity,
    end_of_block, line_of_offset,
)

# ---------------------------------------------------------------------------
# Regex catalogue
# ---------------------------------------------------------------------------

# Strip comments  /* ... */
_RX_COMMENT = re.compile(r'/\*.*?\*/', re.DOTALL)
# Strip // comments (SCSS / Less)
_RX_COMMENT_LINE = re.compile(r'//[^\n]*')

# Selector rule: selector { ... }
# Captures everything up to the first {
_RX_RULE = re.compile(r'^([ \t]*)((?:[^{}@/\n][^{}\n]*)?)\{', re.M)

# @mixin / @function
_RX_MIXIN    = re.compile(r'@mixin\s+([\w-]+)\s*(?:\(([^)]*)\))?', re.M)
_RX_FUNCTION = re.compile(r'@function\s+([\w-]+)\s*(?:\(([^)]*)\))?', re.M)

# CSS custom properties / SCSS variables
_RX_CUSTOM_PROP = re.compile(r'(--[\w-]+)\s*:', re.M)
_RX_SCSS_VAR    = re.compile(r'^[ \t]*(\$[\w-]+)\s*:', re.M)

# @import / @use / @forward
_RX_IMPORT = re.compile(r'@(?:import|use|forward)\s+["\']([^"\']+)["\']', re.M)

# @keyframes / @media / @supports
_RX_AT_RULE = re.compile(r'(@(?:keyframes|media|supports|layer|container))\s+([^{]+)\{', re.M)

# Extract class selectors from a compound selector string
_RX_CLASS_SEL = re.compile(r'\.([\w-]+)')
# Extract id selectors
_RX_ID_SEL    = re.compile(r'#([\w-]+)')


class CSSParser(BaseParser):
    EXTENSIONS = [".css", ".scss", ".less"]
    LANG = "css"

    def collect(self, file_path: str) -> list[Entity]:
        source, lines = read_file_safe(file_path)
        if source is None:
            return []

        ext  = file_path.rsplit(".", 1)[-1].lower()
        lang = "scss" if ext in ("scss", "less") else "css"

        entities: list[Entity] = [make_file_entity(file_path, lines, lang)]
        # Replace comment content with spaces but KEEP newlines
        # so that line_of_offset() returns correct line numbers
        clean = _RX_COMMENT.sub(
            lambda m: re.sub(r"[^\n]", " ", m.group(0)), source
        )
        clean = _RX_COMMENT_LINE.sub(
            lambda m: " " * len(m.group(0)), clean
        )

        entities.extend(self._collect_at_rules(file_path, clean, lines, lang))
        entities.extend(self._collect_rules(file_path, clean, lines, lang))
        entities.extend(self._collect_mixins(file_path, clean, lines, lang))
        entities.extend(self._collect_vars(file_path, clean, lines, lang))
        entities.extend(self._collect_imports(file_path, clean, lines, lang))
        return entities

    # ------------------------------------------------------------------
    # @keyframes / @media / @supports  → stored as `decorator` entities
    # ------------------------------------------------------------------

    def _collect_at_rules(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        for m in _RX_AT_RULE.finditer(src):
            at_kw   = m.group(1)              # @keyframes
            at_name = m.group(2).strip()      # fadeIn / (max-width: 768px)
            ln      = line_of_offset(src, m.start())
            end     = end_of_block(lines, ln)
            e = Entity(
                file=file_path, entity_type="decorator",
                entity_name=at_name,
                parent_class=None,
                line_start=ln, line_end=end,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"]    = lang
            e.__dict__["_at_rule"] = at_kw
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Selector blocks  →  rule + class entities
    # ------------------------------------------------------------------

    def _collect_rules(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        seen_ln: set[int] = set()

        for m in _RX_RULE.finditer(src):
            selector = m.group(2).strip()
            if not selector:
                continue
            # Skip @-rule bodies already captured
            if selector.startswith("@"):
                continue
            ln = line_of_offset(src, m.start())
            if ln in seen_ln:
                continue
            seen_ln.add(ln)
            end = end_of_block(lines, ln)

            # Full rule entity
            e = Entity(
                file=file_path, entity_type="rule",
                entity_name=selector,
                parent_class=None,
                line_start=ln, line_end=end,
                node=None, source_lines=lines,
            )
            e.__dict__["_lang"]     = lang
            e.__dict__["_selector"] = selector
            entities.append(e)

            # Class entities for each .class-name in the selector
            for cls_m in _RX_CLASS_SEL.finditer(selector):
                cls_name = cls_m.group(1)
                ce = Entity(
                    file=file_path, entity_type="class",
                    entity_name=cls_name,
                    parent_class=None,
                    line_start=ln, line_end=end,
                    node=None, source_lines=lines,
                )
                ce.__dict__["_lang"]     = lang
                ce.__dict__["_selector"] = selector
                entities.append(ce)

        return entities

    # ------------------------------------------------------------------
    # @mixin / @function  →  func entities
    # ------------------------------------------------------------------

    def _collect_mixins(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        for rx, kind in ((_RX_MIXIN, "mixin"), (_RX_FUNCTION, "function")):
            for m in rx.finditer(src):
                name   = m.group(1)
                params = self._parse_params(m.group(2) or "")
                ln     = line_of_offset(src, m.start())
                end    = end_of_block(lines, ln)
                e = Entity(
                    file=file_path, entity_type="func",
                    entity_name=name,
                    parent_class=None,
                    line_start=ln, line_end=end,
                    node=None, source_lines=lines,
                )
                e.__dict__["_lang"]       = lang
                e.__dict__["_kind"]       = kind        # mixin | function
                e.__dict__["_args_count"] = len(params)
                e.__dict__["_args_list"]  = params
                e.__dict__["_is_async"]   = False
                e.__dict__["_is_public"]  = True
                entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Variables: CSS custom props + SCSS vars
    # ------------------------------------------------------------------

    def _collect_vars(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        seen: set[str] = set()
        for rx in (_RX_CUSTOM_PROP, _RX_SCSS_VAR):
            for m in rx.finditer(src):
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
                e.__dict__["_lang"] = lang
                entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Imports
    # ------------------------------------------------------------------

    def _collect_imports(self, file_path, src, lines, lang) -> list[Entity]:
        entities = []
        for m in _RX_IMPORT.finditer(src):
            module = m.group(1)
            ln = line_of_offset(src, m.start())
            e = Entity(
                file=file_path, entity_type="import",
                entity_name=module,
                parent_class=None,
                line_start=ln, line_end=ln,
                node=None, source_lines=lines,
            )
            e.__dict__["_module"] = module
            e.__dict__["_lang"]   = lang
            entities.append(e)
        return entities

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_params(self, raw: str) -> list[str]:
        params = []
        for part in raw.split(","):
            p = part.strip().split(":")[0].strip()
            if p:
                params.append(p)
        return params
