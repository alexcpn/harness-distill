# harness-distill

**Turn a project's coding-agent sessions from every tool you've used
(Claude Code, Codex, pi, Gemini CLI, Cursor, VS Code Copilot, Antigravity)
into an `AGENTS.md` and a `HANDOFF.md`, so the next agent can pick up the
work in any tool.**

You've worked on a project for weeks with one coding agent. It knows your
conventions, the dead ends, which PR is waiting on what, and why that branch
exists. Then you open the same folder in another harness and it knows none
of it. Everything it had learned is in that first harness's session files.

`harness-distill` is an [Agent Skill](https://agentskills.io). It reads the
session history that each harness keeps for a project folder, and writes
down what matters:

| File | Contents | Lifetime | In git? |
|---|---|---|---|
| `AGENTS.md` | Durable rules: architecture decisions, conventions you stated or corrected, build/test/release commands that worked, gotchas | As long as the code | Yes |
| `.agents/HANDOFF.md` | Point-in-time state: timeline, decisions and why, open PRs and branches, what was mid-flight, next steps | Days to weeks | No (kept local via `.git/info/exclude`) |

`AGENTS.md` is read natively by Codex, pi, Cursor, VS Code Copilot, Zed and
Antigravity. Claude Code and Gemini CLI need a one-line stub, which the skill
adds when needed. The next agent starts with your project's context, and
nothing has to be replayed.

## Quick start

```bash
# 1. Install. This one directory is scanned by pi, Codex, Gemini CLI, Cursor, Copilot and Antigravity.
git clone https://github.com/alexcpn/harness-distill ~/.agents/skills/harness-distill
ln -s ~/.agents/skills/harness-distill ~/.claude/skills/harness-distill   # Claude Code

# 2. Distill. Open the project in any agent that can run commands, and ask:
cd ~/work/my-app
pi                                  # or claude, codex, agy, Cursor's agent…
> /skill:harness-distill .          # pi (in Claude Code: /harness-distill .)
```

This writes `AGENTS.md` and `.agents/HANDOFF.md`. Review them, then commit
`AGENTS.md`.

```bash
# 3. Continue in the new tool. Open the same folder and ask, cold:
> what is this project, what was I last working on, and what's next?
```

When you finish a session, say *"I'm done for today"*. The agent then
updates `HANDOFF.md`, so whichever tool you open next starts where you
stopped.

## Distill, don't migrate

Several good tools convert or resume a **single session** in another tool.
This one works at the **project** level:

- **It merges every harness.** It reads all of a folder's sessions from all
  of your tools. In the first real run that was 10 sessions across Claude
  Code, Codex and pi.
- **It distills instead of replaying.** A 1.5 MB transcript makes worse
  context than a 3 KB brief. Tool output and thinking are dropped. Prompts,
  decisions and outcomes are kept.
- **It checks claims against git.** Claims about branches, PRs and failing
  tests are checked against the repo before they are written down. Anything
  that can't be confirmed is marked `(?)` rather than guessed.
- **It is scoped to the project.** Sessions are found by folder, not by
  topic, so side work done in the same chat (another repo, an errand) is
  left out.
- **It stays current.** The `AGENTS.md` it writes tells the next agent to
  update `HANDOFF.md` when you end a session or switch tools. The handoff
  keeps itself current; you don't have to re-run the skill.
- **It reads GUI IDE history too**, from Cursor IDE chats, VS Code Copilot
  Chat and Antigravity's plan and walkthrough artifacts, as well as CLI
  agents.

If you want to *resume one exact conversation* in another tool, use
[session-migrate](https://github.com/xhluca/session-migrate) or
[continues](https://github.com/yigitkonur/cli-continues). The two approaches
work well together.

## What it reads

| Harness | Source | What you get |
|---|---|---|
| Claude Code (CLI and IDE extension) | `~/.claude/projects/<slug>/*.jsonl`, `memory/*.md` | Full transcripts, compaction summaries, auto-memory |
| Codex (CLI and IDE extension) | `~/.codex/sessions/**/rollout-*.jsonl` | Full transcripts |
| pi | `~/.pi/agent/sessions/--<cwd>--/*.jsonl` | Full transcripts, compactions |
| Gemini CLI | `~/.gemini/tmp/<project>/chats/*.jsonl` | Full transcripts |
| Cursor IDE | `state.vscdb` (SQLite, opened read-only) | Full chats, tool calls, chat titles |
| VS Code Copilot Chat | `workspaceStorage/<hash>/chatSessions/*.json` | Prompts, replies, tool calls, edited files |
| Antigravity (IDE and `agy`) | `brain/<id>/{task,implementation_plan,walkthrough}.md`, `agy` prompt log | Artifacts and prompts only (conversations are protobuf) |

It also reads any existing instruction files (`AGENTS.md`, `CLAUDE.md`,
`GEMINI.md`, `.cursorrules`, Copilot instructions) and lists project harness
config (MCP, rules, skills) that you need to recreate in the target tool.
Exact paths and formats are in
[`references/harness-locations.md`](references/harness-locations.md).

It does not yet read history from Zed, Windsurf, JetBrains or Kiro. They
still work as targets through `AGENTS.md`.

## Install

Clone it into the shared Agent Skills directory. pi, Codex, Gemini CLI,
Cursor, Copilot and Antigravity all scan this directory:

```bash
git clone https://github.com/alexcpn/harness-distill ~/.agents/skills/harness-distill
# Claude Code reads its own directory:
ln -s ~/.agents/skills/harness-distill ~/.claude/skills/harness-distill
```

Requirements: Python 3.8+, standard library only.

## Use

From the agent you want to continue in, or any agent that has terminal
access:

```text
/skill:harness-distill /path/to/project     # pi
/harness-distill /path/to/project           # Claude Code
```

You can also just ask: *"distill my context for this project, I'm switching
to Cursor"*.

The skill then:

1. Runs `scripts/harvest.py` to build a digest of every session for the folder.
2. Reads the digest and checks it against `git log`, `git status`, branches
   and open PRs.
3. Writes or merges `AGENTS.md`, writes `.agents/HANDOFF.md`, and excludes the
   handoff from git.
4. Checks that the skills you used are available to the target harness, and
   lists any MCP servers or rules you need to recreate.
5. Checks the result by asking the target agent, cold, what the project is
   and what's next.

You can also run the harvester on its own:

```bash
python3 scripts/harvest.py /path/to/project --out digest.md
python3 scripts/harvest.py /path/to/project --source cursor        # one harness
python3 scripts/harvest.py /path/to/project --include-parents      # sessions started from a parent dir
```

## Privacy

- Everything runs locally. Nothing is sent anywhere except to the model the
  skill runs in.
- The digest is raw material and can contain secrets that appeared in tool
  calls. Keep it in a temp directory. The skill tells the agent not to copy
  secrets into the files it writes.
- `HANDOFF.md` is excluded from git by default because it can mention side
  work and people. Commit it only after reviewing it.
- Do not commit the raw chats. Put the reasoning that matters in commit
  messages and PR descriptions, where it is reviewed and tied to the code.

## Related

- Session transfer and resume: [session-migrate](https://github.com/xhluca/session-migrate),
  [continues](https://github.com/yigitkonur/cli-continues),
  [casr](https://github.com/Dicklesworthstone/cross_agent_session_resumer)
- Rules and skills sync across tools: [rulesync](https://github.com/dyoshikawa/rulesync),
  [ruler](https://github.com/intellectronica/ruler)
- Chat archiving: [SpecStory](https://specstory.com)
- The `AGENTS.md` standard: [agents.md](https://agents.md)

## License

MIT
