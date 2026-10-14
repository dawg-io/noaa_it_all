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
- Pull requests into this repository's `main` are squash-merged, so the PR title and commit
  messages become the commit on `main`. Keep them free of attribution as well.

## Versions

Every pull request with a fix or a feature updates the version in the same pull request, so `main`
is always ready to release. Changes to docs, tests or CI alone don't.

- The version is in `custom_components/noaa_it_all/manifest.json`. The last release is the latest
  `vX.Y.Z` tag in `dawg-io/noaa_it_all`.
- If the version on `main` is that tag, bump it: the patch number for a fix (0.7.3 → 0.7.4), the
  minor number for a feature (0.7.3 → 0.8.0). If `main` already has a newer, untagged version, it
  is still open: add to it, and raise a pending patch bump to the next minor only when the pull
  request adds a feature.
- Head the top section of `CHANGELOG.md` with that version, `## [X.Y.Z]`, instead of
  `## [Unreleased]`, and list the change there under Added, Changed or Fixed.

## Documentation

`docs/*.md` is the documentation, written as plain GitHub Markdown with relative links, and
`tests/test_docs.py` checks those links. `website/` builds it into a Starlight site:
`npm run build` there runs `scripts/sync-docs.mjs`, which copies `docs/` into
`website/src/content/docs/` (generated and git-ignored, so never edit it), then builds `website/dist/`.

- A new page in `docs/` needs an entry in `SIDEBAR` in `website/site.mjs`, or the build fails.
- `.github/workflows/docs-pages.yml` builds the site and checks its links whenever `docs/` or
  `website/` changes. It deploys to GitHub Pages only from the public repository's `main`, at
  `https://dawg-io.github.io/noaa_it_all/`, which the README and `info.md` link to.

## Releasing to public

This repository (`turbo5000c/dev-noaa_it_all`) is a fork of the public repository
`dawg-io/noaa_it_all`. A release to public is a pull request from this repository's `main` into
the public repository's `staging` branch.

When asked for a "release to public":

1. Attach the public repository with `add_repo` (owner `dawg-io`, repo `noaa_it_all`, access
   `push`) so the GitHub tools can open a pull request there. If access is refused, stop and
   report the reason.
2. Check the release before opening anything:
   - `main` here has commits that `dawg-io/noaa_it_all:staging` does not.
   - The version in `custom_components/noaa_it_all/manifest.json` is newer than the latest
     `vX.Y.Z` tag in the public repository. A version that is already on the public `main` but
     not tagged is still open, so more changes can ship under it without a bump.
   - The top section of `CHANGELOG.md` is for that version and covers everything being released.
   - If either is off, stop and say what needs to change. Version bumps go through a normal pull
     request into this repository's `main` first.
   - flake8 (`--max-line-length=120`) and pytest pass on `main`.
3. Open a **draft** pull request in `dawg-io/noaa_it_all` with head `turbo5000c:main` and base
   `staging`. If one is already open, it already follows `main`, so update its description
   instead of opening another.
   - Title: `Release X.Y.Z: <one-line summary>`.
   - Body: follow `.github/PULL_REQUEST_TEMPLATE.md`, listing the changes since the public `main`
     from `CHANGELOG.md`, grouped by version.
4. hassfest and HACS Validate are disabled in this fork and only run on the public repository.
   Check their results on the release pull request and report any failure.
5. Stop there. The owner merges the release pull request with a merge commit, not a squash, so
   `staging` keeps this repository's history and later releases don't conflict. The `staging` →
   `main` pull request, release branches, tags and GitHub releases are the owner's unless asked.
