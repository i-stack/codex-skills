"""Sync engine for Qwen Code platform.

Mirrors ``~/.qwen/settings.json``: writes the managed top-level fields
``security`` / ``modelProviders`` / ``model`` and ``env`` into
``~/.qwen/settings.json``, and copies skills from ``~/.claude/skills/`` to
``~/.qwen/skills/``.

Model definitions (``~/.qwen/models.json``) are **not** managed by this syncer
— Qwen owns that file directly.

API fields are gated by ``api.enabled`` (missing ``api`` block defaults to
enabled). When ``api.enabled=false``:
- the managed ``env`` key is removed;
- the managed ``security`` / ``modelProviders`` / ``model`` fields are removed
  (marker-aware — ``modelProviders`` entries are merged/cleaned per ``id``,
  only entries carrying ``_managed_by`` are ever removed).

``$version`` is a Qwen-internal marker and is **never** written or overwritten
by the syncer — every write reads the existing file and merges only owned keys.
"""
import hashlib
import shutil
from typing import Any
from urllib.parse import urlparse

from core.common import (
    api_enabled as _api_enabled,
    is_managed_entry,
    merge_managed_entries,
    read_json_object,
    skill_sync_disabled,
    write_json,
)
from core.paths import (
    claude_skills_base,
    qwen_root_dir,
    qwen_settings_json_path,
    qwen_skills_base,
)

# Top-level qwen.json keys that map into ~/.qwen/settings.json.
SETTINGS_KEYS = ("security", "modelProviders", "model")

# Sentinel used in qwen.json to mark an envKey (or an env block key) that the
# syncer must derive from the provider baseUrl instead of writing verbatim.
# Qwen Code rejects DASHSCOPE_API_KEY for custom OpenAI-compatible providers
# (it is a reserved key routed to Qwen's internal DashScope logic and 401s),
# so custom providers need a baseUrl-derived key — see _derive_qwen_env_keys.
_AUTO_ENV_KEY = "__AUTO__"

# Legacy env var this syncer used to write for qwen. No longer managed; it is
# removed from settings.env on every sync to avoid a lingering 401 key.
_LEGACY_ENV_KEYS = ("DASHSCOPE_API_KEY",)


def _normalize_env_segment(value: str) -> str:
    """Mirror Qwen Code's env-key segment normalizer.

    Uppercase, keep ``[A-Z0-9]``, collapse every other run into a single
    ``_``, strip leading/trailing underscores. ``https://cloud.dataeyes.ai``
    -> ``HTTPS_CLOUD_DATAEYES_AI``.
    """
    out: list[str] = []
    prev_underscore = False
    for ch in value.upper():
        if ch.isascii() and ch.isalnum():
            out.append(ch)
            prev_underscore = False
        elif not prev_underscore:
            out.append("_")
            prev_underscore = True
    return "".join(out).strip("_")


def _derive_qwen_custom_env_key(protocol: str, base_url: str) -> str:
    """Reproduce Qwen Code's ``generateCustomEnvKey`` for a custom provider.

    Algorithm (packages/core/src/providers/presets/custom-provider.ts):

        canonicalBaseUrl = origin (scheme://host, path stripped)
        suffix = SHA256(f"{protocol}\\0{canonicalBaseUrl}").hexdigest()[:12].upper()
        envKey = f"QWEN_CUSTOM_API_KEY_{norm(protocol)}_{norm(canonicalBaseUrl)}_{suffix}"

    Stripping the path reproduces the key Qwen generated when the custom
    provider was first added (``..._HTTPS_CLOUD_DATAEYES_AI_C2DF01B23F5B``),
    verified against the user's installed settings.json.

    FRAGILE: this mirrors Qwen Code's internal, unversioned algorithm by
    reverse-engineering its source. There is no way to verify correctness
    other than diffing against Qwen Code's actual behavior — if Qwen changes
    ``generateCustomEnvKey`` upstream, this silently drifts and starts
    generating env keys Qwen Code's settings.json won't recognize. Re-check
    against ``packages/core/src/providers/presets/custom-provider.ts`` on any
    bug report involving custom-provider auth failing after a Qwen Code
    upgrade.
    """
    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else base_url.rstrip("/")
    canonical = origin.rstrip("/")
    suffix = hashlib.sha256(f"{protocol}\0{canonical}".encode("utf-8")).hexdigest()[:12].upper()
    return (
        f"QWEN_CUSTOM_API_KEY_"
        f"{_normalize_env_segment(protocol)}_"
        f"{_normalize_env_segment(canonical)}_"
        f"{suffix}"
    )


def _derive_qwen_env_keys(cfg: dict[str, Any]) -> None:
    """Replace ``__AUTO__`` envKey placeholders with Qwen-derived custom keys.

    Mutates ``cfg`` in place so the rest of the sync engine can treat the
    derived key as any other literal key. Token values declared under the
    ``__AUTO__`` env key are remapped onto each derived key name.
    """
    auth = cfg.get("security") if isinstance(cfg.get("security"), dict) else {}
    selected = (
        auth.get("auth", {}).get("selectedType")  # type: ignore[union-attr]
        if isinstance(auth.get("auth"), dict)  # type: ignore[union-attr]
        else None
    )
    protocol = selected or "openai"

    derived_keys: set[str] = set()

    providers = cfg.get("modelProviders")
    if isinstance(providers, dict):
        for entries in providers.values():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and entry.get("envKey") == _AUTO_ENV_KEY:
                    base_url = entry.get("baseUrl")
                    if isinstance(base_url, str):
                        key = _derive_qwen_custom_env_key(protocol, base_url)
                        entry["envKey"] = key
                        derived_keys.add(key)

    model = cfg.get("model")
    if isinstance(model, dict) and model.get("envKey") == _AUTO_ENV_KEY:
        base_url = model.get("baseUrl")
        if isinstance(base_url, str):
            key = _derive_qwen_custom_env_key(protocol, base_url)
            model["envKey"] = key
            derived_keys.add(key)

    env = cfg.get("env")
    if isinstance(env, dict) and derived_keys:
        auto_values = {k: v for k, v in env.items() if k == _AUTO_ENV_KEY}
        if auto_values:
            for k in auto_values:
                env.pop(k)
            auto_val = next(iter(auto_values.values()))
            for key in derived_keys:
                env[key] = auto_val


def _merge_model_entries(
    existing_entries: list[Any], config_entries: list[dict[str, Any]]
) -> list[Any]:
    """Merge config-managed model-provider entries into existing entries by id.

    Uses the shared marker-aware merge: config entries appear first in config
    order and carry ``_managed_by``; a same-id entry without the marker is
    user-owned and is never overwritten; managed entries no longer in config
    are pruned; user entries not in config are preserved; non-dict entries with
    no id are preserved at the very end.
    """
    return merge_managed_entries(existing_entries, config_entries, key_field="id")


def _merge_settings_block(existing: dict[str, Any], config_block: dict[str, Any]) -> dict[str, Any]:
    """Deep-merge the managed settings fields into existing settings.json.

    - ``modelProviders`` is merged per-provider-type by entry ``id`` (config
      wins; user entries preserved). Provider types that vanished from
      config still run an empty merge so marked entries are pruned.
    - ``security`` and ``model`` are owned by the config (replaced wholesale).
    - ``$version`` and any other existing top-level key are preserved.
    """
    result = dict(existing)

    for key, value in config_block.items():
        if key == "$version":
            # Qwen-internal marker — never managed by the syncer.
            continue
        if key == "modelProviders" and isinstance(value, dict):
            existing_mp = existing.get("modelProviders")
            if not isinstance(existing_mp, dict):
                existing_mp = {}
            new_mp = dict(existing_mp)
            for provider, entries in value.items():
                if not isinstance(entries, list):
                    continue
                existing_entries = existing_mp.get(provider)
                if not isinstance(existing_entries, list):
                    existing_entries = []
                new_mp[provider] = _merge_model_entries(existing_entries, entries)
            # Provider types that vanished from config still need an empty
            # merge so marked entries are pruned; unmarked user groups stay.
            for provider, existing_entries in existing_mp.items():
                if provider in value:
                    continue
                if not isinstance(existing_entries, list):
                    continue
                merged = _merge_model_entries(existing_entries, [])
                if merged:
                    new_mp[provider] = merged
                else:
                    new_mp.pop(provider, None)
            result["modelProviders"] = new_mp
        else:
            result[key] = value

    return result


def _clean_settings_block(existing: dict[str, Any], config_block: dict[str, Any]) -> bool:
    """Marker-aware removal of managed settings fields.

    Returns True when any managed field was actually removed. ``$version`` and
    unrelated user keys are never touched. Only ``modelProviders`` entries that
    carry the ``_managed_by`` marker are removed; user-added entries stay.
    """
    removed = False

    mp = existing.get("modelProviders")
    if isinstance(mp, dict):
        new_mp: dict[str, Any] = {}
        for provider, entries in mp.items():
            if not isinstance(entries, list):
                new_mp[provider] = entries
                continue
            # Only entries carrying our managed marker are removed; user-added
            # entries (no marker) are kept even if their id matches the config.
            kept = [e for e in entries if not is_managed_entry(e)]
            if kept:
                new_mp[provider] = kept
            else:
                removed = True  # provider fully removed
        if new_mp != mp:
            removed = True
        if new_mp:
            existing["modelProviders"] = new_mp
        else:
            existing.pop("modelProviders", None)

    for key in ("model", "security"):
        if key in config_block and key in existing:
            del existing[key]
            removed = True

    return removed


def _sync_env(env: dict[str, Any], api_enabled: bool) -> None:
    """Merge or clean managed env vars in ~/.qwen/settings.json.

    When ``api_enabled`` is true, the env keys declared in the platform config
    are merged into the settings ``env`` object; other keys (including
    ``$version``) are preserved.

    When ``api_enabled`` is false, only the env keys the syncer manages are
    removed (ownership-aware cleanup) — never unrelated user keys.
    """
    if not env:
        return
    path = qwen_settings_json_path()
    existing = read_json_object(path)
    existing_env = existing.get("env")
    if not isinstance(existing_env, dict):
        existing_env = {}

    if api_enabled:
        merged_env = dict(existing_env)
        merged_env.update(env)
        # Drop the legacy reserved key only when this config no longer manages
        # it — it 401s for custom providers. Kept if the user's config still
        # declares it explicitly.
        for legacy in _LEGACY_ENV_KEYS:
            if legacy not in env and legacy in merged_env:
                del merged_env[legacy]
        existing["env"] = merged_env
        write_json(path, existing)
        keys = ", ".join(env.keys())
        print(f"[qwen] Synced env keys to {path}: {keys}.")
        return

    # API sync disabled: remove only the env keys we manage.
    removed = False
    new_env = dict(existing_env)
    for key in env:
        if key in new_env:
            del new_env[key]
            removed = True
    for legacy in _LEGACY_ENV_KEYS:
        if legacy not in env and legacy in new_env:
            del new_env[legacy]
            removed = True
    if removed:
        if new_env:
            existing["env"] = new_env
        else:
            existing.pop("env", None)
        write_json(path, existing)
        print(
            f"[qwen] API sync disabled — removed managed env keys from {path}: "
            f"{', '.join(env.keys())}."
        )
    else:
        print("[qwen] API sync disabled — no managed env keys to clean.")


def _sync_settings_block(cfg: dict[str, Any], api_enabled: bool) -> None:
    """Merge or clean the managed settings fields in ~/.qwen/settings.json.

    The fields (``security`` / ``modelProviders`` / ``model``) are owned by the
    config and gated by ``api.enabled``. ``$version`` is always preserved.

    When ``api_enabled`` is false, the managed fields are removed (ownership-
    aware) so the provider config no longer drives Qwen; re-enabling restores
    them.
    """
    settings_block = {k: cfg[k] for k in SETTINGS_KEYS if k in cfg}
    if not settings_block:
        # No managed settings fields: nothing to merge or clean.
        return

    path = qwen_settings_json_path()
    existing = read_json_object(path)

    if api_enabled:
        merged = _merge_settings_block(existing, settings_block)
        write_json(path, merged)
        print(f"[qwen] Synced settings to {path} (security/modelProviders/model).")
        return

    # API sync disabled: remove only the managed settings fields.
    if _clean_settings_block(existing, settings_block):
        write_json(path, existing)
        print(f"[qwen] API sync disabled — removed managed settings fields from {path}.")
    else:
        print("[qwen] API sync disabled — no managed settings fields to clean.")


def _sync_skills() -> None:
    if skill_sync_disabled():
        print("[qwen] SKIP_SKILL_SYNC=1 — skipping skill sync.")
        return
    claude_skills_dir = claude_skills_base()
    qwen_skills_dir = qwen_skills_base()
    if not claude_skills_dir.exists():
        print(f"[qwen] Claude skills directory not found: {claude_skills_dir} — skipping skill sync.")
        return

    qwen_skills_dir.mkdir(parents=True, exist_ok=True)
    synced: list[str] = []

    for skill_dir in sorted(claude_skills_dir.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue

        dest = qwen_skills_dir / skill_dir.name
        tmp = qwen_skills_dir / f".{skill_dir.name}.tmp-sync"
        backup = qwen_skills_dir / f".{skill_dir.name}.backup-sync"

        if tmp.exists():
            shutil.rmtree(tmp)
        if backup.exists():
            shutil.rmtree(backup)

        shutil.copytree(skill_dir, tmp)

        if dest.exists():
            dest.rename(backup)
        try:
            tmp.rename(dest)
        except OSError:
            if backup.exists() and not dest.exists():
                backup.rename(dest)
            raise
        finally:
            if tmp.exists():
                shutil.rmtree(tmp)
            if backup.exists():
                shutil.rmtree(backup)
        synced.append(skill_dir.name)

    print(f"[qwen] Synced {len(synced)} skills to {qwen_skills_dir}: {', '.join(synced) or '(none)'}.")


def sync(mcp_servers: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Sync env vars, settings fields, and skills to Qwen Code.

    Qwen Code does not use MCP servers in the same way as other
    platforms — the mcp_servers parameter is accepted but ignored. Model
    definitions (``~/.qwen/models.json``) are owned by Qwen itself and are not
    synced by this engine.
    """
    root = qwen_root_dir()
    if not root.exists():
        print(f"[qwen] Qwen root not found: {root} — skipping (tool not installed).")
        return

    api_enabled = _api_enabled(cfg)
    _derive_qwen_env_keys(cfg)
    _sync_env(cfg.get("env", {}), api_enabled)
    _sync_settings_block(cfg, api_enabled)
    _sync_skills()
