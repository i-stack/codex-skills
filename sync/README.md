# sync

`sync/` reads MCP server definitions and platform configs, **injects secrets** from `env/secrets.json`, then renders them into each platform's native format.

## 快速开始（3 步）

```bash
# 1. 复制 secrets 模板（唯一需要创建的文件）
cp env/secrets.json.example env/secrets.json

# 2. 编辑填写你的 API Keys
$EDITOR env/secrets.json

# 3. 一键同步到所有平台
bash sync.sh
```

## 架构

```text
env/
├── secrets.json            ← 你唯一需要配置的文件（gitignored）
├── secrets.json.example    ← 模板（已提交，列出所有需要的 Key）
│
├── mcp/                    ← MCP 服务器定义（已提交，开箱即用）
│   ├── github.json         ← token 用 ${github.token} 占位
│   ├── apifox.json
│   └── ...
│
├── platforms/              ← 平台配置（已提交，开箱即用）
│   ├── codex.json          ← url/key 用 ${codex.url}/${codex.key} 占位
│   ├── claude.json
│   └── ...
│
└── templates/              ← 模板（供新增 MCP/平台时参考）
    ├── mcp.template.json
    └── platform.template.json
```

## 占位符机制

所有配置文件的敏感值使用 `${platform.field}` 占位，同步时从 `env/secrets.json` 注入：

```json
// env/mcp/github.json（已提交）
{ "headers": { "Authorization": "Bearer ${github.token}" } }

// env/platforms/codex.json（已提交）
{ "model_providers": { "dataeyes": {
    "base_url": "${codex.url}",
    "env_key": "DATAEYES_API_KEY"
  }},
  "env": { "DATAEYES_API_KEY": "${codex.key}" }
}

// env/secrets.json（不提交，用户填写 — 每个平台一个对象）
{
  "github": { "token": "ghp_xxx" },
  "codex":  { "url": "https://api.example.com/v1", "key": "sk-xxx" },
  ...
}

// 运行时解析为：
{ "headers": { "Authorization": "Bearer ghp_xxx" } }
{ "base_url": "https://api.example.com/v1", ... }
```

## MCP Server File Format

Each `env/mcp/<name>.json`:

```json
{
  "name": "my-server",
  "type": "stdio",
  "command": "npx",
  "args": ["-y", "my-mcp-package"],
  "env": {},
  "capabilities": {
    "authority": "read",
    "reversible": true,
    "data_sensitivity": "internal",
    "parallel_safe": true,
    "fallback": "local read-only inspection",
    "verification": "compare with the authoritative source"
  },
  "platforms": ["claude", "codex", "codebuddy"]
}
```

- `type`: `"stdio"` (requires `command`/`args`) or `"sse"` (requires `url`/`headers`)
- `platforms`: optional filter — omit to sync to all platforms, or list specific platforms
- `env`: environment variables passed to the MCP server process
- `capabilities`: required execution contract covering authority, reversibility, data sensitivity, parallel safety, fallback, and verification
- Secrets: use `${platform.field}` syntax, resolved from nested `env/secrets.json` at sync time

## Platform Config Files

Each `env/platforms/<name>.json` mostly follows that platform's native configuration shape,
with a small number of sync-engine metadata fields such as `api.enabled`.

| Platform | File | Follows |
|----------|------|---------|
| Codex | `codex.json` | [Codex config.toml schema](https://developers.openai.com/codex/config-reference) |
| Claude | `claude.json` | Claude Code `env` API sync + preamble/agents metadata |
| CodeBuddy | `codebuddy.json` | CodeBuddy `models.json` schema |
| Gemini | `gemini.json` | Gemini CLI env vars |
| Continue | `continue.json` | Continue `config.yaml` models |
| Cursor | `cursor.json` | (no platform config needed) |
| Cline | `cline.json` | Merge `globalState` + `secrets` into `~/.cline/data/` |
| Qwen Code | `qwen.json` | Merge `env` into `~/.qwen/settings.json`, sync skills |

Engine metadata is consumed by the sync layer and is not written into the target tool config.
For Claude, `api.enabled` defaults to `true`; setting it to `false` skips API env sync and
removes sync-managed API fields, while MCP servers and preamble/agents still sync.
For CodeBuddy, `api.enabled` also defaults to `true`; setting it to `false` skips model
definition sync and clears the managed `availableModels` list in `~/.codebuddy/models.json`
(set to `[]`, not removed) so synced models drop out of the picker without losing provider
definitions. MCP servers, skills, and the preamble still sync.
For Gemini, `api.enabled` also defaults to `true`; setting it to `false` skips syncing the
`model` field into `~/.gemini/settings.json` (pruned via the managed-keys sidecar) and
removes the managed env block (`GEMINI_API_KEY`, `GOOGLE_GEMINI_BASE_URL`, `GEMINI_MODEL`)
from `~/.zshrc`. MCP servers, general settings, and the preamble still sync.

Use the Claude cleanup as the reference contract before adding another
platform's API toggle: [Platform Sync Contract](../docs/platform-sync-contract.md).

## Targets

For Cline, Codex, Claude, CodeBuddy, Gemini, Continue, and Qwen Code, sync first checks
the tool's home directory (`~/.cline`, `~/.codex`, `~/.claude`,
`~/.codebuddy`, `~/.gemini`, `~/.continue`, `~/.qwen`). If that root does not
exist, the target is skipped so sync does not create config for tools the user
has not installed.

Xcode CodingAssistant targets are checked separately. If
`~/Library/Developer/Xcode/CodingAssistant` does not exist, native CLI targets
still sync, but the Xcode-specific Codex / Claude / Gemini outputs are skipped.

## Custom Install Paths

All platform paths are centralized in `sync/core/paths.py`. By default
each tool resolves under its well-known home location (`~/.codex`, `~/.claude`,
`~/.gemini`, …). To support tools installed in non-default locations, override
any platform's install root via the `paths` object in `env/config.json`:

```json
{ "paths": { "codex": "/opt/codex", "claude": "/custom/.claude" } }
```

When a key is set, every derived path for that platform (config, settings,
skills, MCP files) resolves under the override. Empty string `""` or a missing
key falls back to the default. For Codex, the standard `CODEX_HOME` /
`CODEX_CONFIG` env vars still take precedence over this override. See
[env/README.md](../env/README.md#自定义安装路径paths) for the full key list.
Cursor project rule sync can also read additional project roots from
`paths.cursor_project_roots` in `env/config.json`; `CURSOR_PROJECT_ROOTS`
remains available as a one-shot environment override.

| Target | Output |
|--------|--------|
| Cursor | Replace `mcpServers` in `~/.cursor/mcp.json` |
| CodeBuddy | Replace `mcpServers` in `~/.codebuddy/mcp.json`, sync `models.json`, skills |
| Codex CLI | Managed MCP + shared blocks in `~/.codex/config.toml` |
| Xcode Codex | `~/Library/.../CodingAssistant/codex/` |
| Claude Code | Replace `mcpServers` in `~/.claude.json` + Xcode Claude |
| Claude settings | If `api.enabled=true`, merge API `env` into `~/.claude/settings.json` and set `~/.claude/config.json` `primaryApiKey` to `self`; if `false`, clean sync-managed API fields |
| Cline | Replace `mcpServers` in VSCode extension settings + skills sync + merge `globalState`/`secrets` into `~/.cline/data/` |
| Gemini CLI | Replace `mcpServers` in `~/.gemini/settings.json` + `~/.zshrc` env |
| Continue | Update `mcpServers` + `models` in `~/.continue/config.yaml`, creating it when `~/.continue` exists |
| Qwen Code | Merge `env` into `~/.qwen/settings.json`, sync skills to `~/.qwen/skills/` |

> **End-to-end recall:** the historical-recall trigger is wired to Cline
> (`~/.cline/rules/ai-coding-kit-recall.md`) and Qwen Code (`~/.qwen/QWEN.md`)
> as recall-only preambles, and to CodeBuddy (`~/.codebuddy/CODEBUDDY.md`) as a
> **full** preamble (which embeds historical-recall) — all three via
> `skills-engineering/scripts/sync-agent-preamble.sh`. Continue gets it via the
> `rules` field in `~/.continue/config.yaml` (injected by `sync/platforms/continue.py`).
> Run **both** `sync.sh` (covers Continue) and `sync-agent-preamble.sh`
> (covers Cline / CodeBuddy / Qwen) so every platform receives its preamble.

## Adding a Platform

1. Copy template: `cp env/templates/platform.template.json env/platforms/my-platform.json`
2. Fill in config following the platform's official spec
3. Read [Platform Sync Contract](../docs/platform-sync-contract.md) and decide field ownership, cleanup, and `api.enabled` semantics before writing the renderer.
4. If the platform only needs `mcpServers` in a JSON file, add `"mcp_target": "~/.my-platform/mcp.json"` to the config
5. If custom rendering is needed, create `sync/platforms/my_platform.py` with a `sync(mcp_servers, cfg)` function. The sync engine discovers it from `env/platforms/my-platform.json`; no `sync_config.py` registration is needed.
6. Put shared path helpers in `sync/core/paths.py` only when the platform has a well-known default install root. Otherwise prefer the JSON `install_root` / `mcp_target` fields.

## Adding an MCP Server

```bash
cp env/templates/mcp.template.json env/mcp/my-new-server.json
$EDITOR env/mcp/my-new-server.json
bash sync.sh
```

## Commands

```bash
bash sync.sh                              # sync all
python3 sync/cli/main.py sync --target all  # sync all (Python direct)
python3 sync/cli/main.py sync --target codex  # single platform
```

## 跳过 skill 分发

`sync` 会把每个 skill 目录分发到各平台的 `skills/` 目录，并用 `shutil.rmtree` 清理
`.tmp-sync` / `.backup-sync` 临时目录。在带有批量删除保护的环境中（如 CodeBuddy 的
safe-delete，阈值 500），这些递归删除会被拦截并中断同步。此时可设置环境变量跳过
skill 分发（MCP / 模型 / 设置同步不受影响）：

```bash
SKIP_SKILL_SYNC=1 bash sync.sh
```

普通用户与 CI 无需设置该变量，默认行为不变。

## 可选 MCP 服务器

开箱即用的服务器和**非默认、社区/高级**服务器都在 `env/mcp/`。后者以显式 `"enabled": false`
标记**默认不同步**（`load_all_mcp()` 按 `mcp_enabled()` 过滤；停用时还会把已写入各平台
配置的该服务器清理掉）：

```json
// env/mcp/puppeteer.json
{
    "name": "puppeteer",
    "enabled": false,
    "command": "..."
}
```

启用：把 `enabled` 改为 `true` 或删除该字段，下次 `bash sync.sh` 生效；停用：改回 `false`。
当前可选服务器：`puppeteer`、`filesystem-extra`、`wechat-bridge`（详见 `env/README.md`）。

## Design Principles

1. **One file to configure**: user only edits `env/secrets.json` — each platform has its own `{url, key/token}` object
2. **MCP separation**: one file per server — no monolithic config
3. **Platform spec compliance**: config keys match the platform's native naming exactly
4. **Zero field-name mapping**: renderers convert format (JSON→TOML, JSON→YAML), not field names
5. **Auto-discovery**: platforms are discovered from `env/platforms/` directory
6. **Secrets injection**: `${platform.field}` references are resolved from nested `env/secrets.json` at sync time

## Safety

- `env/secrets.json` is **gitignored** — never committed
- `env/mcp/*.json` and `env/platforms/*.json` are **committed** — use `${VAR}` placeholders, no real secrets
- `env/secrets.json.example` is **committed** — shows required keys with placeholder values
- `env/templates/` is **committed** — templates for adding new servers/platforms
