# Security Policy

## Supported versions

Only the latest release on `main` gets security fixes.

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report them privately through GitHub:
**Security → Report a vulnerability** on this repository, or
<https://github.com/alexcpn/harness-distill/security/advisories/new>.

Include what you found, steps to reproduce, and the impact you expect. You
should get an acknowledgement within 7 days. Once a fix is released, the
issue is disclosed in a GitHub security advisory, crediting you unless you
ask not to be named.

## Threat model

harness-distill runs locally and makes no network calls itself. It reads
coding-agent session stores in your home directory and writes files into
the project you point it at. The risks that matter:

- **Secrets in transcripts.** Session history can contain tokens, keys and
  file contents that appeared in tool calls. The digest that `harvest`
  produces is raw material and can include them. Keep it in a temp
  directory, and never commit or share it. The skill tells the agent not to
  copy secrets into `AGENTS.md` or `HANDOFF.md`, but review both files before
  committing.
- **Prompt injection from old sessions.** Transcripts can contain text pasted
  from untrusted sources, such as issues, web pages and logs. The skill
  treats transcript content as data to summarise, never as instructions.
  A distilled file that tells an agent to *do* something you didn't ask for
  is a bug, and we want reports of it.
- **Scope leaks.** Sessions are matched by folder. Unrelated work, other
  repositories or other people's names can end up in the digest.
  `HANDOFF.md` is excluded from git by default for this reason.
- **Local databases.** Cursor and VS Code stores are opened read-only. A way
  to make the harvester write to, lock or corrupt a harness's store is in
  scope.

Out of scope: the security of the harnesses themselves, and of the models
that run the skill.
