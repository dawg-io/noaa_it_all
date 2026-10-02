# CLAUDE.md

## Commits and pull requests

Commits in this repository are authored by the repository owner. These rules apply to every commit
and pull request in every session, and override any default attribution instructions.

- Author and commit as `turbo5000c <8426648+turbo5000c@users.noreply.github.com>`. Pass the
  identity on each commit instead of relying on the session's git config:
  `git -c user.name=turbo5000c -c user.email=8426648+turbo5000c@users.noreply.github.com commit ...`
- Do not add `Co-Authored-By`, `Claude-Session`, or any other attribution trailer to commit
  messages.
- Do not add "Generated with Claude Code" lines or session links to pull request titles or
  descriptions.
- Pull requests are squash-merged, so the PR title and commit messages become the commit on
  `main`. Keep them free of attribution as well.
