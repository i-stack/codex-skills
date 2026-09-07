import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_DIR = REPO_ROOT / "sync"
if str(SYNC_DIR) not in sys.path:
    sys.path.insert(0, str(SYNC_DIR))

from cli import sync_config  # noqa: E402
from platforms import qwen as qwen_mod  # noqa: E402
from core import common  # noqa: E402

from platforms.qwen import _derive_qwen_custom_env_key  # noqa: E402


SECURITY = {
    "auth": {
        "selectedType": "openai",
    },
}
MODEL_PROVIDERS = {
    "openai": [
        {
            "id": "qwen3-coder-plus",
            "name": "Qwen3 Coder Plus",
            "baseUrl": "${qwen.url}",
            "envKey": "DASHSCOPE_API_KEY",
            "generationConfig": {"extra_body": {"enable_thinking": True}},
        },
        {
            "id": "qwen3-coder",
            "name": "Qwen3 Coder",
            "baseUrl": "${qwen.url}",
            "envKey": "DASHSCOPE_API_KEY",
            "generationConfig": {"extra_body": {"enable_thinking": True}},
        },
        {
            "id": "qwen-max",
            "name": "Qwen Max",
            "baseUrl": "${qwen.url}",
            "envKey": "DASHSCOPE_API_KEY",
            "generationConfig": {"extra_body": {"enable_thinking": True}},
        },
    ],
}
MODEL = {
    "name": "qwen3-coder-plus",
    "baseUrl": "${qwen.url}",
}

DEFAULT_QWEN_CFG = {
    "api": {"enabled": True},
    "security": SECURITY,
    "env": {
        "DASHSCOPE_API_KEY": "${qwen.key}",
    },
    "modelProviders": MODEL_PROVIDERS,
    "model": MODEL,
    "preamble": {
        "target": "QWEN.md",
        "mode": "recall",
        "tool": "qwen",
    },
}

# Top-level keys that map into ~/.qwen/settings.json.
SETTINGS_KEYS = ("security", "modelProviders", "model")


def _disabled_cfg(base: dict | None = None) -> dict:
    """Build a config with managed fields but api.enabled=false."""
    base = base if base is not None else DEFAULT_QWEN_CFG
    cfg = {k: base[k] for k in SETTINGS_KEYS}
    cfg["env"] = base["env"]
    cfg["api"] = {"enabled": False}
    return cfg


@contextlib.contextmanager
def patched_sync_environment(root: Path):
    """Redirect HOME and common module paths for isolated Qwen sync tests."""
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


class QwenSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "home" / ".qwen").mkdir(parents=True, exist_ok=True)
        self.platform_cfg = DEFAULT_QWEN_CFG
        self._write_json(
            self.root / "env" / "mcp" / "sample.json",
            {
                "name": "sample",
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "platforms": ["qwen"],
            },
        )
        self._write_json(
            self.root / "env" / "secrets.json",
            {
                "qwen": {
                    "url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                    "key": "sk-test-qwen",
                }
            },
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

    def _run_qwen_sync(self, cfg: dict | None = None) -> dict[str, dict]:
        """Run Qwen sync and return parsed {settings, models} contents."""
        target_cfg = cfg if cfg is not None else self.platform_cfg
        self._write_json(self.root / "env" / "platforms" / "qwen.json", target_cfg)
        with patched_sync_environment(self.root):
            sys.argv = ["sync_config.py", "--target", "qwen"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                sync_config.main()
        return {
            "settings": self._read_json(self.root / "home" / ".qwen" / "settings.json"),
            "models": self._read_json(self.root / "home" / ".qwen" / "models.json"),
        }

    # ── Env sync ──────────────────────────────────────────────────────────────

    def test_env_synced_to_settings_json(self) -> None:
        result = self._run_qwen_sync()

        self.assertIn("env", result["settings"])
        self.assertEqual(
            result["settings"]["env"]["DASHSCOPE_API_KEY"], "sk-test-qwen"
        )

    def test_settings_json_preserves_existing_user_keys(self) -> None:
        """User-added keys in settings.json outside env are preserved."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {"userPref": "keep-me", "env": {"USER_VAR": "should-stay"}},
        )

        result = self._run_qwen_sync()

        self.assertEqual(result["settings"]["userPref"], "keep-me")
        # Managed env key merged; unrelated user env key preserved.
        self.assertEqual(result["settings"]["env"]["DASHSCOPE_API_KEY"], "sk-test-qwen")
        self.assertEqual(result["settings"]["env"]["USER_VAR"], "should-stay")

    # ── Settings fields sync ─────────────────────────────────────────────────

    def test_settings_fields_synced_to_settings_json(self) -> None:
        """The managed top-level fields (security/modelProviders/model) are written."""
        result = self._run_qwen_sync()

        settings = result["settings"]
        self.assertEqual(settings["security"]["auth"]["selectedType"], "openai")
        providers = settings["modelProviders"]["openai"]
        self.assertEqual(len(providers), 3)
        self.assertEqual(providers[0]["id"], "qwen3-coder-plus")
        self.assertEqual(
            providers[0]["baseUrl"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        self.assertEqual(providers[0]["envKey"], "DASHSCOPE_API_KEY")
        self.assertEqual(providers[0]["generationConfig"]["extra_body"]["enable_thinking"], True)
        self.assertEqual(settings["model"]["name"], "qwen3-coder-plus")
        self.assertEqual(
            settings["model"]["baseUrl"],
            "https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    def test_settings_fields_preserves_other_providers(self) -> None:
        """User-added modelProviders entries not in config are preserved."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "modelProviders": {
                    "openai": [
                        {
                            "id": "deepseek-v4-pro",
                            "name": "deepseek-v4-pro",
                            "baseUrl": "https://cloud.dataeyes.ai/v1",
                            "envKey": "QWEN_CUSTOM_API_KEY_OPENAI_X",
                        }
                    ]
                }
            },
        )

        result = self._run_qwen_sync()

        providers = result["settings"]["modelProviders"]["openai"]
        provider_ids = [p["id"] for p in providers]
        self.assertIn("deepseek-v4-pro", provider_ids)
        self.assertIn("qwen3-coder-plus", provider_ids)
        self.assertEqual(len(providers), 4)

    def test_model_provider_same_id_user_entry_not_overwritten(self) -> None:
        """A user-added provider entry with a config id but no marker is preserved.

        Without the marker the entry is user-owned: config must not overwrite
        it. The sync-managed entry (carrying the marker) is updated normally.
        """
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "modelProviders": {
                    "openai": [
                        {
                            "id": "qwen3-coder-plus",
                            "name": "My Custom Qwen",
                            "baseUrl": "https://user.example/v1",
                            "envKey": "MY_KEY",
                        }
                    ]
                }
            },
        )

        result = self._run_qwen_sync()

        providers = result["settings"]["modelProviders"]["openai"]
        user_entry = next(p for p in providers if p["id"] == "qwen3-coder-plus")
        # User-owned entry preserved verbatim; no marker written on it.
        self.assertEqual(user_entry["name"], "My Custom Qwen")
        self.assertEqual(user_entry["baseUrl"], "https://user.example/v1")
        self.assertNotIn("_managed_by", user_entry)
        # The other config entries are still synced in (marked).
        self.assertEqual(len(providers), 3)

    def test_model_provider_marked_entry_overwritten_and_pruned(self) -> None:
        """Marked (sync-managed) entries are updated, then pruned when dropped."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "modelProviders": {
                    "openai": [
                        {
                            "id": "qwen3-coder-plus",
                            "name": "OLD",
                            "baseUrl": "old",
                            "envKey": "old",
                            "_managed_by": "ai-coding-kit",
                        },
                        {
                            "id": "stale-model",
                            "name": "stale",
                            "baseUrl": "stale",
                            "envKey": "stale",
                            "_managed_by": "ai-coding-kit",
                        },
                    ]
                }
            },
        )

        result = self._run_qwen_sync()

        providers = result["settings"]["modelProviders"]["openai"]
        provider_ids = [p["id"] for p in providers]
        # Marked config entry updated to the resolved config values.
        self.assertIn("qwen3-coder-plus", provider_ids)
        self.assertNotIn("stale-model", provider_ids)
        qwen_entry = next(p for p in providers if p["id"] == "qwen3-coder-plus")
        self.assertEqual(qwen_entry["name"], "Qwen3 Coder Plus")

    def test_vanished_provider_type_prunes_marked_and_keeps_user(self) -> None:
        """A provider type gone from config still runs an empty merge."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "modelProviders": {
                    "openai": [
                        {
                            "id": "qwen3-coder-plus",
                            "name": "OLD",
                            "baseUrl": "old",
                            "envKey": "old",
                            "_managed_by": "ai-coding-kit",
                        }
                    ],
                    "anthropic": [
                        {
                            "id": "stale-claude",
                            "name": "stale",
                            "baseUrl": "stale",
                            "envKey": "stale",
                            "_managed_by": "ai-coding-kit",
                        },
                        {
                            "id": "user-claude",
                            "name": "User Claude",
                            "baseUrl": "https://user.example/v1",
                            "envKey": "USER_KEY",
                        },
                    ],
                }
            },
        )

        result = self._run_qwen_sync()

        providers = result["settings"]["modelProviders"]
        self.assertIn("openai", providers)
        self.assertNotIn("stale-claude", [p["id"] for p in providers.get("anthropic", [])])
        user_entries = providers.get("anthropic", [])
        self.assertEqual(len(user_entries), 1)
        self.assertEqual(user_entries[0]["id"], "user-claude")
        self.assertNotIn("_managed_by", user_entries[0])

    def test_no_settings_fields_skips_merge(self) -> None:
        """When config has none of the managed settings keys, nothing is merged."""
        cfg: dict = {"env": self.platform_cfg["env"]}
        result = self._run_qwen_sync(cfg)

        self.assertIn("env", result["settings"])
        self.assertNotIn("modelProviders", result["settings"])
        self.assertNotIn("model", result["settings"])
        self.assertNotIn("security", result["settings"])

    # ── $version preservation ───────────────────────────────────────────────

    def test_version_field_is_preserved(self) -> None:
        """Qwen-internal '$version' is never overwritten or removed by sync."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {"$version": 4, "userPref": "keep-me", "env": {"USER_VAR": "stay"}},
        )

        result = self._run_qwen_sync()

        self.assertEqual(result["settings"]["$version"], 4)
        self.assertEqual(result["settings"]["userPref"], "keep-me")
        # Managed fields still synced alongside the preserved marker.
        self.assertEqual(result["settings"]["env"]["DASHSCOPE_API_KEY"], "sk-test-qwen")
        self.assertEqual(result["settings"]["security"]["auth"]["selectedType"], "openai")

    def test_version_field_preserved_when_disabled(self) -> None:
        """Even when API sync is disabled, '$version' survives cleanup."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "$version": 4,
                "env": {"DASHSCOPE_API_KEY": "old"},
                "modelProviders": {
                    "openai": [
                        {
                            "id": "qwen3-coder-plus",
                            "name": "x",
                            "baseUrl": "y",
                            "envKey": "z",
                            "_managed_by": "ai-coding-kit",
                        }
                    ]
                },
                "model": {"name": "qwen3-coder-plus", "baseUrl": "y"},
                "security": {"auth": {"selectedType": "openai"}},
            },
        )

        result = self._run_qwen_sync(_disabled_cfg())

        self.assertEqual(result["settings"]["$version"], 4)
        # Managed fields cleaned, but $version untouched.
        self.assertNotIn("DASHSCOPE_API_KEY", result["settings"].get("env", {}))
        self.assertNotIn("modelProviders", result["settings"])
        self.assertNotIn("model", result["settings"])
        self.assertNotIn("security", result["settings"])

    # ── API toggle (api.enabled) ────────────────────────────────────────────

    def test_api_enabled_by_default(self) -> None:
        """Missing api block defaults to enabled — settings fields sync."""
        cfg = {
            "security": SECURITY,
            "env": self.platform_cfg["env"],
            "modelProviders": MODEL_PROVIDERS,
            "model": MODEL,
        }
        result = self._run_qwen_sync(cfg)

        self.assertEqual(result["settings"]["model"]["name"], "qwen3-coder-plus")
        self.assertEqual(len(result["settings"]["modelProviders"]["openai"]), 3)
        self.assertEqual(result["settings"]["env"]["DASHSCOPE_API_KEY"], "sk-test-qwen")

    def test_api_disabled_cleans_settings_block(self) -> None:
        """When api.enabled=false, managed settings fields are removed."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "userPref": "keep-me",
                "env": {"DASHSCOPE_API_KEY": "old", "USER_VAR": "keep"},
                "modelProviders": {
                    "openai": [
                        {
                            "id": "qwen3-coder-plus",
                            "name": "x",
                            "baseUrl": "y",
                            "envKey": "z",
                            "_managed_by": "ai-coding-kit",
                        },
                        {"id": "user-only", "name": "u", "baseUrl": "b", "envKey": "e"},
                    ]
                },
                "model": {"name": "qwen3-coder-plus", "baseUrl": "y"},
                "security": {"auth": {"selectedType": "openai"}},
            },
        )

        result = self._run_qwen_sync(_disabled_cfg())

        # Managed provider entry removed; user-only provider preserved.
        providers = result["settings"]["modelProviders"]["openai"]
        self.assertEqual([p["id"] for p in providers], ["user-only"])
        # model / security removed; userPref preserved.
        self.assertNotIn("model", result["settings"])
        self.assertNotIn("security", result["settings"])
        self.assertEqual(result["settings"]["userPref"], "keep-me")
        # env key removed; unrelated user env key preserved.
        self.assertNotIn("DASHSCOPE_API_KEY", result["settings"]["env"])
        self.assertEqual(result["settings"]["env"]["USER_VAR"], "keep")

    def test_api_disabled_cleans_env_keys(self) -> None:
        """When api.enabled=false, managed env keys are removed from settings.json."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {"env": {"DASHSCOPE_API_KEY": "old", "USER_VAR": "keep"}},
        )

        result = self._run_qwen_sync(_disabled_cfg())

        # Managed key removed; unrelated user key preserved.
        self.assertNotIn("DASHSCOPE_API_KEY", result["settings"]["env"])
        self.assertEqual(result["settings"]["env"]["USER_VAR"], "keep")

    def test_api_enabled_after_disabled_restores_settings_block(self) -> None:
        """Re-enabling API sync restores the managed settings fields."""
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {
                "modelProviders": {
                    "openai": [
                        {
                            "id": "qwen3-coder-plus",
                            "name": "OLD",
                            "baseUrl": "old",
                            "envKey": "old",
                            "_managed_by": "ai-coding-kit",
                        }
                    ]
                },
                "model": {"name": "qwen3-coder-plus", "baseUrl": "old"},
                "security": {"auth": {"selectedType": "openai"}},
            },
        )

        self._run_qwen_sync(_disabled_cfg())
        self.assertNotIn("modelProviders", self._read_json(settings_path))

        result = self._run_qwen_sync(DEFAULT_QWEN_CFG)
        self.assertEqual(
            result["settings"]["modelProviders"]["openai"][0]["name"], "Qwen3 Coder Plus"
        )
        self.assertEqual(result["settings"]["model"]["baseUrl"],
                         "https://dashscope.aliyuncs.com/compatible-mode/v1")

    # ── Models.json is owned by Qwen (not synced) ───────────────────────────

    def test_models_json_not_managed_by_qwen(self) -> None:
        """Qwen sync never writes ~/.qwen/models.json."""
        self._run_qwen_sync()

        models_path = self.root / "home" / ".qwen" / "models.json"
        self.assertFalse(models_path.exists(), "qwen engine must not write models.json")

    def test_models_json_existing_preserved(self) -> None:
        """An existing user models.json is left untouched by sync."""
        models_path = self.root / "home" / ".qwen" / "models.json"
        self._write_json(
            models_path,
            {
                "models": [
                    {"id": "custom-model", "name": "Custom Model", "vendor": "custom"}
                ],
                "availableModels": ["custom-model"],
            },
        )

        self._run_qwen_sync()

        result = self._read_json(models_path)
        self.assertEqual(result["availableModels"], ["custom-model"])
        self.assertEqual(result["models"][0]["id"], "custom-model")

    # ── Skills sync ─────────────────────────────────────────────────────────

    def test_skills_synced_from_claude_to_qwen(self) -> None:
        claude_skills = self.root / "home" / ".claude" / "skills"
        skill_dir = claude_skills / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")
        (skill_dir / "helper.py").write_text("# helper script\n", encoding="utf-8")

        self._run_qwen_sync()

        dest = self.root / "home" / ".qwen" / "skills" / "test-skill"
        self.assertTrue(dest.exists(), "Skill directory was not synced to Qwen")
        self.assertTrue((dest / "SKILL.md").exists(), "SKILL.md was not synced")
        self.assertTrue((dest / "helper.py").exists(), "helper.py was not synced")
        self.assertEqual(
            (dest / "SKILL.md").read_text(encoding="utf-8"), "# Test Skill\n"
        )

    def test_skills_missing_claude_dir_skips_gracefully(self) -> None:
        """When ~/.claude/skills doesn't exist, skill sync is skipped without error."""
        result = self._run_qwen_sync()

        skills_dir = self.root / "home" / ".qwen" / "skills"
        self.assertFalse(skills_dir.exists(), "skills dir should not be created when claude skills missing")
        # Env and settings should still sync fine
        self.assertIn("env", result["settings"])
        self.assertIn("modelProviders", result["settings"])

    def test_skill_sync_skipped_when_skip_env_set(self) -> None:
        """SKIP_SKILL_SYNC=1 skips skill distribution but keeps settings sync."""
        claude_skills = self.root / "home" / ".claude" / "skills"
        skill_dir = claude_skills / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")

        old = os.environ.get("SKIP_SKILL_SYNC")
        os.environ["SKIP_SKILL_SYNC"] = "1"
        try:
            result = self._run_qwen_sync()
        finally:
            if old is None:
                os.environ.pop("SKIP_SKILL_SYNC", None)
            else:
                os.environ["SKIP_SKILL_SYNC"] = old

        dest = self.root / "home" / ".qwen" / "skills" / "test-skill"
        self.assertFalse(dest.exists(), "Skill dir should not be synced when SKIP_SKILL_SYNC=1")
        # Env and settings still sync.
        self.assertIn("env", result["settings"])
        self.assertIn("modelProviders", result["settings"])

    # ── MCP handling ────────────────────────────────────────────────────────

    def test_mcp_servers_are_ignored(self) -> None:
        """Qwen sync does not write a managed mcpServers file."""
        self._run_qwen_sync()

        mcp_path = self.root / "home" / ".qwen" / "mcp.json"
        self.assertFalse(mcp_path.exists(), "Qwen sync should not write mcp.json")

    # ── Internal key exclusion ──────────────────────────────────────────────

    def test_internal_keys_excluded_from_output(self) -> None:
        """_comment does not leak into the synced settings.json."""
        result = self._run_qwen_sync()

        self.assertNotIn("_comment", result["settings"])

    # ── Recall preamble ─────────────────────────────────────────────────────

    def test_recall_preamble_not_rendered_by_qwen_engine(self) -> None:
        """qwen.py does not render the recall managed block (engine gap, not error)."""
        self._run_qwen_sync()

        md = self.root / "home" / ".qwen" / "QWEN.md"
        self.assertFalse(md.exists(), "Qwen engine does not render recall preamble yet")

    # ── Missing root ────────────────────────────────────────────────────────

    def test_missing_qwen_root_skips_sync(self) -> None:
        """When ~/.qwen does not exist, sync should not create Qwen files."""
        (self.root / "home" / ".qwen").rmdir()

        result = self._run_qwen_sync()

        self.assertFalse((self.root / "home" / ".qwen").exists())
        self.assertEqual(result["settings"], {})
        self.assertEqual(result["models"], {})

    # ── Idempotency ─────────────────────────────────────────────────────────

    def test_resync_is_idempotent(self) -> None:
        """Re-running sync with the same config does not duplicate provider entries."""
        self._run_qwen_sync()
        result = self._run_qwen_sync()

        providers = result["settings"]["modelProviders"]["openai"]
        self.assertEqual([p["id"] for p in providers], [
            "qwen3-coder-plus", "qwen3-coder", "qwen-max"
        ])

    # ── Auto-derived custom env key (baseUrl -> QWEN_CUSTOM_API_KEY_*) ───────

    def test_auto_env_key_derivation(self) -> None:
        """``__AUTO__`` envKey is derived from baseUrl and the token remapped onto it.

        Qwen Code rejects DASHSCOPE_API_KEY for custom OpenAI-compatible
        providers (reserved key, 401s), so the syncer must write a baseUrl-
        derived key such as QWEN_CUSTOM_API_KEY_OPENAI_HTTPS_CLOUD_DATAEYES_AI_*.
        """
        auto_cfg = {
            "api": {"enabled": True},
            "security": SECURITY,
            "env": {"__AUTO__": "${qwen.key}"},
            "modelProviders": {
                "openai": [
                    {
                        "id": "deepseek-v4-flash",
                        "name": "deepseek-v4-flash",
                        "baseUrl": "${qwen.url}",
                        "envKey": "__AUTO__",
                        "generationConfig": {"extra_body": {"enable_thinking": True}},
                    },
                    {
                        "id": "deepseek-v4-pro",
                        "name": "deepseek-v4-pro",
                        "baseUrl": "${qwen.url}",
                        "envKey": "__AUTO__",
                        "generationConfig": {"extra_body": {"enable_thinking": True}},
                    },
                ]
            },
            "model": {"name": "deepseek-v4-flash", "baseUrl": "${qwen.url}"},
        }
        self._write_json(
            self.root / "env" / "secrets.json",
            {
                "qwen": {"url": "https://cloud.dataeyes.ai/v1", "key": "sk-dataeyes-test"},
            },
        )
        settings_path = self.root / "home" / ".qwen" / "settings.json"
        self._write_json(
            settings_path,
            {"$version": 4, "env": {"DASHSCOPE_API_KEY": "stale", "USER_VAR": "keep"}},
        )

        result = self._run_qwen_sync(auto_cfg)

        expected = _derive_qwen_custom_env_key("openai", "https://cloud.dataeyes.ai/v1")
        env = result["settings"]["env"]
        # Sentinel and legacy reserved key are gone; token landed on derived key.
        self.assertNotIn("__AUTO__", env)
        self.assertNotIn("DASHSCOPE_API_KEY", env)
        self.assertEqual(env[expected], "sk-dataeyes-test")
        self.assertEqual(env["USER_VAR"], "keep")
        providers = result["settings"]["modelProviders"]["openai"]
        for p in providers:
            self.assertEqual(p["envKey"], expected)
        self.assertEqual(result["settings"]["$version"], 4)

    def test_auto_env_key_derivation_matches_real_settings(self) -> None:
        """Derivation reproduces the real working key for cloud.dataeyes.ai."""
        key = _derive_qwen_custom_env_key("openai", "https://cloud.dataeyes.ai/v1")
        self.assertEqual(
            key, "QWEN_CUSTOM_API_KEY_OPENAI_HTTPS_CLOUD_DATAEYES_AI_C2DF01B23F5B"
        )


if __name__ == "__main__":
    unittest.main()
