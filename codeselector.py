"""
CodeSelector — AST-based code search engine for Python projects.

Usage (CLI):
    python codeselector.py "class[name*='Order'] > func[async='true']" ./my_project
    python codeselector.py "func[name='get_user']:name" .
    python codeselector.py "self:callers" . --file services/order.py --line 45

Usage (Python API):
    from codeselector import search, resolve

    results = search("class[name='User'] > func", root="./src")
    results = search("func[async='true']:name", root=".")
    results = resolve(file_path="services/order.py", line=45, modifier="callers", root=".")

Response structure:
    {
        "status": "success" | "error",
        "query": "original query string",
        "matches_count": 3,
        "results": [
            {
                "file": "services/order_service.py",
                "entity_type": "func",
                "entity_name": "calculate_total",
                "parent_class": "OrderService",   # null if top-level
                "line_start": 40,
                "line_end": 52,
                "content": "def calculate_total(...): ..."  # depends on modifier
            }
        ],
        "errors": []
    }

Syntax reference:
    TAGS:        file, dir, class, func, var, call, import, decorator, return
    ATTRIBUTES:  [name="x"]  [name*="x"]  [name^="x"]  [name$="x"]
                 [ext="py"]  [async="true"]  [has_docstring="true"]
                 [args>="3"] [args="0"]  [is_public="true"]
                 [module="os"]  [method="append"]
    COMBINATORS: space (descendant)   > (direct child)   , (OR)
    PSEUDO:      :not([attr="x"])   :has(child_selector)
    MODIFIERS:   :code  :name  :lines  :args  :count  :loc  :docstring
    SELF:        self  self:callers  self:callees  self > func  self var
"""

import ast
import os
import re
import sys
import json
import argparse
from dataclasses import dataclass, field
from typing import Any

# Language registry (parsers for Python, JS, TS, PHP, CSS, SCSS)
try:
    from languages import registry as _lang_registry
    from languages.base import Entity as _LangEntity
    _MULTI_LANG = True
except ImportError:
    _MULTI_LANG = False


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Entity:
    """A single matched code entity."""
    file: str
    entity_type: str          # file, dir, class, func, var, call, import, decorator
    entity_name: str
    parent_class: str | None
    line_start: int
    line_end: int
    node: Any = field(default=None, repr=False)   # raw ast node, not serialised
    source_lines: list[str] = field(default=None, repr=False)

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
            pass  # handled at result-builder level
        elif modifier == "args":
            base["content"] = self._extract_args()
        elif modifier == "docstring":
            base["content"] = self._extract_docstring()
        else:  # "code" (default)
            base["content"] = self._extract_code()
        return base

    def _extract_code(self) -> str:
        if self.source_lines and self.line_start and self.line_end:
            lines = self.source_lines[self.line_start - 1 : self.line_end]
            return "".join(lines).rstrip()
        return ""

    def _extract_docstring(self) -> str:
        if self.node and isinstance(self.node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return ast.get_docstring(self.node) or ""
        return ""

    def _extract_args(self) -> list[str]:
        if self.node and isinstance(self.node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = self.node.args
            names = [a.arg for a in args.args]
            if args.vararg:
                names.append("*" + args.vararg.arg)
            if args.kwarg:
                names.append("**" + args.kwarg.arg)
            return names
        return []


# ---------------------------------------------------------------------------
# Query parser — turns a selector string into a list of rule chains
# ---------------------------------------------------------------------------

@dataclass
class AttrFilter:
    name: str
    op: str      # = ^ $ * > (for numeric comparisons)
    value: str

@dataclass
class SelectorPart:
    tag: str
    attrs: list[AttrFilter]
    combinator: str   # " " descendant, ">" direct child
    pseudo_not: list["SelectorPart"] = field(default_factory=list)
    pseudo_has: list["SelectorPart"] = field(default_factory=list)

@dataclass
class ParsedQuery:
    chains: list[list[SelectorPart]]  # comma-separated → multiple chains
    modifier: str    # code | name | lines | args | count | loc | docstring
    is_self: bool
    self_pseudo: str  # callers | callees | "" (plain self)


def parse_attr_string(raw: str) -> list[AttrFilter]:
    """Parse everything between the first [ and matching ]s from the tag."""
    filters = []
    for m in re.finditer(r'\[([^\]]+)\]', raw):
        content = m.group(1)
        match = re.match(r'([a-zA-Z_]+)\s*(\*=|\^=|\$=|>=|<=|!=|=)\s*["\']?([^"\']*)["\']?', content)
        if match:
            filters.append(AttrFilter(match.group(1), match.group(2), match.group(3)))
    return filters


def parse_pseudo(raw: str, pseudo: str) -> list[AttrFilter] | list:
    """Extract inner selector of :not(...) or :has(...)."""
    pattern = rf':{pseudo}\(([^)]+)\)'
    m = re.search(pattern, raw)
    if not m:
        return []
    return parse_selector_chain(m.group(1))


def extract_modifier(selector: str) -> tuple[str, str]:
    """Split trailing :modifier from selector string. Returns (selector, modifier)."""
    modifier_pattern = r':(code|name|lines|args|count|loc|docstring)\s*$'
    m = re.search(modifier_pattern, selector)
    if m:
        return selector[:m.start()].strip(), m.group(1)
    return selector.strip(), "code"


def parse_selector_chain(chain_str: str) -> list[SelectorPart]:
    """Parse a single selector chain (no commas) into SelectorPart list."""
    # Split on combinators while preserving them
    # We tokenise by scanning character by character
    tokens = []
    current = ""
    depth = 0
    for ch in chain_str:
        if ch in "([":
            depth += 1
            current += ch
        elif ch in ")]":
            depth -= 1
            current += ch
        elif ch == ">" and depth == 0:
            if current.strip():
                tokens.append(("part", current.strip()))
            tokens.append(("comb", ">"))
            current = ""
        elif ch == " " and depth == 0 and current.strip():
            tokens.append(("part", current.strip()))
            current = ""
        else:
            current += ch
    if current.strip():
        tokens.append(("part", current.strip()))

    parts = []
    pending_combinator = " "
    for kind, value in tokens:
        if kind == "comb":
            pending_combinator = ">"
        else:
            # Extract tag (everything before first [ or :not or :has)
            tag_match = re.match(r'^([a-zA-Z_*]+)', value)
            tag = tag_match.group(1) if tag_match else "*"

            attrs = parse_attr_string(value)
            not_parts = parse_pseudo(value, "not")
            has_parts = parse_pseudo(value, "has")

            parts.append(SelectorPart(
                tag=tag,
                attrs=attrs,
                combinator=pending_combinator,
                pseudo_not=not_parts if isinstance(not_parts, list) else [],
                pseudo_has=has_parts if isinstance(has_parts, list) else [],
            ))
            pending_combinator = " "
    return parts


def parse_query(raw_query: str) -> ParsedQuery:
    """Full query parsing entry point."""
    raw_query = raw_query.strip()

    # Handle self keyword
    is_self = raw_query.startswith("self")
    self_pseudo = ""
    if is_self:
        m = re.match(r'^self:(callers|callees)', raw_query)
        if m:
            self_pseudo = m.group(1)
            raw_query = raw_query[m.end():].strip()
        else:
            raw_query = raw_query[4:].strip()  # strip "self"

    # Extract trailing modifier
    raw_query, modifier = extract_modifier(raw_query)

    # Split on top-level commas (OR operator)
    chains = []
    current = ""
    depth = 0
    for ch in raw_query:
        if ch in "([":
            depth += 1
            current += ch
        elif ch in ")]":
            depth -= 1
            current += ch
        elif ch == "," and depth == 0:
            chains.append(parse_selector_chain(current.strip()))
            current = ""
        else:
            current += ch
    if current.strip():
        chains.append(parse_selector_chain(current.strip()))

    return ParsedQuery(
        chains=chains,
        modifier=modifier,
        is_self=is_self,
        self_pseudo=self_pseudo,
    )


# ---------------------------------------------------------------------------
# AST collectors — extract all entities from a single Python file
# ---------------------------------------------------------------------------

def read_file_safe(path: str) -> tuple[str | None, list[str]]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            source = f.read()
        return source, source.splitlines(keepends=True)
    except Exception:
        return None, []


def parse_ast_safe(source: str) -> ast.Module | None:
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def collect_imports(tree: ast.Module, file_path: str, source_lines: list[str]) -> list[Entity]:
    entities = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                entities.append(Entity(
                    file=file_path, entity_type="import",
                    entity_name=alias.asname or alias.name,
                    parent_class=None,
                    line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                    node=node, source_lines=source_lines,
                ))
                # store module name separately so [module=] works
                entities[-1].__dict__["_module"] = alias.name
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                e = Entity(
                    file=file_path, entity_type="import",
                    entity_name=alias.asname or alias.name,
                    parent_class=None,
                    line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                    node=node, source_lines=source_lines,
                )
                e.__dict__["_module"] = module
                entities.append(e)
    return entities


def collect_variables(node: ast.AST, file_path: str, parent_class: str | None,
                      source_lines: list[str]) -> list[Entity]:
    entities = []
    for child in ast.walk(node):
        if isinstance(child, (ast.Assign, ast.AnnAssign)):
            targets = child.targets if isinstance(child, ast.Assign) else [child.target]
            for t in targets:
                name = ""
                if isinstance(t, ast.Name):
                    name = t.id
                elif isinstance(t, ast.Attribute):
                    name = t.attr
                if name:
                    entities.append(Entity(
                        file=file_path, entity_type="var",
                        entity_name=name, parent_class=parent_class,
                        line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno),
                        node=child, source_lines=source_lines,
                    ))
    return entities


def collect_decorators(func_or_class: ast.AST, file_path: str, parent_class: str | None,
                       source_lines: list[str]) -> list[Entity]:
    entities = []
    for dec in getattr(func_or_class, "decorator_list", []):
        if isinstance(dec, ast.Name):
            name = dec.id
        elif isinstance(dec, ast.Attribute):
            name = dec.attr
        elif isinstance(dec, ast.Call):
            inner = dec.func
            name = inner.id if isinstance(inner, ast.Name) else (inner.attr if isinstance(inner, ast.Attribute) else "")
        else:
            name = ""
        if name:
            entities.append(Entity(
                file=file_path, entity_type="decorator",
                entity_name=name, parent_class=parent_class,
                line_start=dec.lineno, line_end=getattr(dec, "end_lineno", dec.lineno),
                node=dec, source_lines=source_lines,
            ))
    return entities


def collect_calls(node: ast.AST, file_path: str, parent_class: str | None,
                  source_lines: list[str]) -> list[Entity]:
    entities = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            name = ""
            method = ""
            if isinstance(func, ast.Name):
                name = func.id
            elif isinstance(func, ast.Attribute):
                name = f"{ast.unparse(func.value)}.{func.attr}" if hasattr(ast, "unparse") else func.attr
                method = func.attr
            if name:
                e = Entity(
                    file=file_path, entity_type="call",
                    entity_name=name, parent_class=parent_class,
                    line_start=child.lineno, line_end=getattr(child, "end_lineno", child.lineno),
                    node=child, source_lines=source_lines,
                )
                e.__dict__["_method"] = method
                entities.append(e)
    return entities


def _decorator_names_list(func_node: ast.AST) -> list:
    names = []
    for dec in getattr(func_node, "decorator_list", []):
        if isinstance(dec, ast.Name):
            names.append(dec.id)
        elif isinstance(dec, ast.Attribute):
            names.append(dec.attr)
        elif isinstance(dec, ast.Call):
            inner = dec.func
            names.append(inner.id if isinstance(inner, ast.Name) else
                         (inner.attr if isinstance(inner, ast.Attribute) else ""))
    return [n for n in names if n]


def collect_functions(class_node: ast.ClassDef | None, scope: ast.AST,
                      file_path: str, source_lines: list[str],
                      parent_class: str | None) -> list[Entity]:
    entities = []
    body = getattr(scope, "body", [])
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_entity = Entity(
                file=file_path, entity_type="func",
                entity_name=node.name, parent_class=parent_class,
                line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                node=node, source_lines=source_lines,
            )
            func_entity.__dict__["_is_async"] = isinstance(node, ast.AsyncFunctionDef)
            func_entity.__dict__["_args_count"] = len(node.args.args)
            func_entity.__dict__["_has_docstring"] = bool(ast.get_docstring(node))
            func_entity.__dict__["_is_public"] = not node.name.startswith("_")
            func_entity.__dict__["_decorator_names"] = _decorator_names_list(node)
            entities.append(func_entity)
            # decorators of this function (stored as child entities)
            entities.extend(collect_decorators(node, file_path, parent_class, source_lines))
    return entities


def collect_file_entities(file_path: str) -> list[Entity]:
    """Main collector: returns all entities from one Python file."""
    source, source_lines = read_file_safe(file_path)
    if source is None:
        return []
    tree = parse_ast_safe(source)
    if tree is None:
        return []

    entities: list[Entity] = []

    # File entity itself
    file_entity = Entity(
        file=file_path, entity_type="file",
        entity_name=os.path.splitext(os.path.basename(file_path))[0],
        parent_class=None,
        line_start=1, line_end=len(source_lines),
        node=tree, source_lines=source_lines,
    )
    file_entity.__dict__["_ext"] = os.path.splitext(file_path)[1].lstrip(".")
    entities.append(file_entity)

    # Top-level imports
    entities.extend(collect_imports(tree, file_path, source_lines))

    # Top-level functions
    entities.extend(collect_functions(None, tree, file_path, source_lines, parent_class=None))

    # Classes and their methods
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_entity = Entity(
                file=file_path, entity_type="class",
                entity_name=node.name, parent_class=None,
                line_start=node.lineno, line_end=node.end_lineno or node.lineno,
                node=node, source_lines=source_lines,
            )
            class_entity.__dict__["_has_docstring"] = bool(ast.get_docstring(node))
            entities.append(class_entity)
            # class decorators
            entities.extend(collect_decorators(node, file_path, node.name, source_lines))
            # methods
            entities.extend(collect_functions(node, node, file_path, source_lines, parent_class=node.name))

    # Variables (top-level only to avoid explosion)
    entities.extend(collect_variables(tree, file_path, parent_class=None, source_lines=source_lines))

    # Calls (top-level and inside functions — walk the whole tree)
    entities.extend(collect_calls(tree, file_path, parent_class=None, source_lines=source_lines))

    return entities


# ---------------------------------------------------------------------------
# File system walker
# ---------------------------------------------------------------------------

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache", ".pytest_cache"}


def walk_python_files(root: str) -> list[str]:
    """Yield all .py file paths under root."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune dirs we never want to enter
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            if fname.endswith(".py"):
                found.append(os.path.join(dirpath, fname))
    return found


def collect_dir_entities(root: str) -> list[Entity]:
    """Return dir entities for all directories under root."""
    entities = []
    for dirpath, dirnames, _ in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for d in dirnames:
            full = os.path.join(dirpath, d)
            entities.append(Entity(
                file=full, entity_type="dir",
                entity_name=d, parent_class=None,
                line_start=0, line_end=0,
                node=None, source_lines=[],
            ))
    return entities


# ---------------------------------------------------------------------------
# Attribute matching — small single-purpose functions
# ---------------------------------------------------------------------------

def match_text_op(value: str, op: str, target: str) -> bool:
    """Apply CSS text operator against a value."""
    if op == "=":
        return value == target
    if op == "*=":
        return target in value
    if op == "^=":
        return value.startswith(target)
    if op == "$=":
        return value.endswith(target)
    if op == "!=":
        return value != target
    return False


def match_numeric_op(value: int, op: str, target: str) -> bool:
    try:
        n = int(target)
    except ValueError:
        return False
    if op == ">=":
        return value >= n
    if op == "<=":
        return value <= n
    if op == "=":
        return value == n
    return False


def entity_attr_value(entity: Entity, attr_name: str) -> str | int | bool | None:
    """Extract a named attribute value from an entity for comparison."""
    extras = entity.__dict__
    if attr_name == "name":
        return entity.entity_name
    if attr_name == "ext":
        return extras.get("_ext", "")
    if attr_name == "async":
        return "true" if extras.get("_is_async") else "false"
    if attr_name == "has_docstring":
        return "true" if extras.get("_has_docstring") else "false"
    if attr_name == "is_public":
        return "true" if extras.get("_is_public") else "false"
    if attr_name == "args":
        return extras.get("_args_count", 0)
    if attr_name == "module":
        return extras.get("_module", "")
    if attr_name == "method":
        return extras.get("_method", "")
    if attr_name == "lang":
        return extras.get("_lang", "")
    if attr_name == "exported":
        return "true" if extras.get("_exported") else "false"
    if attr_name == "visibility":
        return extras.get("_visibility", "public")
    if attr_name == "static":
        return "true" if extras.get("_static") else "false"
    if attr_name == "extends":
        return extras.get("_extends", "")
    return None


def match_attr_filter(entity: Entity, f: AttrFilter) -> bool:
    """Check a single [attr op value] filter against an entity."""
    val = entity_attr_value(entity, f.name)
    if val is None:
        return False
    if f.op in (">=", "<=") or (f.op == "=" and isinstance(val, int)):
        return match_numeric_op(val, f.op, f.value)
    return match_text_op(str(val), f.op, f.value)


def match_all_attrs(entity: Entity, attrs: list[AttrFilter]) -> bool:
    return all(match_attr_filter(entity, a) for a in attrs)


# ---------------------------------------------------------------------------
# Selector part matching
# ---------------------------------------------------------------------------

def entity_matches_part(entity: Entity, part: SelectorPart) -> bool:
    """Check if entity matches one SelectorPart (tag + all attrs + pseudos)."""
    # Tag check
    if part.tag not in ("*", entity.entity_type):
        return False

    # All attribute filters
    if not match_all_attrs(entity, part.attrs):
        return False

    return True


def entities_in_scope(all_entities: list[Entity], parent: Entity) -> list[Entity]:
    """Return entities that are descendants of parent (same file, within line range).

    For func entities, decorators appear *before* the def line in source but are
    logically part of the function. We extend the effective start to include any
    decorator that sits immediately above the function (up to 10 lines before).
    """
    if parent.entity_type == "dir":
        return [e for e in all_entities
                if e.file.startswith(parent.file + os.sep) or e.file.startswith(parent.file + "/")]
    # For func/class, extend upper bound to catch decorators above the def line
    effective_start = parent.line_start
    if parent.entity_type in ("func", "class"):
        effective_start = max(1, parent.line_start - 10)
    return [e for e in all_entities
            if e.file == parent.file
            and e.line_start >= effective_start
            and e.line_end <= parent.line_end
            and e is not parent]


def entities_direct_children(all_entities: list[Entity], parent: Entity) -> list[Entity]:
    """Return direct children only (e.g. methods of a class, not nested classes)."""
    if parent.entity_type in ("class",):
        # direct children: same file, same parent_class
        return [e for e in all_entities
                if e.file == parent.file
                and e.parent_class == parent.entity_name
                and e is not parent]
    if parent.entity_type == "file":
        # direct children: same file, no parent class
        return [e for e in all_entities
                if e.file == parent.file
                and e.parent_class is None
                and e is not parent]
    return entities_in_scope(all_entities, parent)


# ---------------------------------------------------------------------------
# Chain executor — resolves one selector chain against entity pool
# ---------------------------------------------------------------------------

def execute_chain(chain: list[SelectorPart], all_entities: list[Entity],
                  scope: list[Entity] | None = None) -> list[Entity]:
    """
    Evaluate a selector chain left-to-right.
    Returns matched entities for the final (rightmost) part.
    """
    if not chain:
        return []

    # Start with all entities (or provided scope)
    candidates = scope if scope is not None else all_entities

    # First part — filter from candidates
    first = chain[0]
    matched = [e for e in candidates if entity_matches_part(e, first)]

    if len(chain) == 1:
        return matched

    # Subsequent parts
    final_matches = []
    for i in range(1, len(chain)):
        part = chain[i]
        next_matched = []
        for parent in matched:
            if part.combinator == ">":
                children = entities_direct_children(all_entities, parent)
            else:  # descendant
                children = entities_in_scope(all_entities, parent)
            for child in children:
                if entity_matches_part(child, part):
                    if child not in next_matched:
                        next_matched.append(child)
        matched = next_matched

    return matched


# ---------------------------------------------------------------------------
# Pseudo-class filters :has() and :not()
# ---------------------------------------------------------------------------

def apply_pseudo_has(entities: list[Entity], has_chains: list[list[SelectorPart]],
                     all_entities: list[Entity]) -> list[Entity]:
    """Keep only entities that have at least one descendant matching has_chains."""
    if not has_chains:
        return entities
    result = []
    for entity in entities:
        for chain in has_chains:
            scope = entities_in_scope(all_entities, entity)
            if execute_chain(chain, all_entities, scope):
                result.append(entity)
                break
    return result


def apply_pseudo_not(entities: list[Entity], not_chains: list[list[SelectorPart]],
                     all_entities: list[Entity]) -> list[Entity]:
    """Remove entities that match any of the not_chains."""
    if not not_chains:
        return entities
    result = []
    for entity in entities:
        excluded = False
        for chain in not_chains:
            # For :not() — check if entity itself matches a simple part
            if chain and entity_matches_part(entity, chain[0]) and match_all_attrs(entity, chain[0].attrs):
                excluded = True
                break
        if not excluded:
            result.append(entity)
    return result


# ---------------------------------------------------------------------------
# Self / resolver
# ---------------------------------------------------------------------------

def normalize_path(path: str) -> str:
    """Normalize path for consistent comparison."""
    return os.path.normpath(path)


def resolve_entity_at(file_path: str, line: int, all_entities: list[Entity]) -> Entity | None:
    """Find the deepest entity at the given file:line."""
    norm = normalize_path(file_path)
    candidates = [
        e for e in all_entities
        if normalize_path(e.file) == norm
        and e.entity_type in ("func", "class")
        and e.line_start <= line <= e.line_end
    ]
    if not candidates:
        return None
    # deepest = shortest span
    return min(candidates, key=lambda e: e.line_end - e.line_start)


def find_callers(target: Entity, all_entities: list[Entity]) -> list[Entity]:
    """Find all call entities that call target.entity_name anywhere in the project."""
    name = target.entity_name
    return [
        e for e in all_entities
        if e.entity_type == "call"
        and (e.entity_name == name or e.__dict__.get("_method") == name)
    ]


def find_callees(target: Entity, all_entities: list[Entity]) -> list[Entity]:
    """Find all call entities inside target's body."""
    target_norm = normalize_path(target.file)
    return [
        e for e in all_entities
        if e.entity_type == "call"
        and normalize_path(e.file) == target_norm
        and e.line_start >= target.line_start
        and e.line_end <= target.line_end
    ]


# ---------------------------------------------------------------------------
# Result builder
# ---------------------------------------------------------------------------

def build_response(query_str: str, results: list[Entity], modifier: str,
                   resolved_self: Entity | None = None,
                   errors: list[str] | None = None) -> dict:
    if modifier == "count":
        return {
            "status": "success",
            "query": query_str,
            "matches_count": len(results),
            "results": [{"count": len(results)}],
            "resolved_self": resolved_self.to_dict() if resolved_self else None,
            "errors": errors or [],
        }
    return {
        "status": "success",
        "query": query_str,
        "matches_count": len(results),
        "results": [e.to_dict(modifier) for e in results],
        "resolved_self": resolved_self.to_dict("loc") if resolved_self else None,
        "errors": errors or [],
    }


def build_error(query_str: str, message: str) -> dict:
    return {
        "status": "error",
        "query": query_str,
        "matches_count": 0,
        "results": [],
        "resolved_self": None,
        "errors": [message],
    }


# ---------------------------------------------------------------------------
# Main search function
# ---------------------------------------------------------------------------

def walk_all_files(root: str) -> list[str]:
    """Yield all source files known to the language registry."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fname in filenames:
            found.append(os.path.join(dirpath, fname))
    return found


def collect_all_entities(root: str) -> list[Entity]:
    """Collect entities from ALL supported languages under root.

    Python files → Python AST parser (legacy path, always available).
    JS/TS/PHP/CSS/SCSS files → language registry parsers.
    Unknown extensions → skipped.
    """
    entities = collect_dir_entities(root)

    if _MULTI_LANG:
        # Registry path: handles all languages
        for fpath in walk_all_files(root):
            ext = os.path.splitext(fpath)[1].lower()
            if ext == ".py":
                # Keep using the precise AST-based Python collector
                entities.extend(collect_file_entities(fpath))
            elif _lang_registry.can_parse(fpath):
                lang_entities = _lang_registry.collect(fpath)
                # Bridge: lang Entity → codeselector Entity (same dataclass shape)
                for le in lang_entities:
                    e = Entity(
                        file=le.file,
                        entity_type=le.entity_type,
                        entity_name=le.entity_name,
                        parent_class=le.parent_class,
                        line_start=le.line_start,
                        line_end=le.line_end,
                        node=le.node,
                        source_lines=le.source_lines,
                    )
                    # Copy all _extras
                    for k, v in le.__dict__.items():
                        if k.startswith("_"):
                            e.__dict__[k] = v
                    entities.append(e)
    else:
        # Fallback: Python only
        for py_file in walk_python_files(root):
            entities.extend(collect_file_entities(py_file))

    return entities


def search(query_str: str, root: str = ".",
           context_file: str | None = None,
           context_line: int | None = None) -> dict:
    """
    Main entry point for programmatic use.

    Args:
        query_str:    CodeSelector query string
        root:         project root directory to scan
        context_file: active file path (required when query uses `self`)
        context_line: active line number (required when query uses `self`)

    Returns:
        dict with status, matches_count, results, errors
    """
    all_entities = collect_all_entities(root)
    return _execute_query(query_str, all_entities, root, context_file, context_line)


def resolve(file_path: str, line: int, modifier: str = "loc", root: str = ".") -> dict:
    """
    Resolve what entity sits at file_path:line.

    Args:
        file_path: path to the file
        line:      line number (1-based)
        modifier:  result modifier (default: loc)
        root:      project root

    Returns:
        dict with the resolved entity
    """
    all_entities = collect_all_entities(root)
    entity = resolve_entity_at(file_path, line, all_entities)
    if not entity:
        return build_error(f"resolve:{file_path}:{line}",
                           f"No code entity found at {file_path}:{line}")
    return build_response(f"resolve:{file_path}:{line}", [entity], modifier)


def _execute_query(query_str: str, all_entities: list[Entity], root: str,
                   context_file: str | None, context_line: int | None) -> dict:
    """Internal: parse and execute query against pre-collected entities."""
    try:
        parsed = parse_query(query_str)
    except Exception as e:
        return build_error(query_str, f"Parse error: {e}")

    errors = []
    resolved_self: Entity | None = None

    # Handle self
    if parsed.is_self:
        if not context_file or not context_line:
            return build_error(query_str,
                               "Query uses `self` but no context_file / context_line provided.")
        resolved_self = resolve_entity_at(context_file, context_line, all_entities)
        if not resolved_self:
            return build_error(query_str,
                               f"Cannot resolve `self`: no entity found at {context_file}:{context_line}")

        if parsed.self_pseudo == "callers":
            results = find_callers(resolved_self, all_entities)
            return build_response(query_str, results, parsed.modifier, resolved_self, errors)
        if parsed.self_pseudo == "callees":
            results = find_callees(resolved_self, all_entities)
            return build_response(query_str, results, parsed.modifier, resolved_self, errors)

        # self as scope for further selector chains
        if not parsed.chains or all(not c for c in parsed.chains):
            return build_response(query_str, [resolved_self], parsed.modifier, resolved_self)

        scope = entities_in_scope(all_entities, resolved_self)
        all_results = []
        for chain in parsed.chains:
            matched = execute_chain(chain, all_entities, scope)
            for e in matched:
                if e not in all_results:
                    all_results.append(e)
        return build_response(query_str, all_results, parsed.modifier, resolved_self, errors)

    # Normal query — execute all chains and OR the results
    all_results = []
    for chain in parsed.chains:
        if not chain:
            continue
        matched = execute_chain(chain, all_entities)
        for e in matched:
            if e not in all_results:
                all_results.append(e)

    return build_response(query_str, all_results, parsed.modifier, errors=errors)



def inspect_method(method_name: str, root: str = ".") -> dict:
    """
    Full structural analysis of a method: source code, what it calls,
    and where it is called from across the project.

    Args:
        method_name:  exact function/method name to inspect
        root:         project root directory to scan

    Returns:
        {
          "status":      "success" | "error",
          "method_name": str,
          "root":        str,
          "definitions": [           # all occurrences of this method name
            {
              "file", "entity_name", "parent_class",
              "line_start", "line_end", "content"   # full source
            }
          ],
          "callees": [               # what the primary definition calls
            {
              "call_name":    str,   # full call expression e.g. "order.confirm"
              "method":       str,   # short name e.g. "confirm"
              "call_lines":   [int],
              "definitions":  [...]  # found in project (same shape as above)
            }
          ],
          "callers": [               # where this method is invoked
            {
              "file":           str,
              "line":           int,
              "source_line":    str,  # exact source line of the call
              "enclosing_func": str | None,
              "enclosing_class": str | None,
              "enclosing_source": str  # full code of the calling method
            }
          ],
          "errors": []
        }
    """
    errors: list[str] = []

    # ── 1. Find all definitions ─────────────────────────────────────────────
    r_defs = search(f"func[name='{method_name}']", root)
    if r_defs["status"] != "success" or r_defs["matches_count"] == 0:
        return {
            "status": "error",
            "method_name": method_name,
            "root": root,
            "definitions": [],
            "callees": [],
            "callers": [],
            "errors": [f"Method '{method_name}' not found in '{root}'"],
        }

    definitions = [
        {
            "file":         item["file"],
            "entity_name":  item["entity_name"],
            "parent_class": item.get("parent_class"),
            "line_start":   item["line_start"],
            "line_end":     item["line_end"],
            "content":      item.get("content", ""),
        }
        for item in r_defs["results"]
    ]

    # ── 2. Collect all entities once ────────────────────────────────────────
    all_entities = collect_all_entities(root)

    # Use the first definition as primary for callees / callers
    primary = r_defs["results"][0]
    primary_file = primary["file"]
    primary_line = primary["line_start"] + 1

    self_entity = resolve_entity_at(primary_file, primary_line, all_entities)
    if not self_entity:
        self_entity = resolve_entity_at(normalize_path(primary_file), primary_line, all_entities)

    # ── 3. Callees ──────────────────────────────────────────────────────────
    callees_out: list[dict] = []
    if self_entity:
        raw_callees = find_callees(self_entity, all_entities)

        # Group by short method name to deduplicate
        grouped: dict[str, list[Entity]] = {}
        for e in raw_callees:
            short_name = e.__dict__.get("_method") or e.entity_name
            grouped.setdefault(short_name, []).append(e)

        for short_name, call_entities in sorted(grouped.items()):
            full_name = call_entities[0].entity_name
            call_lines = [e.line_start for e in call_entities]

            # Find definitions of this callee in the project
            r_callee_def = search(f"func[name='{short_name}']", root)
            callee_defs = [
                {
                    "file":         d["file"],
                    "entity_name":  d["entity_name"],
                    "parent_class": d.get("parent_class"),
                    "line_start":   d["line_start"],
                    "line_end":     d["line_end"],
                    "content":      d.get("content", ""),
                }
                for d in r_callee_def["results"]
            ] if r_callee_def["matches_count"] > 0 else []

            callees_out.append({
                "call_name":   full_name,
                "method":      short_name,
                "call_lines":  call_lines,
                "definitions": callee_defs,
            })
    else:
        errors.append("Could not resolve primary entity for callees/callers analysis")

    # ── 4. Callers ──────────────────────────────────────────────────────────
    callers_out: list[dict] = []
    if self_entity:
        raw_callers = find_callers(self_entity, all_entities)

        for caller in raw_callers:
            # Source line text
            src_line = ""
            if caller.source_lines and caller.line_start:
                src_line = caller.source_lines[caller.line_start - 1].rstrip()

            # Enclosing method
            enclosing = resolve_entity_at(caller.file, caller.line_start, all_entities)
            enclosing_func  = None
            enclosing_class = None
            enclosing_src   = ""

            if enclosing and enclosing.entity_name != method_name:
                enclosing_func  = enclosing.entity_name
                enclosing_class = enclosing.parent_class
                # Full source of the enclosing method
                r_enc = search(f"func[name='{enclosing.entity_name}']", root)
                for enc_item in r_enc["results"]:
                    if normalize_path(enc_item["file"]) == normalize_path(caller.file):
                        enclosing_src = enc_item.get("content", "")
                        break

            callers_out.append({
                "file":             caller.file,
                "line":             caller.line_start,
                "source_line":      src_line.strip(),
                "enclosing_func":   enclosing_func,
                "enclosing_class":  enclosing_class,
                "enclosing_source": enclosing_src,
            })

    return {
        "status":      "success",
        "method_name": method_name,
        "root":        root,
        "definitions": definitions,
        "callees":     callees_out,
        "callers":     callers_out,
        "errors":      errors,
    }


# ---------------------------------------------------------------------------
# Human-readable inspect output (used by CLI `inspect` command)
# ---------------------------------------------------------------------------

def _print_inspect(result: dict) -> None:
    """Pretty-print inspect_method() result to stdout."""

    def hr(title: str) -> None:
        print(f"\n{'=' * 62}")
        print(f"  {title}")
        print('=' * 62)

    def _code(text: str, indent: str = "    ") -> None:
        if not text:
            return
        print()
        for line in text.splitlines():
            print(f"{indent}{line}")

    def _short(path: str) -> str:
        return path.replace("\\", "/")

    name = result["method_name"]
    print(f"\nАналіз методу: {name!r}   корінь: {result['root']!r}")

    if result["status"] == "error":
        print(f"\n  {result['errors'][0]}")
        print("  Підказка: спробуйте ширший корінь, наприклад 'projects'")
        return

    # ── 1. Definitions ──────────────────────────────────────────────────────
    hr(f"1. КОД МЕТОДУ  '{name}'")
    for d in result["definitions"]:
        loc = f"{_short(d['file'])}  :{d['line_start']}-{d['line_end']}"
        cls = f"  клас: {d['parent_class']}" if d.get("parent_class") else ""
        print(f"\n  [func]  {d['entity_name']}  —  {loc}{cls}")
        _code(d["content"])

    # ── 2. Callees ──────────────────────────────────────────────────────────
    hr(f"2. ЩО ВИКЛИКАЄ  '{name}'  зсередини  (callees)")
    if not result["callees"]:
        print("  (метод нічого не викликає або виклики не розпізнано)")
    else:
        for callee in result["callees"]:
            lines_str = ", ".join(str(l) for l in callee["call_lines"])
            print(f"\n  ┌─ виклик: {callee['call_name']!r}   (рядки: {lines_str})")
            if callee["definitions"]:
                for d in callee["definitions"]:
                    loc = f"{_short(d['file'])}  :{d['line_start']}-{d['line_end']}"
                    cls = f" (клас {d['parent_class']})" if d.get("parent_class") else ""
                    print(f"  │  визначено: {loc}{cls}")
                    _code(d["content"], indent="  │      ")
            else:
                print(f"  │  визначення не знайдено в проєкті (вбудована / зовнішня)")
            print("  └─")

    # ── 3. Callers ──────────────────────────────────────────────────────────
    hr(f"3. ХТО ВИКЛИКАЄ  '{name}'  (callers)")
    if not result["callers"]:
        print("  (ніхто не викликає цей метод в межах проєкту)")
    else:
        for c in result["callers"]:
            print(f"\n  ┌─ {_short(c['file'])}  рядок {c['line']}")
            if c["source_line"]:
                print(f"  │  {c['source_line']}")
            if c["enclosing_func"]:
                cls_info = f" (клас {c['enclosing_class']})" if c["enclosing_class"] else ""
                print(f"  │  в методі: {c['enclosing_func']}{cls_info}")
                _code(c["enclosing_source"], indent="  │      ")
            print("  └─")

    print(f"\n{'=' * 62}\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    """
    Two modes:

    Search mode (default):
        python codeselector.py "<query>" [root] [--file F] [--line N] [--compact]

    Inspect mode:
        python codeselector.py inspect <method_name> [root] [--json]

    Inspect mode options:
        --json    output raw JSON instead of human-readable text
    """
    # Detect inspect sub-command before full argparse
    if len(sys.argv) > 1 and sys.argv[1] == "inspect":
        _main_inspect()
        return

    parser = argparse.ArgumentParser(
        description="CodeSelector — structural code search for Python, JS, TS, PHP, CSS, SCSS",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("query", help="CodeSelector query string")
    parser.add_argument("root", nargs="?", default=".", help="Project root (default: .)")
    parser.add_argument("--file", dest="context_file", default=None,
                        help="Active file path (for `self` queries)")
    parser.add_argument("--line", dest="context_line", type=int, default=None,
                        help="Active line number (for `self` queries)")
    parser.add_argument("--pretty", action="store_true", default=True,
                        help="Pretty-print JSON output (default: true)")
    parser.add_argument("--compact", action="store_true",
                        help="Compact JSON output")
    args = parser.parse_args()

    result = search(
        query_str=args.query,
        root=args.root,
        context_file=args.context_file,
        context_line=args.context_line,
    )

    indent = None if args.compact else 2
    print(json.dumps(result, indent=indent, ensure_ascii=False))

    sys.exit(0 if result["status"] == "success" else 1)


def _main_inspect():
    """Handle: python codeselector.py inspect <method> [root] [--json]"""
    parser = argparse.ArgumentParser(
        prog="codeselector.py inspect",
        description="Inspect a method: source code + callees + callers",
    )
    parser.add_argument("method", help="Method/function name to inspect")
    parser.add_argument("root", nargs="?", default=".", help="Project root (default: .)")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="Output raw JSON instead of human-readable text")
    parser.add_argument("--compact", action="store_true",
                        help="Compact JSON (only with --json)")

    # Strip the 'inspect' sub-command from argv before parsing
    args = parser.parse_args(sys.argv[2:])

    if not os.path.isdir(args.root):
        print(f"Error: directory '{args.root}' does not exist", file=sys.stderr)
        sys.exit(1)

    result = inspect_method(args.method, args.root)

    if args.as_json:
        indent = None if args.compact else 2
        print(json.dumps(result, indent=indent, ensure_ascii=False))
    else:
        _print_inspect(result)

    sys.exit(0 if result["status"] == "success" else 1)




if __name__ == "__main__":
    main()
