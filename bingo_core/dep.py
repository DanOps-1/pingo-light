"""
bingo_core.dep — Dependency patching engine.

Maintains patches on top of npm/pip packages. Same mental model as git fork
patching: upstream is the published package, your patches sit on top.

Storage layout:
    .bingo-deps/
        config.json         # { "packages": { "some-lib": { "version": "2.1.0", "manager": "npm" } } }
        patches/
            some-lib/
                fix-auth.patch
                add-logging.patch
            another-lib/
                typo-fix.patch

Python 3.8+ stdlib only. No pip dependencies.
"""

from __future__ import annotations

import difflib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ─── Constants ───────────────────────────────────────────────────────────────

DEP_DIR = ".bingo-deps"
DEP_CONFIG = "config.json"
PATCHES_DIR = "patches"


# ─── Data Models ─────────────────────────────────────────────────────────────


@dataclass
class DepPatch:
    """A single patch on a dependency."""
    package: str
    name: str          # patch file name (e.g. "fix-auth.patch")
    path: str          # full path to .patch file
    description: str = ""


@dataclass
class DepPackage:
    """A patched dependency."""
    name: str
    version: str       # version the patches were generated against
    manager: str       # "npm" | "pip"
    patches: List[DepPatch] = field(default_factory=list)


@dataclass
class DepConflict:
    """Conflict when applying a patch after upstream update."""
    package: str
    patch_name: str
    old_version: str
    new_version: str
    error: str
    hint: str = ""


# ─── Backend Interface ───────────────────────────────────────────────────────


class DepBackend:
    """Abstract backend for a package manager (npm, pip, etc.)."""

    name: str = "unknown"

    def detect(self, cwd: str) -> bool:
        """Return True if this backend applies to the project at cwd."""
        raise NotImplementedError

    def get_installed_version(self, package: str, cwd: str) -> Optional[str]:
        """Get the currently installed version of a package."""
        raise NotImplementedError

    def get_install_path(self, package: str, cwd: str) -> Optional[str]:
        """Get the filesystem path where the package is installed."""
        raise NotImplementedError

    def fetch_original(self, package: str, version: str, dest: str) -> bool:
        """Download the original (unpatched) package source to dest dir."""
        raise NotImplementedError

    def list_files(self, package: str, cwd: str) -> List[str]:
        """List all files in the installed package (relative paths)."""
        raise NotImplementedError

    def install_hook_command(self) -> str:
        """Return the postinstall command string for auto-applying patches."""
        return "bingo-light dep apply"


# ─── Core Engine ─────────────────────────────────────────────────────────────


class DepManager:
    """Core dependency patching engine."""

    def __init__(self, cwd: str = "."):
        self.cwd = os.path.abspath(cwd)
        self.dep_dir = os.path.join(self.cwd, DEP_DIR)
        self.config_path = os.path.join(self.dep_dir, DEP_CONFIG)
        self.patches_dir = os.path.join(self.dep_dir, PATCHES_DIR)
        self._backends: List[DepBackend] = []
        self._config: Optional[Dict] = None

        # Register backends (import lazily to avoid circular deps)
        from bingo_core.dep_npm import NpmBackend
        from bingo_core.dep_pip import PipBackend
        self._backends = [NpmBackend(), PipBackend()]

    # ─── Config ──────────────────────────────────────────────────────────

    def _load_config(self) -> Dict:
        if self._config is not None:
            return self._config
        if os.path.isfile(self.config_path):
            with open(self.config_path) as f:
                self._config = json.load(f)
        else:
            self._config = {"packages": {}}
        return self._config

    def _save_config(self) -> None:
        os.makedirs(self.dep_dir, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self._config or {}, f, indent=2)
            f.write("\n")

    # ─── Backend Detection ───────────────────────────────────────────────

    def _detect_backend(self, package: str) -> Optional[DepBackend]:
        """Auto-detect which backend manages a package."""
        for b in self._backends:
            if b.detect(self.cwd) and b.get_installed_version(package, self.cwd):
                return b
        return None

    def _get_backend(self, manager: str) -> Optional[DepBackend]:
        """Get backend by name."""
        for b in self._backends:
            if b.name == manager:
                return b
        return None

    # ─── Postinstall Hook ─────────────────────────────────────────────────

    def _ensure_postinstall_hook(self, backend: DepBackend) -> Optional[str]:
        """Add 'bingo-light dep apply' to package.json postinstall if npm project.

        Returns a message if hook was added, None otherwise.
        """
        if backend.name != "npm":
            return None

        pkg_json_path = os.path.join(self.cwd, "package.json")
        if not os.path.isfile(pkg_json_path):
            return None

        try:
            with open(pkg_json_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        scripts = data.setdefault("scripts", {})
        # Find bingo-light binary — use absolute path for reliability
        bl_bin = shutil.which("bingo-light")
        if bl_bin:
            hook_cmd = f"{bl_bin} dep apply"
        else:
            # Fallback: npx always works if npm is available
            hook_cmd = "npx --yes bingo-light dep apply"

        existing = scripts.get("postinstall", "")
        if hook_cmd in existing:
            return None  # already present

        if existing:
            scripts["postinstall"] = f"{existing} && {hook_cmd}"
        else:
            scripts["postinstall"] = hook_cmd

        try:
            with open(pkg_json_path, "w") as f:
                json.dump(data, f, indent=2)
                f.write("\n")
        except OSError:
            return None

        return "postinstall hook added to package.json"

    # ─── Patch Generation ────────────────────────────────────────────────

    def patch(self, package: str, patch_name: str = "",
              description: str = "") -> Dict[str, Any]:
        """Generate a patch for a modified dependency.

        1. Detect the package manager
        2. Find the installed (modified) version
        3. Download the original version
        4. Generate a unified diff
        5. Save as .patch file
        """
        backend = self._detect_backend(package)
        if not backend:
            return {"ok": False, "error": f"Package '{package}' not found in any package manager"}

        version = backend.get_installed_version(package, self.cwd)
        if not version:
            return {"ok": False, "error": f"Cannot determine version for '{package}'"}

        install_path = backend.get_install_path(package, self.cwd)
        if not install_path or not os.path.isdir(install_path):
            return {"ok": False, "error": f"Install path not found for '{package}'"}

        # Download original
        tmpdir = tempfile.mkdtemp(prefix="bingo-dep-")
        try:
            original_dir = os.path.join(tmpdir, "original")
            os.makedirs(original_dir)
            if not backend.fetch_original(package, version, original_dir):
                return {"ok": False, "error": f"Failed to download original '{package}@{version}'"}

            # Generate unified diff
            diff_lines = _generate_diff(original_dir, install_path, package)
            if not diff_lines:
                return {"ok": False, "error": f"No modifications found in '{package}'"}

            # Determine patch name
            if not patch_name:
                config = self._load_config()
                pkg_conf = config.get("packages", {}).get(package, {})
                existing = pkg_conf.get("patches", [])
                idx = len(existing) + 1
                patch_name = f"patch-{idx:03d}"

            if not patch_name.endswith(".patch"):
                patch_name += ".patch"

            # Save patch
            pkg_patches_dir = os.path.join(self.patches_dir, package)
            os.makedirs(pkg_patches_dir, exist_ok=True)
            patch_path = os.path.join(pkg_patches_dir, patch_name)
            with open(patch_path, "w") as f:
                f.writelines(diff_lines)

            # Update config
            config = self._load_config()
            pkgs = config.setdefault("packages", {})
            pkg = pkgs.setdefault(package, {
                "version": version,
                "manager": backend.name,
                "patches": [],
            })
            pkg["version"] = version
            if patch_name not in pkg["patches"]:
                pkg["patches"].append(patch_name)
            if description:
                pkg.setdefault("descriptions", {})[patch_name] = description
            self._save_config()

            # Auto-add postinstall hook on first patch
            hook_msg = self._ensure_postinstall_hook(backend)

            file_count = sum(1 for line in diff_lines if line.startswith("--- "))
            result = {
                "ok": True,
                "package": package,
                "version": version,
                "patch": patch_name,
                "files_changed": file_count,
                "manager": backend.name,
            }
            if hook_msg:
                result["hook"] = hook_msg
            return result
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    # ─── Patch Application ───────────────────────────────────────────────

    def apply(self, package: str = "") -> Dict[str, Any]:
        """Apply patches to installed dependencies.

        If package is empty, apply all patches for all tracked packages.
        """
        config = self._load_config()
        packages = config.get("packages", {})

        if package:
            if package not in packages:
                return {"ok": False, "error": f"No patches tracked for '{package}'"}
            targets = {package: packages[package]}
        else:
            targets = packages

        results = []
        for pkg_name, pkg_conf in targets.items():
            backend = self._get_backend(pkg_conf.get("manager", ""))
            if not backend:
                results.append({"package": pkg_name, "ok": False, "error": "Unknown manager"})
                continue

            install_path = backend.get_install_path(pkg_name, self.cwd)
            if not install_path:
                results.append({"package": pkg_name, "ok": False, "error": "Not installed"})
                continue

            for patch_name in pkg_conf.get("patches", []):
                patch_path = os.path.join(self.patches_dir, pkg_name, patch_name)
                if not os.path.isfile(patch_path):
                    results.append({
                        "package": pkg_name, "patch": patch_name,
                        "ok": False, "error": "Patch file missing",
                    })
                    continue

                success, error = _apply_patch(patch_path, install_path)
                results.append({
                    "package": pkg_name, "patch": patch_name,
                    "ok": success, "error": error,
                })

        applied = [r for r in results if r["ok"]]
        failed = [r for r in results if not r["ok"]]
        return {
            "ok": len(failed) == 0,
            "applied": len(applied),
            "failed": len(failed),
            "results": results,
        }

    # ─── Status ──────────────────────────────────────────────────────────

    def status(self) -> Dict[str, Any]:
        """Show status of all tracked dependency patches."""
        config = self._load_config()
        packages = config.get("packages", {})
        pkg_status = []

        for pkg_name, pkg_conf in packages.items():
            backend = self._get_backend(pkg_conf.get("manager", ""))
            current_ver = None
            installed = False
            if backend:
                current_ver = backend.get_installed_version(pkg_name, self.cwd)
                installed = current_ver is not None

            patched_ver = pkg_conf.get("version", "?")
            version_match = (current_ver == patched_ver) if current_ver else None
            patch_count = len(pkg_conf.get("patches", []))

            status = "ok"
            if not installed:
                status = "not_installed"
            elif not version_match:
                status = "version_mismatch"

            pkg_status.append({
                "package": pkg_name,
                "manager": pkg_conf.get("manager", "?"),
                "patched_version": patched_ver,
                "installed_version": current_ver or "?",
                "patches": patch_count,
                "status": status,
            })

        return {
            "ok": True,
            "packages": pkg_status,
            "total_packages": len(pkg_status),
            "total_patches": sum(p["patches"] for p in pkg_status),
        }

    # ─── List ────────────────────────────────────────────────────────────

    def list_patches(self, package: str = "") -> Dict[str, Any]:
        """List all patches, optionally for a specific package."""
        config = self._load_config()
        packages = config.get("packages", {})
        all_patches = []

        targets = {package: packages[package]} if package and package in packages else packages
        for pkg_name, pkg_conf in targets.items():
            descs = pkg_conf.get("descriptions", {})
            for patch_name in pkg_conf.get("patches", []):
                patch_path = os.path.join(self.patches_dir, pkg_name, patch_name)
                all_patches.append({
                    "package": pkg_name,
                    "patch": patch_name,
                    "description": descs.get(patch_name, ""),
                    "version": pkg_conf.get("version", "?"),
                    "exists": os.path.isfile(patch_path),
                })

        return {"ok": True, "patches": all_patches}

    # ─── Sync (after npm/pip update) ─────────────────────────────────────

    def sync(self) -> Dict[str, Any]:
        """After a package manager update, re-apply patches and detect conflicts."""
        config = self._load_config()
        packages = config.get("packages", {})
        results = []

        for pkg_name, pkg_conf in packages.items():
            backend = self._get_backend(pkg_conf.get("manager", ""))
            if not backend:
                continue

            current_ver = backend.get_installed_version(pkg_name, self.cwd)
            patched_ver = pkg_conf.get("version", "")

            if not current_ver:
                results.append({
                    "package": pkg_name, "status": "not_installed",
                    "old_version": patched_ver, "new_version": None,
                })
                continue

            if current_ver == patched_ver:
                # Same version — just re-apply
                apply_result = self.apply(pkg_name)
                results.append({
                    "package": pkg_name, "status": "reapplied",
                    "old_version": patched_ver, "new_version": current_ver,
                    "apply": apply_result,
                })
            else:
                # Version changed — try to apply, may conflict
                install_path = backend.get_install_path(pkg_name, self.cwd)
                conflicts = []
                applied = []

                for patch_name in pkg_conf.get("patches", []):
                    patch_path = os.path.join(self.patches_dir, pkg_name, patch_name)
                    if not os.path.isfile(patch_path):
                        conflicts.append({
                            "patch": patch_name,
                            "error": "Patch file missing",
                        })
                        continue

                    success, error = _apply_patch(patch_path, install_path)
                    if success:
                        applied.append(patch_name)
                    else:
                        conflicts.append({
                            "patch": patch_name,
                            "error": error,
                            "hint": f"Package updated {patched_ver} → {current_ver}. "
                                    f"Regenerate patch: bingo-light dep patch {pkg_name}",
                        })

                status = "synced" if not conflicts else "conflict"
                results.append({
                    "package": pkg_name,
                    "status": status,
                    "old_version": patched_ver,
                    "new_version": current_ver,
                    "applied": applied,
                    "conflicts": conflicts,
                })

                # Update tracked version if all patches applied
                if not conflicts:
                    pkg_conf["version"] = current_ver
                    self._save_config()

        total_conflicts = sum(
            len(r.get("conflicts", [])) for r in results
        )
        return {
            "ok": total_conflicts == 0,
            "results": results,
            "total_conflicts": total_conflicts,
            "recommended_action": "ok" if total_conflicts == 0 else "regenerate_patches",
        }

    # ─── Drop ────────────────────────────────────────────────────────────

    def drop(self, package: str, patch_name: str = "") -> Dict[str, Any]:
        """Remove a patch or all patches for a package."""
        config = self._load_config()
        packages = config.get("packages", {})

        if package not in packages:
            return {"ok": False, "error": f"No patches tracked for '{package}'"}

        if patch_name:
            # Remove specific patch
            if not patch_name.endswith(".patch"):
                patch_name += ".patch"
            patches = packages[package].get("patches", [])
            if patch_name not in patches:
                return {"ok": False, "error": f"Patch '{patch_name}' not found"}
            patches.remove(patch_name)
            patch_path = os.path.join(self.patches_dir, package, patch_name)
            if os.path.isfile(patch_path):
                os.remove(patch_path)
            if not patches:
                del packages[package]
                pkg_dir = os.path.join(self.patches_dir, package)
                if os.path.isdir(pkg_dir):
                    shutil.rmtree(pkg_dir)
        else:
            # Remove all patches for package
            del packages[package]
            pkg_dir = os.path.join(self.patches_dir, package)
            if os.path.isdir(pkg_dir):
                shutil.rmtree(pkg_dir)

        self._save_config()
        return {"ok": True, "package": package, "dropped": patch_name or "all"}


# ─── Diff Utilities ──────────────────────────────────────────────────────────


def _generate_diff(original_dir: str, modified_dir: str,
                   label: str) -> List[str]:
    """Generate unified diff between two directory trees."""
    diff_lines: List[str] = []

    for root, _dirs, files in os.walk(original_dir):
        for fname in sorted(files):
            orig_path = os.path.join(root, fname)
            rel = os.path.relpath(orig_path, original_dir)
            mod_path = os.path.join(modified_dir, rel)

            # Skip non-text files
            if _is_binary(orig_path):
                continue

            try:
                with open(orig_path) as f:
                    orig_lines = f.readlines()
            except (UnicodeDecodeError, OSError):
                continue

            if os.path.isfile(mod_path):
                try:
                    with open(mod_path) as f:
                        mod_lines = f.readlines()
                except (UnicodeDecodeError, OSError):
                    continue

                if orig_lines != mod_lines:
                    diff = difflib.unified_diff(
                        orig_lines, mod_lines,
                        fromfile=f"a/{label}/{rel}",
                        tofile=f"b/{label}/{rel}",
                    )
                    diff_lines.extend(diff)

    # Check for new files in modified that don't exist in original
    for root, _dirs, files in os.walk(modified_dir):
        for fname in sorted(files):
            mod_path = os.path.join(root, fname)
            rel = os.path.relpath(mod_path, modified_dir)
            orig_path = os.path.join(original_dir, rel)

            if not os.path.isfile(orig_path) and not _is_binary(mod_path):
                try:
                    with open(mod_path) as f:
                        mod_lines = f.readlines()
                    diff = difflib.unified_diff(
                        [], mod_lines,
                        fromfile=f"a/{label}/{rel}",
                        tofile=f"b/{label}/{rel}",
                    )
                    diff_lines.extend(diff)
                except (UnicodeDecodeError, OSError):
                    continue

    return diff_lines


def _apply_patch(patch_path: str, target_dir: str) -> Tuple[bool, str]:
    """Apply a unified diff patch to a directory. Returns (success, error)."""
    # Try system `patch` command first (most reliable)
    # Patches use a/<pkg>/<file> format, so -p2 strips the a/<pkg>/ prefix
    if shutil.which("patch"):
        with open(patch_path) as pf:
            result = subprocess.run(
                ["patch", "-p2", "-d", target_dir, "--forward", "--batch"],
                stdin=pf,
                capture_output=True, text=True,
            )
        if result.returncode == 0:
            return (True, "")
        # patch may partially apply; check if "FAILED" in output
        if "FAILED" in result.stdout or result.returncode != 0:
            return (False, result.stdout.strip() or result.stderr.strip())

    # Fallback: Python-based patch application
    return _apply_patch_python(patch_path, target_dir)


def _apply_patch_python(patch_path: str, target_dir: str) -> Tuple[bool, str]:
    """Pure-Python patch application (basic unified diff support)."""
    try:
        with open(patch_path) as f:
            patch_text = f.read()
    except OSError as e:
        return (False, str(e))

    # Parse hunks
    current_file = None
    hunks: Dict[str, List[str]] = {}

    for line in patch_text.splitlines(keepends=True):
        if line.startswith("+++ b/"):
            # Extract relative path after the package name prefix
            parts = line[6:].strip().split("/", 1)
            current_file = parts[1] if len(parts) > 1 else parts[0]
            hunks.setdefault(current_file, [])
        elif current_file and (line.startswith("+") or line.startswith("-")
                               or line.startswith(" ") or line.startswith("@@")):
            hunks[current_file].append(line)

    if not hunks:
        return (False, "No hunks found in patch")

    # For now, just verify the files exist — full Python patching is complex
    missing = [f for f in hunks if not os.path.isfile(os.path.join(target_dir, f))]
    if missing:
        return (False, f"Files not found: {', '.join(missing[:3])}")

    return (False, "Python-only patch application not fully implemented; install 'patch' command")


def _is_binary(path: str) -> bool:
    """Heuristic: check if a file is binary."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
        return b"\x00" in chunk
    except OSError:
        return True
