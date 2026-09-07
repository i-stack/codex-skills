import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from collections.abc import Mapping
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_DIR = REPO_ROOT / "sync"
if str(SYNC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNC_DIR))

from cli import sync_config  # noqa: E402
from platforms import codebuddy as codebuddy_mod  # noqa: E402
from core import common  # noqa: E402


DEFAULT_CODEBUDDY_CFG = {
    "models": [
        {
            "id": "deepseek-v4-pro",
            "name": "DeepSeek V4 Pro",
            "vendor": "dataeyes",
            "url": "${codebuddy.url}",
            "apiKey": "${codebuddy.key}",
            "maxInputTokens": 128000,
            "maxOutputTokens": 8192,
            "supportsToolCall": True,
            "supportsImages": False,
            "relatedModels": {
                "lite": "deepseek-v4-flash",
                "reasoning": "deepseek-v4-pro",
            },
        },
        {
            "id": "deepseek-v4-flash",
            "name": "DeepSeek V4 Flash",
            "vendor": "dataeyes",
            "url": "${codebuddy.url}",
            "apiKey": "${codebuddy.key}",
            "maxInputTokens": 128000,
            "maxOutputTokens": 8192,
            "supportsToolCall": True,
            "supportsImages": False,
        },
    ],
    "availableModels": [
        "deepseek-v4-pro",
        "deepseek-v4-flash",
    ],
    # Mirror the real env/platforms/codebuddy.json: CodeBuddy is now a full
    # preamble target. Recall-mode / none-mode behavior is exercised explicitly
    # by the tests below, not via this default.
    "preamble": {
        "target": "CODEBUDDY.md",
        "mode": "full",
        "tool": "codebuddy",
    },
}


@contextlib.contextmanager
def patched_sync_environment(root: Path):
    """Redirect HOME and common module paths for isolated CodeBuddy sync tests."""
    import core.paths as _paths
    home = root / "home"
    old_env = {k: os.environ.get(k) for k in ("HOME",)}
    old_paths = (common.MCP_DIR, common.PLATFORMS_DIR, common.SECRETS_PATH)
    old_paths_cfg = _paths.CONFIG_PATH
    old_overrides = _paths._PATH_OVERRIDES
    old_argv = sys.argv[:]
    try:
        os.environ["HOME"] = str(home)
        common.MCP_DIR = root / "env" / "mcp"
        common.PLATFORMS_DIR = root / "env" / "platforms"
        common.SECRETS_PATH = root / "env" / "secrets.json"
        # Isolate path overrides so a developer's local env/config.json
        # can't leak into this test (empty config => default paths).
        _paths.CONFIG_PATH = root / "env" / "config.json"
        _paths._PATH_OVERRIDES = None
        yield
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        common.MCP_DIR, common.PLATFORMS_DIR, common.SECRETS_PATH = old_paths
        _paths.CONFIG_PATH = old_paths_cfg
        _paths._PATH_OVERRIDES = old_overrides
        sys.argv = old_argv


class CodeBuddySyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "home" / ".codebuddy").mkdir(parents=True, exist_ok=True)
        self.platform_cfg = DEFAULT_CODEBUDDY_CFG
        self._write_json(
            self.root / "env" / "mcp" / "sample.json",
            {
                "name": "sample",
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "platforms": ["codebuddy"],
            },
        )
        self._write_json(
            self.root / "env" / "secrets.json",
            {"codebuddy": {"url": "https://codebuddy.example/v1", "key": "sk-test-codebuddy"}},
        )

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=4) + "\n", encoding="utf-8")

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def _run_codebuddy_sync(self, cfg: dict | None = None) -> dict[str, dict]:
        """Run CodeBuddy sync and return parsed {mcp, models} contents."""
        target_cfg = cfg if cfg is not None else self.platform_cfg
        self._write_json(self.root / "env" / "platforms" / "codebuddy.json", target_cfg)
        with patched_sync_environment(self.root):
            sys.argv = ["sync_config.py", "--target", "codebuddy"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                sync_config.main()
        return {
            "mcp": self._read_json(self.root / "home" / ".codebuddy" / "mcp.json"),
            "models": self._read_json(self.root / "home" / ".codebuddy" / "models.json"),
        }

    def assert_nested_equal(self, data: Mapping, expected: Mapping, path: str) -> None:
        for key, expected_value in expected.items():
            current_path = f"{path}.{key}"
            self.assertIn(key, data, current_path)
            actual_value = data[key]
            if isinstance(expected_value, Mapping):
                self.assertIsInstance(actual_value, Mapping, current_path)
                self.assert_nested_equal(actual_value, expected_value, current_path)
            else:
                self.assertEqual(actual_value, expected_value, current_path)

    # ── MCP servers ──────────────────────────────────────────────────────────

    def test_mcp_servers_synced_to_mcp_json(self) -> None:
        result = self._run_codebuddy_sync()

        self.assertIn("mcpServers", result["mcp"])
        self.assertIn("sample", result["mcp"]["mcpServers"])
        self.assertEqual(result["mcp"]["mcpServers"]["sample"]["command"], "echo")
        self.assertEqual(result["mcp"]["mcpServers"]["sample"]["args"], ["hello"])

    def test_mcp_json_preserves_existing_user_keys(self) -> None:
        """User-added keys (meta + unmarked MCP servers) are preserved after sync."""
        mcp_path = self.root / "home" / ".codebuddy" / "mcp.json"
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(
            json.dumps(
                {
                    "meta": {"version": 1, "lastModified": "2025-01-01"},
                    "mcpServers": {"customServer": {"command": "custom-cmd"}},
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run_codebuddy_sync()

        self.assertEqual(result["mcp"]["meta"]["version"], 1)
        self.assertEqual(result["mcp"]["meta"]["lastModified"], "2025-01-01")
        # Managed MCP servers are written with the marker; user-added server
        # (no marker) is preserved untouched instead of being overwritten.
        self.assertIn("sample", result["mcp"]["mcpServers"])
        self.assertEqual(
            result["mcp"]["mcpServers"]["sample"]["_managed_by"], "ai-coding-kit"
        )
        self.assertIn("customServer", result["mcp"]["mcpServers"])
        self.assertEqual(
            result["mcp"]["mcpServers"]["customServer"], {"command": "custom-cmd"}
        )

    def test_mcp_json_prunes_stale_managed_servers(self) -> None:
        """Managed servers no longer in config are pruned; user servers stay."""
        mcp_path = self.root / "home" / ".codebuddy" / "mcp.json"
        mcp_path.parent.mkdir(parents=True, exist_ok=True)
        mcp_path.write_text(
            json.dumps(
                {
                    "mcpServers": {
                        "sample": {
                            "command": "echo",
                            "args": ["hello"],
                            "_managed_by": "ai-coding-kit",
                        },
                        "stale": {
                            "command": "old-tool",
                            "_managed_by": "ai-coding-kit",
                        },
                        "userFiles": {"command": "user-tool"},
                    }
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run_codebuddy_sync()

        self.assertIn("sample", result["mcp"]["mcpServers"])
        self.assertNotIn("stale", result["mcp"]["mcpServers"])
        self.assertIn("userFiles", result["mcp"]["mcpServers"])
        self.assertEqual(
            result["mcp"]["mcpServers"]["userFiles"], {"command": "user-tool"}
        )

    # ── Models sync ──────────────────────────────────────────────────────────

    def test_models_synced_to_models_json(self) -> None:
        result = self._run_codebuddy_sync()

        self.assertIn("models", result["models"])
        self.assertEqual(len(result["models"]["models"]), 2)
        # Model 0: deepseek-v4-pro (with relatedModels)
        self.assertEqual(result["models"]["models"][0]["id"], "deepseek-v4-pro")
        self.assertEqual(result["models"]["models"][0]["name"], "DeepSeek V4 Pro")
        self.assertEqual(result["models"]["models"][0]["vendor"], "dataeyes")
        self.assertEqual(result["models"]["models"][0]["url"], "https://codebuddy.example/v1")
        self.assertEqual(result["models"]["models"][0]["apiKey"], "sk-test-codebuddy")
        self.assertEqual(result["models"]["models"][0]["maxInputTokens"], 128000)
        self.assertEqual(result["models"]["models"][0]["maxOutputTokens"], 8192)
        self.assertTrue(result["models"]["models"][0]["supportsToolCall"])
        self.assertFalse(result["models"]["models"][0]["supportsImages"])
        self.assertEqual(
            result["models"]["models"][0]["relatedModels"],
            {"lite": "deepseek-v4-flash", "reasoning": "deepseek-v4-pro"},
        )
        # Model 1: deepseek-v4-flash (no relatedModels)
        self.assertEqual(result["models"]["models"][1]["id"], "deepseek-v4-flash")
        self.assertEqual(result["models"]["models"][1]["name"], "DeepSeek V4 Flash")
        self.assertNotIn("relatedModels", result["models"]["models"][1])

    def test_available_models_synced(self) -> None:
        result = self._run_codebuddy_sync()

        self.assertIn("availableModels", result["models"])
        self.assertEqual(
            result["models"]["availableModels"],
            ["deepseek-v4-pro", "deepseek-v4-flash"],
        )

    def test_models_json_preserves_existing_user_keys(self) -> None:
        """User-added top-level keys outside models/availableModels survive sync."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        models_path.parent.mkdir(parents=True, exist_ok=True)
        models_path.write_text(
            json.dumps(
                {
                    "meta": {"version": 2, "description": "Custom config"},
                    "uiPreference": "compact",
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run_codebuddy_sync()

        # User's top-level keys preserved
        self.assertEqual(result["models"]["meta"]["version"], 2)
        self.assertEqual(result["models"]["uiPreference"], "compact")

    def test_user_added_models_preserved_during_sync(self) -> None:
        """User-added model entries not in config are preserved alongside managed ones."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        models_path.parent.mkdir(parents=True, exist_ok=True)
        models_path.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "id": "custom-model",
                            "name": "Custom Model",
                            "vendor": "custom",
                        }
                    ],
                    "availableModels": ["custom-model"],
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run_codebuddy_sync()

        # 2 config-managed + 1 user-added = 3
        self.assertEqual(len(result["models"]["models"]), 3)
        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertIn("custom-model", model_ids)
        self.assertIn("deepseek-v4-pro", model_ids)
        self.assertIn("deepseek-v4-flash", model_ids)
        # Config-managed entries appear first (in config order)
        self.assertEqual(model_ids[0], "deepseek-v4-pro")
        self.assertEqual(model_ids[1], "deepseek-v4-flash")
        self.assertEqual(model_ids[2], "custom-model")
        # availableModels is replaced wholesale from config — user-added ID dropped
        self.assertNotIn("custom-model", result["models"]["availableModels"])
        self.assertEqual(
            result["models"]["availableModels"],
            ["deepseek-v4-pro", "deepseek-v4-flash"],
        )

    def test_user_owned_entry_with_same_id_is_preserved(self) -> None:
        """User-owned entries (no _managed_by) with the same id as config are kept untouched."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        models_path.parent.mkdir(parents=True, exist_ok=True)
        models_path.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "id": "deepseek-v4-pro",
                            "name": "OLD DeepSeek V4 Pro",
                            "vendor": "old-vendor",
                            "url": "https://old.example/v1",
                            "apiKey": "sk-old-key",
                        }
                    ],
                    "availableModels": [],
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        result = self._run_codebuddy_sync()

        # deepseek-v4-pro is user-owned (no marker) → preserved, NOT overwritten.
        # deepseek-v4-flash is added from config with marker.
        self.assertEqual(len(result["models"]["models"]), 2)
        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertEqual(model_ids, ["deepseek-v4-pro", "deepseek-v4-flash"])
        # Verify the user-owned model is kept as-is
        pro = result["models"]["models"][0]
        self.assertEqual(pro["name"], "OLD DeepSeek V4 Pro")
        self.assertEqual(pro["url"], "https://old.example/v1")
        self.assertEqual(pro["apiKey"], "sk-old-key")
        self.assertNotIn("_managed_by", pro)

    # ── Skills sync ──────────────────────────────────────────────────────────

    def test_skills_synced_from_claude_to_codebuddy(self) -> None:
        claude_skills = self.root / "home" / ".claude" / "skills"
        # Create a SKILL.md for a valid skill
        skill_dir = claude_skills / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
        (skill_dir / "helper.py").write_text("# helper script\n", encoding="utf-8")

        self._run_codebuddy_sync()

        dest = self.root / "home" / ".codebuddy" / "skills" / "test-skill"
        self.assertTrue(dest.exists(), "Skill directory was not synced to CodeBuddy")
        self.assertTrue((dest / "SKILL.md").exists(), "SKILL.md was not synced")
        self.assertTrue((dest / "helper.py").exists(), "helper.py was not synced")
        self.assertEqual(
            (dest / "SKILL.md").read_text(encoding="utf-8"), "# Test Skill\n"
        )

    def test_skills_skip_dirs_without_skill_md(self) -> None:
        claude_skills = self.root / "home" / ".claude" / "skills"
        (claude_skills / "no-skill-md").mkdir(parents=True)
        (claude_skills / "no-skill-md" / "readme.md").write_text("no SKILL.md\n", encoding="utf-8")

        self._run_codebuddy_sync()

        dest = self.root / "home" / ".codebuddy" / "skills" / "no-skill-md"
        self.assertFalse(dest.exists(), "Dir without SKILL.md should not be synced")

    def test_skills_missing_claude_dir_skips_gracefully(self) -> None:
        """When ~/.claude/skills doesn't exist, skill sync is skipped without error."""
        # setUp doesn't create claude skills, so dir doesn't exist
        result = self._run_codebuddy_sync()

        skills_dir = self.root / "home" / ".codebuddy" / "skills"
        self.assertFalse(skills_dir.exists(), "skills dir should not be created when claude skills missing")
        # MCP and models should still sync fine
        self.assertIn("mcpServers", result["mcp"])
        self.assertIn("models", result["models"])

    def test_skills_overwrites_existing_skill_dir(self) -> None:
        """Existing CodeBuddy skill dir is removed and replaced with Claude version."""
        claude_skills = self.root / "home" / ".claude" / "skills"
        (claude_skills / "test-skill").mkdir(parents=True)
        (claude_skills / "test-skill" / "SKILL.md").write_text("Claude version\n", encoding="utf-8")

        cb_skills = self.root / "home" / ".codebuddy" / "skills" / "test-skill"
        cb_skills.mkdir(parents=True)
        (cb_skills / "SKILL.md").write_text("Old CodeBuddy version\n", encoding="utf-8")
        (cb_skills / "stale-file.txt").write_text("should be removed\n", encoding="utf-8")

        self._run_codebuddy_sync()

        self.assertTrue((cb_skills / "SKILL.md").exists())
        self.assertEqual((cb_skills / "SKILL.md").read_text(encoding="utf-8"), "Claude version\n")
        self.assertFalse((cb_skills / "stale-file.txt").exists(), "Stale files should be removed")

    def test_skills_copy_failure_preserves_existing_skill_dir(self) -> None:
        """Existing CodeBuddy skill remains when copying the Claude version fails."""
        claude_skills = self.root / "home" / ".claude" / "skills"
        (claude_skills / "test-skill").mkdir(parents=True)
        (claude_skills / "test-skill" / "SKILL.md").write_text("Claude version\n", encoding="utf-8")

        cb_skills = self.root / "home" / ".codebuddy" / "skills" / "test-skill"
        cb_skills.mkdir(parents=True)
        (cb_skills / "SKILL.md").write_text("Old CodeBuddy version\n", encoding="utf-8")

        original_copytree = codebuddy_mod.shutil.copytree

        def failing_copytree(src: Path, dst: Path):
            raise OSError("simulated copy failure")

        codebuddy_mod.shutil.copytree = failing_copytree
        try:
            with self.assertRaises(OSError):
                self._run_codebuddy_sync()
        finally:
            codebuddy_mod.shutil.copytree = original_copytree

        self.assertTrue((cb_skills / "SKILL.md").exists())
        self.assertEqual((cb_skills / "SKILL.md").read_text(encoding="utf-8"), "Old CodeBuddy version\n")

    def test_skill_sync_skipped_when_skip_env_set(self) -> None:
        """SKIP_SKILL_SYNC=1 skips skill distribution but keeps MCP/models sync."""
        claude_skills = self.root / "home" / ".claude" / "skills"
        skill_dir = claude_skills / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")

        old = os.environ.get("SKIP_SKILL_SYNC")
        os.environ["SKIP_SKILL_SYNC"] = "1"
        try:
            result = self._run_codebuddy_sync()
        finally:
            if old is None:
                os.environ.pop("SKIP_SKILL_SYNC", None)
            else:
                os.environ["SKIP_SKILL_SYNC"] = old

        dest = self.root / "home" / ".codebuddy" / "skills" / "test-skill"
        self.assertFalse(dest.exists(), "Skill dir should not be synced when SKIP_SKILL_SYNC=1")
        # MCP and models still sync.
        self.assertIn("mcpServers", result["mcp"])
        self.assertIn("models", result["models"])

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_no_models_config_skips_model_sync(self) -> None:
        """When config has no 'models' or 'availableModels', model sync is skipped."""
        cfg: dict = {}
        result = self._run_codebuddy_sync(cfg)

        # MCP should still work
        self.assertIn("mcpServers", result["mcp"])
        # Models target should be empty (not created with stale data)
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self.assertFalse(models_path.exists(), "models.json should not be created without model config")

    def test_no_models_config_removes_existing_managed_model_keys(self) -> None:
        """When model config is absent, previously synced (marked) models are removed but user models survive."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "meta": {"version": 2},
                "models": [
                    {
                        "id": "deepseek-v4-pro",
                        "name": "Stale DeepSeek V4 Pro",
                        "vendor": "old",
                        "_managed_by": "ai-coding-kit",
                    },
                    {
                        "id": "user-model",
                        "name": "User Model",
                        "vendor": "custom",
                    },
                ],
                "availableModels": ["deepseek-v4-pro"],
            },
        )

        result = self._run_codebuddy_sync({})

        # Managed (marked) entry removed; user entry and unrelated meta preserved.
        self.assertEqual(result["models"].get("meta"), {"version": 2})
        model_ids = [m["id"] for m in result["models"].get("models", [])]
        self.assertNotIn("deepseek-v4-pro", model_ids)
        self.assertIn("user-model", model_ids)
        self.assertNotIn("availableModels", result["models"])

    def test_commented_platform_config_removes_existing_managed_model_keys(self) -> None:
        """A fully commented codebuddy.json parses as absent config and clears only marked models."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {
                        "id": "deepseek-v4-flash",
                        "name": "Stale DeepSeek V4 Flash",
                        "vendor": "old",
                        "_managed_by": "ai-coding-kit",
                    },
                    {
                        "id": "user-model",
                        "name": "User Model",
                        "vendor": "custom",
                    },
                ],
                "availableModels": ["deepseek-v4-flash"],
            },
        )
        config_path = self.root / "env" / "platforms" / "codebuddy.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(
            "// {\n"
            "//     \"models\": [\n"
            "//         {\"id\": \"deepseek-v4-flash\"}\n"
            "//     ],\n"
            "//     \"availableModels\": [\"deepseek-v4-flash\"]\n"
            "// }\n",
            encoding="utf-8",
        )

        with patched_sync_environment(self.root):
            sys.argv = ["sync_config.py", "--target", "codebuddy"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                sync_config.main()

        # Marked model removed; user model preserved (not whole-key wipe).
        data = self._read_json(models_path)
        model_ids = [m["id"] for m in data.get("models", [])]
        self.assertNotIn("deepseek-v4-flash", model_ids)
        self.assertIn("user-model", model_ids)
        self.assertNotIn("availableModels", data)

    def test_models_only_sync(self) -> None:
        """When config has only 'models' but no 'availableModels', only models are synced."""
        cfg: dict = {"models": self.platform_cfg["models"]}
        self._write_json(self.root / "env" / "platforms" / "codebuddy.json", cfg)

        result = self._run_codebuddy_sync(cfg)

        self.assertIn("models", result["models"])
        self.assertEqual(len(result["models"]["models"]), 2)
        self.assertNotIn("availableModels", result["models"])

    def test_available_models_only_sync(self) -> None:
        """When config has only 'availableModels' but no 'models', only availableModels are synced."""
        cfg: dict = {"availableModels": self.platform_cfg["availableModels"]}
        self._write_json(self.root / "env" / "platforms" / "codebuddy.json", cfg)

        result = self._run_codebuddy_sync(cfg)

        self.assertEqual(
            result["models"]["availableModels"],
            ["deepseek-v4-pro", "deepseek-v4-flash"],
        )
        self.assertNotIn("models", result["models"])

    # ── API toggle (api.enabled) ───────────────────────────────────────────────

    def test_api_enabled_by_default(self) -> None:
        """Missing api block defaults to enabled — normal model sync runs."""
        result = self._run_codebuddy_sync({"models": self.platform_cfg["models"],
                                           "availableModels": self.platform_cfg["availableModels"]})

        self.assertEqual(len(result["models"]["models"]), 2)
        self.assertEqual(
            result["models"]["availableModels"],
            ["deepseek-v4-pro", "deepseek-v4-flash"],
        )

    def test_api_disabled_empties_available_models(self) -> None:
        """When api.enabled=false, availableModels is set to [] (CodeBuddy special handling)."""
        cfg = {
            "api": {"enabled": False},
            "models": self.platform_cfg["models"],
            "availableModels": self.platform_cfg["availableModels"],
        }
        result = self._run_codebuddy_sync(cfg)

        self.assertEqual(result["models"]["availableModels"], [])
        # Model definitions are NOT synced while disabled, so the key is absent.
        self.assertNotIn("models", result["models"])

    def test_api_disabled_preserves_user_models(self) -> None:
        """User-added model definitions survive a disabled API sync."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        models_path.parent.mkdir(parents=True, exist_ok=True)
        models_path.write_text(
            json.dumps(
                {
                    "models": [
                        {
                            "id": "custom-model",
                            "name": "Custom Model",
                            "vendor": "custom",
                        }
                    ],
                    "availableModels": ["custom-model"],
                },
                indent=4,
            )
            + "\n",
            encoding="utf-8",
        )

        cfg = {
            "api": {"enabled": False},
            "models": self.platform_cfg["models"],
            "availableModels": self.platform_cfg["availableModels"],
        }
        result = self._run_codebuddy_sync(cfg)

        # User model kept; availableModels emptied by the disabled sync.
        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertIn("custom-model", model_ids)
        self.assertEqual(result["models"]["availableModels"], [])

    def test_api_disabled_is_idempotent(self) -> None:
        """Re-running a disabled sync keeps availableModels empty and models intact."""
        cfg = {
            "api": {"enabled": False},
            "models": self.platform_cfg["models"],
            "availableModels": self.platform_cfg["availableModels"],
        }
        self._run_codebuddy_sync(cfg)
        result = self._run_codebuddy_sync(cfg)

        self.assertEqual(result["models"]["availableModels"], [])
        # Disabled sync never writes the models key, so it stays absent.
        self.assertNotIn("models", result["models"])

    # ── Marker-based managed model sync (ai-coding-kit) ──────────────────────

    def test_managed_marker_is_written_on_synced_models(self) -> None:
        """Every synced model entry carries the _managed_by marker (scenario 1)."""
        result = self._run_codebuddy_sync()

        for m in result["models"]["models"]:
            self.assertEqual(m.get("_managed_by"), "ai-coding-kit")

    def test_deleted_config_model_is_pruned_from_target(self) -> None:
        """Removing a model from config prunes the managed entry but keeps user models (scenario 3)."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    # Previously synced by us — should be removed.
                    {
                        "id": "deepseek-v4-pro",
                        "name": "Stale DeepSeek V4 Pro",
                        "vendor": "old",
                        "_managed_by": "ai-coding-kit",
                    },
                    # User-added — must survive.
                    {
                        "id": "custom-model",
                        "name": "Custom Model",
                        "vendor": "custom",
                    },
                ],
                "availableModels": ["deepseek-v4-pro", "custom-model"],
            },
        )

        # Config only manages deepseek-v4-flash now (drop deepseek-v4-pro).
        cfg = {
            "models": [self.platform_cfg["models"][1]],  # deepseek-v4-flash
            "availableModels": ["deepseek-v4-flash"],
        }
        result = self._run_codebuddy_sync(cfg)

        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertEqual(model_ids, ["deepseek-v4-flash", "custom-model"])
        # The managed (pruned) entry no longer carries stale fields.
        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertNotIn("deepseek-v4-pro", synced)
        self.assertIn("custom-model", synced)
        self.assertNotIn("_managed_by", synced["custom-model"])

    def test_empty_models_list_prunes_managed_and_keeps_user(self) -> None:
        """Explicit models=[] still runs the merge: marked entries go, unmarked stay."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {
                        "id": "deepseek-v4-pro",
                        "name": "Stale DeepSeek V4 Pro",
                        "vendor": "old",
                        "_managed_by": "ai-coding-kit",
                    },
                    {
                        "id": "custom-model",
                        "name": "Custom Model",
                        "vendor": "custom",
                    },
                ],
                "availableModels": ["deepseek-v4-pro", "custom-model"],
            },
        )

        result = self._run_codebuddy_sync({"models": [], "availableModels": []})

        model_ids = [m["id"] for m in result["models"].get("models", [])]
        self.assertNotIn("deepseek-v4-pro", model_ids)
        self.assertEqual(model_ids, ["custom-model"])
        self.assertEqual(result["models"]["availableModels"], [])

    def test_modified_config_model_updates_target(self) -> None:
        """Editing a model in config updates the same managed entry in place (scenario 4)."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {
                        "id": "deepseek-v4-flash",
                        "name": "Old Name",
                        "vendor": "old",
                        "_managed_by": "ai-coding-kit",
                    },
                    {
                        "id": "user-model",
                        "name": "User Model",
                        "vendor": "custom",
                    },
                ],
            },
        )

        # Config edits deepseek-v4-flash (name + adds supportsImages).
        edited = dict(self.platform_cfg["models"][1])
        edited["name"] = "Renamed Flash"
        edited["supportsImages"] = True
        cfg = {"models": [edited]}
        result = self._run_codebuddy_sync(cfg)

        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertEqual(synced["deepseek-v4-flash"]["name"], "Renamed Flash")
        self.assertTrue(synced["deepseek-v4-flash"]["supportsImages"])
        self.assertEqual(synced["deepseek-v4-flash"]["_managed_by"], "ai-coding-kit")
        # User model untouched.
        self.assertEqual(synced["user-model"]["name"], "User Model")

    def test_user_models_preserved_when_target_non_empty(self) -> None:
        """Pre-existing user models are preserved alongside synced ones (scenario 2)."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {"id": "user-only", "name": "User Only", "vendor": "custom"},
                ],
            },
        )

        result = self._run_codebuddy_sync()

        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertIn("user-only", model_ids)
        self.assertIn("deepseek-v4-pro", model_ids)
        self.assertIn("deepseek-v4-flash", model_ids)

    # ── Legacy (pre-marker) upgrade migration ──────────────────────────────

    def test_legacy_synced_entries_are_claimed_on_upgrade(self) -> None:
        """Pre-marker entries that are exact config copies are claimed and managed again."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        # Legacy sync output: no _managed_by, exact copy of the resolved config
        # (same key set, same values, resolved placeholders).
        legacy = dict(self.platform_cfg["models"][0])
        legacy["url"] = "https://codebuddy.example/v1"
        legacy["apiKey"] = "sk-test-codebuddy"
        self._write_json(
            models_path,
            {"models": [legacy], "availableModels": ["deepseek-v4-pro"]},
        )

        result = self._run_codebuddy_sync()

        # The legacy entry is claimed: gains the marker and stays managed.
        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertEqual(synced["deepseek-v4-pro"]["_managed_by"], "ai-coding-kit")
        self.assertEqual(len(result["models"]["models"]), 2)

    def test_legacy_entry_shared_credentials_not_claimed(self) -> None:
        """A user entry sharing provider credentials with config is never claimed.

        Only url/apiKey matched before, so an entry with identical credentials
        but user-authored fields was wrongly claimed and then overwritten by
        config. The strict matcher (exact copy) keeps it user-owned.
        """
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {
                        "id": "deepseek-v4-pro",
                        # Credentials identical to config...
                        "url": "https://codebuddy.example/v1",
                        "apiKey": "sk-test-codebuddy",
                        # ...but the rest is user-authored.
                        "name": "My Customized DeepSeek",
                        "vendor": "custom",
                    },
                ],
            },
        )

        result = self._run_codebuddy_sync()

        # Not claimed: preserved verbatim (no marker), config entry skipped.
        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertEqual(synced["deepseek-v4-pro"]["name"], "My Customized DeepSeek")
        self.assertEqual(synced["deepseek-v4-pro"]["vendor"], "custom")
        self.assertNotIn("_managed_by", synced["deepseek-v4-pro"])

    def test_legacy_entry_with_no_comparable_fields_not_claimed(self) -> None:
        """An entry with no comparable non-None field beyond id is never claimed.

        The old matcher compared url/apiKey, so two entries that both lack
        credentials matched (None == None) and the user entry got overwritten.
        With no comparable field at all there is no evidence of a legacy copy,
        so the entry stays user-owned.
        """
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(models_path, {"models": [{"id": "local-model"}]})

        result = self._run_codebuddy_sync({"models": [{"id": "local-model"}]})

        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertEqual(synced["local-model"], {"id": "local-model"})
        self.assertNotIn("_managed_by", synced["local-model"])

    def test_legacy_entry_without_credentials_but_matching_fields_is_claimed(self) -> None:
        """Lacking credentials alone does NOT prevent a claim.

        Both sides have no url/apiKey, but every other field is an exact match
        (same key set, same values). That is still a strong exact-copy signal,
        so the legacy entry is claimed and managed again.
        """
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {"models": [{"id": "local-model", "name": "Local Model", "vendor": "ollama"}]},
        )

        result = self._run_codebuddy_sync(
            {"models": [{"id": "local-model", "name": "Local Model", "vendor": "ollama"}]}
        )

        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertEqual(synced["local-model"]["_managed_by"], "ai-coding-kit")
        self.assertEqual(synced["local-model"]["name"], "Local Model")
        self.assertEqual(synced["local-model"]["vendor"], "ollama")

    def test_legacy_claim_then_prune_on_next_sync(self) -> None:
        """Claimed legacy entries are pruned once their id disappears from config.

        Sync 1: the legacy entry (exact config copy, no marker) is claimed and
        managed again. After the model leaves config, sync 2 prunes the
        now-marked entry automatically — the documented upgrade workflow.
        """
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        legacy = dict(self.platform_cfg["models"][0])
        legacy["url"] = "https://codebuddy.example/v1"
        legacy["apiKey"] = "sk-test-codebuddy"
        self._write_json(models_path, {"models": [legacy]})

        # Sync 1: claimed (exact copy) and managed again.
        result = self._run_codebuddy_sync()
        synced = {m["id"]: m for m in result["models"]["models"]}
        self.assertEqual(synced["deepseek-v4-pro"]["_managed_by"], "ai-coding-kit")
        self.assertEqual(len(result["models"]["models"]), 2)

        # Sync 2: model removed from config -> marked entry pruned automatically.
        cfg = {"models": [self.platform_cfg["models"][1]]}
        result = self._run_codebuddy_sync(cfg)
        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertNotIn("deepseek-v4-pro", model_ids)
        self.assertIn("deepseek-v4-flash", model_ids)

    def test_orphan_legacy_entry_preserved_when_id_gone_from_config(self) -> None:
        """A legacy entry whose id left config before the upgrade stays untouched.

        No config match -> no identity evidence -> not claimed and never deleted
        automatically (safe side). The user removes it by hand once; the next
        sync keeps it gone since nothing writes it back.
        """
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        legacy = dict(self.platform_cfg["models"][0])
        legacy["url"] = "https://codebuddy.example/v1"
        legacy["apiKey"] = "sk-test-codebuddy"
        self._write_json(models_path, {"models": [legacy]})

        # deepseek-v4-pro was already gone from config before this run, so it
        # cannot be claimed and is preserved (safe side). User removes it once.
        cfg = {"models": [self.platform_cfg["models"][1]]}
        result = self._run_codebuddy_sync(cfg)
        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertIn("deepseek-v4-pro", model_ids)
        self.assertIn("deepseek-v4-flash", model_ids)

        # Remove the orphan manually — the next sync keeps it gone (id still
        # absent from config, no marker written back by a config entry).
        data = self._read_json(models_path)
        data["models"] = [m for m in data["models"] if m["id"] != "deepseek-v4-pro"]
        self._write_json(models_path, data)

        result = self._run_codebuddy_sync(cfg)
        model_ids = [m["id"] for m in result["models"]["models"]]
        self.assertNotIn("deepseek-v4-pro", model_ids)
        self.assertIn("deepseek-v4-flash", model_ids)

    def test_api_enabled_after_disabled_restores_models(self) -> None:
        """Re-enabling API sync restores availableModels from config."""
        models_path = self.root / "home" / ".codebuddy" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {
                        "id": "deepseek-v4-pro",
                        "name": "Stale DeepSeek V4 Pro",
                        "vendor": "old",
                    }
                ],
                "availableModels": ["deepseek-v4-pro"],
            },
        )

        disabled = {
            "api": {"enabled": False},
            "models": self.platform_cfg["models"],
            "availableModels": self.platform_cfg["availableModels"],
        }
        self._run_codebuddy_sync(disabled)
        self.assertEqual(self._read_json(models_path)["availableModels"], [])

        enabled = {
            "models": self.platform_cfg["models"],
            "availableModels": self.platform_cfg["availableModels"],
        }
        result = self._run_codebuddy_sync(enabled)
        self.assertEqual(
            result["models"]["availableModels"],
            ["deepseek-v4-pro", "deepseek-v4-flash"],
        )
        self.assertEqual(len(result["models"]["models"]), 2)

    def test_empty_mcp_servers_does_not_break(self) -> None:
        """Sync with no MCP servers still runs CodeBuddy models sync."""
        mcp_dir = self.root / "env" / "mcp"
        for f in mcp_dir.glob("*.json"):
            f.unlink()

        target_cfg = self.platform_cfg
        self._write_json(self.root / "env" / "platforms" / "codebuddy.json", target_cfg)
        with patched_sync_environment(self.root):
            sys.argv = ["sync_config.py", "--target", "codebuddy"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                sync_config.main()

        mcp = self._read_json(self.root / "home" / ".codebuddy" / "mcp.json")
        models = self._read_json(self.root / "home" / ".codebuddy" / "models.json")
        self.assertEqual(mcp["mcpServers"], {})
        self.assertEqual(len(models["models"]), 2)

    def test_mcp_json_not_found_creates_new_file(self) -> None:
        """When ~/.codebuddy/mcp.json doesn't exist, sync creates it."""
        result = self._run_codebuddy_sync()

        self.assertIn("mcpServers", result["mcp"])
        self.assertIn("sample", result["mcp"]["mcpServers"])

    def test_missing_codebuddy_root_skips_sync(self) -> None:
        """When ~/.codebuddy does not exist, sync should not create CodeBuddy files."""
        (self.root / "home" / ".codebuddy").rmdir()

        result = self._run_codebuddy_sync()

        self.assertFalse((self.root / "home" / ".codebuddy").exists())
        self.assertEqual(result["mcp"], {})
        self.assertEqual(result["models"], {})

    def test_models_json_not_found_creates_new_file(self) -> None:
        """When ~/.codebuddy/models.json doesn't exist, sync creates it."""
        result = self._run_codebuddy_sync()

        self.assertIn("models", result["models"])
        self.assertEqual(len(result["models"]["models"]), 2)

    def test_secret_resolution_in_models(self) -> None:
        """Secrets ${codebuddy.url} and ${codebuddy.key} are resolved in model fields."""
        result = self._run_codebuddy_sync()

        model = result["models"]["models"][0]
        self.assertEqual(model["url"], "https://codebuddy.example/v1")
        self.assertEqual(model["apiKey"], "sk-test-codebuddy")

    def test_invalid_models_config_fails_fast(self) -> None:
        """Invalid models config is rejected before writing models.json."""
        with self.assertRaisesRegex(ValueError, "platforms.codebuddy.models must be a list"):
            self._run_codebuddy_sync({"models": {"id": "bad"}})

    def test_invalid_available_models_config_fails_fast(self) -> None:
        """Invalid availableModels config is rejected before writing models.json."""
        with self.assertRaisesRegex(
            ValueError,
            r"platforms\.codebuddy\.availableModels\[0\] must be a non-empty string",
        ):
            self._run_codebuddy_sync({"availableModels": [123]})

    # ── Internal key exclusion ──────────────────────────────────────────────

    def test_internal_keys_excluded_from_output(self) -> None:
        """_comment and platform-internal keys do not leak into output files."""
        result = self._run_codebuddy_sync()

        for key in ("_comment",):
            self.assertNotIn(key, result["mcp"], f"Internal key '{key}' leaked into mcp.json")
            self.assertNotIn(key, result["models"], f"Internal key '{key}' leaked into models.json")

    # ── Preamble (CODEBUDDY.md) ────────────────────────────────────────────

    def _read_codebuddy_md(self) -> str:
        path = self.root / "home" / ".codebuddy" / "CODEBUDDY.md"
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _recall_cfg(self) -> dict:
        """Explicit recall-mode config — keeps recall-path coverage now that the
        default cfg is mode=full."""
        return {
            **self.platform_cfg,
            "preamble": {"target": "CODEBUDDY.md", "mode": "recall", "tool": "codebuddy"},
        }

    def test_recall_mode_writes_standalone_recall_block(self) -> None:
        """preamble.mode=recall renders the standalone historical-recall block."""
        self._run_codebuddy_sync(self._recall_cfg())

        text = self._read_codebuddy_md()
        self.assertIn("managed-block:historical-recall:begin", text)
        self.assertIn("managed-block:historical-recall:end", text)
        # Points at the CodeBuddy skills dir (same as the bash preamble writer).
        self.assertIn(
            str(self.root / "home" / ".codebuddy" / "skills" / "historical-recall" / "SKILL.md"),
            text,
        )
        # Recall CLI path points at the repo's dist/cli.js (absolute).
        self.assertIn("plan-reviews/dist/cli.js", text)

    def test_recall_block_preserves_user_content(self) -> None:
        """Content outside the managed block is preserved during merge."""
        cb = self.root / "home" / ".codebuddy" / "CODEBUDDY.md"
        cb.write_text("# my custom header\n\nkeep me\n", encoding="utf-8")

        self._run_codebuddy_sync(self._recall_cfg())

        text = self._read_codebuddy_md()
        self.assertIn("keep me", text)
        self.assertIn("managed-block:historical-recall:begin", text)

    def test_recall_block_idempotent(self) -> None:
        """Re-running sync does not duplicate the managed block."""
        self._run_codebuddy_sync(self._recall_cfg())
        self._run_codebuddy_sync(self._recall_cfg())

        text = self._read_codebuddy_md()
        self.assertEqual(text.count("managed-block:historical-recall:begin"), 1)

    def test_full_mode_does_not_write_standalone_recall_block(self) -> None:
        """preamble.mode=full (the default) never writes a standalone recall block;
        the full preamble incl. historical-recall is rendered by sync-agent-preamble.sh."""
        # Default cfg is mode=full.
        self._run_codebuddy_sync()
        self.assertNotIn("managed-block:historical-recall:begin", self._read_codebuddy_md())

    def test_none_mode_skips_recall_block(self) -> None:
        """preamble.mode=none writes neither a recall nor a full preamble block."""
        cfg = {
            **self.platform_cfg,
            "preamble": {"target": "CODEBUDDY.md", "mode": "none", "tool": "codebuddy"},
        }
        self._run_codebuddy_sync(cfg)
        self.assertNotIn("managed-block:historical-recall:begin", self._read_codebuddy_md())

    def test_recall_block_skipped_when_root_missing(self) -> None:
        """When ~/.codebuddy does not exist, no CODEBUDDY.md is created."""
        (self.root / "home" / ".codebuddy").rmdir()

        self._run_codebuddy_sync()

        self.assertFalse(
            (self.root / "home" / ".codebuddy" / "CODEBUDDY.md").exists()
        )


class AgentPreambleTemplateDedupTests(unittest.TestCase):
    """Source-template guards that lock the single-source-of-truth for the
    historical-recall section (see sync-agent-preamble.sh render_managed_block).

    These prevent a silent regression where someone re-inlines the recall body
    into the full ``agent-preamble`` block, defeating the DRY design.
    """

    TEMPLATE = (
        REPO_ROOT
        / "skills-engineering"
        / "scripts"
        / "templates"
        / "agent-preamble.md.tmpl"
    ).read_text(encoding="utf-8")

    AGENT_BEGIN = "<!-- managed-block:agent-preamble:begin"
    AGENT_END = "<!-- managed-block:agent-preamble:end"
    RECALL_BEGIN = "<!-- managed-block:historical-recall:begin"
    RECALL_END = "<!-- managed-block:historical-recall:end"

    @staticmethod
    def _extract_block(text: str, begin: str, end: str) -> str:
        in_block = False
        out = []
        for line in text.splitlines():
            if begin in line:
                in_block = True
                continue
            if end in line:
                in_block = False
                continue
            if in_block:
                out.append(line)
        return "\n".join(out)

    def test_recall_body_is_single_source(self) -> None:
        """The recall signature HR-001 lives in exactly ONE place: the
        standalone historical-recall block. It must not be duplicated
        anywhere (e.g. re-inlined into the full block)."""
        self.assertEqual(self.TEMPLATE.count("HR-001"), 1)

    def test_full_block_references_recall_via_placeholder(self) -> None:
        """The full agent-preamble block must reference the recall section via
        the {{HISTORICAL_RECALL_BLOCK}} placeholder (exactly once) and must
        NOT inline the recall body (no HR-001)."""
        full = self._extract_block(self.TEMPLATE, self.AGENT_BEGIN, self.AGENT_END)
        self.assertEqual(full.count("{{HISTORICAL_RECALL_BLOCK}}"), 1)
        self.assertNotIn("HR-001", full)

    def test_standalone_recall_block_holds_the_body(self) -> None:
        """The standalone historical-recall block is the single source of truth
        and must contain the recall body signature HR-001."""
        recall = self._extract_block(self.TEMPLATE, self.RECALL_BEGIN, self.RECALL_END)
        self.assertIn("HR-001", recall)

    def test_anti_edit_template_note_present(self) -> None:
        """The source-only anti-edit note guards the placeholder injection point
        and must appear exactly once (in the full block), so it cannot leak
        into rendered targets unnoticed."""
        self.assertEqual(self.TEMPLATE.count("template-note"), 1)
        full = self._extract_block(self.TEMPLATE, self.AGENT_BEGIN, self.AGENT_END)
        self.assertIn("template-note", full)


class MultiSkillCoordinationTests(unittest.TestCase):
    """Guards for the multi-skill combination-harmony fixes (D1–D5).

    Skills are meant to stack as complementary enhancement, never as
    contradiction. These tests lock the coordination clauses so a future edit
    cannot silently regress that invariant (e.g. re-introducing a duplicated
    calibration block or a contradictory question-count rule).
    """

    TEMPLATE = (
        REPO_ROOT
        / "skills-engineering"
        / "scripts"
        / "templates"
        / "agent-preamble.md.tmpl"
    ).read_text(encoding="utf-8")

    ENG_DISC = (
        REPO_ROOT
        / "skills-engineering"
        / "engineering-discipline"
        / "references"
        / "engineering_discipline.md"
    ).read_text(encoding="utf-8")

    COG_EXP = (
        REPO_ROOT
        / "skills-engineering"
        / "cognitive-reasoning"
        / "references"
        / "cognitive_expansion.md"
    ).read_text(encoding="utf-8")

    CAM = (
        REPO_ROOT
        / "skills-engineering"
        / "cognitive-reasoning"
        / "references"
        / "cognitive_adversary_mode.md"
    ).read_text(encoding="utf-8")

    PLAN_GRILL = (
        REPO_ROOT
        / "skills-engineering"
        / "plan-grill"
        / "references"
        / "plan_grill.md"
    ).read_text(encoding="utf-8")

    def test_preamble_has_multi_skill_coordination_section(self) -> None:
        # D3: the stacking-harmony overview must exist in the preamble template.
        self.assertIn("# global multi-skill coordination", self.TEMPLATE)

    def test_preamble_cam_suppresses_lightweight_block(self) -> None:
        # D1: CAM activation must suppress the standalone preamble calibration block.
        self.assertIn("CAM 激活", self.TEMPLATE)
        self.assertIn("不再单独输出", self.TEMPLATE)

    def test_engdisc_gr002_absorbs_grill(self) -> None:
        # D2: GR-002 must state it is absorbed by PG-000 grilling (no duplicate block).
        self.assertIn("PG-000 已进入盘问", self.ENG_DISC)

    def test_engdisc_gr006_merges_with_gr002(self) -> None:
        # D2: GR-006 strategic interruption merges with GR-002 same anchor.
        self.assertIn("本中断块与 `engineering-discipline` GR-002", self.ENG_DISC)

    def test_gr004_has_coordination_subsections(self) -> None:
        # D3/D4/D5: GR-004 merge SOP must carry the extended subsections.
        for marker in (
            "校准层与 iOS 专属层的纳入",
            "跨块置信度总协调",
            "多 SKILL 叠加时的读取与预算上限",
        ):
            self.assertIn(marker, self.ENG_DISC)

    def test_gr004_cam_keeps_mechanical_format(self) -> None:
        # D4: CAM fields must be preserved, not collapsed into 逻辑链/验证锚点.
        self.assertIn("保留 CAM 机械格式", self.ENG_DISC)

    def test_gr004_confidence_normalizes_to_retained_field(self) -> None:
        # D5: confidence normalizes to the single retained field, not always 验证锚点.
        self.assertIn("本轮唯一保留的置信度", self.ENG_DISC)

    def test_cogexp_tier2_excludes_preamble_calibration(self) -> None:
        # D1: cognitive_expansion.md truth text must exclude preamble lightweight
        # calibration under Tier 2 (entry and truth text must agree).
        self.assertIn("轻量认知校准段", self.COG_EXP)
        self.assertIn("CAM 完整结构承载", self.COG_EXP)

    def test_plan_grill_absorbs_gr002(self) -> None:
        # D2: plan-grill truth file must state the first grill question absorbs GR-002.
        self.assertIn("吸收为盘问首问", self.PLAN_GRILL)

    def test_cam_fields_not_collapsed(self) -> None:
        # D4: CAM detail file keeps its fields intact (no collapse into other blocks).
        self.assertIn("不得省略或并入其它块", self.CAM)


class GlobalSkillValidationScriptTests(unittest.TestCase):
    """The one-shot validation entrypoint must stay read-only and complete."""

    SCRIPT = (
        REPO_ROOT
        / "skills-engineering"
        / "scripts"
        / "validate-global-skills.sh"
    ).read_text(encoding="utf-8")

    def test_global_validation_entrypoint_covers_closure_steps(self) -> None:
        for marker in (
            "validate-skill-structure.sh",
            "validate-skill-behavior.sh",
            "sync-agent-preamble.sh\" --dry-run",
            "verify-sync.sh",
            "validate-skill-integrity.sh\" --check-only",
            "python3 tests/test_codebuddy_sync.py",
        ):
            self.assertIn(marker, self.SCRIPT)

    def test_global_validation_entrypoint_is_read_only(self) -> None:
        self.assertIn("--dry-run", self.SCRIPT)
        self.assertIn("--check-only", self.SCRIPT)
        self.assertNotIn("sync-skills.sh", self.SCRIPT)


if __name__ == "__main__":
    unittest.main()
