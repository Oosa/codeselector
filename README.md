# CodeSelector — Structural Code Search Engine

Part of the **iScan** toolkit. CodeSelector finds exact code entities (functions, classes, variables, imports, calls) across Python, JavaScript, TypeScript, PHP, CSS, and SCSS files using CSS-like selector syntax.

```
func[name="process_payment"]::code          → full source of the method
class[name="Cart"] > func:name              → method names of a class
func[has_docstring='false'][is_public='true']:count   → count of undocumented public methods
self:callers                                → who calls the method at cursor
```

No fuzzy search. No guessing. Every result is a precise AST match with file path and line numbers.

---

## Why

AI agents and developers waste tokens reading entire files looking for one method. CodeSelector replaces that with a single targeted query that returns exactly the code needed — nothing more.

---

## Installation

Python 3.10+ required. No external dependencies.

```
codeselector/
├── codeselector.py          ← main engine + CLI
├── inspect_method.py        ← standalone method analyser (legacy, now built-in)
└── languages/
    ├── __init__.py          ← language registry
    ├── base.py              ← base parser + Entity + utilities
    ├── python_parser.py     ← .py .pyw  (AST-based, 100% precise)
    ├── js_parser.py         ← .js .ts .mjs .cjs .jsx .tsx  (regex)
    ├── php_parser.py        ← .php  (regex)
    └── css_parser.py        ← .css .scss .less  (regex)
```

---

## Usage

### CLI

```bash
# Basic search
python codeselector.py "func[name='_refill']" projects/blogapi
python codeselector.py "class[name='Cart'] > func:name" projects/webshop
python codeselector.py "func[has_docstring='false']:count" projects

# With context (for self queries)
python codeselector.py "self:callers" projects \
    --file projects/blogapi/middleware/rate_limiter.py --line 37

# Inspect a method (code + callees + callers)
python codeselector.py inspect _refill projects
python codeselector.py inspect process_payment projects --json

# Compact output
python codeselector.py "func[async='true']:name" projects --compact
```

### Python API

```python
from codeselector import search, inspect_method

# Search
result = search("class[name='OrderService'] > func[async='true']", root="projects")

# Inspect
info = inspect_method("process_payment", root="projects")
info["definitions"]   # where it's defined
info["callees"]       # what it calls (with source)
info["callers"]       # who calls it (with enclosing method)
```

---

## Query Syntax

### Tags

| Tag         | Finds                                                    |
|-------------|----------------------------------------------------------|
| `file`      | Files (`.py`, `.js`, `.php`, `.css` …)                  |
| `dir`       | Directories                                              |
| `class`     | Classes (Python/JS/PHP) or CSS class selectors           |
| `func`      | Functions and methods (including SCSS `@mixin`)          |
| `var`       | Variables, constants, CSS custom properties (`--var`)    |
| `import`    | Import / `use` / `require` statements                    |
| `call`      | Function or method call sites                            |
| `decorator` | Python decorators, CSS `@keyframes`, `@media`            |
| `rule`      | Full CSS selector blocks                                 |

### Attribute operators

```
[name="exact"]      exact match
[name*="part"]      contains
[name^="pre"]       starts with
[name$="suf"]       ends with
[name!="val"]       not equal
[args>="3"]         numeric >= (argument count)
```

### Key attributes

| Attribute       | Type         | Where             |
|-----------------|--------------|-------------------|
| `name`          | string       | all entities      |
| `ext`           | string       | `file`            |
| `lang`          | string       | all (`py` `js` `ts` `php` `css` `scss`) |
| `async`         | true/false   | `func`            |
| `has_docstring` | true/false   | `func`, `class`   |
| `is_public`     | true/false   | `func`            |
| `args`          | number       | `func`            |
| `module`        | string       | `import`          |
| `method`        | string       | `call`            |
| `exported`      | true/false   | JS/TS `func`, `class` |
| `visibility`    | string       | PHP `func` (`public`, `private`, `protected`) |

### Combinators

```
space   descendant:    file func
>       direct child:  class > func
,       OR union:      class[name="A"], class[name="B"]
```

### Modifiers (what `content` field returns)

| Modifier     | Returns                           |
|--------------|-----------------------------------|
| `:code`      | full source code (default)        |
| `:name`      | name string only                  |
| `:lines`     | `"10-25"`                         |
| `:loc`       | `"file.py:10-25"`                 |
| `:args`      | parameter names list              |
| `:docstring` | docstring / JSDoc text            |
| `:count`     | `{"count": N}` (single result)    |

### `self` — context-aware queries

```bash
python codeselector.py "self"           projects --file path/to/file.py --line 45
python codeselector.py "self:callers"   projects --file path/to/file.py --line 45
python codeselector.py "self:callees"   projects --file path/to/file.py --line 45
python codeselector.py "self > func"    projects --file path/to/file.py --line 45
```

---

## Response Format

```json
{
  "status": "success",
  "query": "class[name='Cart'] > func:name",
  "matches_count": 8,
  "results": [
    {
      "file": "js/cart.js",
      "entity_type": "func",
      "entity_name": "addItem",
      "parent_class": "Cart",
      "line_start": 20,
      "line_end": 28,
      "content": "addItem"
    }
  ],
  "errors": []
}
```

---

## Examples

```bash
# Find async Service methods
python codeselector.py "class[name*='Service'] > func[async='true']:name" projects

# Undocumented public functions
python codeselector.py "func[has_docstring='false'][is_public='true']:name" projects

# PHP public methods in OrderService
python codeselector.py "class[name='OrderService'] > func[visibility='public']:name" projects

# CSS custom properties
python codeselector.py "var[name^='--']" projects/webshop

# TS async functions
python codeselector.py "func[async='true'][lang='ts']:name" projects/dashboard

# Classes that have a delete method
python codeselector.py "class:has(func[name='delete'])" projects

# Count undocumented functions
python codeselector.py "func[has_docstring='false']:count" projects
```

---

## Running Tests

```bash
python tests/test_codeselector.py            # 100 Python tests
python tests/test_multilang.py               # 100 JS/TS/PHP/CSS/SCSS tests

# Single category
python tests/test_codeselector.py FunctionTests
```

---

## Adding a New Language

1. Create `languages/ruby_parser.py` inheriting from `BaseParser`
2. Implement `EXTENSIONS`, `LANG`, and `collect(file_path)` method
3. Register in `languages/__init__.py`

CodeSelector picks it up automatically — no changes to the main engine needed.

---

## Part of iScan

| Tool               | Role                                    |
|--------------------|-----------------------------------------|
| **CodeSelector**   | 🔍 Read — find exact code entities      |
| CodeScanner        | 🗺️ Analyse — project structure & metadata |
| CodeImplementor    | 🛠️ Write — modify code and files        |
| CodeTester         | 🧪 Verify — run tests and check results |
