# harness-distill

**Switch AI coding tools without losing what your old tool learned about your project.**

You've been building a project with an AI coding assistant such as Claude
Code, Cursor or Codex. Over weeks it learned your conventions, which
approaches failed, which pull request is waiting on what, and what you
planned next. Then you open the same project in a different assistant, and
it knows none of that.

harness-distill fixes this. It reads the chat history your old assistants
saved for the project and writes the important parts into two plain text
files. Any assistant reads them when it opens the project:

| File | What's in it | Commit it to git? |
|---|---|---|
| `AGENTS.md` | Lasting rules: how the project is built and tested, your conventions, decisions and why, known pitfalls | Yes |
| `.agents/HANDOFF.md` | Where you left off: recent work, open branches and PRs, next steps | No, it stays on your machine |

Works with **Claude Code, Codex, pi, Cursor, VS Code Copilot, Antigravity and
Gemini CLI**, in any direction. If you use [claude-mem](https://github.com/thedotmack/claude-mem),
it reads that memory too.

## Before you start

You need:

1. **At least one AI coding assistant** that can run terminal commands.
   Any of the tools above works.
2. **Python 3.8 or newer.** Check with `python3 --version`.
3. **uv**, a Python tool installer. Check with `uv --version`. If it's
   missing, install it:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```
   (Windows: `powershell -c "irm https://astral.sh/uv/install.ps1 | iex"`.
   More options are on [uv's install page](https://docs.astral.sh/uv/getting-started/installation/).)

## Quick start

**Step 1. Install.** Run these in your terminal:

```bash
uv tool install harness-distill
harness-distill install
```

The second command adds the skill to your assistants. You should see two
`ok` lines. **Restart any assistant that is already open** so it notices the
new skill.

**Step 2. Distill your project.** In your terminal, go to your project
folder and start an assistant:

```bash
cd ~/work/my-app      # your project folder
claude                # or: pi, codex, agy … or open the folder in Cursor / VS Code
```

Then type this **in the assistant's chat**, not in the terminal:

```text
Use the harness-distill skill on this project.
```

The assistant reads your past sessions, checks them against git, and
writes `AGENTS.md` and `.agents/HANDOFF.md`. It shows you what it wrote.
Read both files and fix anything that's wrong. Then commit `AGENTS.md`:

```bash
git add AGENTS.md && git commit -m "Add AGENTS.md"
```

**Step 3. Continue in the new tool.** Open the project in the assistant you
are switching to, and ask in its chat:

```text
What is this project, what was I last working on, and what's next?
```

If it answers correctly, you're done.

**Every day after that:** when you finish working, tell the assistant
*"I'm done for today"*. It updates `HANDOFF.md`, so whichever tool you open
next starts where you stopped. You don't need to run the skill again.

## What the result looks like

An example `AGENTS.md` for a small web app:

```markdown
# my-app
Flask API + React front end for internal expense reports.

## Rules
- Use `uv`, not pip: the Docker build depends on uv.lock.
- All money values are integer cents. Floats caused rounding bugs (PR #41).
- Never edit `migrations/` by hand; run `make migration name=...`.

## Build and test
- `make dev` starts both servers; `make test` runs pytest + vitest.

## Session handoff
Recent history and open threads are in `.agents/HANDOFF.md` (local only).
Read it at the start of a session; update it before you end one.
```

`HANDOFF.md` is similar, but holds the current state: "PR #52 (CSV export)
waiting for review; next: add pagination to /reports".

## Troubleshooting

| Problem | Fix |
|---|---|
| The assistant doesn't know the skill | Restart the assistant. In pi, `/reload` also works. Check that `~/.agents/skills/harness-distill/SKILL.md` exists. Run `harness-distill install` again if it doesn't. |
| "0 sessions" or very little history found | You may have started those sessions from a parent folder. Ask the assistant to use `--include-parents`. If you only used a tool this skill can't read yet (see below), there's nothing to import. |
| The new assistant ignores `AGENTS.md` | **Claude Code** reads `CLAUDE.md`: create one containing just the line `@AGENTS.md`. **Gemini CLI** reads `GEMINI.md`: put `@AGENTS.md` in one. Antigravity needs version 1.20.3 or newer. |
| `harness-distill: command not found` | Run `uv tool update-shell`, then open a new terminal. |
| The files contain something private or wrong | Edit or delete it. They're plain text, and nothing is uploaded anywhere. |

Tested on Linux. macOS and Windows paths are included for Cursor and VS
Code, but are untested. Please [open an issue](https://github.com/alexcpn/harness-distill/issues)
if something doesn't work.

## Words used here

- **Harness / assistant**: the app around the AI model, such as Claude Code,
  Cursor or Codex. Each one saves its own chat history, which the others
  can't read.
- **Skill**: a folder of instructions (`SKILL.md`) that an assistant loads
  when a task needs it. This project is one. See [agentskills.io](https://agentskills.io).
- **Distill**: keep only what matters. A month of chats becomes a few
  hundred lines of facts and rules.
- **`AGENTS.md`**: a standard file name for instructions to AI coding
  assistants. Most of them read it automatically. See [agents.md](https://agents.md).

---

## For experienced users

### Distill, don't migrate

Other tools convert or resume a **single session** in another tool. This
one works at the **project** level:

- **It merges every harness.** It reads all of a folder's sessions from all
  of your tools. The first real run found 10 sessions across Claude Code,
  Codex and pi.
- **It distills instead of replaying.** A 1.5 MB transcript makes worse
  context than a 3 KB brief. Tool output and thinking are dropped. Prompts,
  decisions and outcomes are kept.
- **It checks claims against git.** Claims about branches, PRs and failing
  tests are checked against the repo before they are written down. Anything
  that can't be confirmed is marked `(?)` rather than guessed.
- **It is scoped to the project.** Unrelated side work done in the same chats
  is left out.
- **It stays current.** The end-of-session rule in `AGENTS.md` keeps the
  handoff current without re-running the skill.
- **It reads GUI IDE history too**: Cursor IDE, VS Code Copilot Chat, and
  Antigravity's artifacts.

### How it compares to claude-mem

[claude-mem](https://github.com/thedotmack/claude-mem) is the popular way to give agents
memory across sessions. It works differently:

| | claude-mem | harness-distill |
|---|---|---|
| When it captures | From the moment you install its hooks | After the fact: it reads history you already have, even from tools you never set up |
| What runs | A background service, SQLite and a vector DB, with model calls on every session | Nothing in the background: one script and one agent run |
| Where memory lives | Its database (`~/.claude-mem`) or its cloud | Plain files in your repo: `AGENTS.md` is committed, `HANDOFF.md` stays local |
| Who can use it | Tools with a claude-mem integration | Any tool that reads `AGENTS.md`, and any teammate who opens the file |
| Review | Through its viewer and search | A diff in a pull request, checked against git |

They work together. If you run claude-mem, harness-distill reads its database as one more
source, and turns those observations into an `AGENTS.md` that tools and teammates without
claude-mem can read.

To resume one exact conversation in another tool, use
[session-migrate](https://github.com/xhluca/session-migrate) or
[continues](https://github.com/yigitkonur/cli-continues). The two approaches
work well together.

### What it reads

| Harness | Source | What you get |
|---|---|---|
| Claude Code (CLI and IDE extension) | `~/.claude/projects/<slug>/*.jsonl`, `memory/*.md` | Full transcripts, compaction summaries, auto-memory |
| Codex (CLI and IDE extension) | `~/.codex/sessions/**/rollout-*.jsonl` | Full transcripts |
| pi | `~/.pi/agent/sessions/--<cwd>--/*.jsonl` | Full transcripts, compactions |
| Gemini CLI | `~/.gemini/tmp/<project>/chats/*.jsonl` | Full transcripts |
| Cursor IDE | `state.vscdb` (SQLite, opened read-only) | Full chats, tool calls, chat titles |
| VS Code Copilot Chat | `workspaceStorage/<hash>/chatSessions/*.json` | Prompts, replies, tool calls, edited files |
| Antigravity (IDE and `agy`) | `brain/<id>/{task,implementation_plan,walkthrough}.md`, `agy` prompt log | Artifacts and prompts only (conversations are protobuf) |
| [claude-mem](https://github.com/thedotmack/claude-mem) (if installed) | `~/.claude-mem/claude-mem.db` (opened read-only) | Its compressed observations and session summaries, from every harness it hooks |

It also reads existing instruction files (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursorrules`, Copilot instructions). It lists the project
config you need to recreate in the target tool: MCP servers, rules and
skills. History from Zed, Windsurf, JetBrains and Kiro isn't read yet, but
those tools still pick up `AGENTS.md`. Exact paths and formats are in
[`references/harness-locations.md`](https://github.com/alexcpn/harness-distill/blob/main/references/harness-locations.md).

### Commands

```bash
harness-distill install [--target agents|claude]   # agents = ~/.agents/skills (pi, Codex, Cursor, Copilot, Antigravity, Gemini)
harness-distill uninstall
harness-distill harvest /path/to/project --out digest.md      # build the raw digest yourself
harness-distill harvest /path/to/project --source cursor      # one harness only
harness-distill harvest /path/to/project --include-parents    # include sessions started from parent dirs
```

Slash commands: `/skill:harness-distill <path>` in pi, `/harness-distill <path>`
in Claude Code.

Upgrade: `uv tool install --force --refresh harness-distill && harness-distill install`.
Remove: `harness-distill uninstall && uv tool uninstall harness-distill`.
`pipx install harness-distill` works too. To try the unreleased `main` branch: `uv tool install --force git+https://github.com/alexcpn/harness-distill`.

### Install with git instead

The repo root is the skill itself:

```bash
git clone https://github.com/alexcpn/harness-distill ~/.agents/skills/harness-distill
ln -s ~/.agents/skills/harness-distill ~/.claude/skills/harness-distill   # Claude Code
```

### How the skill works

1. Runs `scripts/harvest.py` to build a digest of every session for the folder.
2. Reads the digest as data, never as instructions, and checks it against
   `git log`, `git status`, branches and open PRs.
3. Writes or merges `AGENTS.md`, writes `.agents/HANDOFF.md`, and excludes the
   handoff from git via `.git/info/exclude`.
4. Checks that the skills you used are available in the target tool, and
   lists any MCP servers or rules you need to recreate.
5. Checks the result by asking the target agent, cold, what the project is
   and what's next.

## Privacy

- Everything runs locally. Nothing is sent anywhere except to the model the
  skill runs in.
- The raw digest can contain secrets that appeared in past tool calls. Keep
  it in a temp directory. The skill tells the agent not to copy secrets into
  the files it writes, but review them anyway.
- `HANDOFF.md` stays out of git by default because it can mention side work
  and people.
- Don't commit raw chat logs. Put the reasoning that matters in commit
  messages and PR descriptions.

See [SECURITY.md](https://github.com/alexcpn/harness-distill/blob/main/SECURITY.md) for the threat model and how to report a
vulnerability privately.

## Related

- Session transfer and resume: [session-migrate](https://github.com/xhluca/session-migrate),
  [continues](https://github.com/yigitkonur/cli-continues),
  [casr](https://github.com/Dicklesworthstone/cross_agent_session_resumer)
- Rules and skills sync across tools: [rulesync](https://github.com/dyoshikawa/rulesync),
  [ruler](https://github.com/intellectronica/ruler)
- Persistent agent memory: [claude-mem](https://github.com/thedotmack/claude-mem). It captures
  sessions from now on; harness-distill can read its database.
- Chat archiving: [SpecStory](https://specstory.com)

## License

[MIT](https://github.com/alexcpn/harness-distill/blob/main/LICENSE)
