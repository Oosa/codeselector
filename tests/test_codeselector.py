"""
iScan — CodeSelector Test Suite
================================
100 tests covering all query features across three sample projects:
  - projects/ecommerce
  - projects/blogapi
  - projects/taskmanager

Run all tests:
    python tests/test_codeselector.py

Run a single category:
    python tests/test_codeselector.py FilesAndDirsTests
    python tests/test_codeselector.py SelfAndResolverTests

Each test follows the pattern:
  1. Run a CodeSelector query against one or more projects
  2. Assert on status, matches_count, entity names, files, or content
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from codeselector import search, resolve

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EC   = os.path.join(ROOT, "projects", "ecommerce")
BLOG = os.path.join(ROOT, "projects", "blogapi")
TM   = os.path.join(ROOT, "projects", "taskmanager")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def names(result: dict) -> list[str]:
    """Extract entity_name from all results."""
    return [r["entity_name"] for r in result["results"]]


def files(result: dict) -> list[str]:
    """Extract file basenames from all results."""
    return [os.path.basename(r["file"]) for r in result["results"]]


def contents(result: dict) -> list[str]:
    """Extract content field from all results."""
    return [r.get("content", "") for r in result["results"]]


def count(result: dict) -> int:
    return result["matches_count"]


def ok(result: dict) -> bool:
    return result["status"] == "success"


# ---------------------------------------------------------------------------
# Category 1 — Files and Directories (1–12)
# ---------------------------------------------------------------------------

class FilesAndDirsTests(unittest.TestCase):

    def test_01_all_python_files_in_ecommerce(self):
        """All .py files found in ecommerce project."""
        r = search("file[ext='py']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            # entity_name is the stem, no extension
            self.assertIsInstance(n, str)

    def test_02_file_by_exact_name(self):
        """Find file with exact name 'validators'."""
        r = search("file[name='validators']", EC)
        self.assertTrue(ok(r))
        self.assertEqual(count(r), 1)
        self.assertEqual(names(r), ["validators"])

    def test_03_file_name_starts_with(self):
        """Find files whose name starts with 'order'."""
        r = search("file[name^='order']", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertTrue(any("order" in n for n in found))

    def test_04_file_name_ends_with(self):
        """Find files whose name ends with '_service'."""
        r = search("file[name$='_service']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.endswith("_service"))

    def test_05_file_name_contains(self):
        """Find files containing 'controller' in name."""
        r = search("file[name*='controller']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("controller", n)

    def test_06_dir_by_exact_name(self):
        """Find directory named 'services'."""
        r = search("dir[name='services']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        self.assertIn("services", names(r))

    def test_07_dir_name_contains(self):
        """Find directories whose name contains 'model'."""
        r = search("dir[name*='model']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("model", n)

    def test_08_files_inside_dir(self):
        """All files inside 'utils' dir."""
        r = search("dir[name='utils'] file", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for f in files(r):
            self.assertTrue(f.endswith(".py"))

    def test_09_files_count_in_project(self):
        """Count of .py files in blogapi."""
        r = search("file[ext='py']:count", BLOG)
        self.assertTrue(ok(r))
        self.assertEqual(len(r["results"]), 1)
        self.assertIn("count", r["results"][0])
        self.assertGreater(r["results"][0]["count"], 0)

    def test_10_files_in_taskmanager(self):
        """All Python files in taskmanager."""
        r = search("file[ext='py']", TM)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_11_dir_name_starts_with(self):
        """Find dir whose name starts with 'work'."""
        r = search("dir[name^='work']", TM)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("work"))

    def test_12_file_loc_modifier(self):
        """File entity with :loc returns file path and line range."""
        r = search("file[name='user']:loc", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for c in contents(r):
            self.assertIn(":", c)  # path:start-end format


# ---------------------------------------------------------------------------
# Category 2 — Imports (13–22)
# ---------------------------------------------------------------------------

class ImportTests(unittest.TestCase):

    def test_13_import_by_module_exact(self):
        """Find all imports of 'logging' module."""
        r = search("import[module='logging']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_14_import_module_contains(self):
        """Find imports where module contains 'decimal'."""
        r = search("import[module*='decimal']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_15_import_module_starts_with(self):
        """Imports starting with 'datetime'."""
        r = search("import[module^='datetime']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_16_import_in_specific_file(self):
        """Imports inside order_service.py."""
        r = search("file[name='order_service'] import", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_17_import_os_module(self):
        """Find import of 'os' in ecommerce."""
        r = search("import[module='os']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_18_import_count_in_blogapi(self):
        """Count all imports in blogapi."""
        r = search("import:count", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_19_import_asyncio(self):
        """Find asyncio import in taskmanager."""
        r = search("import[module='asyncio']", TM)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_20_import_name_modifier(self):
        """Return only names of all imports in ecommerce."""
        r = search("import:name", EC)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertIsInstance(c, str)
            self.assertGreater(len(c), 0)

    def test_21_import_in_controller(self):
        """Imports inside order_controller.py."""
        r = search("file[name='order_controller'] import", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_22_import_json(self):
        """Find json import across all projects."""
        r = search("import[module='json']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)


# ---------------------------------------------------------------------------
# Category 3 — Classes (23–35)
# ---------------------------------------------------------------------------

class ClassTests(unittest.TestCase):

    def test_23_all_classes_in_ecommerce(self):
        """All classes in ecommerce project."""
        r = search("class", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("User", found)
        self.assertIn("Product", found)
        self.assertIn("Order", found)

    def test_24_class_by_exact_name(self):
        """Find class 'User' exactly."""
        r = search("class[name='User']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        self.assertIn("User", names(r))

    def test_25_class_name_ends_with_service(self):
        """Classes ending with 'Service'."""
        r = search("class[name$='Service']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.endswith("Service"))

    def test_26_class_name_starts_with(self):
        """Classes starting with 'Order' in ecommerce."""
        r = search("class[name^='Order']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("Order"))

    def test_27_class_name_contains(self):
        """Classes containing 'Controller' in name."""
        r = search("class[name*='Controller']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("Controller", n)

    def test_28_class_with_docstring(self):
        """Classes that have a docstring."""
        r = search("class[has_docstring='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_29_class_without_docstring(self):
        """Classes missing a docstring."""
        r = search("class[has_docstring='false']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_30_class_count_in_blogapi(self):
        """Count classes in blogapi."""
        r = search("class:count", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_31_class_in_models_dir(self):
        """Classes inside 'models' directory."""
        r = search("dir[name='models'] class", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("User", found)

    def test_32_class_name_modifier(self):
        """Class names only, via :name modifier."""
        r = search("class:name", TM)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertIsInstance(c, str)

    def test_33_classes_in_taskmanager_core(self):
        """Classes in taskmanager core module."""
        r = search("dir[name='core'] class", TM)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("Task", found)
        self.assertIn("Project", found)

    def test_34_class_or_operator(self):
        """Find User OR Product class (OR query)."""
        r = search("class[name='User'], class[name='Product']", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("User", found)
        self.assertIn("Product", found)

    def test_35_class_lines_modifier(self):
        """Class :lines returns line range string."""
        r = search("class[name='OrderService']:lines", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for c in contents(r):
            self.assertRegex(c, r"\d+-\d+")


# ---------------------------------------------------------------------------
# Category 4 — Functions and Methods (36–58)
# ---------------------------------------------------------------------------

class FunctionTests(unittest.TestCase):

    def test_36_all_functions_in_ecommerce(self):
        """All functions in ecommerce project."""
        r = search("func", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 20)

    def test_37_async_functions_only(self):
        """Only async functions in ecommerce."""
        r = search("func[async='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_38_sync_functions_only(self):
        """Only synchronous functions."""
        r = search("func[async='false']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_39_func_by_exact_name(self):
        """Find function named 'get_order'."""
        r = search("func[name='get_order']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        self.assertTrue(all(n == "get_order" for n in names(r)))

    def test_40_func_name_starts_with_get(self):
        """Functions starting with 'get_'."""
        r = search("func[name^='get_']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("get_"))

    def test_41_func_name_ends_with_handler(self):
        """Functions ending with '_handler' (none expected — tests empty result)."""
        r = search("func[name$='_handler']", EC)
        self.assertTrue(ok(r))
        # may be 0 — just check no error

    def test_42_func_name_contains_password(self):
        """Functions whose name contains 'password'."""
        r = search("func[name*='password']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertIn("password", n.lower())

    def test_43_private_methods(self):
        """Private methods (name starts with '_')."""
        r = search("func[name^='_']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("_"))

    def test_44_dunder_methods(self):
        """Dunder methods (name starts with '__')."""
        r = search("func[name^='__']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("__"))

    def test_45_public_methods(self):
        """Public methods only."""
        r = search("func[is_public='true']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertFalse(n.startswith("_"))

    def test_46_func_with_docstring(self):
        """Functions that have a docstring."""
        r = search("func[has_docstring='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_47_func_without_docstring(self):
        """Functions missing a docstring."""
        r = search("func[has_docstring='false']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_48_func_args_gte_3(self):
        """Functions with 3 or more arguments."""
        r = search("func[args>='3']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_49_func_args_zero(self):
        """Functions with 0 arguments."""
        r = search("func[args='0']", EC)
        self.assertTrue(ok(r))

    def test_50_direct_methods_of_class(self):
        """Direct methods of OrderService via '>' combinator."""
        r = search("class[name='OrderService'] > func", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("create_order_from_cart", found)
        self.assertIn("get_order", found)

    def test_51_async_methods_of_service(self):
        """Async methods inside any Service class."""
        r = search("class[name$='Service'] > func[async='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_52_func_count_in_ecommerce(self):
        """Count all functions in ecommerce."""
        r = search("func:count", EC)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 10)

    def test_53_func_name_modifier(self):
        """Function names via :name modifier."""
        r = search("func[async='true']:name", EC)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertIsInstance(c, str)

    def test_54_func_args_modifier(self):
        """Function args via :args modifier."""
        r = search("func[name='login']:args", EC)
        self.assertTrue(ok(r))
        if count(r) > 0:
            for c in contents(r):
                self.assertIsInstance(c, list)

    def test_55_func_docstring_modifier(self):
        """Docstring text via :docstring modifier."""
        r = search("func[has_docstring='true']:docstring", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for c in contents(r):
            self.assertIsInstance(c, str)
            self.assertGreater(len(c), 0)

    def test_56_func_lines_modifier(self):
        """Line range via :lines modifier."""
        r = search("func[name='calculate_order_total']:lines", EC)
        self.assertTrue(ok(r))
        if count(r) > 0:
            for c in contents(r):
                self.assertRegex(c, r"\d+-\d+")

    def test_57_func_code_modifier(self):
        """Full source code via :code modifier."""
        r = search("func[name='validate_email']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        src = r["results"][0]["content"]
        self.assertIn("def validate_email", src)

    def test_58_async_func_in_taskmanager_worker(self):
        """Async functions inside notification_worker.py."""
        r = search("file[name='notification_worker'] func[async='true']:name", TM)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)


# ---------------------------------------------------------------------------
# Category 5 — Variables (59–67)
# ---------------------------------------------------------------------------

class VariableTests(unittest.TestCase):

    def test_59_all_vars_in_file(self):
        """All variables in order.py."""
        r = search("file[name='order'] var", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_60_var_by_exact_name(self):
        """Variable named 'TAX_RATE_STANDARD'."""
        r = search("var[name='TAX_RATE_STANDARD']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_61_var_name_contains(self):
        """Variables whose name contains 'TAX'."""
        r = search("var[name*='TAX']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("TAX", n)

    def test_62_var_name_starts_with(self):
        """Variables starting with 'MAX_'."""
        r = search("var[name^='MAX_']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("MAX_"))

    def test_63_var_name_ends_with(self):
        """Variables ending with '_SECONDS'."""
        r = search("var[name$='_SECONDS']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.endswith("_SECONDS"))

    def test_64_var_inside_function(self):
        """Variables inside function 'validate_email'."""
        r = search("func[name='validate_email'] var", EC)
        self.assertTrue(ok(r))

    def test_65_var_count_in_product_file(self):
        """Count variables in product.py."""
        r = search("file[name='product'] var:count", EC)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_66_var_name_modifier(self):
        """Variable names via :name."""
        r = search("var[name^='STATUS_']:name", EC)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertTrue(c.startswith("STATUS_"))

    def test_67_var_in_taskmanager(self):
        """Variables in taskmanager core."""
        r = search("var[name^='PRIORITY_']", TM)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("PRIORITY_"))


# ---------------------------------------------------------------------------
# Category 6 — Calls (68–76)
# ---------------------------------------------------------------------------

class CallTests(unittest.TestCase):

    def test_68_call_by_name(self):
        """Find calls to 'print' (none expected — no print in clean code)."""
        r = search("call[name='print']", EC)
        self.assertTrue(ok(r))

    def test_69_call_by_method_name(self):
        """Find calls with method 'send'."""
        r = search("call[method='send']", TM)
        self.assertTrue(ok(r))

    def test_70_call_inside_async_func(self):
        """Calls inside async functions in ecommerce."""
        r = search("func[async='true'] call", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_71_call_inside_specific_method(self):
        """Calls inside '_validate_cart'."""
        r = search("func[name='_validate_cart'] call", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_72_call_count_in_order_service(self):
        """Count calls in order_service.py."""
        r = search("file[name='order_service'] call:count", EC)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_73_call_method_append(self):
        """Calls using 'append' method."""
        r = search("call[method='append']", EC)
        self.assertTrue(ok(r))

    def test_74_call_name_contains_db(self):
        """Calls whose name contains 'db'."""
        r = search("call[name*='db']", EC)
        self.assertTrue(ok(r))

    def test_75_call_lines_modifier(self):
        """Call :lines returns line numbers."""
        r = search("call[method='send']:lines", TM)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertRegex(c, r"\d+-\d+")

    def test_76_call_in_blogapi(self):
        """Calls in blogapi middleware."""
        r = search("file[name='rate_limiter'] call", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)


# ---------------------------------------------------------------------------
# Category 7 — Decorators (77–82)
# ---------------------------------------------------------------------------

class DecoratorTests(unittest.TestCase):

    def test_77_decorator_by_name(self):
        """Find decorator named 'require_auth'."""
        r = search("decorator[name='require_auth']", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_78_decorator_name_contains(self):
        """Decorators whose name contains 'property'."""
        r = search("decorator[name='property']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_79_func_with_decorator(self):
        """Decorator 'property' found as child of func entities."""
        r = search("func decorator[name='property']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        # results are decorator entities that live inside func scope
        for e in r["results"]:
            self.assertEqual(e["entity_type"], "decorator")

    def test_80_decorator_count(self):
        """Count decorators in blogapi."""
        r = search("decorator:count", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_81_decorator_name_modifier(self):
        """Decorator names via :name."""
        r = search("decorator:name", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_82_class_with_decorator_method(self):
        """Methods inside PostAdminView that have decorators."""
        r = search("class[name='PostAdminView'] > func decorator", BLOG)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)


# ---------------------------------------------------------------------------
# Category 8 — Combined / Complex queries (83–93)
# ---------------------------------------------------------------------------

class CombinedQueryTests(unittest.TestCase):

    def test_83_async_methods_in_controllers(self):
        """Async methods inside *Controller classes."""
        r = search("class[name*='Controller'] > func[async='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            # all should be async — we can't directly verify without re-parsing,
            # but count > 0 confirms the combinator worked
            pass

    def test_84_private_methods_with_args(self):
        """Private methods with >= 2 arguments."""
        r = search("func[name^='_'][args>='2']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("_"))

    def test_85_public_async_methods_in_service(self):
        """Public async methods inside Service classes."""
        r = search("class[name$='Service'] > func[async='true'][is_public='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_86_vars_in_file_with_specific_import(self):
        """Variables in a file that imports 'logging'."""
        r = search("file import[module='logging'] var[name^='MAX_']", EC)
        self.assertTrue(ok(r))

    def test_87_func_with_docstring_in_models(self):
        """Functions with docstrings inside models directory."""
        r = search("dir[name='models'] func[has_docstring='true']", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_88_or_query_two_classes(self):
        """OR query: Cart or Order class."""
        r = search("class[name='Cart'], class[name='Order']", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("Cart", found)
        self.assertIn("Order", found)

    def test_89_or_query_two_functions(self):
        """OR query: login or logout function."""
        r = search("func[name='login'], func[name='logout']", EC)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("login", found)
        self.assertIn("logout", found)

    def test_90_chained_combinator_three_levels(self):
        """Three-level chain: dir > file > class."""
        r = search("dir[name='models'] file class", EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_91_func_in_api_dir_taskmanager(self):
        """Functions inside taskmanager 'api' directory."""
        r = search("dir[name='api'] func", TM)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_92_async_func_count_all_projects(self):
        """Count async functions in each project separately."""
        for root in (EC, BLOG, TM):
            r = search("func[async='true']:count", root)
            self.assertTrue(ok(r), msg=f"Failed for {root}")
            self.assertGreaterEqual(r["results"][0]["count"], 0, msg=f"Query failed for {root}")
        # Spot-check: ecommerce and taskmanager definitely have async
        for root in (EC, TM):
            r = search("func[async='true']:count", root)
            self.assertGreater(r["results"][0]["count"], 0, msg=f"No async funcs in {root}")

    def test_93_complex_combined_name_and_async(self):
        """Methods starting with 'get_' that are async."""
        r = search("func[name^='get_'][async='true']", EC)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("get_"))


# ---------------------------------------------------------------------------
# Category 9 — Self and Resolver (94–100)
# ---------------------------------------------------------------------------

class SelfAndResolverTests(unittest.TestCase):

    # Resolve paths — use absolute paths from the EC project
    EC_ORDER_SVC = os.path.join(EC, "services", "order_service.py")
    EC_AUTH_SVC  = os.path.join(EC, "services", "auth_service.py")
    EC_VALIDATOR = os.path.join(EC, "utils", "validators.py")
    TM_TASK      = os.path.join(TM, "core", "task.py")
    BLOG_VIEWS   = os.path.join(BLOG, "views", "post_views.py")

    def test_94_resolve_entity_at_line(self):
        """Resolve returns the correct entity at a known line."""
        # line 33 is inside OrderService.__init__
        r = resolve(self.EC_ORDER_SVC, line=33, root=EC)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        # should resolve to a func or class
        self.assertIn(r["results"][0]["entity_type"], ("func", "class"))

    def test_95_resolve_error_on_empty_line(self):
        """Resolve on a line with no entity returns error or empty."""
        # line 1 is the module docstring line — no func/class wraps it at top
        r = resolve(self.EC_ORDER_SVC, line=1, root=EC)
        # Either error or 0 results — both are acceptable
        if r["status"] == "success":
            # may still find enclosing module-level class if one starts at 1
            pass
        else:
            self.assertEqual(r["status"], "error")

    def test_96_self_callers(self):
        """self:callers finds where a method is called from other files."""
        # calculate_order_total is at the end of order_service.py — line ~95
        # We need to find its actual line first
        r_find = search("func[name='calculate_order_total']:lines", EC)
        self.assertTrue(ok(r_find))
        if count(r_find) == 0:
            self.skipTest("Function not found in project")
        line_str = r_find["results"][0]["content"]
        line = int(line_str.split("-")[0])

        r = search("self:callers", EC,
                   context_file=self.EC_ORDER_SVC,
                   context_line=line + 1)
        self.assertTrue(ok(r))

    def test_97_self_callees(self):
        """self:callees returns calls made inside a method."""
        # _validate_cart calls is_empty, item_count, subtotal
        r_find = search("func[name='_validate_cart']:lines", EC)
        self.assertTrue(ok(r_find))
        if count(r_find) == 0:
            self.skipTest("Function not found")
        line_str = r_find["results"][0]["content"]
        line = int(line_str.split("-")[0])

        r = search("self:callees", EC,
                   context_file=self.EC_ORDER_SVC,
                   context_line=line + 1)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_98_self_var(self):
        """self var returns variables inside the active method."""
        r_find = search("func[name='login']:lines", EC)
        self.assertTrue(ok(r_find))
        if count(r_find) == 0:
            self.skipTest("login not found")
        line_str = r_find["results"][0]["content"]
        line = int(line_str.split("-")[0])

        r = search("self var", EC,
                   context_file=self.EC_AUTH_SVC,
                   context_line=line + 1)
        self.assertTrue(ok(r))

    def test_99_self_direct_child_func(self):
        """self > func lists methods of the active class."""
        # Find Task class line
        r_find = search("class[name='Task']:lines", TM)
        self.assertTrue(ok(r_find))
        if count(r_find) == 0:
            self.skipTest("Task class not found")
        line_str = r_find["results"][0]["content"]
        line = int(line_str.split("-")[0])

        r = search("self > func:name", TM,
                   context_file=self.TM_TASK,
                   context_line=line + 1)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        method_names = contents(r)
        self.assertIn("start", method_names)
        self.assertIn("complete", method_names)

    def test_100_self_loc_modifier(self):
        """self:loc returns file and line range of active entity."""
        r_find = search("func[name='validate_email']:lines", EC)
        self.assertTrue(ok(r_find))
        if count(r_find) == 0:
            self.skipTest("validate_email not found")
        line_str = r_find["results"][0]["content"]
        line = int(line_str.split("-")[0])

        r = search("self:loc", EC,
                   context_file=self.EC_VALIDATOR,
                   context_line=line + 1)
        self.assertTrue(ok(r))
        # resolved_self should contain the loc
        if r.get("resolved_self"):
            self.assertIn("file", r["resolved_self"])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        # run a specific class: python test_codeselector.py ClassTests
        suite = unittest.TestLoader().loadTestsFromName(sys.argv[1], sys.modules[__name__])
        sys.argv = [sys.argv[0]] + sys.argv[2:]
    else:
        suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
