"""
test_core.py — Unit tests for bingo_core package

Uses unittest + real temp git repos.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Ensure bingo_core is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bingo_core import (
    VERSION,
    PATCH_PREFIX,
    CONFIG_FILE,
    BINGO_DIR,
    DEFAULT_TRACKING,
    DEFAULT_PATCHES,
    BingoError,
    GitError,
    NotGitRepoError,
    NotInitializedError,
    DirtyTreeError,
    PatchInfo,
    ConflictInfo,
    Git,
    Config,
    State,
    Repo,
)


def _run(cmd: str, cwd: str) -> str:
    """Helper: run a shell command in a directory."""
    result = subprocess.run(
        cmd, shell=True, cwd=cwd, capture_output=True, text=True
    )
    return result.stdout.strip()


def _create_git_repo(path: str) -> str:
    """Create a bare-bones git repo with one commit."""
    os.makedirs(path, exist_ok=True)
    _run("git init", path)
    _run("git config user.email test@test.com", path)
    _run("git config user.name Test", path)
    # Create initial commit on main
    _run("git checkout -b main", path)
    with open(os.path.join(path, "README.md"), "w") as f:
        f.write("# Test\n")
    _run("git add -A && git commit -m 'initial'", path)
    return path


def _create_upstream_and_fork() -> tuple:
    """Create an upstream repo and a fork (clone) for testing.

    Returns (upstream_path, fork_path).
    """
    base_dir = tempfile.mkdtemp(prefix="bl-test-")
    upstream = os.path.join(base_dir, "upstream")
    fork = os.path.join(base_dir, "fork")

    # Create upstream
    _create_git_repo(upstream)

    # Clone as fork
    _run(f"git clone {upstream} {fork}", base_dir)
    _run("git config user.email test@test.com", fork)
    _run("git config user.name Test", fork)

    return upstream, fork


class TestGit(unittest.TestCase):
    """Tests for the Git class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bl-git-test-")
        _create_git_repo(self.tmpdir)
        self.git = Git(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_run_success(self):
        """git.run should return stdout on success."""
        result = self.git.run("rev-parse", "HEAD")
        self.assertTrue(len(result) == 40)  # full sha1

    def test_run_failure_raises(self):
        """git.run with check=True should raise GitError on failure."""
        with self.assertRaises(GitError) as ctx:
            self.git.run("rev-parse", "nonexistent-ref-xyz")
        self.assertIn("nonexistent-ref-xyz", str(ctx.exception))

    def test_run_ok_success(self):
        """git.run_ok should return True on success."""
        self.assertTrue(self.git.run_ok("rev-parse", "HEAD"))

    def test_run_ok_failure(self):
        """git.run_ok should return False on failure."""
        self.assertFalse(self.git.run_ok("rev-parse", "nonexistent-ref-xyz"))

    def test_rev_parse_valid(self):
        """rev_parse should return a full sha for valid ref."""
        sha = self.git.rev_parse("HEAD")
        self.assertIsNotNone(sha)
        self.assertEqual(len(sha), 40)

    def test_rev_parse_invalid(self):
        """rev_parse should return None for invalid ref."""
        self.assertIsNone(self.git.rev_parse("nonexistent-branch-xyz"))

    def test_is_clean(self):
        """is_clean should return True for a clean repo."""
        self.assertTrue(self.git.is_clean())

    def test_is_clean_dirty(self):
        """is_clean should return False when there are uncommitted changes."""
        with open(os.path.join(self.tmpdir, "dirty.txt"), "w") as f:
            f.write("dirty\n")
        _run("git add dirty.txt", self.tmpdir)
        self.assertFalse(self.git.is_clean())

    def test_ls_files_unmerged_clean(self):
        """ls_files_unmerged should return [] when no conflicts exist."""
        self.assertEqual(self.git.ls_files_unmerged(), [])

    def test_rev_list_count(self):
        """rev_list_count should return correct count."""
        # There is 1 commit (initial)
        # HEAD~1 doesn't exist if there's only 1 commit, so count the full history
        count = self.git.rev_list_count("HEAD")
        self.assertEqual(count, 1)

    def test_current_branch(self):
        """current_branch should return 'main'."""
        self.assertEqual(self.git.current_branch(), "main")

    def test_merge_base(self):
        """merge_base should return the commit itself for identical refs."""
        head = self.git.rev_parse("HEAD")
        base = self.git.merge_base("HEAD", "HEAD")
        self.assertEqual(base, head)

    def test_merge_base_invalid(self):
        """merge_base should return None for nonexistent refs."""
        self.assertIsNone(self.git.merge_base("HEAD", "nonexistent-xyz"))

    def test_log_patches_empty(self):
        """log_patches should return [] for an invalid range."""
        patches = self.git.log_patches("HEAD", "HEAD")
        self.assertEqual(patches, [])

    def test_diff_names_no_changes(self):
        """diff_names should return [] when there are no changes."""
        names = self.git.diff_names("HEAD..HEAD")
        self.assertEqual(names, [])


class TestConfig(unittest.TestCase):
    """Tests for the Config class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bl-config-test-")
        _create_git_repo(self.tmpdir)
        self.config = Config(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_not_initialized(self):
        """load should raise NotInitializedError if no config file."""
        with self.assertRaises(NotInitializedError):
            self.config.load()

    def test_save_and_load(self):
        """save then load should roundtrip config values."""
        self.config.save(
            url="https://example.com/upstream.git",
            branch="main",
            patches_branch="my-patches",
            tracking_branch="my-tracking",
        )
        data = self.config.load()
        self.assertEqual(data["upstream_url"], "https://example.com/upstream.git")
        self.assertEqual(data["upstream_branch"], "main")
        self.assertEqual(data["patches_branch"], "my-patches")
        self.assertEqual(data["tracking_branch"], "my-tracking")

    def test_get_set(self):
        """get/set should store and retrieve arbitrary keys."""
        self.config.save("url", "main")
        self.config.set("test.command", "make test")
        val = self.config.get("test.command")
        self.assertEqual(val, "make test")

    def test_get_nonexistent(self):
        """get should return None for nonexistent key."""
        self.config.save("url", "main")
        self.assertIsNone(self.config.get("nonexistent-key-xyz"))

    def test_exists(self):
        """exists should return True after save."""
        self.assertFalse(self.config.exists())
        self.config.save("url", "main")
        self.assertTrue(self.config.exists())

    def test_list_all(self):
        """list_all should return all config values."""
        self.config.save("url", "main")
        self.config.set("custom.key", "custom-value")
        items = self.config.list_all()
        self.assertIn("bingolight.upstream-url", items)
        self.assertIn("bingolight.custom.key", items)
        self.assertEqual(items["bingolight.custom.key"], "custom-value")


class TestState(unittest.TestCase):
    """Tests for the State class."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bl-state-test-")
        _create_git_repo(self.tmpdir)
        self.state = State(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_undo_roundtrip(self):
        """save_undo then load_undo should roundtrip."""
        self.state.save_undo("abc123", "def456")
        head, tracking = self.state.load_undo()
        self.assertEqual(head, "abc123")
        self.assertEqual(tracking, "def456")

    def test_undo_active(self):
        """mark_undo_active / is_undo_active should work."""
        self.assertFalse(self.state.is_undo_active())
        self.state.mark_undo_active()
        self.assertTrue(self.state.is_undo_active())

    def test_undo_save_clears_active(self):
        """save_undo should clear the undo-active marker."""
        self.state.mark_undo_active()
        self.assertTrue(self.state.is_undo_active())
        self.state.save_undo("head", "tracking")
        self.assertFalse(self.state.is_undo_active())

    def test_circuit_breaker_not_tripped_initially(self):
        """Circuit breaker should not be tripped initially."""
        self.assertFalse(self.state.check_circuit_breaker("target-hash"))

    def test_circuit_breaker_three_strikes(self):
        """Circuit breaker should trip after 3 failures on same target."""
        target = "abc123"
        self.state.record_circuit_breaker(target)
        self.assertFalse(self.state.check_circuit_breaker(target))
        self.state.record_circuit_breaker(target)
        self.assertFalse(self.state.check_circuit_breaker(target))
        self.state.record_circuit_breaker(target)
        self.assertTrue(self.state.check_circuit_breaker(target))

    def test_circuit_breaker_different_target(self):
        """Circuit breaker should reset when target changes."""
        self.state.record_circuit_breaker("target-1")
        self.state.record_circuit_breaker("target-1")
        self.state.record_circuit_breaker("target-1")
        # Different target should not be tripped
        self.assertFalse(self.state.check_circuit_breaker("target-2"))

    def test_circuit_breaker_clear(self):
        """clear_circuit_breaker should reset the breaker."""
        target = "abc123"
        for _ in range(3):
            self.state.record_circuit_breaker(target)
        self.assertTrue(self.state.check_circuit_breaker(target))
        self.state.clear_circuit_breaker()
        self.assertFalse(self.state.check_circuit_breaker(target))

    def test_patch_meta_get_default(self):
        """patch_meta_get should return defaults for unknown patch."""
        meta = self.state.patch_meta_get("unknown-patch")
        self.assertEqual(meta["reason"], "")
        self.assertEqual(meta["tags"], [])
        self.assertEqual(meta["status"], "permanent")

    def test_patch_meta_set_and_get(self):
        """patch_meta_set then get should work."""
        self.state.patch_meta_set("my-patch", "reason", "fixing a bug")
        meta = self.state.patch_meta_get("my-patch")
        self.assertEqual(meta["reason"], "fixing a bug")

    def test_patch_meta_tag(self):
        """patch_meta_set with 'tag' should append to tags list."""
        self.state.patch_meta_set("my-patch", "tag", "security")
        self.state.patch_meta_set("my-patch", "tag", "critical")
        meta = self.state.patch_meta_get("my-patch")
        self.assertIn("security", meta["tags"])
        self.assertIn("critical", meta["tags"])

    def test_patch_meta_tag_no_duplicates(self):
        """Adding same tag twice should not create duplicates."""
        self.state.patch_meta_set("my-patch", "tag", "security")
        self.state.patch_meta_set("my-patch", "tag", "security")
        meta = self.state.patch_meta_get("my-patch")
        self.assertEqual(meta["tags"].count("security"), 1)

    def test_sync_history_empty(self):
        """get_sync_history should return empty list initially."""
        history = self.state.get_sync_history()
        self.assertEqual(history["syncs"], [])

    def test_sync_history_record(self):
        """record_sync should add entries."""
        self.state.record_sync(
            behind=5,
            upstream_before="abc",
            upstream_after="def",
            patches=[{"name": "p1", "hash": "111"}],
        )
        history = self.state.get_sync_history()
        self.assertEqual(len(history["syncs"]), 1)
        self.assertEqual(history["syncs"][0]["upstream_commits_integrated"], 5)
        self.assertEqual(len(history["syncs"][0]["patches"]), 1)

    def test_sync_history_multiple(self):
        """Multiple record_sync calls should accumulate."""
        for i in range(3):
            self.state.record_sync(behind=i, upstream_before=f"b{i}", upstream_after=f"a{i}", patches=[])
        history = self.state.get_sync_history()
        self.assertEqual(len(history["syncs"]), 3)

    def test_session_roundtrip(self):
        """update_session / get_session should roundtrip."""
        self.assertIsNone(self.state.get_session())
        self.state.update_session("# Session notes\nHello")
        content = self.state.get_session()
        self.assertIn("Session notes", content)

    def test_load_undo_empty(self):
        """load_undo should return (None, None) if nothing saved."""
        head, tracking = self.state.load_undo()
        self.assertIsNone(head)
        self.assertIsNone(tracking)

    def test_patch_meta_tags_comma(self):
        """Comma-separated tags stored individually."""
        self.state._ensure_dir()
        self.state.patch_meta_set("p1", "tags", "a,b,c")
        meta = self.state.patch_meta_get("p1")
        self.assertEqual(meta["tags"], ["a", "b", "c"])

    def test_patch_meta_tags_plural_key(self):
        """'tags' key works same as 'tag'."""
        self.state._ensure_dir()
        self.state.patch_meta_set("p1", "tags", "x")
        self.state.patch_meta_set("p1", "tag", "y")
        meta = self.state.patch_meta_get("p1")
        self.assertEqual(sorted(meta["tags"]), ["x", "y"])

    def test_patch_meta_tags_dedup(self):
        """Duplicate tags not added."""
        self.state._ensure_dir()
        self.state.patch_meta_set("p1", "tags", "a,b")
        self.state.patch_meta_set("p1", "tags", "b,c")
        meta = self.state.patch_meta_get("p1")
        self.assertEqual(meta["tags"], ["a", "b", "c"])


class TestRepo(unittest.TestCase):
    """Integration tests for the Repo class with real git repos."""

    def setUp(self):
        self.upstream_path, self.fork_path = _create_upstream_and_fork()

    def tearDown(self):
        # Both are under the same base_dir parent
        base_dir = os.path.dirname(self.upstream_path)
        shutil.rmtree(base_dir, ignore_errors=True)

    def test_init_basic(self):
        """Repo.init should set up branches and config."""
        repo = Repo(self.fork_path)
        result = repo.init(self.upstream_path, "main")
        self.assertTrue(result["ok"])
        self.assertEqual(result["branch"], "main")
        self.assertEqual(result["tracking"], DEFAULT_TRACKING)
        self.assertEqual(result["patches"], DEFAULT_PATCHES)

        # Verify branches exist
        git = Git(self.fork_path)
        self.assertIsNotNone(git.rev_parse(DEFAULT_TRACKING))
        self.assertIsNotNone(git.rev_parse(DEFAULT_PATCHES))

        # Verify config file exists
        config = Config(self.fork_path)
        self.assertTrue(config.exists())
        data = config.load()
        self.assertEqual(data["upstream_branch"], "main")

    def test_init_and_status(self):
        """Repo.init followed by status should work."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        st = repo.status()
        self.assertTrue(st["ok"])
        self.assertEqual(st["behind"], 0)
        self.assertEqual(st["patch_count"], 0)
        self.assertTrue(st["up_to_date"])
        self.assertEqual(st["recommended_action"], "up_to_date")

    def test_status_behind(self):
        """Status should detect when behind upstream."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        # Add a commit to upstream
        with open(os.path.join(self.upstream_path, "new-file.txt"), "w") as f:
            f.write("upstream change\n")
        _run("git add -A && git commit -m 'upstream update'", self.upstream_path)

        st = repo.status()
        self.assertTrue(st["ok"])
        self.assertEqual(st["behind"], 1)
        self.assertFalse(st["up_to_date"])
        self.assertEqual(st["recommended_action"], "sync_safe")

    def test_patch_new_and_list(self):
        """patch_new should create a patch; patch_list should return it."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        # Make a change
        with open(os.path.join(self.fork_path, "feature.txt"), "w") as f:
            f.write("my custom feature\n")

        result = repo.patch_new("my-feature", "added feature")
        self.assertTrue(result["ok"])
        self.assertEqual(result["patch"], "my-feature")

        lst = repo.patch_list()
        self.assertTrue(lst["ok"])
        self.assertEqual(lst["count"], 1)
        self.assertEqual(lst["patches"][0]["name"], "my-feature")

    def test_patch_new_validates_name(self):
        """patch_new should reject invalid names."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "f.txt"), "w") as f:
            f.write("change\n")

        with self.assertRaises(BingoError):
            repo.patch_new("-invalid", "bad name")

        with self.assertRaises(BingoError):
            repo.patch_new("a" * 101, "too long")

    def test_patch_new_no_changes(self):
        """patch_new should fail when there are no changes."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with self.assertRaises(BingoError) as ctx:
            repo.patch_new("empty-patch")
        self.assertIn("No changes", str(ctx.exception))

    def test_patch_duplicate_name(self):
        """patch_new should reject duplicate names."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "f1.txt"), "w") as f:
            f.write("change1\n")
        repo.patch_new("my-patch", "first")

        with open(os.path.join(self.fork_path, "f2.txt"), "w") as f:
            f.write("change2\n")
        with self.assertRaises(BingoError) as ctx:
            repo.patch_new("my-patch", "duplicate")
        self.assertIn("already exists", str(ctx.exception))

    def test_patch_drop(self):
        """patch_drop should remove a patch."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "f.txt"), "w") as f:
            f.write("change\n")
        repo.patch_new("drop-me", "will be dropped")

        result = repo.patch_drop("drop-me")
        self.assertTrue(result["ok"])
        self.assertEqual(result["dropped"], "drop-me")

        lst = repo.patch_list()
        self.assertEqual(lst["count"], 0)

    def test_patch_drop_by_index(self):
        """patch_drop should work with 1-based index."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "f.txt"), "w") as f:
            f.write("change\n")
        repo.patch_new("test-patch", "desc")

        result = repo.patch_drop("1")
        self.assertTrue(result["ok"])

    def test_sync_up_to_date(self):
        """sync when already up to date should return cleanly."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        result = repo.sync()
        self.assertTrue(result["ok"])
        self.assertTrue(result.get("up_to_date", False) or result.get("behind_before", 0) == 0)

    def test_sync_with_upstream_changes(self):
        """sync should rebase patches onto new upstream."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        # Create a patch
        with open(os.path.join(self.fork_path, "custom.txt"), "w") as f:
            f.write("custom\n")
        repo.patch_new("custom-feature", "my custom")

        # Add upstream commit (non-conflicting)
        with open(os.path.join(self.upstream_path, "upstream-new.txt"), "w") as f:
            f.write("new upstream\n")
        _run("git add -A && git commit -m 'upstream: new file'", self.upstream_path)

        result = repo.sync()
        self.assertTrue(result["ok"])
        self.assertTrue(result["synced"])
        self.assertEqual(result["behind_before"], 1)
        self.assertEqual(result["patches_rebased"], 1)

    def test_sync_dry_run(self):
        """sync dry_run should not modify anything."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "custom.txt"), "w") as f:
            f.write("custom\n")
        repo.patch_new("custom-feature", "my custom")

        with open(os.path.join(self.upstream_path, "upstream-new.txt"), "w") as f:
            f.write("new upstream\n")
        _run("git add -A && git commit -m 'upstream: new file'", self.upstream_path)

        git = Git(self.fork_path)
        head_before = git.rev_parse("HEAD")

        result = repo.sync(dry_run=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["dry_run"])
        self.assertTrue(result["clean"])

        head_after = git.rev_parse("HEAD")
        self.assertEqual(head_before, head_after)

    def test_undo(self):
        """undo should restore previous state after sync."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "custom.txt"), "w") as f:
            f.write("custom\n")
        repo.patch_new("custom-feature", "my custom")

        git = Git(self.fork_path)
        head_before_sync = git.rev_parse("HEAD")

        with open(os.path.join(self.upstream_path, "upstream-new.txt"), "w") as f:
            f.write("new upstream\n")
        _run("git add -A && git commit -m 'upstream: new file'", self.upstream_path)

        repo.sync()
        head_after_sync = git.rev_parse("HEAD")
        self.assertNotEqual(head_before_sync, head_after_sync)

        result = repo.undo()
        self.assertTrue(result["ok"])
        head_after_undo = git.rev_parse("HEAD")
        self.assertEqual(head_before_sync, head_after_undo)

    def test_doctor(self):
        """doctor should return all-pass for a healthy repo."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        result = repo.doctor()
        self.assertTrue(result["ok"])
        self.assertEqual(result["issues"], 0)

    def test_diff_no_patches(self):
        """diff with no patches should return empty."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        result = repo.diff()
        self.assertTrue(result["ok"])
        self.assertEqual(result["diff"], "")

    def test_history_empty(self):
        """history should return empty syncs initially."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        result = repo.history()
        self.assertTrue(result["ok"])
        self.assertEqual(result["syncs"], [])

    def test_config_get_set(self):
        """config_get / config_set should work."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        repo.config_set("test.key", "test-value")
        result = repo.config_get("test.key")
        self.assertTrue(result["ok"])
        self.assertEqual(result["value"], "test-value")

    def test_config_list(self):
        """config_list should return all config."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        result = repo.config_list()
        self.assertTrue(result["ok"])
        self.assertIn("bingolight.upstream-url", result["config"])

    def test_patch_show(self):
        """patch_show should return diff content."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "feature.txt"), "w") as f:
            f.write("feature content\n")
        repo.patch_new("show-me", "patch to show")

        result = repo.patch_show("show-me")
        self.assertTrue(result["ok"])
        self.assertEqual(result["patch"]["name"], "show-me")
        self.assertIn("feature content", result["patch"]["diff"])

    def test_patch_show_by_index(self):
        """patch_show by index should work."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "feature.txt"), "w") as f:
            f.write("feature content\n")
        repo.patch_new("indexed-patch", "by index")

        result = repo.patch_show("1")
        self.assertTrue(result["ok"])
        self.assertEqual(result["patch"]["name"], "indexed-patch")

    def test_patch_export_import(self):
        """Export and re-import patches should round-trip."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "feature.txt"), "w") as f:
            f.write("feature content\n")
        repo.patch_new("export-me", "will be exported")

        export_dir = os.path.join(self.fork_path, "patches-out")
        result = repo.patch_export(export_dir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        self.assertTrue(len(result["files"]) == 1)

        # Verify series file exists
        self.assertTrue(os.path.isfile(os.path.join(export_dir, "series")))

    def test_not_git_repo(self):
        """Operations on a non-git directory should raise NotGitRepoError."""
        tmpdir = tempfile.mkdtemp(prefix="bl-nogit-")
        try:
            repo = Repo(tmpdir)
            with self.assertRaises(NotGitRepoError):
                repo.status()
        finally:
            shutil.rmtree(tmpdir, ignore_errors=True)

    def test_not_initialized(self):
        """Operations on an uninitialized repo should raise NotInitializedError."""
        repo = Repo(self.fork_path)
        with self.assertRaises(NotInitializedError):
            repo.status()

    def test_dirty_tree(self):
        """Sync on dirty tree should raise DirtyTreeError."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "dirty.txt"), "w") as f:
            f.write("dirty\n")
        _run("git add dirty.txt", self.fork_path)

        with self.assertRaises(DirtyTreeError):
            repo.sync()

    def test_session(self):
        """session update and read should work."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        result = repo.session()
        self.assertTrue(result["ok"])
        self.assertEqual(result["session"], "")

        result = repo.session(update=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["updated"])
        self.assertIn("bingo-light session notes", result["session"])

    def test_patch_meta(self):
        """patch_meta get/set should work."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")

        with open(os.path.join(self.fork_path, "f.txt"), "w") as f:
            f.write("change\n")
        repo.patch_new("meta-test", "testing meta")

        # Set metadata
        result = repo.patch_meta("meta-test", "reason", "bug fix")
        self.assertTrue(result["ok"])
        self.assertEqual(result["set"], "reason")

        # Get metadata
        result = repo.patch_meta("meta-test")
        self.assertTrue(result["ok"])
        self.assertEqual(result["meta"]["reason"], "bug fix")

    def test_reinit_detection(self):
        """Re-init returns reinit flag."""
        repo = Repo(self.fork_path)
        r1 = repo.init(self.upstream_path, "main")
        self.assertTrue(r1["ok"])
        self.assertNotIn("reinit", r1)
        r2 = repo.init(self.upstream_path, "main")
        self.assertTrue(r2["ok"])
        self.assertTrue(r2.get("reinit"))

    def test_conflict_resolve_no_rebase(self):
        """conflict_resolve raises when no rebase in progress."""
        repo = Repo(self.fork_path)
        repo.init(self.upstream_path, "main")
        with self.assertRaises(BingoError):
            repo.conflict_resolve("app.py", "content")

    def test_workspace_remove(self):
        """workspace remove deletes entry."""
        tmpconfig = tempfile.mkdtemp(prefix="bl-ws-cfg-")
        old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmpconfig
        try:
            repo = Repo(self.fork_path)
            repo.workspace_init()
            repo.workspace_add(self.fork_path, "test-fork")
            result = repo.workspace_remove("test-fork")
            self.assertTrue(result["ok"])
            self.assertEqual(result["removed"], "test-fork")
            ws = repo.workspace_list()
            self.assertEqual(len(ws["repos"]), 0)
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old_xdg
            shutil.rmtree(tmpconfig, ignore_errors=True)

    def test_workspace_remove_not_found(self):
        """workspace remove raises for nonexistent alias."""
        tmpconfig = tempfile.mkdtemp(prefix="bl-ws-cfg-")
        old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmpconfig
        try:
            repo = Repo(self.fork_path)
            repo.workspace_init()
            with self.assertRaises(BingoError):
                repo.workspace_remove("nope")
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old_xdg
            shutil.rmtree(tmpconfig, ignore_errors=True)

    def test_workspace_status(self):
        """workspace status returns per-repo details."""
        tmpconfig = tempfile.mkdtemp(prefix="bl-ws-cfg-")
        old_xdg = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = tmpconfig
        try:
            repo = Repo(self.fork_path)
            repo.init(self.upstream_path, "main")
            repo.workspace_init()
            repo.workspace_add(self.fork_path, "test-fork")
            result = repo.workspace_status()
            self.assertTrue(result["ok"])
            self.assertEqual(len(result["repos"]), 1)
            r = result["repos"][0]
            self.assertEqual(r["alias"], "test-fork")
            self.assertIn("behind", r)
            self.assertIn("patches", r)
        finally:
            if old_xdg is None:
                os.environ.pop("XDG_CONFIG_HOME", None)
            else:
                os.environ["XDG_CONFIG_HOME"] = old_xdg
            shutil.rmtree(tmpconfig, ignore_errors=True)

    def test_version_constant(self):
        """VERSION should be 2.2.0."""
        self.assertEqual(VERSION, "2.2.0")


class TestDataClasses(unittest.TestCase):
    """Tests for PatchInfo and ConflictInfo data classes."""

    def test_patch_info_to_dict(self):
        p = PatchInfo(name="test", hash="abc123", subject="[bl] test: desc", files=3)
        d = p.to_dict()
        self.assertEqual(d["name"], "test")
        self.assertEqual(d["hash"], "abc123")
        self.assertEqual(d["files"], 3)

    def test_conflict_info_to_dict(self):
        c = ConflictInfo(
            file="foo.txt", ours="a", theirs="b", conflict_count=1, merge_hint="merge"
        )
        d = c.to_dict()
        self.assertEqual(d["file"], "foo.txt")
        self.assertEqual(d["conflict_count"], 1)

    def test_patch_info_defaults(self):
        p = PatchInfo(name="", hash="", subject="")
        self.assertEqual(p.files, 0)
        self.assertEqual(p.stat, "")
        self.assertEqual(p.insertions, 0)
        self.assertEqual(p.deletions, 0)


class TestExceptions(unittest.TestCase):
    """Tests for exception classes."""

    def test_bingo_error(self):
        e = BingoError("test error")
        self.assertEqual(str(e), "test error")

    def test_git_error(self):
        e = GitError(["git", "foo"], 1, "bad command")
        self.assertEqual(e.returncode, 1)
        self.assertEqual(e.stderr, "bad command")
        self.assertIn("git", str(e))

    def test_not_git_repo_error(self):
        e = NotGitRepoError()
        self.assertIn("git repository", str(e))

    def test_not_initialized_error(self):
        e = NotInitializedError()
        self.assertIn("not initialized", str(e))

    def test_dirty_tree_error(self):
        e = DirtyTreeError()
        self.assertIn("dirty", str(e))


class TestTeam(unittest.TestCase):
    """Tests for team collaboration (locking)."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")
        # Create a patch
        with open(os.path.join(self.fork, "feature.txt"), "w") as f:
            f.write("feature\n")
        _run("git add -A && git commit -m '[bl] my-patch: test feature'", self.fork)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def test_lock_unlock_roundtrip(self):
        result = self.repo.patch_lock("my-patch", reason="working on it")
        self.assertTrue(result["ok"])
        self.assertEqual(result["patch"], "my-patch")
        self.assertIn("locked_at", result)

        # Verify lock info
        lock = self.repo.team.get_lock("my-patch")
        self.assertIsNotNone(lock)
        self.assertEqual(lock["reason"], "working on it")

        # Unlock
        result = self.repo.patch_unlock("my-patch")
        self.assertTrue(result["ok"])
        self.assertTrue(result["was_locked"])

        # Verify unlocked
        lock = self.repo.team.get_lock("my-patch")
        self.assertIsNone(lock)

    def test_lock_conflict(self):
        # Lock as user A
        self.repo.team.lock("my-patch", owner="alice")

        # Try to lock as user B
        with self.assertRaises(BingoError) as ctx:
            self.repo.team.lock("my-patch", owner="bob")
        self.assertIn("locked by alice", str(ctx.exception))

    def test_lock_enforcement_patch_drop(self):
        # Lock as "other-user"
        self.repo.team.lock("my-patch", owner="other-user")

        # Try to drop — should be blocked
        with self.assertRaises(BingoError) as ctx:
            self.repo.patch_drop("my-patch")
        self.assertIn("locked by other-user", str(ctx.exception))

    def test_lock_enforcement_patch_edit(self):
        # Lock as "other-user"
        self.repo.team.lock("my-patch", owner="other-user")

        # Stage a change for edit
        with open(os.path.join(self.fork, "feature.txt"), "w") as f:
            f.write("edited\n")
        _run("git add feature.txt", self.fork)

        # Try to edit — should be blocked
        with self.assertRaises(BingoError) as ctx:
            self.repo.patch_edit("my-patch")
        self.assertIn("locked by other-user", str(ctx.exception))

    def test_unlock_force(self):
        self.repo.team.lock("my-patch", owner="alice")
        # Force unlock as different user
        result = self.repo.team.unlock("my-patch", owner="bob", force=True)
        self.assertTrue(result["ok"])
        self.assertTrue(result["was_locked"])

    def test_unlock_not_locked(self):
        result = self.repo.patch_unlock("my-patch")
        self.assertTrue(result["ok"])
        self.assertFalse(result.get("was_locked", True))

    def test_list_locks(self):
        self.repo.patch_lock("my-patch", reason="testing")
        locks = self.repo.team.list_locks()
        self.assertEqual(len(locks), 1)
        self.assertEqual(locks[0]["patch"], "my-patch")


class TestSmartPatch(unittest.TestCase):
    """Tests for smart patch management (check, upstream, expire, stats)."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")
        # Create a patch
        with open(os.path.join(self.fork, "feature.txt"), "w") as f:
            f.write("my feature\n")
        _run("git add -A && git commit -m '[bl] test-patch: add feature'", self.fork)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def test_patch_check_active(self):
        result = self.repo.patch_check()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["patches"]), 1)
        self.assertEqual(result["patches"][0]["name"], "test-patch")
        self.assertEqual(result["patches"][0]["status"], "active")

    def test_patch_check_obsolete(self):
        # Make the same change in upstream
        with open(os.path.join(self.upstream, "feature.txt"), "w") as f:
            f.write("my feature\n")
        _run("git add -A && git commit -m 'add feature upstream'", self.upstream)
        # Fetch upstream in fork
        _run("git fetch upstream", self.fork)
        _run("git branch -f upstream-tracking upstream/main", self.fork)

        result = self.repo.patch_check("test-patch")
        self.assertTrue(result["ok"])
        self.assertEqual(result["patches"][0]["status"], "obsolete")

    def test_patch_upstream_export(self):
        result = self.repo.patch_upstream("test-patch")
        self.assertTrue(result["ok"])
        self.assertEqual(result["patch"], "test-patch")
        self.assertIn("feature.txt", result["diff"])
        self.assertEqual(result["description"], "add feature")
        self.assertIn("feature.txt", result["files"])

    def test_patch_expire_none(self):
        result = self.repo.patch_expire()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["expired"]), 0)
        self.assertEqual(len(result["expiring_soon"]), 0)

    def test_patch_expire_past(self):
        self.repo.state.patch_meta_set("test-patch", "expires", "2020-01-01")
        result = self.repo.patch_expire()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["expired"]), 1)
        self.assertEqual(result["expired"][0]["name"], "test-patch")

    def test_patch_stats(self):
        result = self.repo.patch_stats()
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["patches"]), 1)
        p = result["patches"][0]
        self.assertEqual(p["name"], "test-patch")
        self.assertGreaterEqual(p["files"], 1)


class TestReport(unittest.TestCase):
    """Tests for the report command."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")
        # Create a patch
        with open(os.path.join(self.fork, "feature.txt"), "w") as f:
            f.write("feature\n")
        _run("git add -A && git commit -m '[bl] rpt-patch: report test'", self.fork)

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def test_report_basic(self):
        result = self.repo.report()
        self.assertTrue(result["ok"])
        self.assertIn("# Fork Health Report", result["report"])
        self.assertIn("Patch Stack", result["report"])
        self.assertIn("rpt-patch", result["report"])
        self.assertEqual(result["summary"]["patches"], 1)

    def test_doctor_report_flag(self):
        result = self.repo.doctor(report=True)
        self.assertTrue(result["ok"])
        # Should have the extended checks
        check_names = [c["name"] for c in result["checks"]]
        self.assertIn("team_locks", check_names)
        self.assertIn("patch_expiry", check_names)


class TestVerifyHints(unittest.TestCase):
    """Unit tests for Repo._verify_hints_for."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="bl-vh-")
        _create_git_repo(self.tmpdir)
        self.repo = Repo(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_py_extension(self):
        hints = self.repo._verify_hints_for(["src/app.py"])
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["file"], "src/app.py")
        self.assertEqual(hints[0]["kind"], "syntax")
        self.assertEqual(hints[0]["command"], "python3 -m py_compile src/app.py")

    def test_json_extension(self):
        hints = self.repo._verify_hints_for(["pkg.json"])
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["kind"], "parse")
        self.assertIn("json.load", hints[0]["command"])
        self.assertTrue(hints[0]["command"].endswith("pkg.json"))

    def test_yaml_extensions(self):
        h1 = self.repo._verify_hints_for(["a.yml"])
        h2 = self.repo._verify_hints_for(["b.yaml"])
        self.assertEqual(len(h1), 1)
        self.assertEqual(len(h2), 1)
        self.assertIn("yaml.safe_load", h1[0]["command"])
        self.assertIn("yaml.safe_load", h2[0]["command"])

    def test_toml_extension(self):
        hints = self.repo._verify_hints_for(["pyproject.toml"])
        self.assertEqual(len(hints), 1)
        self.assertIn("tomllib.load", hints[0]["command"])

    def test_sh_extension(self):
        hints = self.repo._verify_hints_for(["run.sh"])
        self.assertEqual(len(hints), 1)
        self.assertEqual(hints[0]["command"], "bash -n run.sh")
        self.assertEqual(hints[0]["kind"], "syntax")

    def test_unknown_extension_skipped(self):
        hints = self.repo._verify_hints_for(["data.xyz", "no-ext"])
        self.assertEqual(hints, [])

    def test_mixed_files_preserves_order(self):
        hints = self.repo._verify_hints_for(["a.py", "skip.xyz", "b.json"])
        self.assertEqual(len(hints), 2)
        self.assertEqual(hints[0]["file"], "a.py")
        self.assertEqual(hints[1]["file"], "b.json")

    def test_path_with_space_is_shell_quoted(self):
        hints = self.repo._verify_hints_for(["has space.py"])
        self.assertEqual(len(hints), 1)
        self.assertIn("'has space.py'", hints[0]["command"])

    def test_empty_list(self):
        self.assertEqual(self.repo._verify_hints_for([]), [])


class TestPatchIntent(unittest.TestCase):
    """Unit tests for Repo._build_patch_intent.

    These use synthetic .git/rebase-merge/ contents so we don't need
    to induce a real rebase for unit coverage. The full end-to-end
    path is covered in the conflict_analyze integration tests.
    """

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def _seed_rebase_state(self, message, sha=None):
        """Write synthetic .git/rebase-merge/{message,stopped-sha}."""
        rdir = os.path.join(self.fork, ".git", "rebase-merge")
        os.makedirs(rdir, exist_ok=True)
        with open(os.path.join(rdir, "message"), "w") as f:
            f.write(message)
        if sha is not None:
            with open(os.path.join(rdir, "stopped-sha"), "w") as f:
                f.write(sha + "\n")

    def test_no_rebase_returns_empty_skeleton(self):
        intent = self.repo._build_patch_intent()
        self.assertEqual(intent["name"], "")
        self.assertEqual(intent["subject"], "")
        self.assertEqual(intent["message"], "")
        self.assertIsNone(intent["original_sha"])
        self.assertIsNone(intent["original_diff"])
        self.assertIsNone(intent["meta"])
        self.assertIsNone(intent["stack_position"])
        self.assertFalse(intent["message_truncated"])
        self.assertFalse(intent["diff_truncated"])

    def test_non_bingo_commit_message(self):
        self._seed_rebase_state("Some upstream commit\n\nBody text")
        intent = self.repo._build_patch_intent()
        self.assertEqual(intent["name"], "")
        self.assertEqual(intent["subject"], "")
        self.assertEqual(intent["message"], "Some upstream commit\n\nBody text")
        self.assertIsNone(intent["meta"])
        self.assertIsNone(intent["stack_position"])

    def test_bingo_commit_name_parsed(self):
        self._seed_rebase_state(
            "[bl] foo: disable analytics\n\nKeep privacy-first default."
        )
        intent = self.repo._build_patch_intent()
        self.assertEqual(intent["name"], "foo")
        self.assertEqual(intent["subject"], "disable analytics")
        self.assertIn("disable analytics", intent["message"])
        self.assertIn("privacy-first", intent["message"])

    def test_missing_stopped_sha(self):
        self._seed_rebase_state("[bl] foo: test", sha=None)
        intent = self.repo._build_patch_intent()
        self.assertIsNone(intent["original_sha"])
        self.assertIsNone(intent["original_diff"])

    def test_stopped_sha_points_to_head(self):
        head = _run("git rev-parse HEAD", self.fork)
        self._seed_rebase_state("[bl] foo: test", sha=head)
        intent = self.repo._build_patch_intent()
        self.assertEqual(intent["original_sha"], head)
        self.assertIsNotNone(intent["original_diff"])
        self.assertFalse(intent["diff_truncated"])

    def test_invalid_stopped_sha(self):
        self._seed_rebase_state("[bl] foo: test", sha="deadbeef" * 5)
        intent = self.repo._build_patch_intent()
        self.assertEqual(intent["original_sha"], "deadbeef" * 5)
        self.assertIsNone(intent["original_diff"])

    def test_message_truncation(self):
        big = "[bl] foo: short\n\n" + ("x" * 3000)
        self._seed_rebase_state(big)
        intent = self.repo._build_patch_intent()
        self.assertTrue(intent["message_truncated"])
        self.assertLessEqual(len(intent["message"]), 2048)

    def test_diff_truncation(self):
        big_file = os.path.join(self.fork, "big.txt")
        with open(big_file, "w") as f:
            f.write("x" * 100000)
        _run("git add -A && git commit -m 'big'", self.fork)
        head = _run("git rev-parse HEAD", self.fork)
        self._seed_rebase_state("[bl] foo: big", sha=head)
        intent = self.repo._build_patch_intent()
        self.assertTrue(intent["diff_truncated"])
        self.assertLessEqual(len(intent["original_diff"]), 50000)

    def test_meta_populated_for_known_patch(self):
        state = State(self.fork)
        state.patch_meta_set("foo", "reason", "privacy")
        self._seed_rebase_state("[bl] foo: short")
        intent = self.repo._build_patch_intent()
        self.assertIsNotNone(intent["meta"])
        self.assertEqual(intent["meta"]["reason"], "privacy")


class TestConflictAnalyzeEnriched(unittest.TestCase):
    """Integration: conflict_analyze output includes patch_intent and verify fields."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def _induce_conflict(self):
        """Create a patch touching foo.py, upstream-modify the same file,
        sync to induce a rebase conflict."""
        foo = os.path.join(self.fork, "foo.py")
        with open(foo, "w") as f:
            f.write("print('fork version')\n")
        _run("git add -A && git commit -m '[bl] custom: add foo.py'", self.fork)
        _run("git branch -f bingo-patches HEAD", self.fork)

        foo_up = os.path.join(self.upstream, "foo.py")
        with open(foo_up, "w") as f:
            f.write("print('upstream version')\n")
        _run("git add -A && git commit -m 'upstream foo'", self.upstream)

        _run("git fetch upstream", self.fork)
        _run("git branch -f upstream-tracking upstream/main", self.fork)
        _run("git checkout bingo-patches", self.fork)
        subprocess.run(
            ["git", "rebase", "upstream-tracking"],
            cwd=self.fork, capture_output=True,
        )

    def test_output_contains_new_keys_when_in_rebase(self):
        self._induce_conflict()
        result = self.repo.conflict_analyze()
        self.assertTrue(result["ok"])
        self.assertTrue(result["in_rebase"])
        self.assertIn("patch_intent", result)
        self.assertIn("verify", result)

    def test_patch_intent_fields_populated(self):
        self._induce_conflict()
        result = self.repo.conflict_analyze()
        pi = result["patch_intent"]
        self.assertEqual(pi["name"], "custom")
        self.assertIn("add foo.py", pi["subject"])
        self.assertIsNotNone(pi["original_sha"])

    def test_verify_has_file_hints_for_py(self):
        self._induce_conflict()
        result = self.repo.conflict_analyze()
        hints = result["verify"]["file_hints"]
        self.assertTrue(any(h["file"] == "foo.py" for h in hints))

    def test_verify_test_command_nullable(self):
        self._induce_conflict()
        result = self.repo.conflict_analyze()
        self.assertIn("test_command", result["verify"])
        self.assertIsNone(result["verify"]["test_command"])

    def test_verify_test_command_populated(self):
        self.repo.config_set("test.command", "make test")
        self._induce_conflict()
        result = self.repo.conflict_analyze()
        self.assertEqual(result["verify"]["test_command"], "make test")

    def test_no_new_keys_when_not_in_rebase(self):
        result = self.repo.conflict_analyze()
        self.assertFalse(result["in_rebase"])
        self.assertNotIn("patch_intent", result)
        self.assertNotIn("verify", result)


class TestConflictResolveVerify(unittest.TestCase):
    """conflict_resolve(verify=True) runs test.command after final rebase continue."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def _induce_single_patch_conflict(self):
        foo = os.path.join(self.fork, "foo.py")
        with open(foo, "w") as f:
            f.write("print('fork')\n")
        _run("git add -A && git commit -m '[bl] custom: add foo.py'", self.fork)
        _run("git branch -f bingo-patches HEAD", self.fork)

        foo_up = os.path.join(self.upstream, "foo.py")
        with open(foo_up, "w") as f:
            f.write("print('upstream')\n")
        _run("git add -A && git commit -m 'upstream foo'", self.upstream)
        _run("git fetch upstream", self.fork)
        _run("git branch -f upstream-tracking upstream/main", self.fork)
        _run("git checkout bingo-patches", self.fork)
        subprocess.run(
            ["git", "rebase", "upstream-tracking"],
            cwd=self.fork, capture_output=True,
        )

    def test_verify_false_default_no_test_run(self):
        self._induce_single_patch_conflict()
        result = self.repo.conflict_resolve("foo.py", "print('merged')\n")
        self.assertTrue(result["ok"])
        self.assertNotIn("verify_result", result)

    def test_verify_true_no_test_command_skipped(self):
        self._induce_single_patch_conflict()
        result = self.repo.conflict_resolve(
            "foo.py", "print('merged')\n", verify=True
        )
        self.assertTrue(result["ok"])
        self.assertIn("verify_result", result)
        self.assertTrue(result["verify_result"].get("skipped"))

    def test_verify_true_test_passes(self):
        self.repo.config_set("test.command", "true")
        self._induce_single_patch_conflict()
        result = self.repo.conflict_resolve(
            "foo.py", "print('merged')\n", verify=True
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verify_result"]["test"], "pass")

    def test_verify_true_test_fails_still_ok_true(self):
        self.repo.config_set("test.command", "false")
        self._induce_single_patch_conflict()
        result = self.repo.conflict_resolve(
            "foo.py", "print('merged')\n", verify=True
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["verify_result"]["test"], "fail")


class TestUpstreamContext(unittest.TestCase):
    """Integration: conflict_analyze exposes upstream_context when undo state exists."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def _run_sync_with_conflict(self):
        """Induce a sync-driven rebase conflict so .bingo/.undo-tracking is set."""
        foo = os.path.join(self.fork, "foo.py")
        with open(foo, "w") as f:
            f.write("print('fork')\n")
        _run("git add -A && git commit -m '[bl] custom: add foo.py'", self.fork)
        _run("git branch -f bingo-patches HEAD", self.fork)

        foo_up = os.path.join(self.upstream, "foo.py")
        with open(foo_up, "w") as f:
            f.write("print('upstream')\n")
        _run("git add -A && git commit -m 'upstream refactor (#42)'", self.upstream)

        # Use real sync so undo state is recorded
        try:
            self.repo.sync(force=True)
        except Exception:
            pass  # conflicts cause errors; we want the rebase-paused state

    def test_upstream_context_absent_without_undo_state(self):
        """When no rebase has been attempted, upstream_context is absent."""
        result = self.repo.conflict_analyze()
        self.assertFalse(result["in_rebase"])
        self.assertNotIn("upstream_context", result)

    def test_upstream_context_present_during_conflict(self):
        self._run_sync_with_conflict()
        result = self.repo.conflict_analyze()
        if not result.get("in_rebase"):
            self.skipTest("Sync completed without triggering rebase conflict")
        self.assertIn("upstream_context", result)
        uc = result["upstream_context"]
        self.assertIn("range", uc)
        self.assertIn("total_commits", uc)
        self.assertGreaterEqual(uc["total_commits"], 1)
        commits = uc["commits_touching_conflicts"]
        self.assertTrue(any("refactor" in c["subject"] for c in commits))

    def test_pr_number_extracted_from_subject(self):
        self._run_sync_with_conflict()
        result = self.repo.conflict_analyze()
        if not result.get("in_rebase"):
            self.skipTest("Sync completed without triggering rebase conflict")
        commits = result["upstream_context"]["commits_touching_conflicts"]
        found_pr = next((c for c in commits if c.get("pr") == "42"), None)
        self.assertIsNotNone(found_pr, "Expected to find PR #42 in upstream context")


class TestPatchDependencies(unittest.TestCase):
    """_build_patch_dependencies finds later patches touching same files."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def _make_patch(self, name, filename, content):
        p = os.path.join(self.fork, filename)
        with open(p, "w") as f:
            f.write(content)
        _run(
            f"git add -A && git commit -m '[bl] {name}: edit {filename}'",
            self.fork,
        )
        _run("git branch -f bingo-patches HEAD", self.fork)

    def test_no_dependents_when_name_empty(self):
        deps = self.repo._build_patch_dependencies("")
        self.assertIsNone(deps)

    def test_no_dependents_when_stack_empty(self):
        deps = self.repo._build_patch_dependencies("nonexistent")
        self.assertIsNone(deps)

    def test_no_dependents_when_none_overlap(self):
        self._make_patch("first", "a.py", "1\n")
        self._make_patch("second", "b.py", "2\n")
        deps = self.repo._build_patch_dependencies("first")
        self.assertIsNotNone(deps)
        self.assertEqual(deps["dependents"], [])

    def test_detects_overlap(self):
        self._make_patch("first", "shared.py", "1\n")
        self._make_patch("second", "shared.py", "1\n2\n")
        self._make_patch("third", "other.py", "3\n")
        deps = self.repo._build_patch_dependencies("first")
        self.assertIsNotNone(deps)
        self.assertEqual(len(deps["dependents"]), 1)
        dep = deps["dependents"][0]
        self.assertEqual(dep["name"], "second")
        self.assertEqual(dep["overlapping_files"], ["shared.py"])

    def test_does_not_look_backwards(self):
        self._make_patch("first", "shared.py", "1\n")
        self._make_patch("second", "shared.py", "1\n2\n")
        deps = self.repo._build_patch_dependencies("second")
        self.assertIsNotNone(deps)
        self.assertEqual(deps["dependents"], [])


class TestSemanticClassify(unittest.TestCase):
    """Unit tests for bingo_core.semantic.classify_conflict."""

    def test_whitespace_only(self):
        from bingo_core import classify_conflict
        self.assertEqual(
            classify_conflict("x=1\ny=2", "x = 1\ny = 2"),
            "whitespace",
        )
        self.assertEqual(
            classify_conflict("x=1\ny=2\n", "x=1\n\ny=2\n"),
            "whitespace",
        )

    def test_whitespace_not_classified_when_content_differs(self):
        from bingo_core import classify_conflict
        self.assertEqual(
            classify_conflict("x=1", "x=2"),
            "logic",
        )

    def test_import_reorder(self):
        from bingo_core import classify_conflict
        ours = "import os\nimport sys\nimport json"
        theirs = "import json\nimport os\nimport sys"
        self.assertEqual(classify_conflict(ours, theirs), "import_reorder")

    def test_import_added_is_not_reorder(self):
        """Different set of imports → logic, not reorder."""
        from bingo_core import classify_conflict
        ours = "import os"
        theirs = "import os\nimport json"
        self.assertEqual(classify_conflict(ours, theirs), "logic")

    def test_import_with_non_import_line_is_logic(self):
        from bingo_core import classify_conflict
        ours = "import os\nx = 1"
        theirs = "import os\nx = 2"
        self.assertEqual(classify_conflict(ours, theirs), "logic")

    def test_signature_change_python(self):
        from bingo_core import classify_conflict
        ours = "def foo(a, b):"
        theirs = "def foo(a, b, c=None):"
        self.assertEqual(classify_conflict(ours, theirs), "signature_change")

    def test_signature_same_name_same_params_is_whitespace(self):
        from bingo_core import classify_conflict
        ours = "def foo(a, b):"
        theirs = "def foo(a,b):"
        self.assertEqual(classify_conflict(ours, theirs), "whitespace")

    def test_signature_different_name_is_logic(self):
        """Rename is NOT signature_change — names differ."""
        from bingo_core import classify_conflict
        ours = "def foo(a):"
        theirs = "def bar(a):"
        self.assertEqual(classify_conflict(ours, theirs), "logic")

    def test_empty_inputs_are_logic(self):
        from bingo_core import classify_conflict
        self.assertEqual(classify_conflict("", ""), "logic")
        self.assertEqual(classify_conflict("something", ""), "logic")


class TestDecisionMemory(unittest.TestCase):
    """Unit tests for bingo_core.decisions.DecisionMemory."""

    def setUp(self):
        from bingo_core import DecisionMemory
        self.tmpdir = tempfile.mkdtemp(prefix="bl-dm-")
        os.makedirs(os.path.join(self.tmpdir, ".bingo"), exist_ok=True)
        self.mem = DecisionMemory(self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_lookup_empty_when_no_history(self):
        self.assertEqual(self.mem.lookup("foo"), [])

    def test_record_and_lookup(self):
        self.mem.record(
            "foo", file="a.py", semantic_class="whitespace",
            resolution_strategy="keep_ours",
            upstream_sha="abc123", upstream_subject="fmt",
        )
        entries = self.mem.lookup("foo")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["file"], "a.py")
        self.assertEqual(entries[0]["resolution_strategy"], "keep_ours")

    def test_relevance_ranking(self):
        self.mem.record("foo", "a.py", "logic", "manual")
        self.mem.record("foo", "b.py", "whitespace", "keep_ours")
        self.mem.record("foo", "a.py", "whitespace", "keep_ours")
        # Lookup with both file+class match should rank the 3rd entry top.
        entries = self.mem.lookup(
            "foo", file="a.py", semantic_class="whitespace"
        )
        self.assertEqual(entries[0]["file"], "a.py")
        self.assertEqual(entries[0]["semantic_class"], "whitespace")
        self.assertIn("same_file", entries[0]["relevance"])
        self.assertIn("same_class", entries[0]["relevance"])

    def test_unsafe_patch_name_rejected(self):
        self.mem.record("../escape", "x", "logic", "manual")
        self.assertEqual(self.mem.lookup("../escape"), [])
        escape_path = os.path.join(self.tmpdir, ".bingo", "decisions")
        if os.path.isdir(escape_path):
            self.assertEqual(os.listdir(escape_path), [])

    def test_max_decisions_enforced(self):
        from bingo_core.decisions import MAX_DECISIONS_PER_PATCH
        for i in range(MAX_DECISIONS_PER_PATCH + 5):
            self.mem.record("foo", f"f{i}.py", "logic", "manual")
        entries = self.mem.lookup("foo", limit=100)
        self.assertLessEqual(len(entries), MAX_DECISIONS_PER_PATCH)


class TestDetectResolutionStrategy(unittest.TestCase):
    """Unit tests for bingo_core.decisions.detect_resolution_strategy."""

    def test_keep_ours(self):
        from bingo_core import detect_resolution_strategy
        self.assertEqual(
            detect_resolution_strategy("upstream\n", "upstream\n", "fork\n"),
            "keep_ours",
        )

    def test_keep_theirs(self):
        from bingo_core import detect_resolution_strategy
        self.assertEqual(
            detect_resolution_strategy("fork\n", "upstream\n", "fork\n"),
            "keep_theirs",
        )

    def test_manual(self):
        from bingo_core import detect_resolution_strategy
        self.assertEqual(
            detect_resolution_strategy(
                "merged\n", "upstream\n", "fork\n"
            ),
            "manual",
        )

    def test_empty_content_is_manual(self):
        from bingo_core import detect_resolution_strategy
        self.assertEqual(
            detect_resolution_strategy("", "upstream", "fork"),
            "manual",
        )


class TestConflictResolveRecordsDecision(unittest.TestCase):
    """Integration: conflict_resolve records a decision on success."""

    def setUp(self):
        self.upstream, self.fork = _create_upstream_and_fork()
        self.repo = Repo(self.fork)
        self.repo.init(self.upstream, "main")

    def tearDown(self):
        shutil.rmtree(os.path.dirname(self.upstream), ignore_errors=True)

    def _induce_conflict(self):
        foo = os.path.join(self.fork, "foo.py")
        with open(foo, "w") as f:
            f.write("print('fork')\n")
        _run("git add -A && git commit -m '[bl] custom: add foo.py'", self.fork)
        _run("git branch -f bingo-patches HEAD", self.fork)

        foo_up = os.path.join(self.upstream, "foo.py")
        with open(foo_up, "w") as f:
            f.write("print('upstream')\n")
        _run("git add -A && git commit -m 'upstream refactor'", self.upstream)

        _run("git fetch upstream", self.fork)
        _run("git branch -f upstream-tracking upstream/main", self.fork)
        _run("git checkout bingo-patches", self.fork)
        subprocess.run(
            ["git", "rebase", "upstream-tracking"],
            cwd=self.fork, capture_output=True,
        )

    def test_decision_recorded_after_resolve(self):
        self._induce_conflict()
        self.repo.conflict_resolve("foo.py", "print('merged')\n")
        entries = self.repo.decisions.lookup("custom", file="foo.py")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["file"], "foo.py")
        self.assertEqual(entries[0]["resolution_strategy"], "manual")

    def test_subsequent_analyze_surfaces_memory(self):
        self._induce_conflict()
        self.repo.conflict_resolve("foo.py", "print('merged')\n")
        # Abort to reset rebase, then re-induce the same conflict
        subprocess.run(["git", "rebase", "--abort"], cwd=self.fork,
                       capture_output=True)
        # Re-create conflict
        foo_up = os.path.join(self.upstream, "foo.py")
        with open(foo_up, "w") as f:
            f.write("print('upstream v2')\n")
        _run("git add -A && git commit -m 'upstream round 2'", self.upstream)
        _run("git fetch upstream", self.fork)
        _run("git branch -f upstream-tracking upstream/main", self.fork)
        _run("git checkout bingo-patches", self.fork)
        subprocess.run(
            ["git", "rebase", "upstream-tracking"],
            cwd=self.fork, capture_output=True,
        )
        result = self.repo.conflict_analyze()
        if not result.get("in_rebase"):
            self.skipTest("Sync did not leave a conflict for second round")
        self.assertIn("decision_memory", result)
        dm = result["decision_memory"]
        self.assertEqual(dm["patch"], "custom")
        self.assertTrue(len(dm["entries"]) > 0)


if __name__ == "__main__":
    unittest.main()
