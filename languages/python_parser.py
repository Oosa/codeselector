"""
Python language parser for CodeSelector.
Handles: .py, .pyw
Uses Python's built-in `ast` module for precise parsing.
"""

from __future__ import annotations
import ast
import os
from .base import BaseParser, Entity, read_file_safe, make_file_entity


class PythonParser(BaseParser):
    EXTENSIONS = [".py", ".pyw"]
    LANG = "python"

    def collect(self, file_path: str) -> list[Entity]:
        source, lines = read_file_safe(file_path)
        if source is None:
            return []
        tree = self._parse_ast(source)
        if tree is None:
            return []

        entities: list[Entity] = []

        # File entity
        fe = make_file_entity(file_path, lines, self.LANG)
        entities.append(fe)

        # Imports
        entities.extend(self._collect_imports(file_path, source, lines, tree))

        # Top-level functions
        entities.extend(self._collect_functions_in_scope(None, tree, file_path, lines, None))

        # Classes + their methods
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                ce = self._make_class_entity(node, file_path, lines)
                entities.append(ce)
                entities.extend(self._collect_decorators_of(node, file_path, node.name, lines))
                entities.extend(self._collect_functions_in_scope(node, node, file_path, lines, node.name))

        # Top-level variables
        entities.extend(self._collect_vars(file_path, source, lines, tree))

        # Calls
        entities.extend(self._collect_calls(file_path, source, lines, tree))

        return entities

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _parse_ast(self, source: str) -> ast.Module | None:
        try:
            return ast.parse(source)
        except SyntaxError:
            return None

    def _make_class_entity(self, node: ast.ClassDef, file_path: str, lines: list[str]) -> Entity:
        e = Entity(
            file=file_path, entity_type="class",
            entity_name=node.name, parent_class=None,
            line_start=node.lineno, line_end=node.end_lineno or node.lineno,
            node=node, source_lines=lines,
        )
        e.__dict__["_has_docstring"] = bool(ast.get_docstring(node))
        e.__dict__["_lang"] = self.LANG
        return e

    def _collect_functions_in_scope(self, class_node, scope, file_path, lines, parent_class):
        entities = []
        for node in getattr(scope, "body", []):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                e = self._make_func_entity(node, file_path, lines, parent_class)
                entities.append(e)
                entities.extend(self._collect_decorators_of(node, file_path, parent_class, lines))
        return entities

    def _make_func_entity(self, node, file_path, lines, parent_class) -> Entity:
        e = Entity(
            file=file_path, entity_type="func",
            entity_name=node.name, parent_class=parent_class,
            line_start=node.lineno, line_end=node.end_lineno or node.lineno,
            node=node, source_lines=lines,
        )
        is_async = isinstance(node, ast.AsyncFunctionDef)
        args = node.args
        arg_names = [a.arg for a in args.args]
        if args.vararg:
            arg_names.append("*" + args.vararg.arg)
        if args.kwarg:
            arg_names.append("**" + args.kwarg.arg)
        doc = ast.get_docstring(node) or ""

        e.__dict__["_is_async"]        = is_async
        e.__dict__["_args_count"]      = len(args.args)
        e.__dict__["_args_list"]       = arg_names
        e.__dict__["_has_docstring"]   = bool(doc)
        e.__dict__["_docstring"]       = doc
        e.__dict__["_is_public"]       = not node.name.startswith("_")
        e.__dict__["_decorator_names"] = self._decorator_names(node)
        e.__dict__["_lang"]            = self.LANG
        return e

    def _decorator_names(self, node) -> list[str]:
        names = []
        for dec in getattr(node, "decorator_list", []):
            if isinstance(dec, ast.Name):
                names.append(dec.id)
            elif isinstance(dec, ast.Attribute):
                names.append(dec.attr)
            elif isinstance(dec, ast.Call):
                inner = dec.func
                n = inner.id if isinstance(inner, ast.Name) else \
                    (inner.attr if isinstance(inner, ast.Attribute) else "")
                if n:
                    names.append(n)
        return names

    def _collect_decorators_of(self, node, file_path, parent_class, lines) -> list[Entity]:
        entities = []
        for dec in getattr(node, "decorator_list", []):
            name = ""
            if isinstance(dec, ast.Name):
                name = dec.id
            elif isinstance(dec, ast.Attribute):
                name = dec.attr
            elif isinstance(dec, ast.Call):
                inner = dec.func
                name = inner.id if isinstance(inner, ast.Name) else \
                       (inner.attr if isinstance(inner, ast.Attribute) else "")
            if name:
                e = Entity(
                    file=file_path, entity_type="decorator",
                    entity_name=name, parent_class=parent_class,
                    line_start=dec.lineno, line_end=getattr(dec, "end_lineno", dec.lineno),
                    node=dec, source_lines=lines,
                )
                e.__dict__["_lang"] = self.LANG
                entities.append(e)
        return entities

    def _collect_imports(self, file_path, source, lines, tree=None) -> list[Entity]:
        if tree is None:
            tree = self._parse_ast(source)
            if tree is None:
                return []
        entities = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    e = Entity(
                        file=file_path, entity_type="import",
                        entity_name=alias.asname or alias.name,
                        parent_class=None,
                        line_start=node.lineno, line_end=getattr(node, "end_lineno", node.lineno),
                        node=node, source_lines=lines,
                    )
                    e.__dict__["_module"] = alias.name
                    e.__dict__["_lang"]   = self.LANG
                    entities.append(e)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    e = Entity(
                        file=file_path, entity_type="import",
                        entity_name=alias.asname or alias.name,
                        parent_class=None,
                        line_start=node.lineno, line_end=getattr(node, "end_lineno", node.lineno),
                        node=node, source_lines=lines,
                    )
                    e.__dict__["_module"] = module
                    e.__dict__["_lang"]   = self.LANG
                    entities.append(e)
        return entities

    def _collect_vars(self, file_path, source, lines, tree=None) -> list[Entity]:
        if tree is None:
            tree = self._parse_ast(source)
            if tree is None:
                return []
        entities = []
        for child in ast.walk(tree):
            if isinstance(child, (ast.Assign, ast.AnnAssign)):
                targets = child.targets if isinstance(child, ast.Assign) else [child.target]
                for t in targets:
                    name = t.id if isinstance(t, ast.Name) else \
                           (t.attr if isinstance(t, ast.Attribute) else "")
                    if name:
                        e = Entity(
                            file=file_path, entity_type="var",
                            entity_name=name, parent_class=None,
                            line_start=child.lineno,
                            line_end=getattr(child, "end_lineno", child.lineno),
                            node=child, source_lines=lines,
                        )
                        e.__dict__["_lang"] = self.LANG
                        entities.append(e)
        return entities

    def _collect_calls(self, file_path, source, lines, tree=None) -> list[Entity]:
        if tree is None:
            tree = self._parse_ast(source)
            if tree is None:
                return []
        entities = []
        for child in ast.walk(tree):
            if isinstance(child, ast.Call):
                func = child.func
                name = method = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    try:
                        name = f"{ast.unparse(func.value)}.{func.attr}"
                    except Exception:
                        name = func.attr
                    method = func.attr
                if name:
                    e = Entity(
                        file=file_path, entity_type="call",
                        entity_name=name, parent_class=None,
                        line_start=child.lineno,
                        line_end=getattr(child, "end_lineno", child.lineno),
                        node=child, source_lines=lines,
                    )
                    e.__dict__["_method"] = method
                    e.__dict__["_lang"]   = self.LANG
                    entities.append(e)
        return entities
