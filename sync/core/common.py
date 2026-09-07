import json
import os
import re
import shlex
from pathlib import Path
from typing import Any, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_DIR = REPO_ROOT / "env" / "mcp"
PLATFORMS_DIR = REPO_ROOT / "env" / "platforms"
SECRETS_PATH = REPO_ROOT / "env" / "secrets.json"

_SECRET_REF_RE = re.compile(r'\$\{([^}]+)\}')
_ENV_VAR_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


# ── Secrets resolution ───────────────────────────────────────────────────────

def _flatten_secrets(data: dict[str, Any], prefix: str = "") -> dict[str, str]:
    """Recursively flatten nested dict into {prefix.key: str_value} entries.

    Skips _comment keys at any level.
    Example: {"codex": {"url": "https://...", "key": "sk-..."}}
          -> {"codex.url": "https://...", "codex.key": "sk-..."}
    """
    flat: dict[str, str] = {}
    for k, v in data.items():
        if k.startswith("_"):
            continue
        full_key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            flat.update(_flatten_secrets(v, full_key))
        elif isinstance(v, (str, int, float)):
            flat[full_key] = str(v)
        elif isinstance(v, list):
            flat[full_key] = json.dumps(v, ensure_ascii=False)
    return flat


def load_secrets() -> dict[str, str]:
    """Load secrets from env/secrets.json.

    Returns a flat dot-notation dict, e.g. {"github.token": "...", "codex.url": "...", "codex.key": "..."}.
    Supports per-platform nested format: {"codex": {"url": "...", "key": "..."}}

    If secrets.json doesn't exist, returns {} and prints a warning.
    """
    if not SECRETS_PATH.is_file():
        print("[sync] ⚠ env/secrets.json not found — copy env/secrets.json.example and fill in your keys.")
        return {}
    try:
        data = json.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[sync] Failed to load secrets: {exc}")
        return {}
    if not isinstance(data, dict):
        return {}
    return _flatten_secrets(data)


def resolve_secrets(data: Any, secrets: dict[str, str]) -> Any:
    """Recursively resolve ${VAR} references in strings using secrets dict.

    Walks dicts, lists, and strings. Non-string values are returned as-is.
    Each "${VAR}" occurrence in any string is replaced by secrets[VAR].
    If VAR is not found in secrets, the placeholder is left unchanged.
    """
    if isinstance(data, str):
        def _replacer(m: re.Match[str]) -> str:
            key = m.group(1)
            if key in secrets:
                return secrets[key]
            return m.group(0)
        return _SECRET_REF_RE.sub(_replacer, data)
    if isinstance(data, dict):
        return {k: resolve_secrets(v, secrets) for k, v in data.items()}
    if isinstance(data, list):
        return [resolve_secrets(v, secrets) for v in data]
    return data


def find_unresolved_placeholders(data: Any) -> list[str]:
    """Recursively scan data for unresolved ${VAR} placeholders.

    Returns a list of placeholder strings (e.g. ["${github.token}"]) found
    in the data. Empty list means all placeholders were resolved.
    """
    found: list[str] = []

    def _scan(value: Any) -> None:
        if isinstance(value, str):
            found.extend(m.group(0) for m in _SECRET_REF_RE.finditer(value))
        elif isinstance(value, dict):
            for v in value.values():
                _scan(v)
        elif isinstance(value, list):
            for v in value:
                _scan(v)

    _scan(data)
    return found


# ── Configuration loading ────────────────────────────────────────────────────

def load_all_mcp() -> dict[str, Any]:
    """Scan env/mcp/*.json, resolve secrets, and return {server_name: server_config}.

    Each file should contain:
      {"name": "server-name", "type": "stdio|sse", ..., "platforms": [...]}

    Secrets (${VAR}) are resolved from env/secrets.json before returning.
    Returns {} if env/mcp/ is missing or empty (graceful degradation).
    Warns about any unresolved placeholders after resolution.
    Disabled servers (explicit "enabled": false) are skipped *before* secret
    resolution, so default-disabled optional servers never emit missing-secret
    warnings for secrets the user doesn't need to provide.
    """
    if not MCP_DIR.is_dir():
        print(f"[sync] {MCP_DIR} directory not found — no MCP servers loaded.")
        return {}

    secrets = load_secrets()
    result: dict[str, Any] = {}
    for f in sorted(MCP_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[sync] Skipping {f.name}: {exc}")
            continue
        if not isinstance(data, dict):
            print(f"[sync] Skipping {f.name}: not a JSON object.")
            continue
        # Per-server sync toggle first: explicit "enabled": false skips the
        # server before any secret resolution, so it is neither resolved nor
        # synced (the marker merge prunes its previously-synced managed entries).
        # Missing defaults to enabled.
        if not mcp_enabled(data):
            print(f"[sync] MCP server '{f.stem}' is disabled (enabled=false) — skipped.")
            continue
        # Resolve secrets before stripping metadata
        data = resolve_secrets(data, secrets)
        # Warn about unresolved placeholders
        unresolved = find_unresolved_placeholders(data)
        if unresolved:
            print(f"[sync] ⚠ {f.name}: unresolved placeholders: {', '.join(unresolved)} — add them to env/secrets.json")
        name = data.get("name", f.stem)
        clean = {k: v for k, v in data.items() if k not in ("name", "_comment", "enabled")}
        result[name] = clean
    return result


def load_platform_config(platform: str) -> dict[str, Any]:
    """Load platform-specific config from env/platforms/<platform>.json.

    Secrets (${VAR}) are resolved from env/secrets.json before returning.
    Returns {} if the file doesn't exist.
    Warns about any unresolved placeholders after resolution.
    """
    path = PLATFORMS_DIR / f"{platform}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[sync] Failed to load {path}: {exc}")
        return {}
    if not isinstance(data, dict):
        print(f"[sync] {path} must contain a JSON object — skipped.")
        return {}
    secrets = load_secrets()
    data = resolve_secrets(data, secrets)
    # Warn about unresolved placeholders
    unresolved = find_unresolved_placeholders(data)
    if unresolved:
        print(f"[sync] ⚠ {path.name}: unresolved placeholders: {', '.join(unresolved)} — add them to env/secrets.json")
    return {k: v for k, v in data.items() if k not in ("_comment",)}


def env_for_platform(platform: str) -> dict[str, str]:
    """Extract env vars from a platform config's top-level 'env' key.

    The 'env' key holds {VAR_NAME: value} pairs that the sync engine writes
    to ~/.zshrc managed blocks or platform settings.json as appropriate.
    """
    cfg = load_platform_config(platform)
    env = cfg.get("env", {})
    if env is None:
        env = {}
    if not isinstance(env, dict):
        raise ValueError(f"platforms.{platform}.env must be an object.")
    return {k: v for k, v in env.items() if isinstance(k, str) and isinstance(v, str) and v != ""}


def sync_env_to_zshrc(platform: str, env: dict[str, str]) -> None:
    """Write platform env vars into a managed block in ~/.zshrc.

    Convention:
      - env/platforms/<platform>.json declares an "env" object with VAR=value pairs.
      - The platform's sync() calls this function (optionally gated by
        an "export_env_to_zshrc" flag if the platform supports alternative
        env delivery methods like settings.json).

    The managed block format is:
      # BEGIN <PLATFORM> ENV SYNC (from env/platforms/<platform>.json)
      export VAR='value'
      # END <PLATFORM> ENV SYNC

    Existing blocks for the same platform are replaced in-place; blocks for
    other platforms are left untouched.

    The user still needs to `source ~/.zshrc` in their open terminal.
    """
    if not env:
        return

    lines: list[str] = []
    for k, v in env.items():
        if not _ENV_VAR_NAME_RE.fullmatch(k):
            raise ValueError(f"Invalid environment variable name for {platform}: {k!r}")
        lines.append(f"export {k}={shlex.quote(str(v))}")
    if not lines:
        return

    begin = f"# BEGIN {platform.upper()} ENV SYNC (from env/platforms/{platform}.json)"
    end = f"# END {platform.upper()} ENV SYNC"
    block = begin + "\n" + "\n".join(lines) + "\n" + end + "\n"

    block_re = re.compile(
        r"# BEGIN " + platform.upper() + r" ENV SYNC(?: \(from [^)]+\))?"
        + r".*?"
        + re.escape(end)
        + r"\n?",
        re.DOTALL,
    )

    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        text = zshrc.read_text(encoding="utf-8")
        if block_re.search(text):
            new_text = block_re.sub(block, text)
        else:
            new_text = text.rstrip() + "\n\n" + block
    else:
        new_text = block

    zshrc.write_text(new_text, encoding="utf-8")
    print(f"[{platform}] Updated env vars in {zshrc}.")
    print(f"[{platform}] Run 'source {zshrc}' in your terminal to apply changes.")


def clear_env_block(platform: str) -> bool:
    """Remove the platform's managed env block from ~/.zshrc, if present.

    Used when a platform's API sync is disabled so previously-synced API env
    vars are cleaned rather than left lingering. Returns True if a block was
    removed, False if there was nothing to remove.
    """
    zshrc = Path.home() / ".zshrc"
    if not zshrc.exists():
        return False
    text = zshrc.read_text(encoding="utf-8")
    block_re = re.compile(
        r"# BEGIN " + platform.upper() + r" ENV SYNC(?: \(from [^)]+\))?"
        + r".*?"
        + re.escape(f"# END {platform.upper()} ENV SYNC")
        + r"\n?",
        re.DOTALL,
    )
    new_text = block_re.sub("", text)
    if new_text == text:
        return False
    zshrc.write_text(new_text, encoding="utf-8")
    print(f"[{platform}] Removed managed env block from {zshrc} (API sync disabled).")
    return True


def filter_mcp_for_platform(mcp_all: dict[str, Any], platform: str) -> dict[str, Any]:
    """Filter MCP servers to those enabled for the given platform.

    A server is included if:
      - It has no 'platforms' key (included everywhere), OR
      - Its 'platforms' list includes the given platform name.

    The 'platforms' key is stripped from the output.
    The 'type' key is also stripped (rendering concern, not output concern).
    """
    result: dict[str, Any] = {}
    for name, cfg in mcp_all.items():
        if not isinstance(cfg, dict):
            result[name] = cfg
            continue
        allowed = cfg.get("platforms")
        if allowed is not None:
            if not isinstance(allowed, list) or platform not in allowed:
                continue
        result[name] = {k: v for k, v in cfg.items() if k not in ("platforms", "type")}
    return result


def discover_platforms() -> list[str]:
    """Return platform names that have a config file in env/platforms/.

    Used by the orchestrator to auto-discover sync targets.
    """
    if not PLATFORMS_DIR.is_dir():
        return []
    return sorted(
        f.stem for f in PLATFORMS_DIR.glob("*.json")
    )


# ── Marker-based entry management (shared by all platforms) ──────────────────

# Constant written into every entry this tool syncs (e.g. MCP servers, model
# entries). Self-describing, so the target tool and the user can tell which
# entries the sync engine owns without a sidecar file.
MANAGED_BY = "ai-coding-kit"


def is_managed_entry(entry: Any) -> bool:
    """True when ``entry`` is a dict carrying our ``_managed_by`` marker."""
    return isinstance(entry, dict) and entry.get("_managed_by") == MANAGED_BY


def _matches_config_exactly(entry: dict[str, Any], cfg: dict[str, Any], key_field: str) -> bool:
    """True only when ``entry`` looks like an exact legacy copy of ``cfg``.

    A legacy sync wrote the resolved config entry verbatim (no marker), so an
    exact match needs:
    - the same key set beyond ``key_field``/``_managed_by`` (extra or missing
      keys mean the entry was touched by the user or a UI rewrite),
    - equal values for every key,
    - at least one non-``None`` comparable field beyond ``key_field`` (an entry
      whose only field beyond ``key_field`` is ``None`` carries no evidence).

    Lacking credentials alone does NOT prevent a claim: an entry without
    ``url``/``apiKey`` on either side but with other matching fields (same key
    set, same values) is still an exact copy and is claimed.
    """
    entry_keys = {k for k in entry if k not in (key_field, "_managed_by")}
    cfg_keys = {k for k in cfg if k not in (key_field, "_managed_by")}
    if not cfg_keys or not any(cfg.get(k) is not None for k in cfg_keys):
        return False
    if entry_keys != cfg_keys:
        return False
    return all(entry.get(k) == cfg.get(k) for k in cfg_keys)


def claim_legacy_entries(
    existing_entries: list[Any], config_entries: list[dict[str, Any]], key_field: str = "id"
) -> list[Any]:
    """Tag legacy (pre-marker) synced entries with the managed marker.

    Older sync versions wrote entries WITHOUT the marker. An unmarked entry that
    is an *exact* copy of the resolved config (same key set, same values) is a
    legacy sync output — claim it so it updates and prunes normally from now on.

    Claiming is deliberately conservative: the identity signal is the whole
    entry. A claim means the config will overwrite the entry on this same sync,
    so a false positive silently destroys a user-owned entry.
    """
    if not config_entries:
        return existing_entries
    config_by_key: dict[str, dict[str, Any]] = {
        m[key_field]: m for m in config_entries if isinstance(m, dict) and key_field in m
    }

    result: list[Any] = []
    for entry in existing_entries:
        if not isinstance(entry, dict) or key_field not in entry or is_managed_entry(entry):
            result.append(entry)
            continue
        cfg = config_by_key.get(entry[key_field])
        if cfg is not None and _matches_config_exactly(entry, cfg, key_field):
            claimed = dict(entry)
            claimed["_managed_by"] = MANAGED_BY
            result.append(claimed)
        else:
            result.append(entry)
    return result


def merge_managed_entries(
    existing_entries: list[Any], config_entries: list[dict[str, Any]], key_field: str = "id"
) -> list[Any]:
    """Marker-aware merge of list-of-dict entries keyed by ``key_field``.

    - Config entries are written first (config order), each tagged with the
      managed marker so future syncs can recognize them.
    - A same-key entry in the target WITHOUT the marker is user-owned: it is
      preserved verbatim and the config entry is skipped (never overwritten).
    - Managed entries that are no longer in config are dropped (deletion).
    - User-owned entries are preserved as-is.
    - Non-dict entries with no key are preserved at the very end.
    - An empty ``config_entries`` removes every managed entry while keeping
      user-owned entries (cleanup without config).
    """
    config_by_key: dict[str, dict[str, Any]] = {
        m[key_field]: m for m in config_entries if isinstance(m, dict) and key_field in m
    }

    # Claim legacy (pre-marker) synced entries first so they are managed again.
    existing_entries = claim_legacy_entries(existing_entries, config_entries, key_field)

    existing_by_key: dict[str, Any] = {}
    for m in existing_entries:
        if isinstance(m, dict) and key_field in m:
            existing_by_key[m[key_field]] = m
    user_owned_keys: set[str] = {
        k for k, entry in existing_by_key.items() if not is_managed_entry(entry)
    }

    result: list[Any] = []

    # Config-managed entries first (in config order), each tagged with the marker.
    # Skip config entries whose key is already owned by a user entry.
    for m in config_entries:
        if not isinstance(m, dict) or key_field not in m:
            continue
        key = m[key_field]
        if key in user_owned_keys:
            result.append(existing_by_key[key])
            continue
        tagged = dict(m)
        tagged["_managed_by"] = MANAGED_BY
        result.append(tagged)

    # User-added entries from existing (not managed by us), preserving order.
    for m in existing_entries:
        if not isinstance(m, dict) or key_field not in m:
            continue
        if is_managed_entry(m):
            # Ours but no longer in config -> drop (deletion).
            continue
        key = m[key_field]
        if key not in config_by_key:
            result.append(m)

    # Trailing non-standard entries.
    for m in existing_entries:
        if not isinstance(m, dict) or key_field not in m:
            result.append(m)

    return result


# Temporary identity used only while a name-keyed dict is converted to a list
# for :func:`merge_managed_entries`. Must not collide with real payload fields
# such as MCP ``name`` (display name) or ``id``.
_DICT_MAP_KEY = "_ack_map_key"


def _dict_values_to_entries(mapping: dict[str, Any]) -> list[dict[str, Any]]:
    """Lift dict values into list entries keyed by the map key, not a payload field."""
    return [
        {**cfg, _DICT_MAP_KEY: name}
        for name, cfg in mapping.items()
        if isinstance(cfg, dict)
    ]


def merge_managed_dict(
    existing: dict[str, Any], config: dict[str, Any], key_field: str = "name"
) -> dict[str, Any]:
    """Marker-aware merge for name-keyed dict containers (e.g. ``mcpServers``).

    Identity is the dict key. Dict values are lifted into list entries with a
    reserved map-key field (not ``key_field``), merged via
    :func:`merge_managed_entries`, then converted back. Payload fields such as
    ``name`` survive the round-trip. ``key_field`` is kept for call compatibility
    and is not used as the temporary identity.

    Non-dict existing values cannot carry a marker; they are user-owned and
    preserved verbatim. Non-dict config values are skipped (they cannot be
    tagged). A same-key opaque existing value wins over a config dict.

    An empty or non-dict ``config`` is treated as ``{}`` and still runs the
    merge, so marked entries are pruned — same contract as the list engine.
    """
    del key_field  # identity is the dict key; do not inject a payload field
    if not isinstance(existing, dict):
        existing = {}
    if not isinstance(config, dict):
        config = {}

    merged = merge_managed_entries(
        _dict_values_to_entries(existing),
        _dict_values_to_entries(config),
        _DICT_MAP_KEY,
    )
    result: dict[str, Any] = {}
    for entry in merged:
        name = entry[_DICT_MAP_KEY]
        existing_val = existing.get(name)
        if name in existing and not isinstance(existing_val, dict):
            result[name] = existing_val
            continue
        result[name] = {k: v for k, v in entry.items() if k != _DICT_MAP_KEY}
    for name, cfg in existing.items():
        if name not in result and not isinstance(cfg, dict):
            result[name] = cfg
    return result


# ── JSON I/O utilities ───────────────────────────────────────────────────────

def sync_json_mcp(path: Path, servers: dict[str, Any]) -> None:
    # Read existing content BEFORE unlinking. When `path` is a symlink,
    # read_json_object() follows it and returns the target's full content, so
    # non-mcpServers top-level keys are preserved. Unlinking first would make
    # read_json_object() return {} and silently drop every other key.
    existing = read_json_object(path)
    if path.is_symlink():
        # Replace the symlink with a regular file so we don't write through it
        # into the (possibly shared) link target.
        path.unlink()
    existing_mcp = existing.get("mcpServers")
    if not isinstance(existing_mcp, dict):
        existing_mcp = {}
    existing["mcpServers"] = merge_managed_dict(existing_mcp, servers)
    write_json(path, existing)
    print(f"Synced MCP servers in {path}.")


def read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object.")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")


def prune_managed_keys_via_sidecar(
    settings_path: Path,
    managed_keys: set[str],
    sidecar_path: Path,
) -> None:
    """Prune previously-managed settings keys that are no longer managed.

    Platforms that push a set of "team-shared" top-level keys into a tool's
    settings file keep a sidecar (``sidecar_path``) recording exactly which keys
    they manage. After the renderer has merged the current ``managed`` dict into
    ``settings_path`` and written it, call this to:

      * remove any top-level key that was previously managed (recorded in the
        sidecar) but is absent from ``managed_keys`` — e.g. a key dropped from
        the platform config between syncs;
      * persist the new ``managed_keys`` set to the sidecar so the next sync can
        still prune keys removed in the meantime.

    The sidecar only ever tracks managed (team-shared) keys — never universal
    payloads such as ``mcpServers`` or per-developer ``env``/``hooks`` — so those
    are never removed by this routine. The sidecar is a dot-file ignored by the
    target tool.
    """
    record = set(read_json_object(sidecar_path).get("managedKeys", []))
    if not record and not managed_keys:
        return

    existing = read_json_object(settings_path)
    stale = record - managed_keys
    if stale:
        for key in stale:
            existing.pop(key, None)
        write_json(settings_path, existing)

    if record != managed_keys:
        write_json(sidecar_path, {"managedKeys": sorted(managed_keys)})


def merge_object(existing: Any, updates: dict[str, Any]) -> dict[str, Any]:
    base = existing if isinstance(existing, dict) else {}
    return {**base, **updates}


def api_enabled(cfg: dict[str, Any]) -> bool:
    """Third-party API sync toggle, shared by every platform's sync engine.

    A missing ``api`` block or missing ``api.enabled`` defaults to enabled,
    preserving the historical always-sync behavior. Only an explicit
    ``false`` disables synced API fields.
    """
    api = cfg.get("api")
    if not isinstance(api, dict):
        return True
    return api.get("enabled", True) is True


def mcp_enabled(cfg: dict[str, Any]) -> bool:
    """Per-MCP-server sync toggle, evaluated by load_all_mcp().

    A missing ``enabled`` key defaults to enabled, preserving the historical
    always-sync behavior for every MCP in env/mcp/. Only an explicit
    ``false`` excludes the server from sync. Because disabled servers are
    absent from the synced set, the marker-aware merge prunes their
    previously-synced managed entries from every target tool config.
    """
    if not isinstance(cfg, dict):
        return True
    return cfg.get("enabled", True) is True


def skill_sync_disabled() -> bool:
    """Return True when the SKIP_SKILL_SYNC env var is set to ``1``.

    Skill distribution copies every skill dir into each platform's skills
    folder and then cleans its ``.tmp-sync`` / ``.backup-sync`` staging dirs via
    ``shutil.rmtree``. In environments with a bulk-delete guard (e.g. CodeBuddy's
    safe-delete threshold), those recursive deletes are intercepted and abort the
    sync, so callers may opt out of skill sync entirely by setting
    ``SKIP_SKILL_SYNC=1``. MCP / model / settings sync is unaffected.
    """
    return os.environ.get("SKIP_SKILL_SYNC") == "1"


# ── Path helpers (imported from centralized paths module) ────────────────────

from .paths import (  # noqa: F401
    codex_config_path,
    codex_root_dir,
    xcode_codex_dir,
    xcode_coding_assistant_exists,
    xcode_gemini_dir,
    gemini_settings_path,
)


# ── TOML generation utilities ────────────────────────────────────────────────

def toml_quote(s: str) -> str:
    """Escape and quote a string for TOML basic string format.

    Handles: backslash, double-quote, newline, tab, carriage-return,
    backspace, form-feed.
    """
    s = s.replace("\\", "\\\\")
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    s = s.replace("\t", "\\t")
    s = s.replace("\r", "\\r")
    s = s.replace("\b", "\\b")
    s = s.replace("\f", "\\f")
    return '"' + s + '"'


def toml_bare_key_segment(s: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", s))


def toml_header_key_segment(s: str) -> str:
    """Format a key for use in a TOML header like [a.b.c].

    If the key contains dots, each segment is individually quoted if needed.
    E.g. 'sandbox_write.nested' -> 'sandbox_write.nested' (both bare)
         'my.key/with.dots' -> '"my.key/with.dots"' (quoted as one segment)
    """
    if "." in s:
        # Each dot-separated segment must be individually checked
        parts = s.split(".")
        return ".".join(
            p if toml_bare_key_segment(p) else toml_quote(p)
            for p in parts
        )
    return s if toml_bare_key_segment(s) else toml_quote(s)


def toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return toml_quote(str(value))


def toml_array(items: list[Any]) -> str:
    return "[" + ", ".join(toml_quote(str(x)) for x in items) + "]"


def toml_inline_table(values: dict[str, Any]) -> str:
    return "{ " + ", ".join(f"{k} = {toml_value(v)}" for k, v in values.items()) + " }"


def toml_section(entries: dict[str, Any], *, ignore: Optional[set[str]] = None) -> str:
    """Convert a dict tree to TOML key-value lines and [table] sections.

    Skips keys in `ignore` (default: {'env', '_comment', 'projects', 'model_providers', 'export_env_to_zshrc'}).
    Nested dicts with scalar values become [parent] tables with key=value lines.
    Deeper nested dicts become [parent.child] tables.
    Returns a TOML string suitable for insertion into managed blocks.
    """
    skip = ignore if ignore is not None else {"env", "_comment", "projects", "model_providers", "export_env_to_zshrc"}
    lines: list[str] = []

    def _emit_table(parent_key: str, sub: dict[str, Any]) -> None:
        """Emit a TOML [table] section from a dict."""
        # Separate scalars/lists from nested dicts
        sub_tables: dict[str, dict[str, Any]] = {}
        has_scalars = False
        for k, v in sub.items():
            if isinstance(v, dict):
                sub_tables[k] = v
            else:
                has_scalars = True
                if isinstance(v, list):
                    lines.append(f"{k} = {toml_value(v)}")
                elif v is not None:
                    lines.append(f"{k} = {toml_value(v)}")
        # Emit nested sub-tables
        for sub_key, sub_value in sub_tables.items():
            full_key = f"{parent_key}.{sub_key}"
            section_key = toml_header_key_segment(full_key)
            lines.append(f"[{section_key}]")
            _emit_table(full_key, sub_value)
        if has_scalars or not sub_tables:
            lines.append("")

    # Top-level scalars and simple values
    for key, value in entries.items():
        if key in skip:
            continue
        if isinstance(value, dict):
            # Insert blank line separator before [table] when following a scalar
            if lines and lines[-1] != "":
                lines.append("")
            # Emit as [key] table
            # Check if any sub-value is itself a dict (deeper nesting)
            has_deep = any(isinstance(v, dict) for v in value.values())
            if has_deep:
                lines.append(f"[{key}]")
                _emit_table(key, value)
            else:
                # Flat dict: emit as [key] with key=value lines
                lines.append(f"[{key}]")
                for sub_key, sub_value in value.items():
                    if isinstance(sub_value, list):
                        lines.append(f"{sub_key} = {toml_value(sub_value)}")
                    elif sub_value is not None:
                        lines.append(f"{sub_key} = {toml_value(sub_value)}")
                lines.append("")
        elif isinstance(value, list):
            lines.append(f"{key} = {toml_value(value)}")
        elif value is not None:
            lines.append(f"{key} = {toml_value(value)}")

    # model_providers section
    providers = entries.get("model_providers")
    if "model_providers" not in skip and isinstance(providers, dict):
        for pid, pcfg in providers.items():
            if not isinstance(pcfg, dict):
                continue
            # Ensure single blank line separator before each provider
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[model_providers.{toml_header_key_segment(str(pid))}]")
            for k, v in pcfg.items():
                lines.append(f"{k} = {toml_value(v)}")

    # projects section
    projects = entries.get("projects")
    if "projects" not in skip and isinstance(projects, dict):
        for path, pcfg in projects.items():
            if not isinstance(pcfg, dict):
                continue
            # Ensure single blank line separator before each project
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"[projects.{toml_header_key_segment(str(path))}]")
            for k, v in pcfg.items():
                lines.append(f"{k} = {toml_value(v)}")

    return "\n".join(lines)
