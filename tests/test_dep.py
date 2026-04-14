#!/usr/bin/env python3
"""
Tests for bingo_core.dep — dependency patching engine.

End-to-end tests using a real npm project with lodash.
Requires: npm, patch (GNU patch), internet access.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Ensure bingo_core is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bingo_core.dep import DepManager

BINGO_LIGHT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bingo-light"
)


def _has_npm():
    return shutil.which("npm") is not None


def _has_patch():
    return shutil.which("patch") is not None


def _run_bl(args, cwd):
    """Run bingo-light CLI with --json and return parsed result."""
    result = subprocess.run(
        [sys.executable, BINGO_LIGHT] + args + ["--json", "--yes"],
        cwd=cwd, capture_output=True, text=True,
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": result.stderr or result.stdout, "returncode": result.returncode}


@unittest.skipUnless(_has_npm(), "npm not available")
@unittest.skipUnless(_has_patch(), "patch command not available")
class TestDepNpm(unittest.TestCase):
    """End-to-end tests for npm dependency patching."""

    @classmethod
    def setUpClass(cls):
        """Create a temporary npm project with lodash installed."""
        cls.tmpdir = tempfile.mkdtemp(prefix="bingo-dep-test-")
        # npm init
        subprocess.run(
            ["npm", "init", "-y"],
            cwd=cls.tmpdir, capture_output=True,
        )
        # install lodash (small, stable, well-known)
        subprocess.run(
            ["npm", "install", "lodash"],
            cwd=cls.tmpdir, capture_output=True, timeout=60,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _modify_lodash(self):
        """Add a comment to lodash.js."""
        path = os.path.join(self.tmpdir, "node_modules", "lodash", "lodash.js")
        with open(path, "a") as f:
            f.write("\n// bingo-light-test-marker\n")

    def _lodash_has_marker(self):
        """Check if lodash.js has our test marker."""
        path = os.path.join(self.tmpdir, "node_modules", "lodash", "lodash.js")
        with open(path) as f:
            return "bingo-light-test-marker" in f.read()

    def _clean_reinstall(self):
        """Remove node_modules and reinstall (without postinstall hook)."""
        # Temporarily remove postinstall to get a clean baseline
        pkg_json = os.path.join(self.tmpdir, "package.json")
        with open(pkg_json) as f:
            data = json.load(f)
        saved_hook = data.get("scripts", {}).pop("postinstall", None)
        with open(pkg_json, "w") as f:
            json.dump(data, f, indent=2)

        nm = os.path.join(self.tmpdir, "node_modules")
        shutil.rmtree(nm, ignore_errors=True)
        subprocess.run(
            ["npm", "install"],
            cwd=self.tmpdir, capture_output=True, timeout=60,
        )

        # Restore hook
        if saved_hook:
            with open(pkg_json) as f:
                data = json.load(f)
            data.setdefault("scripts", {})["postinstall"] = saved_hook
            with open(pkg_json, "w") as f:
                json.dump(data, f, indent=2)

    def _clean_patches(self):
        """Remove .bingo-deps directory."""
        bd = os.path.join(self.tmpdir, ".bingo-deps")
        if os.path.isdir(bd):
            shutil.rmtree(bd)

    # ── Tests ────────────────────────────────────────────────────────────

    def test_01_status_empty(self):
        """dep status with no patches returns empty list."""
        self._clean_patches()
        dm = DepManager(self.tmpdir)
        result = dm.status()
        self.assertTrue(result["ok"])
        self.assertEqual(result["total_packages"], 0)

    def test_02_patch_no_changes(self):
        """dep patch on unmodified package returns error."""
        self._clean_patches()
        dm = DepManager(self.tmpdir)
        result = dm.patch("lodash")
        self.assertFalse(result["ok"])
        self.assertIn("No modifications", result.get("error", ""))

    def test_03_patch_generates_file(self):
        """dep patch on modified package creates .patch file."""
        self._clean_patches()
        self._modify_lodash()
        dm = DepManager(self.tmpdir)
        result = dm.patch("lodash", "test-fix", "test description")
        self.assertTrue(result["ok"])
        self.assertEqual(result["package"], "lodash")
        self.assertEqual(result["patch"], "test-fix.patch")
        self.assertEqual(result["manager"], "npm")
        self.assertGreater(result["files_changed"], 0)
        # Verify file exists
        patch_path = os.path.join(
            self.tmpdir, ".bingo-deps", "patches", "lodash", "test-fix.patch"
        )
        self.assertTrue(os.path.isfile(patch_path))

    def test_04_status_shows_package(self):
        """dep status shows tracked package after patching."""
        dm = DepManager(self.tmpdir)
        result = dm.status()
        self.assertTrue(result["ok"])
        self.assertEqual(result["total_packages"], 1)
        pkg = result["packages"][0]
        self.assertEqual(pkg["package"], "lodash")
        self.assertEqual(pkg["status"], "ok")
        self.assertEqual(pkg["patches"], 1)

    def test_05_list_patches(self):
        """dep list shows the created patch."""
        dm = DepManager(self.tmpdir)
        result = dm.list_patches()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["patches"]), 1)
        p = result["patches"][0]
        self.assertEqual(p["package"], "lodash")
        self.assertEqual(p["patch"], "test-fix.patch")
        self.assertTrue(p["exists"])

    def test_06_apply_after_reinstall(self):
        """dep apply restores patch after clean npm install."""
        self._clean_reinstall()
        self.assertFalse(self._lodash_has_marker())

        dm = DepManager(self.tmpdir)
        result = dm.apply()
        self.assertTrue(result["ok"])
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertTrue(self._lodash_has_marker())

    def test_07_sync_same_version(self):
        """dep sync on same version reapplies patches."""
        self._clean_reinstall()
        dm = DepManager(self.tmpdir)
        result = dm.sync()
        self.assertTrue(result["ok"])
        self.assertEqual(result["total_conflicts"], 0)
        self.assertTrue(self._lodash_has_marker())

    def test_08_drop_patch(self):
        """dep drop removes the patch."""
        dm = DepManager(self.tmpdir)
        result = dm.drop("lodash", "test-fix")
        self.assertTrue(result["ok"])
        # Verify gone
        result2 = dm.list_patches()
        self.assertEqual(len(result2["patches"]), 0)

    def test_09_patch_unknown_package(self):
        """dep patch on non-existent package returns error."""
        dm = DepManager(self.tmpdir)
        result = dm.patch("nonexistent-package-xyz-123")
        self.assertFalse(result["ok"])

    def test_10_cli_dep_status(self):
        """CLI: bingo-light dep status --json works."""
        result = _run_bl(["dep", "status"], self.tmpdir)
        self.assertTrue(result["ok"])
        self.assertIn("total_packages", result)

    def test_11_cli_dep_patch_and_apply(self):
        """CLI: full patch → reinstall → apply cycle via CLI."""
        self._clean_patches()
        self._modify_lodash()

        # Patch
        result = _run_bl(["dep", "patch", "lodash", "cli-test"], self.tmpdir)
        self.assertTrue(result["ok"], f"Patch failed: {result}")

        # Reinstall (wipes changes)
        self._clean_reinstall()
        self.assertFalse(self._lodash_has_marker())

        # Apply
        result = _run_bl(["dep", "apply"], self.tmpdir)
        self.assertTrue(result["ok"], f"Apply failed: {result}")
        self.assertTrue(self._lodash_has_marker())

        # Cleanup
        dm = DepManager(self.tmpdir)
        dm.drop("lodash")


@unittest.skipUnless(_has_npm(), "npm not available")
@unittest.skipUnless(_has_patch(), "patch command not available")
class TestDepEdgeCases(unittest.TestCase):
    """Edge case tests for dep patching."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="bingo-dep-edge-")
        subprocess.run(["npm", "init", "-y"], cwd=cls.tmpdir, capture_output=True)
        subprocess.run(
            ["npm", "install", "lodash"],
            cwd=cls.tmpdir, capture_output=True, timeout=60,
        )

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def _clean(self):
        bd = os.path.join(self.tmpdir, ".bingo-deps")
        if os.path.isdir(bd):
            shutil.rmtree(bd)

    def test_multiple_patches_per_package(self):
        """Multiple patches on the same package stack correctly."""
        self._clean()
        dm = DepManager(self.tmpdir)

        # First patch: modify lodash.js
        path = os.path.join(self.tmpdir, "node_modules", "lodash", "lodash.js")
        with open(path, "a") as f:
            f.write("\n// patch-one\n")
        r1 = dm.patch("lodash", "first-fix")
        self.assertTrue(r1["ok"])

        # Second patch: modify a different file
        fp2 = os.path.join(self.tmpdir, "node_modules", "lodash", "lodash.min.js")
        if os.path.isfile(fp2):
            with open(fp2, "a") as f:
                f.write("\n// patch-two\n")
            r2 = dm.patch("lodash", "second-fix")
            self.assertTrue(r2["ok"])

            # List shows both
            lst = dm.list_patches("lodash")
            self.assertEqual(len(lst["patches"]), 2)

        self._clean()

    def test_postinstall_hook_idempotent(self):
        """Calling patch twice doesn't duplicate the postinstall hook."""
        self._clean()
        dm = DepManager(self.tmpdir)

        path = os.path.join(self.tmpdir, "node_modules", "lodash", "lodash.js")
        with open(path, "a") as f:
            f.write("\n// idem-test\n")
        dm.patch("lodash", "idem-1")

        # Read package.json postinstall
        with open(os.path.join(self.tmpdir, "package.json")) as f:
            data = json.load(f)
        hook1 = data.get("scripts", {}).get("postinstall", "")

        # Patch again
        with open(path, "a") as f:
            f.write("\n// idem-test-2\n")
        dm.patch("lodash", "idem-2")

        with open(os.path.join(self.tmpdir, "package.json")) as f:
            data2 = json.load(f)
        hook2 = data2.get("scripts", {}).get("postinstall", "")

        # Hook should not be duplicated
        self.assertEqual(hook1, hook2)
        self.assertEqual(hook2.count("dep apply"), 1)

        self._clean()
        # Restore original package.json
        data2.get("scripts", {}).pop("postinstall", None)
        with open(os.path.join(self.tmpdir, "package.json"), "w") as f:
            json.dump(data2, f, indent=2)

    def test_drop_all_then_status(self):
        """Dropping all patches leaves clean state."""
        self._clean()
        dm = DepManager(self.tmpdir)

        path = os.path.join(self.tmpdir, "node_modules", "lodash", "lodash.js")
        with open(path, "a") as f:
            f.write("\n// drop-test\n")
        dm.patch("lodash", "to-drop")
        dm.drop("lodash")

        st = dm.status()
        self.assertEqual(st["total_packages"], 0)
        self.assertEqual(st["total_patches"], 0)

    def test_apply_missing_package(self):
        """Apply when tracked package is uninstalled reports error."""
        self._clean()
        dm = DepManager(self.tmpdir)

        # Create a patch config manually for a non-installed package
        os.makedirs(os.path.join(self.tmpdir, ".bingo-deps", "patches", "fake-pkg"), exist_ok=True)
        with open(os.path.join(self.tmpdir, ".bingo-deps", "patches", "fake-pkg", "test.patch"), "w") as f:
            f.write("--- a/fake-pkg/index.js\n+++ b/fake-pkg/index.js\n")
        config = dm._load_config()
        config["packages"]["fake-pkg"] = {
            "version": "1.0.0", "manager": "npm", "patches": ["test.patch"]
        }
        dm._save_config()

        result = dm.apply("fake-pkg")
        self.assertFalse(result["ok"])

        self._clean()

    def test_sync_empty(self):
        """Sync with no tracked packages is ok."""
        self._clean()
        dm = DepManager(self.tmpdir)
        result = dm.sync()
        self.assertTrue(result["ok"])
        self.assertEqual(result["total_conflicts"], 0)


class TestDepManager(unittest.TestCase):
    """Unit tests for DepManager without network access."""

    def test_empty_project(self):
        """DepManager on empty dir returns empty status."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dm = DepManager(tmpdir)
            result = dm.status()
            self.assertTrue(result["ok"])
            self.assertEqual(result["total_packages"], 0)

    def test_list_empty(self):
        """list_patches on empty project returns empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dm = DepManager(tmpdir)
            result = dm.list_patches()
            self.assertTrue(result["ok"])
            self.assertEqual(result["patches"], [])

    def test_drop_nonexistent(self):
        """drop on non-tracked package returns error."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dm = DepManager(tmpdir)
            result = dm.drop("nonexistent")
            self.assertFalse(result["ok"])

    def test_apply_empty(self):
        """apply with no tracked packages returns ok."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dm = DepManager(tmpdir)
            result = dm.apply()
            self.assertTrue(result["ok"])
            self.assertEqual(result["applied"], 0)


if __name__ == "__main__":
    unittest.main()
