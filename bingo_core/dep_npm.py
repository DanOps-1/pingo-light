"""
bingo_core.dep_npm — npm/pnpm/yarn backend for dependency patching.

Detects npm projects, fetches original packages from registry,
resolves install paths in node_modules/.

Python 3.8+ stdlib only.
"""

from __future__ import annotations

import json
import os
import tarfile
from typing import List, Optional
from urllib.request import urlopen

from bingo_core.dep import DepBackend


class NpmBackend(DepBackend):
    """Backend for npm/pnpm/yarn packages."""

    name = "npm"

    def detect(self, cwd: str) -> bool:
        """Detect npm project by presence of package.json or node_modules/."""
        return (
            os.path.isfile(os.path.join(cwd, "package.json"))
            or os.path.isdir(os.path.join(cwd, "node_modules"))
        )

    def get_installed_version(self, package: str, cwd: str) -> Optional[str]:
        """Get installed version from node_modules/<package>/package.json."""
        pkg_json = os.path.join(cwd, "node_modules", package, "package.json")
        if not os.path.isfile(pkg_json):
            # Try scoped package
            if "/" in package:
                pkg_json = os.path.join(cwd, "node_modules", package, "package.json")
            if not os.path.isfile(pkg_json):
                return None
        try:
            with open(pkg_json) as f:
                data = json.load(f)
            return data.get("version")
        except (json.JSONDecodeError, OSError):
            return None

    def get_install_path(self, package: str, cwd: str) -> Optional[str]:
        """Get the filesystem path of the installed package."""
        path = os.path.join(cwd, "node_modules", package)
        if os.path.isdir(path):
            return path
        return None

    def fetch_original(self, package: str, version: str, dest: str) -> bool:
        """Download original package from npm registry and extract to dest.

        Uses the npm registry API to get the tarball URL, downloads and
        extracts it. The tarball contains a 'package/' prefix which we strip.
        """
        try:
            # Fetch package metadata from registry
            # Handle scoped packages: @scope/name -> @scope%2Fname
            encoded = package.replace("/", "%2F")
            url = f"https://registry.npmjs.org/{encoded}/{version}"
            with urlopen(url, timeout=30) as resp:
                meta = json.loads(resp.read().decode())

            tarball_url = meta.get("dist", {}).get("tarball")
            if not tarball_url:
                return False

            # Download tarball
            tmptar = os.path.join(dest, "_pkg.tgz")
            with urlopen(tarball_url, timeout=60) as resp:
                with open(tmptar, "wb") as f:
                    f.write(resp.read())

            # Extract (npm tarballs have a 'package/' prefix)
            with tarfile.open(tmptar, "r:gz") as tar:
                for member in tar.getmembers():
                    # Strip the 'package/' prefix
                    if member.name.startswith("package/"):
                        member.name = member.name[len("package/"):]
                    elif member.name == "package":
                        continue
                    # Security: skip absolute paths and ..
                    if member.name.startswith("/") or ".." in member.name:
                        continue
                    tar.extract(member, dest)

            os.remove(tmptar)
            return True

        except Exception:
            return False

    def list_files(self, package: str, cwd: str) -> List[str]:
        """List all files in the installed package."""
        install_path = self.get_install_path(package, cwd)
        if not install_path:
            return []
        result = []
        for root, _dirs, files in os.walk(install_path):
            for f in files:
                full = os.path.join(root, f)
                rel = os.path.relpath(full, install_path)
                result.append(rel)
        return sorted(result)

    def install_hook_command(self) -> str:
        return "bingo-light dep apply"
