import re
import shutil
from pathlib import Path
from typing import Any

from core.common import (
    api_enabled as _api_enabled,
    merge_managed_dict,
    read_json_object,
    skill_sync_disabled,
    write_json,
)
from core.paths import (
    claude_skills_base,
    cline_data_dir,
    cline_root_dir,
    cline_global_state_path,
    cline_mcp_candidate_paths,
    cline_secrets_path,
    cline_skills_base,
)

# Matches a value that is still a single unresolved ${VAR} placeholder.
_UNRESOLVED_PLACEHOLDER_RE = re.compile(r"\A\$\{[^}]+\}\Z")

# Sidecar that records which keys this tool currently manages, so a key
# removed from the platform config can be pruned from the user's files on the
# next sync. Without this record the managed set would have to be hardcoded
# (and kept in sync by hand every time the config gains or drops a key). Lives
# next to globalState.json / secrets.json; Cline ignores dot-files. Computed at
# runtime (not module import) so it respects a patched HOME and any install_root
# override set before path resolution.
def _managed_keys_sidecar() -> Path:
    return cline_data_dir() / ".managed_keys.json"


def _load_managed_keys() -> dict[str, set[str]]:
    """Return the set of keys this tool currently manages, per section.

    The sidecar is the single source of truth and is updated on every sync,
    so the managed set is derived from actual sync history rather than
    hardcoded. On a fresh install (no sidecar yet) there is nothing to prune,
    and the first sync writes the current config's keys into the sidecar.
    """
    data = read_json_object(_managed_keys_sidecar())
    if data:
        return {
            "globalState": set(data.get("globalState", [])),
            "secrets": set(data.get("secrets", [])),
        }
    return {"globalState": set(), "secrets": set()}


def _save_managed_keys(global_state_keys: set[str], secret_keys: set[str]) -> None:
    """Persist the currently-managed key sets to the sidecar."""
    write_json(_managed_keys_sidecar(), {
        "globalState": sorted(global_state_keys),
        "secrets": sorted(secret_keys),
    })


def _sync_mcp(servers: dict[str, Any]) -> None:
    targets = [p for p in cline_mcp_candidate_paths() if p.parent.exists()]
    if not targets:
        print("[cline] No Cline MCP settings directory found (checked Cursor, Code, Code - Insiders).")
        return
    for path in targets:
        data = read_json_object(path)
        existing_mcp = data.get("mcpServers")
        data["mcpServers"] = merge_managed_dict(
            existing_mcp if isinstance(existing_mcp, dict) else {}, servers
        )
        write_json(path, data)
        print(f"Synced MCP servers in {path}.")


def _sync_skills() -> None:
    if skill_sync_disabled():
        print("[cline] SKIP_SKILL_SYNC=1 — skipping skill sync.")
        return
    claude_skills_dir = claude_skills_base()
    cline_skills_dir = cline_skills_base()
    if not claude_skills_dir.exists():
        print(f"[cline] Claude skills directory not found: {claude_skills_dir} — skipping skill sync.")
        return

    cline_skills_dir.mkdir(parents=True, exist_ok=True)
    synced: list[str] = []

    for skill_dir in sorted(claude_skills_dir.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue

        dest = cline_skills_dir / skill_dir.name
        tmp = cline_skills_dir / f".{skill_dir.name}.tmp-sync"
        backup = cline_skills_dir / f".{skill_dir.name}.backup-sync"

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

    print(f"Synced {len(synced)} skills to {cline_skills_dir}: {', '.join(synced) or '(none)'}.")


def _sync_global_state(managed: dict[str, Any], api_enabled: bool = True) -> None:
    """Merge the managed keys into ~/.cline/data/globalState.json, gated by api.enabled.

    Preserves every other key in the file (welcome state, auto-approval
    settings, workspace roots, etc.). Unresolved ${VAR} placeholders are
    skipped so a missing cline.url never writes literal "${cline.url}" into
    the user's global state.

    When ``api_enabled`` is false, API sync is disabled: no managed keys are
    merged and every key previously managed by the syncer (tracked in the
    sidecar) is removed, then dropped from the sidecar so re-enabling starts
    from a clean slate.

    Any key we previously managed (tracked in the sidecar) that is no longer
    present in the config is deleted from the file, so removing a key from the
    platform config (e.g. planModeApiProvider) also removes its stale value
    instead of leaving it behind on the next sync.
    """
    path = cline_global_state_path()
    record = _load_managed_keys()
    if not api_enabled:
        # Disable: treat as "no config-managed keys" so the sidecar-driven
        # prune below removes every key we currently own, then we clear the
        # managed set so a future re-enable re-merges cleanly.
        managed = {}
    if not managed and not record["globalState"]:
        return
    existing = read_json_object(path)
    merged = dict(existing)
    applied = 0
    if api_enabled:
        for key, value in managed.items():
            if isinstance(value, str) and _UNRESOLVED_PLACEHOLDER_RE.match(value):
                print(f"[cline] Skipping globalState.{key}: unresolved placeholder {value} — set cline.url in secrets.json.")
                continue
            merged[key] = value
            applied += 1
    removed = 0
    for key in record["globalState"]:
        if key not in managed and key in merged:
            del merged[key]
            removed += 1
    if applied or removed:
        write_json(path, merged)
        record["globalState"] = set(managed.keys())
        _save_managed_keys(record["globalState"], record["secrets"])
        parts = []
        if applied:
            parts.append(f"set {applied} global state key(s)")
        if removed:
            parts.append(f"removed {removed} stale global state key(s)")
        print(f"Synced global state to {path}: {'; '.join(parts)}.")
    else:
        print("[cline] No global state changes to sync — skipping.")


def _sync_secrets(secrets: dict[str, Any], api_enabled: bool = True) -> None:
    """Merge API secrets into ~/.cline/data/secrets.json, gated by api.enabled.

    Cline stores each provider's key under the <provider>ApiKey key
    (e.g. geminiApiKey). Existing keys for other providers are preserved.
    Unresolved ${VAR} placeholders are skipped to avoid writing garbage.

    When ``api_enabled`` is false, API sync is disabled: no secret keys are
    merged and every key previously managed by the syncer (tracked in the
    sidecar) is removed, then dropped from the sidecar so re-enabling starts
    clean.

    Any key we previously managed (tracked in the sidecar) that is no longer
    present in the config is deleted from the file, so removing a provider
    (e.g. geminiApiKey) also removes its stale secret on the next sync.
    """
    path = cline_secrets_path()
    record = _load_managed_keys()
    if not api_enabled:
        # Disable: treat as "no config-managed keys" so the sidecar-driven
        # prune below removes every key we currently own, then we clear the
        # managed set so a future re-enable re-merges cleanly.
        secrets = {}
    if not secrets and not record["secrets"]:
        return
    existing = read_json_object(path)
    merged = dict(existing)
    applied = 0
    if api_enabled:
        for key, value in secrets.items():
            if isinstance(value, str) and _UNRESOLVED_PLACEHOLDER_RE.match(value):
                print(f"[cline] Skipping secret '{key}': unresolved placeholder {value} — set cline.key in secrets.json.")
                continue
            merged[key] = value
            applied += 1
    removed = 0
    for key in record["secrets"]:
        if key not in secrets and key in merged:
            del merged[key]
            removed += 1
    if applied or removed:
        write_json(path, merged)
        record["secrets"] = set(secrets.keys())
        _save_managed_keys(record["globalState"], record["secrets"])
        parts = []
        if applied:
            parts.append(f"set {applied} secret key(s)")
        if removed:
            parts.append(f"removed {removed} stale secret key(s)")
        print(f"Synced secrets to {path}: {'; '.join(parts)}.")
    else:
        print("[cline] No secret changes to sync — skipping.")


def sync(mcp_servers: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Sync MCP servers, skills, global state, and secrets to Cline (VSCode extension).

    MCP servers and skills are always synced when Cline is installed. Managed
    globalState and secrets are API sync fields gated by ``api.enabled``
    (missing defaults to enabled, preserving the historical always-sync
    behavior). When ``api.enabled=false`` the syncer-owned globalState and
    secret keys are cleaned instead of merged. The recall preamble (declared
    under ``preamble``) is independent of API sync and handled separately.
    """
    root = cline_root_dir()
    if not root.exists():
        print(f"[cline] Cline root not found: {root} — skipping (tool not installed).")
        return

    api_enabled = _api_enabled(cfg)
    _sync_mcp(mcp_servers)
    _sync_skills()
    _sync_global_state(cfg.get("globalState", {}), api_enabled)
    _sync_secrets(cfg.get("secrets", {}), api_enabled)
