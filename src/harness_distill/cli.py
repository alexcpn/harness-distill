"""Command line for harness-distill.

  harness-distill install     install the skill, plus session-start hooks so it runs by itself
  harness-distill uninstall   remove the skill copies and hooks made by install
  harness-distill check       is this project's distilled context missing or behind? (used by hooks)
  harness-distill harvest …   run the session harvester (same flags as scripts/harvest.py)
"""
import argparse
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

from . import __version__

SKILL_NAME = "harness-distill"
HOME = Path.home()
TARGETS = {
    # ~/.agents/skills is scanned by pi, Codex, Gemini CLI, Cursor, Copilot and Antigravity.
    "agents": HOME / ".agents/skills",
    "claude": HOME / ".claude/skills",
}
HOOK_MARK = "harness_distill.cli check"
CLAUDE_SETTINGS = HOME / ".claude/settings.json"
CODEX_HOOKS = HOME / ".codex/hooks.json"
PI_EXTENSION = HOME / ".pi/agent/extensions/harness-distill.ts"


def skill_source():
    packaged = Path(__file__).parent / "skill"
    if (packaged / "SKILL.md").is_file():
        return packaged
    # Editable/dev install: the skill lives at the repo root.
    return Path(__file__).resolve().parents[2]


def harvester():
    return runpy.run_path(str(skill_source() / "scripts/harvest.py"))


def chosen_targets(name):
    return TARGETS.items() if name == "all" else [(name, TARGETS[name])]


# ---------- hooks ----------

def hook_command(hook, mode):
    # Absolute interpreter path: hooks often run without the user's PATH.
    return f'"{sys.executable}" -m harness_distill.cli check --hook {hook} --mode {mode}'


def _load_json(path):
    if not path.exists():
        return {}
    return json.loads(path.read_text() or "{}")


def _strip_ours(entries):
    kept = []
    for entry in entries or []:
        hooks = [h for h in entry.get("hooks", []) if HOOK_MARK not in h.get("command", "")]
        if hooks:
            kept.append({**entry, "hooks": hooks})
    return kept


def _set_session_start(path, command, extra):
    """Add (or replace) our SessionStart hook in a Claude Code / Codex style hooks file."""
    try:
        data = _load_json(path)
    except json.JSONDecodeError:
        return f"skip  {path} is not valid JSON; add the hook by hand"
    hooks = data.setdefault("hooks", {})
    entries = _strip_ours(hooks.get("SessionStart"))
    if command:
        entries.append({"matcher": "startup|clear",
                        "hooks": [{"type": "command", "command": command, "timeout": 30, **extra}]})
    if entries:
        hooks["SessionStart"] = entries
    else:
        hooks.pop("SessionStart", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")
    return None


PI_EXTENSION_SOURCE = """\
// Installed by `harness-distill install`. Remove with `harness-distill uninstall`.
// At session start, asks harness-distill whether this project's AGENTS.md/HANDOFF.md is missing
// or behind, and if so adds a one-time note to the system prompt.
import { execFileSync } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PYTHON = __PYTHON__;
const MODE = __MODE__;

export default function harnessDistill(pi: ExtensionAPI) {
\tlet note = "";
\tpi.on("session_start", async (_event, ctx) => {
\t\tif (process.env.HARNESS_DISTILL_HOOK === "off") return;
\t\ttry {
\t\t\tnote = execFileSync(PYTHON, ["-m", "harness_distill.cli", "check", "--hook", "plain", "--mode", MODE, "--path", ctx.cwd],
\t\t\t\t{ encoding: "utf8", timeout: 20000 }).trim();
\t\t} catch {
\t\t\tnote = "";
\t\t}
\t});
\tpi.on("before_agent_start", async (event) => {
\t\tif (!note) return;
\t\tconst text = note;
\t\tnote = "";
\t\treturn { systemPrompt: event.systemPrompt + "\\n\\n" + text };
\t});
}
"""


def install_hooks(mode):
    out = []
    err = _set_session_start(CLAUDE_SETTINGS, hook_command("claude", mode), {})
    out.append(err or f"ok    hook    Claude Code  {CLAUDE_SETTINGS}")
    err = _set_session_start(CODEX_HOOKS, hook_command("codex", mode),
                             {"statusMessage": "harness-distill: checking project memory"})
    out.append(err or f"ok    hook    Codex        {CODEX_HOOKS}")
    PI_EXTENSION.parent.mkdir(parents=True, exist_ok=True)
    PI_EXTENSION.write_text(PI_EXTENSION_SOURCE.replace("__PYTHON__", json.dumps(sys.executable))
                            .replace("__MODE__", json.dumps(mode)))
    out.append(f"ok    hook    pi           {PI_EXTENSION}")
    return out


def uninstall_hooks():
    out = []
    for path in (CLAUDE_SETTINGS, CODEX_HOOKS):
        if path.exists():
            err = _set_session_start(path, None, {})
            out.append(err or f"gone  hook    {path}")
    if PI_EXTENSION.exists():
        PI_EXTENSION.unlink()
        out.append(f"gone  hook    {PI_EXTENSION}")
    return out


# ---------- commands ----------

def install(args):
    src = skill_source()
    for label, root in chosen_targets(args.target):
        dest = root / SKILL_NAME
        if dest.is_symlink():
            if not args.force:
                print(f"skip  {dest} is a symlink (to {dest.resolve()}); use --force to replace it")
                continue
            dest.unlink()
        elif dest.exists():
            shutil.rmtree(dest)
        root.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dest, ignore=shutil.ignore_patterns(
            "__pycache__", "*.pyc", ".git", "src", "pyproject.toml", "uv.lock", ".github",
            "dist", "AGENTS.md", "CLAUDE.md", ".agents"))
        print(f"ok    skill   {label:<12} {dest}")
    if args.no_hooks:
        print("Hooks not installed: run the skill yourself (`/harness-distill .` in Claude Code).")
        return
    for line in install_hooks(args.mode):
        print(line)
    print(f"\nAutomatic mode is on ({args.mode}). When you start Claude Code, Codex or pi in a project, it checks\n"
          "whether the project's AGENTS.md/HANDOFF.md is missing or behind and has the agent "
          + ("refresh it." if args.mode == "auto" else "offer to refresh it.")
          + "\nCodex asks you to trust new hooks once: open `codex` and run /hooks to approve it.\n"
          "Cursor, Copilot and Antigravity follow the same rule from AGENTS.md once it exists.\n"
          "Turn off for one run with HARNESS_DISTILL_HOOK=off, or remove with `harness-distill uninstall`.")


def uninstall(args):
    for label, root in chosen_targets(args.target):
        dest = root / SKILL_NAME
        if dest.is_symlink():
            print(f"skip  {dest} is a symlink you created; remove it by hand if intended")
        elif dest.exists():
            shutil.rmtree(dest)
            print(f"gone  skill   {label:<12} {dest}")
    for line in uninstall_hooks():
        print(line)


def check_cmd(args):
    """Never fails loudly: a broken check must not break the user's session start."""
    if os.environ.get("HARNESS_DISTILL_HOOK") == "off":
        return
    payload = {}
    if args.hook in ("claude", "codex") and not sys.stdin.isatty():
        try:
            payload = json.loads(sys.stdin.read() or "{}")
        except (ValueError, OSError):
            payload = {}
    path = args.path or payload.get("cwd") or os.getcwd()
    try:
        note = harvester()["check"](path, exclude=[payload.get("transcript_path")], mode=args.mode)
    except Exception:  # noqa: BLE001
        return
    if not note:
        return
    if args.hook in ("claude", "codex"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": note}}))
    else:
        print(note)


def harvest(rest):
    script = skill_source() / "scripts/harvest.py"
    sys.argv = [str(script)] + rest
    runpy.run_path(str(script), run_name="__main__")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # Hand everything after `harvest` to the harvester untouched, so its own --help works.
    if argv[:1] == ["harvest"]:
        return harvest(argv[1:])

    ap = argparse.ArgumentParser(prog="harness-distill", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("install", help="install the skill and session-start hooks")
    p.add_argument("--target", choices=["all", *TARGETS], default="all")
    p.add_argument("--force", action="store_true", help="replace an existing symlink")
    p.add_argument("--no-hooks", action="store_true", help="skill only; never run automatically")
    p.add_argument("--mode", choices=["auto", "ask"], default="auto",
                   help="auto: refresh without asking (default); ask: the agent offers first")
    p.set_defaults(fn=install)

    p = sub.add_parser("uninstall", help="remove installed copies and hooks")
    p.add_argument("--target", choices=["all", *TARGETS], default="all")
    p.set_defaults(fn=uninstall)

    p = sub.add_parser("check", help="report whether the project's distilled context is missing or behind")
    p.add_argument("--path", help="project folder (default: hook payload cwd, then the current dir)")
    p.add_argument("--hook", choices=["claude", "codex", "plain"], default="plain")
    p.add_argument("--mode", choices=["auto", "ask"], default="auto")
    p.set_defaults(fn=check_cmd)

    sub.add_parser("harvest", help="build a session digest for a project (see `harvest --help`)")
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
