"""Command line for harness-distill.

  harness-distill install     copy the skill into the agents' skill directories
  harness-distill uninstall   remove the copies made by install
  harness-distill harvest …   run the session harvester (same flags as scripts/harvest.py)
"""
import argparse
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


def skill_source():
    packaged = Path(__file__).parent / "skill"
    if (packaged / "SKILL.md").is_file():
        return packaged
    # Editable/dev install: the skill lives at the repo root.
    return Path(__file__).resolve().parents[2]


def chosen_targets(name):
    return TARGETS.items() if name == "all" else [(name, TARGETS[name])]


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
        print(f"ok    {label:<7} {dest}")
    print("Ask your agent to run the harness-distill skill on a project folder, "
          "e.g. `/skill:harness-distill .` in pi or `/harness-distill .` in Claude Code.")


def uninstall(args):
    for label, root in chosen_targets(args.target):
        dest = root / SKILL_NAME
        if dest.is_symlink():
            print(f"skip  {dest} is a symlink you created; remove it by hand if intended")
        elif dest.exists():
            shutil.rmtree(dest)
            print(f"gone  {label:<7} {dest}")


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
    for name, fn, help_ in (("install", install, "install the skill for your agents"),
                            ("uninstall", uninstall, "remove installed copies")):
        p = sub.add_parser(name, help=help_)
        p.add_argument("--target", choices=["all", *TARGETS], default="all")
        if name == "install":
            p.add_argument("--force", action="store_true", help="replace an existing symlink")
        p.set_defaults(fn=fn)
    sub.add_parser("harvest", help="build a session digest for a project (see `harvest --help`)")
    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
