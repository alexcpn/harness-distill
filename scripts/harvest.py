#!/usr/bin/env python3
"""Harvest agent-harness context for one project folder into a compact markdown digest.

Reads (best effort, stdlib only):
  - context files in the project and its ancestors: CLAUDE.md, AGENTS.md, GEMINI.md, .cursorrules, ...
  - Claude Code: ~/.claude/projects/<slug>/*.jsonl transcripts + memory/*.md
  - pi:          ~/.pi/agent/sessions/--<slug>--/*.jsonl
  - Codex CLI:   ~/.codex/sessions/**/rollout-*.jsonl whose cwd matches
  - Gemini CLI:  ~/.gemini/tmp/<project>/chats/session-*.jsonl (via ~/.gemini/projects.json)
  - Cursor:      ~/.config/Cursor/User (or macOS/Windows equivalent) state.vscdb composer chats
  - VS Code Copilot Chat: <Code User>/workspaceStorage/<hash>/chatSessions/*.json
  - Antigravity: ~/.gemini/antigravity{,-cli}/brain/<id>/{task,implementation_plan,walkthrough}.md
                 plus the agy CLI's prompt log ~/.gemini/antigravity-cli/history.jsonl
                 (conversation steps themselves are protobuf; these are what's readable)

Usage:
  harvest.py /path/to/project [--source claude|pi|codex|gemini|cursor|copilot|antigravity|all] [--include-parents]
             [--max-chars 400000] [--out digest.md]

The digest keeps user prompts, assistant prose, compaction summaries and one-line
tool calls; it drops thinking blocks, tool output and harness bookkeeping.
"""
import argparse
import datetime
import glob
import json
import os
import hashlib
import re
import sqlite3
import sys
from pathlib import Path

HOME = Path.home()
CONTEXT_FILES = ["AGENTS.md", "AGENTS.override.md", "CLAUDE.md", "CLAUDE.local.md", "GEMINI.md",
                 ".cursorrules", ".windsurfrules", ".github/copilot-instructions.md"]

USER_LIMIT = 2500
ASSISTANT_LIMIT = 2000
TOOL_ARG_LIMIT = 200


def clip(text, limit):
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit] + f" …[+{len(text) - limit} chars]"


def clean_user_text(text):
    # Harness-injected wrappers carry no project knowledge.
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.S)
    text = re.sub(r"<local-command-(stdout|stderr)>.*?</local-command-\1>", "", text, flags=re.S)
    text = re.sub(r"<command-(message|args)>.*?</command-\1>", "", text, flags=re.S)
    # Keep pasted content, but clip it hard; it is often a long spec.
    text = re.sub(r"<pasted_content[^>]*>(.*?)</pasted_content>",
                  lambda m: "[pasted] " + clip(m.group(1), 1200), text, flags=re.S)
    return text.strip()


def describe_tool(name, args):
    if isinstance(args, dict) and isinstance(args.get("input"), str):
        cmds = re.findall(r'cmd:\s*"((?:[^"\\]|\\.)*)"', args["input"])
        if cmds:
            return f"{name}: " + clip(" ; ".join(c.encode().decode("unicode_escape", "ignore") for c in cmds)
                                      .replace(chr(10), " ⏎ "), TOOL_ARG_LIMIT)
    if not isinstance(args, dict):
        return f"{name}"
    for key in ("command", "cmd", "file_path", "path", "pattern", "url", "query", "skill", "description", "prompt"):
        if key in args and args[key]:
            val = args[key]
            if isinstance(val, list):
                val = " ".join(map(str, val))
            return f"{name}: {clip(str(val).replace(chr(10), ' ⏎ '), TOOL_ARG_LIMIT)}"
    return f"{name}: {clip(json.dumps(args), TOOL_ARG_LIMIT)}"


def touched_path(name, args):
    if isinstance(args, dict) and name.lower() in ("edit", "write", "multiedit", "notebookedit", "apply_patch"):
        return args.get("file_path") or args.get("path")
    return None


# ---------- per-harness readers: each yields (timestamp, role, text) and collects files ----------

def read_claude(path, files):
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        t = e.get("type")
        ts = e.get("timestamp", "")
        if t == "summary" and e.get("summary"):
            yield ts, "summary", e["summary"]
            continue
        if t not in ("user", "assistant") or e.get("isSidechain") or e.get("isMeta"):
            continue
        if e.get("isCompactSummary"):
            content = e["message"].get("content")
            text = content if isinstance(content, str) else " ".join(
                b.get("text", "") for b in content if isinstance(b, dict))
            yield ts, "summary", text
            continue
        content = e.get("message", {}).get("content")
        if isinstance(content, str):
            text = clean_user_text(content) if t == "user" else content
            if text:
                yield ts, t, text
            continue
        for b in content or []:
            bt = b.get("type")
            if bt == "text" and b.get("text", "").strip():
                text = clean_user_text(b["text"]) if t == "user" else b["text"]
                if text:
                    yield ts, t, text
            elif bt == "tool_use":
                p = touched_path(b.get("name", ""), b.get("input"))
                if p:
                    files.add(p)
                yield ts, "tool", describe_tool(b.get("name", "?"), b.get("input"))
            elif bt == "tool_result" and b.get("is_error"):
                c = b.get("content")
                c = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c or [] if isinstance(x, dict))
                yield ts, "tool-error", clip(c, 300)


def read_pi(path, files):
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = e.get("timestamp", "")
        if e.get("type") in ("compaction", "branch_summary") and e.get("summary"):
            yield ts, "summary", e["summary"]
            continue
        if e.get("type") != "message":
            continue
        m = e["message"]
        role = m.get("role")
        content = m.get("content")
        if role == "user":
            text = content if isinstance(content, str) else " ".join(
                b.get("text", "") for b in content or [] if b.get("type") == "text")
            text = clean_user_text(text)
            if text:
                yield ts, "user", text
        elif role == "assistant":
            for b in content or []:
                bt = b.get("type")
                if bt == "text" and b.get("text", "").strip():
                    yield ts, "assistant", b["text"]
                elif bt in ("toolCall", "tool_use", "toolUse"):
                    args = b.get("arguments") or b.get("input") or {}
                    p = touched_path(b.get("name", ""), args)
                    if p:
                        files.add(p)
                    yield ts, "tool", describe_tool(b.get("name", "?"), args)
        elif role == "toolResult" and m.get("isError"):
            text = " ".join(b.get("text", "") for b in content or [] if b.get("type") == "text")
            yield ts, "tool-error", clip(text, 300)


def read_codex(path, _files):
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = e.get("timestamp", "")
        p = e.get("payload", {})
        if e.get("type") != "response_item":
            continue
        if p.get("type") == "message":
            role = p.get("role")
            text = " ".join(b.get("text", "") for b in p.get("content", []) if isinstance(b, dict))
            if role == "user":
                text = clean_user_text(text)
                if text and not text.startswith("<environment_context>") and not text.startswith("<user_instructions>"):
                    yield ts, "user", text
            elif role == "assistant" and text.strip():
                yield ts, "assistant", text
        elif p.get("type") in ("function_call", "local_shell_call", "custom_tool_call"):
            args = p.get("arguments") or p.get("action") or p.get("input") or {}
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {"input": args}
            yield ts, "tool", describe_tool(p.get("name", "shell"), args)


def read_gemini(path, files):
    # Entries are re-emitted as they stream; the last copy of each id wins.
    entries = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("id") and e.get("type") in ("user", "gemini", "info", "error"):
            entries[e["id"]] = e
    for e in entries.values():
        ts = e.get("timestamp", "")
        content = e.get("content")
        text = content if isinstance(content, str) else " ".join(
            b.get("text", "") for b in content or [] if isinstance(b, dict))
        if e["type"] == "user":
            text = clean_user_text(text)
            if text:
                yield ts, "user", text
        elif e["type"] == "gemini":
            if text.strip():
                yield ts, "assistant", text
            for tc in e.get("toolCalls") or []:
                args = tc.get("args") or {}
                p = touched_path({"write_file": "write", "replace": "edit"}.get(tc.get("name"), ""), args)
                if p:
                    files.add(p)
                yield ts, "tool", describe_tool(tc.get("name", "?"), args)
                if tc.get("status") == "error":
                    yield ts, "tool-error", clip(json.dumps(tc.get("result", ""))[:300], 300)


def read_cursor(key, files):
    db, composer = key.rsplit("#", 1)
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    row = con.execute("select value from cursorDiskKV where key=?", (f"composerData:{composer}",)).fetchone()
    if not row or not row[0]:
        return
    data = json.loads(row[0])
    ts = datetime.datetime.fromtimestamp((data.get("createdAt") or 0) / 1000).isoformat()
    if data.get("name"):
        yield ts, "summary", f"Chat title: {data['name']}"
    for h in data.get("fullConversationHeadersOnly") or []:
        b = con.execute("select value from cursorDiskKV where key=?",
                        (f"bubbleId:{composer}:{h['bubbleId']}",)).fetchone()
        if not b or not b[0]:
            continue
        bubble = json.loads(b[0])
        text = bubble.get("text") or ""
        if bubble.get("type") == 1:
            if text.strip():
                yield ts, "user", clean_user_text(text)
            continue
        if text.strip():
            yield ts, "assistant", text
        tool = bubble.get("toolFormerData") or {}
        if tool.get("name"):
            try:
                args = json.loads(tool.get("rawArgs") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {"input": tool.get("rawArgs")}
            if tool["name"] in ("edit_file", "write", "search_replace") and args.get("target_file"):
                files.add(args["target_file"])
            yield ts, "tool", describe_tool(tool["name"], {"path": args.get("target_file"), **args})


def load_copilot_session(path):
    if path.endswith(".json"):
        return json.load(open(path, encoding="utf-8"))
    # Newer VS Code writes .jsonl: a kind-0 snapshot followed by patches. Use the snapshot
    # and append any whole requests added by later patches (best effort).
    session = {}
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("kind") == 0:
            session = e.get("v") or {}
        elif isinstance(e.get("v"), list) and e.get("k") == ["requests"]:
            session.setdefault("requests", []).extend(x for x in e["v"] if isinstance(x, dict))
    return session


def read_copilot(path, files):
    try:
        session = load_copilot_session(path)
    except (OSError, json.JSONDecodeError):
        return
    for req in session.get("requests") or []:
        ts = datetime.datetime.fromtimestamp((req.get("timestamp") or 0) / 1000).isoformat()
        text = (req.get("message") or {}).get("text", "")
        if text.strip():
            yield ts, "user", clean_user_text(text)
        prose = []
        for part in req.get("response") or []:
            kind = part.get("kind")
            if kind in (None, "markdownContent") and isinstance(part.get("value"), str):
                prose.append(part["value"])
            elif kind == "toolInvocationSerialized":
                if prose and "".join(prose).strip(" `\n"):
                    yield ts, "assistant", "".join(prose)
                prose = []
                msg = part.get("invocationMessage")
                msg = msg.get("value", "") if isinstance(msg, dict) else (msg or "")
                yield ts, "tool", f"{part.get('toolId', '?')}: {clip(str(msg), TOOL_ARG_LIMIT)}"
            elif kind == "textEditGroup" and isinstance(part.get("uri"), dict):
                files.add(part["uri"].get("path") or part["uri"].get("fsPath", ""))
        if prose and "".join(prose).strip(" `\n"):
            yield ts, "assistant", "".join(prose)


ANTIGRAVITY_ARTIFACTS = ("task.md", "implementation_plan.md", "walkthrough.md")


def read_antigravity(brain_dir, _files):
    if "history.jsonl#" in brain_dir:
        yield from read_agy_history(brain_dir)
        return
    for name in ANTIGRAVITY_ARTIFACTS:
        f = Path(brain_dir) / name
        if not f.is_file():
            continue
        ts = ""
        meta = f.with_name(name + ".metadata.json")
        if meta.is_file():
            try:
                ts = json.loads(meta.read_text()).get("updatedAt", "")
            except json.JSONDecodeError:
                pass
        yield ts, "summary", f"[{name}]\n" + f.read_text(errors="replace")


def read_agy_history(key):
    path, workspace = key.rsplit("#", 1)
    for line in open(path, encoding="utf-8", errors="replace"):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:
            continue
        if e.get("workspace") == workspace and e.get("type") != "slash_command" and e.get("display"):
            ts = datetime.datetime.fromtimestamp(e.get("timestamp", 0) / 1000).isoformat()
            yield ts, "user", e["display"]


# ---------- session discovery ----------

def claude_slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def pi_slug(path):
    return "--" + re.sub(r"[/\\:]", "-", str(path).lstrip("/")) + "--"


def candidate_dirs(project, include_parents):
    dirs = [project]
    if include_parents:
        dirs += [p for p in project.parents if p != Path("/") and p != HOME and p != HOME.parent]
    return dirs


def cursor_user_dirs():
    return [HOME / ".config/Cursor/User", HOME / "Library/Application Support/Cursor/User",
            HOME / "AppData/Roaming/Cursor/User"]


def vscode_user_dirs():
    bases = [HOME / ".config", HOME / "Library/Application Support", HOME / "AppData/Roaming"]
    return [b / v / "User" for b in bases for v in ("Code", "Code - Insiders", "VSCodium")]


def find_sessions(project, source, include_parents):
    found = []  # (harness, path-or-key, cwd)
    for d in candidate_dirs(project, include_parents):
        if source in ("claude", "all"):
            for f in glob.glob(str(HOME / ".claude/projects" / claude_slug(d) / "*.jsonl")):
                found.append(("claude", f, d))
        if source in ("pi", "all"):
            for f in glob.glob(str(HOME / ".pi/agent/sessions" / pi_slug(d) / "*.jsonl")):
                found.append(("pi", f, d))
    if source in ("codex", "all"):
        targets = {str(d) for d in candidate_dirs(project, include_parents)}
        for f in glob.glob(str(HOME / ".codex/sessions/**/rollout-*.jsonl"), recursive=True):
            try:
                first = json.loads(open(f, encoding="utf-8").readline())
                cwd = first.get("payload", {}).get("cwd")
            except Exception:
                continue
            if cwd in targets:
                found.append(("codex", f, Path(cwd)))
    if source in ("gemini", "all"):
        try:
            names = json.loads((HOME / ".gemini/projects.json").read_text()).get("projects", {})
        except (OSError, json.JSONDecodeError):
            names = {}
        for d in candidate_dirs(project, include_parents):
            # Newer Gemini CLI uses a short name from projects.json; older builds a sha256 of the path.
            for sub in {names.get(str(d)), hashlib.sha256(str(d).encode()).hexdigest()} - {None}:
                for f in glob.glob(str(HOME / ".gemini/tmp" / sub / "chats" / "*.json*")):
                    found.append(("gemini", f, d))
    if source in ("cursor", "all"):
        targets = {Path(d).as_uri(): d for d in candidate_dirs(project, include_parents)}
        for udir in cursor_user_dirs():
            gdb = udir / "globalStorage/state.vscdb"
            for wj in glob.glob(str(udir / "workspaceStorage/*/workspace.json")):
                try:
                    folder = json.loads(open(wj).read()).get("folder")
                    if folder not in targets:
                        continue
                    con = sqlite3.connect(f"file:{Path(wj).with_name('state.vscdb')}?mode=ro", uri=True)
                    row = con.execute("select value from ItemTable where key='composer.composerData'").fetchone()
                except (OSError, json.JSONDecodeError, sqlite3.Error):
                    continue
                for c in json.loads(row[0]).get("allComposers", []) if row else []:
                    found.append(("cursor", f"{gdb}#{c['composerId']}", targets[folder]))
    if source in ("copilot", "all"):
        targets = {Path(d).as_uri(): d for d in candidate_dirs(project, include_parents)}
        for udir in vscode_user_dirs():
            for wj in glob.glob(str(udir / "workspaceStorage/*/workspace.json")):
                try:
                    folder = json.loads(open(wj).read()).get("folder")
                except (OSError, json.JSONDecodeError):
                    continue
                if folder in targets:
                    for f in glob.glob(str(Path(wj).parent / "chatSessions/*.json*")):
                        found.append(("copilot", f, targets[folder]))
    if source in ("antigravity", "all"):
        # Artifacts are matched by the file links inside them. Only the project itself
        # counts: every artifact under a parent like /ssd would link "into" it.
        uri = project.as_uri() + "/"
        for bd in glob.glob(str(HOME / ".gemini/antigravity*/brain/*")):
            text = "".join((Path(bd) / n).read_text(errors="replace")
                           for n in ANTIGRAVITY_ARTIFACTS if (Path(bd) / n).is_file())
            if uri in text:
                found.append(("antigravity", bd, project))
        hist = HOME / ".gemini/antigravity-cli/history.jsonl"
        if hist.is_file():
            text = hist.read_text(errors="replace")
            for d in candidate_dirs(project, include_parents):
                if f'"workspace":"{d}"' in text:
                    found.append(("antigravity", f"{hist}#{d}", d))
    found.sort(key=lambda x: session_mtime(x[1]))
    return found


def session_mtime(key):
    path = key.rsplit("#", 1)[0] if ("state.vscdb#" in key or "history.jsonl#" in key) else key
    return os.path.getmtime(path)


def mentions_project(path, project):
    needle = project.name
    if "state.vscdb#" in path or "history.jsonl#" in path or os.path.isdir(path):
        return True
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return needle in fh.read()
    except OSError:
        return False


# ---------- main ----------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("project")
    ap.add_argument("--source", default="all", choices=["claude", "pi", "codex", "gemini", "cursor", "copilot", "antigravity", "all"])
    ap.add_argument("--include-parents", action="store_true",
                    help="also scan sessions started in ancestor dirs that mention the project")
    ap.add_argument("--max-chars", type=int, default=400_000,
                    help="cap on digest size; oldest turns are trimmed first")
    ap.add_argument("--out", help="write digest here instead of stdout")
    a = ap.parse_args()

    project = Path(a.project).expanduser().resolve()
    out = []
    out.append(f"# Harness context digest: `{project}`\n")

    # 1. Context/instruction files already on disk
    out.append("## Instruction files found\n")
    any_ctx = False
    for d in [project] + [p for p in project.parents if p != Path("/")]:
        for name in CONTEXT_FILES:
            f = d / name
            if f.is_file():
                any_ctx = True
                out.append(f"### {f}\n```\n{clip(f.read_text(errors='replace'), 6000)}\n```\n")
    for f in [HOME / ".claude/CLAUDE.md", HOME / ".pi/agent/AGENTS.md", HOME / ".codex/AGENTS.md",
              HOME / ".gemini/GEMINI.md"]:
        if f.is_file():
            any_ctx = True
            out.append(f"### {f} (user-global)\n```\n{clip(f.read_text(errors='replace'), 3000)}\n```\n")
    if not any_ctx:
        out.append("_none_\n")

    # 2. Claude Code auto-memory
    mem_files = sorted(glob.glob(str(HOME / ".claude/projects" / claude_slug(project) / "memory" / "*.md")))
    out.append("## Claude Code project memory\n")
    if mem_files:
        for f in mem_files:
            out.append(f"### {f}\n```\n{clip(Path(f).read_text(errors='replace'), 4000)}\n```\n")
    else:
        out.append("_none_\n")

    # 3. Project-scoped harness config worth porting
    out.append("## Project harness config\n")
    cfg = []
    for rel in (".claude/settings.json", ".claude/settings.local.json", ".mcp.json", ".claude/commands",
                ".claude/agents", ".claude/skills", ".pi/settings.json", ".pi/skills", ".agents/skills",
                ".codex/config.toml", ".cursor/rules", ".cursor/skills", ".cursor/mcp.json",
                ".gemini/settings.json", ".gemini/skills", ".agents/rules", ".agents/workflows",
                ".agents/mcp_config.json", ".github/copilot-instructions.md", ".github/instructions",
                ".github/prompts", ".vscode/mcp.json"):
        p = project / rel
        if p.exists():
            cfg.append(f"- `{p}`" + (f" ({', '.join(sorted(os.listdir(p)))})" if p.is_dir() else ""))
    out.append("\n".join(cfg) + "\n" if cfg else "_none_\n")

    # 4. Sessions
    sessions = find_sessions(project, a.source, a.include_parents)
    sessions = [s for s in sessions if s[2] == project or mentions_project(s[1], project)]
    readers = {"claude": read_claude, "pi": read_pi, "codex": read_codex, "gemini": read_gemini,
               "cursor": read_cursor, "copilot": read_copilot, "antigravity": read_antigravity}
    files_touched = set()
    skills_used = set()
    blocks = []
    seen = set()
    for harness, path, cwd in sessions:
        lines = []
        for _ts, role, text in readers[harness](path, files_touched):
            if role in ("user", "assistant", "summary") and len(text) > 40:
                key = (role, text)
                if key in seen:
                    continue
                seen.add(key)
            if role == "tool" and text.lower().startswith("skill:"):
                skills_used.add(text.split(":", 1)[1].strip())
            limit = USER_LIMIT if role in ("user", "summary") else ASSISTANT_LIMIT
            if harness == "antigravity":
                limit = 6000
            prefix = {"user": "**USER**", "assistant": "**AGENT**",
                      "summary": "**ARTIFACT**" if harness == "antigravity" else "**SUMMARY**",
                      "tool": "  ↳", "tool-error": "  ✗ tool error:"}[role]
            body = clip(text, limit) if role not in ("tool",) else text
            lines.append(f"{prefix} {body}")
        if lines:
            hdr = f"### [{harness}] {Path(path).name}  (cwd: {cwd}, modified: " \
                  f"{datetime.datetime.fromtimestamp(session_mtime(path)):%Y-%m-%d %H:%M})"
            blocks.append(hdr + "\n\n" + "\n\n".join(lines) + "\n")

    out.append(f"## Sessions ({len(blocks)} with content, oldest first)\n")
    if skills_used:
        out.append("Skills invoked: " + ", ".join(sorted(skills_used)) + "\n")
    if files_touched:
        out.append("Files edited/written:\n" + "\n".join(f"- {f}" for f in sorted(files_touched)) + "\n")

    head = "\n".join(out)
    budget = a.max_chars - len(head)
    body = "\n".join(blocks)
    if len(body) > budget > 0:
        body = f"_…{len(body) - budget} chars of older history trimmed; rerun with a larger --max-chars to see it…_\n\n" \
               + body[-budget:]
    digest = head + "\n" + body

    if a.out:
        Path(a.out).write_text(digest, encoding="utf-8")
        print(f"wrote {a.out}: {len(digest):,} chars, {len(blocks)} sessions", file=sys.stderr)
    else:
        sys.stdout.write(digest)


if __name__ == "__main__":
    main()
