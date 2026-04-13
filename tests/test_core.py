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
        """VERSION should be 2.1.1."""
        self.assertEqual(VERSION, "2.1.1")


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


if __name__ == "__main__":
    unittest.main()
