# Harness context locations

Paths verified on this machine (Oct 2026) against Claude Code, pi 1.0.0, Codex CLI, Gemini CLI 0.62, Cursor (2025 composer schema) and Antigravity (IDE + agy).

## Claude Code
- Sessions: `~/.claude/projects/<slug>/<uuid>.jsonl`. `<slug>` is the absolute cwd
  with every non-alphanumeric character replaced by `-`
  (`/home/me/work/my-app` → `-home-me-work-my-app`).
  - Entries have `type` set to `user`, `assistant`, `summary`, `attachment`,
    `system`, and so on. `message.content` is a string or a list of blocks
    (`text`, `thinking`, `tool_use`, `tool_result`). `isSidechain: true` marks
    subagent turns. `isCompactSummary` marks a compaction summary.
- Auto-memory: `~/.claude/projects/<slug>/memory/*.md` with a `MEMORY.md` index.
- Instructions: `CLAUDE.md`, `CLAUDE.local.md` (project and parents), `~/.claude/CLAUDE.md`.
  `@path` lines import other files.
- Config: `.claude/settings*.json`, `.mcp.json`, `.claude/commands/`, `.claude/agents/`.
- Skills: `~/.claude/skills/<name>/SKILL.md`, `.claude/skills/`.

## pi (earendil-works/pi-coding-agent)
- Sessions: `~/.pi/agent/sessions/--<cwd without leading />--/<ts>_<uuid>.jsonl`, with
  `/ \ :` replaced by `-`. This is a v3 tree format: a `session` header,
  then `message` entries (role `system|user|assistant|toolResult`),
  `compaction`, `branch_summary`, `custom_message`, and so on. Docs:
  `docs/session-format.md` in the install.
- Instructions: `AGENTS.override.md` > `AGENTS.md` > `CLAUDE.md` per directory, cwd and
  parents, plus `~/.pi/agent/AGENTS.md`. These load even without project trust.
  `--no-context-files` disables them.
- Skills: `~/.pi/agent/skills`, `~/.agents/skills`, `.agents/skills` (cwd up to repo
  root), `.pi/skills`. Uses the Agent Skills spec, the same SKILL.md as Claude Code.
  Force one with `/skill:name`.
- MCP: see `docs/mcp.md`. Existing `mcpServers` entries from Claude can be copied.
- Docs live at `~/.pi/agent/install/releases/<ver>/node_modules/@earendil-works/pi-coding-agent/docs/`.

## Codex CLI
- Sessions: `~/.codex/sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl`. The first line's
  `payload.cwd` is the project. `response_item` entries hold `message`,
  `function_call` and `reasoning` payloads.
- Instructions: `AGENTS.md` (repo root down to cwd), `~/.codex/AGENTS.md`.
- Skills: `~/.agents/skills`, `~/.codex/skills`.

## Gemini CLI
- Sessions: `~/.gemini/tmp/<name>/chats/session-*.jsonl`. `<name>` comes from
  `~/.gemini/projects.json` (`{"projects": {"/abs/path": "name"}}`). Older builds used
  `sha256(abs path)` as the directory name and `.json` files.
  - Line types: a header, then `{"id", "type": "user"|"gemini", "content", "toolCalls"}`.
    The same `id` is re-emitted as it streams, so keep the last copy. `$set` lines are
    metadata patches.
- Instructions: `GEMINI.md` (global `~/.gemini/GEMINI.md`, project, subdirs). Other names
  are read only via `context.fileName` in `settings.json`. `@file.md` lines import files.
- Skills: `~/.gemini/skills`, `~/.agents/skills` (the alias wins), `.gemini/skills`, `.agents/skills`.

## Cursor (IDE)
- Chats live in SQLite, not files:
  - `<User>/workspaceStorage/<hash>/workspace.json` → `{"folder": "file:///abs/path"}`.
  - The same dir's `state.vscdb`, `ItemTable` key `composer.composerData` → `allComposers[].composerId`.
  - `<User>/globalStorage/state.vscdb`, table `cursorDiskKV`:
    - `composerData:<id>`: `name`, `createdAt`, and `fullConversationHeadersOnly[]` in order.
    - `bubbleId:<composer>:<bubble>`: `type` 1 = user, 2 = assistant, `text`,
      and `toolFormerData {name, rawArgs}`.
  - `<User>` is `~/.config/Cursor/User` (Linux), `~/Library/Application Support/Cursor/User`
    (macOS), or `%APPDATA%/Cursor/User` (Windows). Open the databases read-only.
- The Cursor CLI (`cursor-agent`) keeps chats under `~/.cursor/chats/`. The harvester doesn't read these yet.
- Instructions: `AGENTS.md` (root and subdirs), `.cursor/rules/*.mdc`, legacy `.cursorrules`.
  There is no global file; User Rules live in settings.
- Skills: `.agents/skills`, `.cursor/skills`, `~/.agents/skills`, `~/.cursor/skills`.
  MCP: `.cursor/mcp.json`.

## Antigravity (IDE and `agy` CLI)
- Conversations: `~/.gemini/antigravity/conversations/<id>.pb` (IDE) and
  `~/.gemini/antigravity-cli/conversations/<id>.db` (CLI, SQLite with protobuf blobs).
  Neither is readable without the schema.
- Readable: `~/.gemini/antigravity{,-cli}/brain/<id>/task.md`, `implementation_plan.md`,
  `walkthrough.md` (with `*.metadata.json` → `updatedAt`). These are matched to a project by
  the `file:///abs/path/` links inside them. The CLI's `history.jsonl` logs every prompt
  with its `workspace`.
- Instructions: `AGENTS.md` (v1.20.3+), `GEMINI.md` (global `~/.gemini/GEMINI.md`; wins on
  conflict), `.agents/rules/`. Workflows: `.agents/workflows/`. MCP: `.agents/mcp_config.json`
  or `~/.gemini/antigravity/mcp_config.json`.
- Skills: `.agents/skills`, `~/.agents/skills`. These are standard SKILL.md files.

## VS Code Copilot Chat
- `<User>/workspaceStorage/<hash>/workspace.json` → `{"folder": "file:///abs/path"}`. The
  same dir's `chatSessions/<id>.json` has `requests[]`, each with `message.text`, a
  `timestamp`, and `response[]` parts: markdown parts (no `kind`, a `value` string),
  `toolInvocationSerialized` (`toolId`, `invocationMessage`), and `textEditGroup` (`uri`).
  Newer builds write `.jsonl`: a kind-0 snapshot followed by patches. The harvester reads
  the snapshot plus appended requests.
- `<User>` is `~/.config/Code/User` (or `Code - Insiders`, `VSCodium`, or the macOS/Windows equivalents).
- Instructions: `AGENTS.md`, `.github/copilot-instructions.md`, `.github/instructions/*.instructions.md`.
  MCP: `.vscode/mcp.json`.

## IDE extensions of CLI harnesses
- The Claude Code and Codex VS Code/JetBrains extensions write to `~/.claude/projects` and
  `~/.codex/sessions` like their CLIs, so the same readers apply.

## Not harvested (target only)
- Zed: `~/.local/share/zed/threads/threads.db` (SQLite, with JSON or zstd blobs; untested). It reads the first
  of `.rules`, `.cursorrules`, …, `AGENTS.md`, `CLAUDE.md`, `GEMINI.md` in the project.
- Windsurf, JetBrains AI/Junie, Kiro: history formats were not checked. They can still be targets via `AGENTS.md`.
