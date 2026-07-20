"""
iScan — Multi-Language CodeSelector Test Suite
===============================================
100 tests covering JS, TS, PHP, CSS, SCSS across four projects:
  - projects/webshop     (JS + PHP + CSS)
  - projects/dashboard   (TS + SCSS + PHP)
  - projects/portfolio   (JS + SCSS)
  - projects/cms         (JS + PHP + CSS)

Categories:
  1.  File & dir discovery         (1-10)
  2.  JavaScript — classes         (11-18)
  3.  JavaScript — functions       (19-30)
  4.  JavaScript — variables       (31-36)
  5.  JavaScript — imports/calls   (37-42)
  6.  TypeScript extras            (43-50)
  7.  PHP — classes                (51-56)
  8.  PHP — functions/visibility   (57-66)
  9.  PHP — imports / vars         (67-72)
  10. CSS — classes / rules        (73-82)
  11. SCSS — mixins/vars/keyframes (83-90)
  12. Cross-language queries       (91-100)

Run all:
    python tests/test_multilang.py

Run one category:
    python tests/test_multilang.py JSFunctionTests
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from codeselector import search

ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WS      = os.path.join(ROOT, "projects", "webshop")       # JS + PHP + CSS
DASH    = os.path.join(ROOT, "projects", "dashboard")     # TS + SCSS + PHP
PORT    = os.path.join(ROOT, "projects", "portfolio")     # JS + SCSS
CMS     = os.path.join(ROOT, "projects", "cms")           # JS + PHP + CSS
ALL     = os.path.join(ROOT, "projects")                  # all four


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def names(r):       return [x["entity_name"] for x in r["results"]]
def files(r):       return [os.path.basename(x["file"]) for x in r["results"]]
def contents(r):    return [x.get("content", "") for x in r["results"]]
def count(r):       return r["matches_count"]
def ok(r):          return r["status"] == "success"
def langs(r):       return [x["file"].rsplit(".", 1)[-1] for x in r["results"]]


# ---------------------------------------------------------------------------
# 1. File & Directory discovery (1–10)
# ---------------------------------------------------------------------------

class FileDiscoveryTests(unittest.TestCase):

    def test_01_js_files_in_webshop(self):
        r = search("file[ext='js']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertIsInstance(n, str)

    def test_02_php_files_in_webshop(self):
        r = search("file[ext='php']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_03_css_files_in_webshop(self):
        r = search("file[ext='css']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_04_ts_files_in_dashboard(self):
        r = search("file[ext='ts']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_05_scss_files_in_dashboard(self):
        r = search("file[ext='scss']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_06_file_by_exact_name_cart(self):
        r = search("file[name='cart']", WS)
        self.assertTrue(ok(r))
        self.assertEqual(count(r), 1)
        self.assertIn("cart", names(r))

    def test_07_file_name_contains_service(self):
        r = search("file[name*='Service']", ALL)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("Service", n)

    def test_08_file_name_ends_with_controller(self):
        r = search("file[name$='Controller']", ALL)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.endswith("Controller"))

    def test_09_dir_js_in_webshop(self):
        r = search("dir[name='js']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_10_files_inside_css_dir(self):
        r = search("dir[name='css'] file", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)


# ---------------------------------------------------------------------------
# 2. JavaScript — classes (11–18)
# ---------------------------------------------------------------------------

class JSClassTests(unittest.TestCase):

    def test_11_all_js_classes_in_webshop(self):
        r = search("class", WS)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("Cart", found)

    def test_12_class_by_exact_name_cart(self):
        r = search("class[name='Cart']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        self.assertIn("Cart", names(r))

    def test_13_class_name_contains_api(self):
        r = search("class[name*='Api']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("Api", n)

    def test_14_class_name_ends_with_api(self):
        r = search("class[name$='Api']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.endswith("Api"))

    def test_15_class_api_error(self):
        r = search("class[name='ApiError']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_16_all_classes_in_portfolio(self):
        r = search("class", PORT)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        found = names(r)
        self.assertIn("ProjectFilter", found)

    def test_17_class_count_in_webshop(self):
        r = search("class:count", WS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_18_class_name_modifier(self):
        r = search("class:name", WS)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertIsInstance(c, str)


# ---------------------------------------------------------------------------
# 3. JavaScript — functions (19–30)
# ---------------------------------------------------------------------------

class JSFunctionTests(unittest.TestCase):

    def test_19_all_js_funcs_in_webshop(self):
        r = search("func", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 10)

    def test_20_async_js_funcs(self):
        r = search("func[async='true']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        found = names(r)
        self.assertIn("fetchProductDetails", found)

    def test_21_func_by_exact_name(self):
        r = search("func[name='addItem']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_22_func_name_starts_with_get(self):
        r = search("func[name^='get']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("get"))

    def test_23_func_name_starts_with_underscore(self):
        r = search("func[name^='_']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("_"))

    def test_24_func_name_contains_render(self):
        r = search("func[name*='render']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertIn("render", n.lower())

    def test_25_func_name_contains_cart_or_order(self):
        r = search("func[name*='cart'], func[name*='Cart']", WS)
        self.assertTrue(ok(r))

    def test_26_direct_methods_of_cart_class(self):
        r = search("class[name='Cart'] > func", WS)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("addItem", found)
        self.assertIn("removeItem", found)

    def test_27_direct_methods_of_cart_ui(self):
        r = search("class[name='CartUI'] > func", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_28_func_count_in_portfolio(self):
        r = search("func:count", PORT)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 5)

    def test_29_func_lines_modifier(self):
        r = search("func[name='addItem']:lines", WS)
        self.assertTrue(ok(r))
        if count(r) > 0:
            for c in contents(r):
                self.assertRegex(c, r"\d+-\d+")

    def test_30_func_code_modifier(self):
        r = search("func[name='grandTotal']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        src = r["results"][0]["content"]
        self.assertIn("grandTotal", src)


# ---------------------------------------------------------------------------
# 4. JavaScript — variables (31–36)
# ---------------------------------------------------------------------------

class JSVariableTests(unittest.TestCase):

    def test_31_all_vars_in_webshop_js(self):
        r = search("file[ext='js'] var", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_32_var_by_exact_name_tax_rate(self):
        r = search("var[name='TAX_RATE']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_33_var_name_starts_with_underscore(self):
        r = search("var[name^='_']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("_"))

    def test_34_var_name_contains_url(self):
        r = search("var[name*='URL'], var[name*='Url']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_35_var_count_in_cms_js(self):
        r = search("file[ext='js'] var:count", CMS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_36_var_name_modifier(self):
        r = search("var[name^='_']:name", WS)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertTrue(c.startswith("_"))


# ---------------------------------------------------------------------------
# 5. JavaScript — imports & calls (37–42)
# ---------------------------------------------------------------------------

class JSImportCallTests(unittest.TestCase):

    def test_37_imports_in_js_files(self):
        r = search("file[ext='js'] import", WS)
        self.assertTrue(ok(r))

    def test_38_import_from_api_client(self):
        r = search("import[module*='api']", ALL)
        self.assertTrue(ok(r))

    def test_39_call_inside_async_func(self):
        r = search("func[async='true'] call", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_40_call_by_method_name_fetch(self):
        r = search("call[name*='fetch']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_41_call_count_in_cart(self):
        r = search("file[name='cart'] call:count", WS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_42_call_method_json(self):
        r = search("call[method='json']", WS)
        self.assertTrue(ok(r))


# ---------------------------------------------------------------------------
# 6. TypeScript extras (43–50)
# ---------------------------------------------------------------------------

class TypeScriptTests(unittest.TestCase):

    def test_43_all_classes_in_dashboard_ts(self):
        r = search("class", DASH)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("Dashboard", found)

    def test_44_ts_async_funcs(self):
        r = search("func[async='true'][lang='ts']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_45_ts_func_by_name(self):
        r = search("func[name='fetchMetrics']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_46_ts_class_dashboard_methods(self):
        r = search("class[name='Dashboard'] > func", DASH)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("init", found)
        self.assertIn("loadAllMetrics", found)

    def test_47_ts_imports_in_dashboard(self):
        r = search("import", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_48_ts_private_methods(self):
        r = search("func[name^='_'][lang='ts']", DASH)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("_"))

    def test_49_ts_vars_in_dashboard(self):
        r = search("var", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_50_ts_func_count(self):
        r = search("func[lang='ts']:count", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)


# ---------------------------------------------------------------------------
# 7. PHP — classes (51–56)
# ---------------------------------------------------------------------------

class PHPClassTests(unittest.TestCase):

    def test_51_all_php_classes_in_webshop(self):
        r = search("class", WS)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertTrue(any("Controller" in n or "Service" in n for n in found))

    def test_52_php_class_by_exact_name(self):
        r = search("class[name='ProductController']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_53_php_class_name_ends_with_service(self):
        r = search("class[name$='Service']", ALL)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.endswith("Service"))

    def test_54_php_class_name_contains_controller(self):
        r = search("class[name*='Controller']", ALL)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertIn("Controller", n)

    def test_55_php_abstract_class(self):
        r = search("class[name='Plugin']", CMS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_56_php_class_count_in_cms(self):
        r = search("class:count", CMS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)


# ---------------------------------------------------------------------------
# 8. PHP — functions / visibility (57–66)
# ---------------------------------------------------------------------------

class PHPFunctionTests(unittest.TestCase):

    def test_57_all_php_funcs_in_webshop(self):
        r = search("file[ext='php'] func", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_58_php_func_by_name(self):
        r = search("func[name='processPayment']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_59_php_func_name_starts_with(self):
        r = search("func[name^='get']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("get"))

    def test_60_php_private_funcs(self):
        r = search("func[name^='_'][lang='php']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("_"))

    def test_61_php_methods_of_order_service(self):
        r = search("class[name='OrderService'] > func", WS)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("createFromCart", found)
        self.assertIn("processPayment", found)

    def test_62_php_func_count_in_plugin(self):
        r = search("file[name='Plugin'] func:count", CMS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_63_php_func_name_contains_validate(self):
        r = search("func[name*='validate'], func[name*='Validate']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_64_php_func_name_ends_with_handler(self):
        # just ensure no crash on empty result
        r = search("func[name$='Handler']", ALL)
        self.assertTrue(ok(r))

    def test_65_php_constructor_methods(self):
        r = search("func[name='__construct']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_66_php_func_args_gte_3(self):
        r = search("func[args>='3'][lang='php']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)


# ---------------------------------------------------------------------------
# 9. PHP — imports / variables (67–72)
# ---------------------------------------------------------------------------

class PHPImportVarTests(unittest.TestCase):

    def test_67_php_imports_in_webshop(self):
        r = search("import", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_68_php_import_by_module_contains(self):
        r = search("import[module*='Service']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_69_php_import_name(self):
        r = search("import:name", WS)
        self.assertTrue(ok(r))
        for c in contents(r):
            self.assertIsInstance(c, str)

    def test_70_php_vars_in_order_service(self):
        r = search("file[name='OrderService'] var", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_71_php_var_name_starts_dollar(self):
        r = search("var[name^='$'][lang='php']", WS)
        self.assertTrue(ok(r))
        for n in names(r):
            self.assertTrue(n.startswith("$"))

    def test_72_php_import_count(self):
        r = search("import:count", WS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)


# ---------------------------------------------------------------------------
# 10. CSS — classes / rules (73–82)
# ---------------------------------------------------------------------------

class CSSClassRuleTests(unittest.TestCase):

    def test_73_all_css_class_entities_in_webshop(self):
        r = search("class", WS)
        self.assertTrue(ok(r))
        # CSS classes are mixed with JS classes — just ensure some found
        self.assertGreater(count(r), 0)

    def test_74_css_class_name_starts_with_btn(self):
        r = search("class[name^='btn']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("btn"))

    def test_75_css_class_name_contains_card(self):
        r = search("class[name*='card']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertIn("card", n)

    def test_76_css_var_custom_properties(self):
        r = search("var[name^='--']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("--"))

    def test_77_css_var_count_in_webshop(self):
        r = search("var[name^='--']:count", WS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_78_css_import_in_file(self):
        # shop.css has no @import; theme.css also none → just test no crash
        r = search("import[lang='css']", ALL)
        self.assertTrue(ok(r))

    def test_79_css_decorator_keyframes(self):
        r = search("decorator", WS)
        self.assertTrue(ok(r))

    def test_80_css_rule_count_in_theme(self):
        r = search("rule:count", CMS)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_81_css_class_name_badge(self):
        r = search("class[name^='badge']", WS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("badge"))

    def test_82_css_class_nav_in_cms(self):
        r = search("class[name*='nav']", CMS)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertIn("nav", n)


# ---------------------------------------------------------------------------
# 11. SCSS — mixins / vars / keyframes (83–90)
# ---------------------------------------------------------------------------

class SCSSTests(unittest.TestCase):

    def test_83_scss_funcs_are_mixins(self):
        r = search("func[lang='scss']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_84_scss_mixin_by_name(self):
        r = search("func[name='flex-center']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_85_scss_mixin_name_starts_with_flex(self):
        r = search("func[name^='flex']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("flex"))

    def test_86_scss_vars_dollar(self):
        r = search("var[name^='$']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("$"))

    def test_87_scss_var_name_contains_color(self):
        r = search("var[name*='color']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertIn("color", n)

    def test_88_scss_keyframes_as_decorators(self):
        r = search("decorator[lang='scss']", DASH)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_89_scss_class_count_in_portfolio(self):
        r = search("class[lang='scss']:count", PORT)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)

    def test_90_scss_mixin_count(self):
        r = search("func:count", PORT)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 0)


# ---------------------------------------------------------------------------
# 12. Cross-language queries (91–100)
# ---------------------------------------------------------------------------

class CrossLanguageTests(unittest.TestCase):

    def test_91_func_name_init_across_all_langs(self):
        """Functions named 'init' exist in both JS and PHP."""
        r = search("func[name='init']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_92_class_name_service_all_langs(self):
        """Classes ending in Service found in both JS and PHP."""
        r = search("class[name$='Service']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_93_all_async_funcs_across_projects(self):
        """Async functions exist in JS, TS — PHP has none (expected)."""
        r = search("func[async='true']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)

    def test_94_search_by_lang_js_only(self):
        """lang='js' filter returns only JS entities."""
        r = search("func[lang='js']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for item in r["results"]:
            ext = item["file"].rsplit(".", 1)[-1]
            self.assertIn(ext, ("js", "mjs", "cjs", "jsx"))

    def test_95_search_by_lang_php_only(self):
        """lang='php' filter returns only PHP entities."""
        r = search("class[lang='php']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for item in r["results"]:
            self.assertTrue(item["file"].endswith(".php"))

    def test_96_or_query_js_and_php_class(self):
        """OR: Cart (JS) OR OrderService (PHP)."""
        r = search("class[name='Cart'], class[name='OrderService']", ALL)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("Cart", found)
        self.assertIn("OrderService", found)

    def test_97_func_in_js_and_php_same_name(self):
        """calculateTotals exists in PHP; grandTotal in JS."""
        r = search("func[name='calculateTotals'], func[name='grandTotal']", ALL)
        self.assertTrue(ok(r))
        found = names(r)
        self.assertIn("calculateTotals", found)
        self.assertIn("grandTotal", found)

    def test_98_vars_starting_with_max_all_langs(self):
        """MAX_ constants across JS (MAX_DATA_POINTS) and PHP (MAX_ITEMS)."""
        r = search("var[name^='MAX']", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(count(r), 0)
        for n in names(r):
            self.assertTrue(n.startswith("MAX"))

    def test_99_count_all_classes_across_four_projects(self):
        """Total class count across all 4 projects."""
        r = search("class:count", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 10)

    def test_100_count_all_funcs_across_four_projects(self):
        """Total function count across all 4 projects."""
        r = search("func:count", ALL)
        self.assertTrue(ok(r))
        self.assertGreater(r["results"][0]["count"], 50)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        suite = unittest.TestLoader().loadTestsFromName(
            sys.argv[1], sys.modules[__name__]
        )
        sys.argv = [sys.argv[0]] + sys.argv[2:]
    else:
        suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
