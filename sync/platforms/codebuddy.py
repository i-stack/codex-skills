import shutil
from pathlib import Path
from typing import Any

from core import recall
from core.common import (
    api_enabled as _api_enabled,
    is_managed_entry,
    merge_managed_entries,
    read_json_object,
    skill_sync_disabled,
    sync_json_mcp,
    write_json,
)
from core.paths import (
    claude_skills_base,
    codebuddy_mcp_path,
    codebuddy_models_path,
    codebuddy_root_dir,
    codebuddy_skills_base,
    workbuddy_root_dir,
    workbuddy_skills_base,
)

# ── Standalone historical recall (used only when preamble.mode=recall) ──
# CodeBuddy normally receives the full agent-preamble from
# sync-agent-preamble.sh. This renderer is kept for explicit recall-mode configs
# and uses the same template as other standalone recall targets.
_RECALL_BEGIN = "<!-- managed-block:historical-recall:begin"
_RECALL_END = "<!-- managed-block:historical-recall:end"


def _repo_root() -> Path:
    """Repo root: sync/platforms/<this file> -> parents[2]."""
    return Path(__file__).resolve().parents[2]


def _render_recall_block(codebuddy_skills_dir: Path) -> str | None:
    """Render the historical-recall managed block from the shared template.

    Delegates to sync.core.recall (the single source of truth shared with
    the Bash preamble writer and continue.py) so every path stays byte-consistent.
    """
    cli_path = str(
        (
            _repo_root()
            / "skills-engineering"
            / "plan-reviews"
            / "dist"
            / "cli.js"
        ).resolve()
    )
    return recall.render_recall_block(
        str(codebuddy_skills_dir / "historical-recall") + "/", cli_path
    )


def _merge_recall_block(target: Path, block: str) -> None:
    """Idempotently merge the historical-recall managed block into CODEBUDDY.md.

    Delegates to sync.core.recall (shared with the Bash preamble writer).
    """
    recall.merge_recall_block_markdown(target, block)


def _validate_model_entries(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError("platforms.codebuddy.models must be a list.")

    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise ValueError(f"platforms.codebuddy.models[{index}] must be an object.")
        model_id = entry.get("id")
        if not isinstance(model_id, str) or not model_id:
            raise ValueError(f"platforms.codebuddy.models[{index}].id must be a non-empty string.")
    return value


def _validate_available_models(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("platforms.codebuddy.availableModels must be a list.")

    for index, model_id in enumerate(value):
        if not isinstance(model_id, str) or not model_id:
            raise ValueError(
                f"platforms.codebuddy.availableModels[{index}] must be a non-empty string."
            )
    return value


def _merge_model_entries(
    existing_entries: list[Any], config_entries: list[dict[str, Any]]
) -> list[Any]:
    """Merge config-managed model entries into existing entries by id.

    Delegates to the shared marker engine so empty config prunes managed
    entries the same way as other platforms.
    """
    return merge_managed_entries(existing_entries, config_entries, key_field="id")


def _merge_available_models(
    existing_available: list[Any], config_available: list[Any]
) -> list[Any]:
    """Replace availableModels wholesale with the config list.

    availableModels is a plain string list with no per-item marker, so the
    config is the single source of truth: any user/UI-added IDs not in the
    config are dropped on the next sync. An explicitly empty list from config
    means "clear all enabled models".
    """
    return list(config_available)


def _sync_models(cfg: dict[str, Any]) -> None:
    api_enabled = _api_enabled(cfg)
    models = cfg.get("models")
    available_models = cfg.get("availableModels")
    models_path = codebuddy_models_path()

    # No model config at all: clean up any previously synced managed entries.
    if models is None and available_models is None:
        existing = read_json_object(models_path)
        removed = False
        # Drop only our managed model entries, keeping user/system entries.
        existing_entries = existing.get("models")
        if isinstance(existing_entries, list) and any(is_managed_entry(m) for m in existing_entries):
            existing["models"] = [m for m in existing_entries if not is_managed_entry(m)]
            if not existing["models"]:
                existing.pop("models", None)
            removed = True
        if "availableModels" in existing:
            existing.pop("availableModels", None)
            removed = True
        if removed:
            write_json(models_path, existing)
            print(f"[codebuddy] Removed managed models config from {models_path} (model config absent).")
        else:
            print("[codebuddy] No models config found — skipping model sync.")
        return

    existing = read_json_object(models_path)

    # API sync disabled: do not sync API fields. CodeBuddy special handling —
    # empty availableModels (key preserved) rather than removing it, so synced
    # models are disabled from selection without dropping provider definitions.
    # Config-managed model definitions are left untouched (not synced, not
    # removed); "do not sync" means we skip merging, not that we delete.
    if not api_enabled:
        existing["availableModels"] = []
        write_json(models_path, existing)
        print(f"[codebuddy] API sync disabled — availableModels cleared in {models_path}.")
        return

    if models is not None:
        models = _validate_model_entries(models)
        existing_entries = existing.get("models")
        if not isinstance(existing_entries, list):
            existing_entries = []
        existing["models"] = _merge_model_entries(existing_entries, models)

    if available_models is not None:
        available_models = _validate_available_models(available_models)
        existing_avail = existing.get("availableModels")
        if not isinstance(existing_avail, list):
            existing_avail = []
        existing["availableModels"] = _merge_available_models(existing_avail, available_models)

    write_json(models_path, existing)
    print(f"Merged models into {models_path}.")



def _sync_skills_to(claude_skills_dir: Path, target_skills_dir: Path, label: str) -> None:
    target_skills_dir.mkdir(parents=True, exist_ok=True)
    synced: list[str] = []

    for skill_dir in sorted(claude_skills_dir.iterdir()):
        if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
            continue

        dest = target_skills_dir / skill_dir.name
        tmp = target_skills_dir / f".{skill_dir.name}.tmp-sync"
        backup = target_skills_dir / f".{skill_dir.name}.backup-sync"

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

    print(f"Synced {len(synced)} skills to {target_skills_dir} ({label}): {', '.join(synced) or '(none)'}.")


def _sync_skills() -> None:
    if skill_sync_disabled():
        print("[codebuddy] SKIP_SKILL_SYNC=1 — skipping skill sync.")
        return
    claude_skills_dir = claude_skills_base()
    if not claude_skills_dir.exists():
        print(f"[codebuddy] Claude skills directory not found: {claude_skills_dir} — skipping skill sync.")
        return

    _sync_skills_to(claude_skills_dir, codebuddy_skills_base(), "codebuddy")

    workbuddy_root = workbuddy_root_dir()
    if workbuddy_root.exists():
        _sync_skills_to(claude_skills_dir, workbuddy_skills_base(), "workbuddy")
    else:
        print(f"[codebuddy] WorkBuddy root not found: {workbuddy_root} — skipping workbuddy skill sync.")


def sync(mcp_servers: dict[str, Any], cfg: dict[str, Any]) -> None:
    """Sync MCP servers, models, skills, and CodeBuddy's preamble to CODEBUDDY.md.

    The preamble shape is driven by env/platforms/codebuddy.json `preamble.mode`:
    recall -> standalone historical-recall block; full -> skipped here (rendered by
    sync-agent-preamble.sh as the embedded full preamble); none -> skipped.
    """
    root = codebuddy_root_dir()
    if not root.exists():
        print(f"[codebuddy] CodeBuddy root not found: {root} — skipping (tool not installed).")
        return

    sync_json_mcp(codebuddy_mcp_path(), mcp_servers)
    _sync_models(cfg)
    _sync_skills()

    # Sync the global historical-recall managed block into the platform's
    # preamble file. Driven by the `preamble` declaration in
    # env/platforms/codebuddy.json (single source of truth).
    #
    # - mode == "recall": write the standalone historical-recall block here
    #   (legacy/explicit recall mode, same standalone block shape as Cline /
    #   Qwen / Continue).
    # - mode == "full": the full preamble block (which *embeds* historical-recall)
    #   is rendered by `sync-agent-preamble.sh` into CODEBUDDY.md; writing a
    #   separate standalone block here would duplicate it, so we skip.
    # - mode == "none": nothing is written.
    preamble = cfg.get("preamble") or {}
    recall_mode = preamble.get("mode", "recall")
    if recall_mode == "recall":
        recall_target = codebuddy_root_dir() / preamble.get("target", "CODEBUDDY.md")
        block = _render_recall_block(codebuddy_skills_base())
        if block is not None:
            _merge_recall_block(recall_target, block)
        else:
            print("[codebuddy] agent-preamble template not found — skipping CODEBUDDY.md recall sync.")
    elif recall_mode == "none":
        print("[codebuddy] historical-recall preamble disabled via preamble.mode=none.")
    else:  # full
        print(
            "[codebuddy] preamble.mode=full — full preamble (incl. historical-recall) "
            "is rendered by sync-agent-preamble.sh; skipping standalone recall block here."
        )
