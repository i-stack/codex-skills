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
from core import common  # noqa: E402

DEFAULT_CLINE_CFG = {
    "api": {"enabled": True},
    "globalState": {
        "openAiBaseUrl": "${cline.url}",
        "planModeOpenAiModelId": "deepseek-ai/deepseek-v4-pro",
        "actModeOpenAiModelId": "deepseek-ai/deepseek-v4-flash",
    },
    "secrets": {
        "openAiApiKey": "${cline.key}",
    },
}


@contextlib.contextmanager
def patched_sync_environment(root: Path):
    """Redirect HOME and module-level paths for isolated Cline sync tests."""
    import core.paths as _paths
    old_env = {k: os.environ.get(k) for k in ("HOME",)}
    old_paths = (common.MCP_DIR, common.PLATFORMS_DIR, common.SECRETS_PATH)
    old_paths_cfg = _paths.CONFIG_PATH
    old_overrides = _paths._PATH_OVERRIDES
    old_argv = sys.argv[:]
    try:
        os.environ["HOME"] = str(root / "home")
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


class ClineSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        # The install root must exist or both the orchestrator and the
        # platform sync() early-return.
        (self.root / "home" / ".cline").mkdir(parents=True, exist_ok=True)
        self.platform_cfg = json.loads(json.dumps(DEFAULT_CLINE_CFG))
        self._write_json(
            self.root / "env" / "mcp" / "sample.json",
            {
                "name": "sample",
                "type": "stdio",
                "command": "echo",
                "args": ["hello"],
                "platforms": ["cline"],
            },
        )
        self._write_json(
            self.root / "env" / "secrets.json",
            {"cline": {"url": "https://api.example.com/v1", "key": "sk-test-cline"}},
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

    def _run_cline_sync(self, cfg: dict | None = None) -> None:
        """Run Cline sync via the orchestrator and redirect all output."""
        target_cfg = cfg if cfg is not None else self.platform_cfg
        self._write_json(self.root / "env" / "platforms" / "cline.json", target_cfg)
        with patched_sync_environment(self.root):
            sys.argv = ["sync_config.py", "--target", "cline"]
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                sync_config.main()

    @property
    def global_state_path(self) -> Path:
        return self.root / "home" / ".cline" / "data" / "globalState.json"

    @property
    def secrets_path(self) -> Path:
        return self.root / "home" / ".cline" / "data" / "secrets.json"

    def _managed_keys(self) -> dict:
        return self._read_json(
            self.root / "home" / ".cline" / "data" / ".managed_keys.json"
        )

    # ── API sync enabled ──────────────────────────────────────────────────────

    def test_api_enabled_by_default(self) -> None:
        # Missing api block defaults to enabled.
        cfg = {k: v for k, v in self.platform_cfg.items() if k != "api"}
        self._run_cline_sync(cfg)
        gs = self._read_json(self.global_state_path)
        secrets = self._read_json(self.secrets_path)
        self.assertEqual(gs["openAiBaseUrl"], "https://api.example.com/v1")
        self.assertEqual(gs["planModeOpenAiModelId"], "deepseek-ai/deepseek-v4-pro")
        self.assertEqual(secrets["openAiApiKey"], "sk-test-cline")

    def test_api_enabled_explicit(self) -> None:
        cfg = json.loads(json.dumps(self.platform_cfg))
        cfg["api"]["enabled"] = True
        self._run_cline_sync(cfg)
        gs = self._read_json(self.global_state_path)
        secrets = self._read_json(self.secrets_path)
        self.assertEqual(gs["openAiBaseUrl"], "https://api.example.com/v1")
        self.assertEqual(secrets["openAiApiKey"], "sk-test-cline")

    # ── API sync disabled ─────────────────────────────────────────────────────

    def test_api_disabled_cleans_managed_keys(self) -> None:
        self._run_cline_sync(self.platform_cfg)
        self.assertIn("openAiApiKey", self._read_json(self.secrets_path))

        disabled = json.loads(json.dumps(self.platform_cfg))
        disabled["api"]["enabled"] = False
        self._run_cline_sync(disabled)

        gs = self._read_json(self.global_state_path)
        secrets = self._read_json(self.secrets_path)
        self.assertNotIn("openAiBaseUrl", gs)
        self.assertNotIn("planModeOpenAiModelId", gs)
        self.assertNotIn("actModeOpenAiModelId", gs)
        self.assertNotIn("openAiApiKey", secrets)
        # Managed-key sidecar is cleared (empty sets) so re-enabling starts clean.
        self.assertEqual(self._managed_keys().get("globalState"), [])
        self.assertEqual(self._managed_keys().get("secrets"), [])

    def test_idempotent_resync(self) -> None:
        self._run_cline_sync(self.platform_cfg)
        first = self._read_json(self.global_state_path)
        self._run_cline_sync(self.platform_cfg)
        second = self._read_json(self.global_state_path)
        self.assertEqual(first, second)

    def test_user_fields_preserved(self) -> None:
        # Pre-populate unrelated user keys that the syncer must never touch.
        self._write_json(
            self.global_state_path,
            {"telemetryEnabled": False, "welcomeShown": True},
        )
        self._write_json(
            self.secrets_path,
            {"anthropicApiKey": "sk-user-anthropic"},
        )
        self._run_cline_sync(self.platform_cfg)

        gs = self._read_json(self.global_state_path)
        secrets = self._read_json(self.secrets_path)
        # Managed keys merged.
        self.assertEqual(gs["openAiBaseUrl"], "https://api.example.com/v1")
        self.assertEqual(secrets["openAiApiKey"], "sk-test-cline")
        # Unrelated user keys survive.
        self.assertEqual(gs["telemetryEnabled"], False)
        self.assertEqual(gs["welcomeShown"], True)
        self.assertEqual(secrets["anthropicApiKey"], "sk-user-anthropic")

    def test_re_enable_restores(self) -> None:
        self._run_cline_sync(self.platform_cfg)
        self.assertIn("openAiApiKey", self._read_json(self.secrets_path))

        disabled = json.loads(json.dumps(self.platform_cfg))
        disabled["api"]["enabled"] = False
        self._run_cline_sync(disabled)
        self.assertNotIn("openAiApiKey", self._read_json(self.secrets_path))

        self._run_cline_sync(self.platform_cfg)
        self.assertEqual(
            self._read_json(self.secrets_path)["openAiApiKey"], "sk-test-cline"
        )
        self.assertEqual(
            self._read_json(self.global_state_path)["openAiBaseUrl"],
            "https://api.example.com/v1",
        )

    def test_unresolved_placeholder_skipped(self) -> None:
        # cline.key missing -> openAiApiKey must not be written as a literal.
        self._write_json(
            self.root / "env" / "secrets.json",
            {"cline": {"url": "https://api.example.com/v1"}},
        )
        self._run_cline_sync(self.platform_cfg)
        gs = self._read_json(self.global_state_path)
        secrets = self._read_json(self.secrets_path)
        # url resolves, key placeholder is skipped.
        self.assertEqual(gs["openAiBaseUrl"], "https://api.example.com/v1")
        self.assertNotIn("openAiApiKey", secrets)

    def test_skill_sync_skipped_when_skip_env_set(self) -> None:
        """SKIP_SKILL_SYNC=1 skips skill distribution but keeps state/secrets sync."""
        claude_skills = self.root / "home" / ".claude" / "skills"
        skill_dir = claude_skills / "test-skill"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("# Test Skill\n", encoding="utf-8")

        old = os.environ.get("SKIP_SKILL_SYNC")
        os.environ["SKIP_SKILL_SYNC"] = "1"
        try:
            self._run_cline_sync()
        finally:
            if old is None:
                os.environ.pop("SKIP_SKILL_SYNC", None)
            else:
                os.environ["SKIP_SKILL_SYNC"] = old

        dest = self.root / "home" / ".cline" / "skills" / "test-skill"
        self.assertFalse(dest.exists(), "Skill dir should not be synced when SKIP_SKILL_SYNC=1")
        # globalState and secrets still sync.
        self.assertEqual(
            self._read_json(self.global_state_path)["openAiBaseUrl"],
            "https://api.example.com/v1",
        )
        self.assertEqual(
            self._read_json(self.secrets_path)["openAiApiKey"], "sk-test-cline"
        )


if __name__ == "__main__":
    unittest.main()
