"""
Language Registry for CodeSelector.

Usage:
    from languages import registry
    entities = registry.collect(file_path)
    parsers  = registry.parsers_for(file_path)   # list of parser instances

Adding a new language:
    1. Create languages/mylang_parser.py with class MyLangParser(BaseParser)
    2. Add it to PARSER_CLASSES below — the registry picks it up automatically.

Multi-parser files:
    Some file types are handled by more than one parser.
    E.g. .php → [PHPParser, CSSParser-not-needed] but could be
         .vue  → [JSParser, CSSParser]
    Configure via MULTI_PARSERS dict below.
"""

from __future__ import annotations
import os

from .base import Entity, BaseParser
from .python_parser import PythonParser
from .js_parser import JSParser
from .php_parser import PHPParser
from .css_parser import CSSParser

# ---------------------------------------------------------------------------
# Single-parser mapping  ext → parser class
# (order matters: first match wins for single-parser lookup)
# ---------------------------------------------------------------------------

PARSER_CLASSES: list[type[BaseParser]] = [
    PythonParser,
    JSParser,
    PHPParser,
    CSSParser,
]

# ---------------------------------------------------------------------------
# Multi-parser mapping  ext → [parser classes]
# Files listed here are parsed by ALL parsers in the list, and results merged.
# ---------------------------------------------------------------------------

MULTI_PARSERS: dict[str, list[type[BaseParser]]] = {
    # Vue SFC: template(HTML-like) + script(JS/TS) + style(CSS/SCSS)
    ".vue":  [JSParser, CSSParser],
    # Svelte: similar to Vue
    ".svelte": [JSParser, CSSParser],
    # JSX: JS + HTML-like syntax
    ".jsx":  [JSParser],
    # TSX: TS + HTML-like
    ".tsx":  [JSParser],
}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class LanguageRegistry:
    """
    Central coordinator: maps file extensions to parser instances.

    Parsers are instantiated once and reused (they are stateless).
    """

    def __init__(self):
        # Instantiate all parsers once
        self._instances: dict[type[BaseParser], BaseParser] = {
            cls: cls() for cls in PARSER_CLASSES
        }
        # Build ext → [parsers] index
        self._ext_map: dict[str, list[BaseParser]] = {}

        for cls in PARSER_CLASSES:
            inst = self._instances[cls]
            for ext in cls.EXTENSIONS:
                self._ext_map.setdefault(ext.lower(), []).append(inst)

        # Register multi-parser overrides
        for ext, classes in MULTI_PARSERS.items():
            self._ext_map[ext.lower()] = [
                self._instances.get(cls) or cls()
                for cls in classes
            ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parsers_for(self, file_path: str) -> list[BaseParser]:
        """Return the list of parsers that handle this file."""
        ext = os.path.splitext(file_path)[1].lower()
        return self._ext_map.get(ext, [])

    def can_parse(self, file_path: str) -> bool:
        return len(self.parsers_for(file_path)) > 0

    def collect(self, file_path: str) -> list[Entity]:
        """
        Parse file_path with all applicable parsers.
        Merge entities; deduplicate by (entity_type, entity_name, line_start).
        """
        parsers = self.parsers_for(file_path)
        if not parsers:
            return []

        all_entities: list[Entity] = []
        seen: set[tuple] = set()

        for parser in parsers:
            for e in parser.collect(file_path):
                key = (e.entity_type, e.entity_name, e.line_start)
                if key not in seen:
                    seen.add(key)
                    all_entities.append(e)

        return all_entities

    def supported_extensions(self) -> list[str]:
        return sorted(self._ext_map.keys())

    def language_of(self, file_path: str) -> str:
        parsers = self.parsers_for(file_path)
        if parsers:
            return parsers[0].LANG
        return "unknown"


# Singleton instance used by codeselector.py
registry = LanguageRegistry()

__all__ = ["registry", "LanguageRegistry", "BaseParser", "Entity"]
