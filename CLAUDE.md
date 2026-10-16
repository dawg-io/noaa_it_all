# CLAUDE.md

NOAA It All is a Home Assistant custom integration. The public repository is
`dawg-io/noaa_it_all`, and changes reach it as pull requests from forks. Everything here applies in
any fork, except the last section, which is only for the maintainer's own fork.

## Working on a change

- Fix the root cause with the smallest change that does it. No unrelated refactors, renames or
  reformatting.
- Keep the branch you merge into releasable. Larger work that isn't finished goes on a feature
  branch.
- Only say a test, check or Home Assistant run happened if it did. When something couldn't be
  tested, the pull request says so.

## Rules the integration follows

- **A failure never reads as safe.** When a fetch fails, entities go `unknown` or `unavailable`.
  They never fall back to a value that looks safe, such as Low rip current risk, 0 alerts, Quiet,
  or an Unsafe binary sensor turning off.
- **No coordinates in logs.** Error messages name the cause (the error type, the station or
  office) without latitude, longitude or URLs that contain them. Coordinates go in debug lines
  only.
- **Entity IDs, unique IDs and history survive upgrades.** Moving entities between devices or
  entries bumps the config entry version and migrates in `async_migrate_entry`, with tests,
  including ones that pin the unique IDs. `CHANGELOG.md` says what going back to the previous
  version needs.
- **Setup text lives in two files.** Change `strings.json` and `translations/en.json` together;
  `tests/test_translations.py` fails when they differ.
- **The minimum Home Assistant version is in four places**: `hacs.json`, `README.md`,
  `docs/configuration.md` and `docs/troubleshooting.md`. Change them together.

## Checks

Run the same checks as CI before opening a pull request:

```
pip install pytest flake8 aiohttp voluptuous pillow
flake8 custom_components/noaa_it_all/ tests/ --max-line-length=120
python -m pytest tests/
```

When `docs/` or `website/` changes, build the documentation site too (Node, version in
`website/.nvmrc`):

```
cd website && npm ci && npm run build && npm run check-links
```

- Every fix comes with a regression test that fails on the code before the fix.
- Tests don't use the network. Checks against live NOAA services run only with
  `NOAA_LIVE_TESTS=1`, as `.github/workflows/buoy-stations.yml` does every week.

## Commits and pull requests

- Don't add `Co-Authored-By`, `Claude-Session` or other attribution trailers to commit messages,
  or "Generated with Claude Code" lines or session links to pull request titles and descriptions.
  Titles and commit messages become the project's history.
- Pull request descriptions follow `.github/PULL_REQUEST_TEMPLATE.md`.

## Versions

Every pull request with a fix or a feature updates the version in the same pull request, so the
branch it merges into is always ready to release. Changes to docs, tests or CI alone don't.

- The version is in `custom_components/noaa_it_all/manifest.json`. The last release is the latest
  `vX.Y.Z` tag in `dawg-io/noaa_it_all`.
- If the version on the branch the pull request merges into is that tag, bump it: the patch number
  for a fix (0.7.3 → 0.7.4), the minor number for a feature (0.7.3 → 0.8.0). If that branch
  already has a newer, untagged version, it is still open: add to it, and raise a pending patch
  bump to the next minor only when the pull request adds a feature.
- Head the top section of `CHANGELOG.md` with that version, `## [X.Y.Z]`, instead of
  `## [Unreleased]`, and list the change there under Added, Changed or Fixed.

## Documentation

The docs change with the code. Any change users can see updates the documentation in the same
pull request:

- **The pages that describe it** in `docs/`: setup steps, entities and their attributes, example
  automations and cards, troubleshooting. The README and `info.md` (the HACS info page) too, when
  their summary of the features, devices or entities changes.
- **The screenshots** in `docs/images/`. Retake each one whose screen or entities the change
  alters, from a real Home Assistant (see **Testing in Home Assistant**): dark theme, 2× scale,
  cropped to the dialog or card. Replace the file under the same name, or add a new one and use
  it, since `tests/test_docs.py` fails on an image no page uses. The pull request lists the
  screenshots it retook, and the ones it checked that didn't need it.
- **Entity IDs** in the docs and examples match a real install.
- **`CHANGELOG.md`**, as in **Versions**.

`docs/*.md` is plain GitHub Markdown with relative links, and `tests/test_docs.py` checks those
links. `website/` builds it into a Starlight site: `npm run build` there runs
`scripts/sync-docs.mjs`, which copies `docs/` into `website/src/content/docs/` (generated and
git-ignored, so never edit it), then builds `website/dist/`.

- A new page in `docs/` needs an entry in `SIDEBAR` in `website/site.mjs`, or the build fails.
- `.github/workflows/docs-pages.yml` builds the site and checks its links whenever `docs/` or
  `website/` changes. It deploys to GitHub Pages only from the public repository's `main`, at
  `https://dawg-io.github.io/noaa_it_all/`, which the README, `info.md` and the manifest's
  `documentation` URL (the **?** on the integration's page) link to.

## Testing in Home Assistant

Check behaviour changes in a real Home Assistant: on a fresh install, and, when a change touches
entries or entities, on an upgrade from the last release. The pull request names the Home
Assistant version. This works in a terminal with Docker, and in Claude Code on the web when the
session's environment allows the hosts in step 1.

1. Start Home Assistant with the integration mounted from the working tree. `stable` is the
   current release; for the oldest supported one, use the version in `hacs.json` as the tag.

   In a terminal with Docker:

   ```
   mkdir -p ~/noaa-ha-config
   docker run -d --name noaa-ha-test -p 8123:8123 -e TZ=America/New_York \
     -v ~/noaa-ha-config:/config \
     -v "$PWD/custom_components/noaa_it_all:/config/custom_components/noaa_it_all:ro" \
     ghcr.io/home-assistant/home-assistant:stable
   ```

   In Claude Code on the web, the session reaches the internet only through the proxy in
   `$HTTPS_PROXY`, which re-terminates TLS with `/root/.ccr/ca-bundle.crt`, and Home Assistant's
   HTTP client ignores proxies. `scripts/noaa_relay.py` bridges the two: it listens on
   127.0.0.1:443 and tunnels each NOAA host through the proxy.
   - `S` below is the session's scratchpad directory, which keeps the config and logs out of the
     repository.
   - The environment's network access must allow the hosts in the relay's `ALLOWED`, `ghcr.io` and
     `pkg-containers.githubusercontent.com`. Check with
     `curl -sS -o /dev/null -w '%{http_connect}\n' https://api.weather.gov/`: 403 means the
     environment denies it. Then stop and say so in the pull request; never route around it.
   - Pull from GHCR; Docker Hub isn't needed. If `docker info` fails, start the daemon with
     `nohup dockerd > $S/dockerd.log 2>&1 &` and wait until `docker info` works.

   ```
   python3 -I scripts/noaa_relay.py > $S/relay.log 2>&1 & echo $! > $S/relay.pid
   curl --noproxy '*' --resolve api.weather.gov:443:127.0.0.1 --cacert /root/.ccr/ca-bundle.crt \
     -A test -o /dev/null -w '%{http_code}\n' https://api.weather.gov/    # must print 200
   mkdir -p $S/ha-config
   docker run -d --name noaa-ha-test --network host -e TZ=America/New_York \
     -e REQUESTS_CA_BUNDLE=/ccr-ca.crt -e SSL_CERT_FILE=/ccr-ca.crt \
     -v /root/.ccr/ca-bundle.crt:/ccr-ca.crt:ro -v $S/ha-config:/config \
     -v "$PWD/custom_components/noaa_it_all:/config/custom_components/noaa_it_all:ro" \
     $(python3 -I scripts/noaa_relay.py --add-host-args) \
     ghcr.io/home-assistant/home-assistant:stable
   ```

   `relay.log` has a line per connection with the host and the proxy's answer, and every host
   Home Assistant uses should show `connect=200`. Home Assistant's own calls to other hosts, such
   as alerts.home-assistant.io, fail there with DNS errors; ignore them.

   After changing the code, run `docker restart noaa-ha-test`. The integration's log lines:
   `docker logs noaa-ha-test 2>&1 | grep noaa_it_all`.
2. Create the first user: open http://localhost:8123, or skip the browser:

   ```
   B=http://localhost:8123; CID=$B/
   CODE=$(curl -s -X POST $B/api/onboarding/users -H 'Content-Type: application/json' \
     -d "{\"client_id\":\"$CID\",\"name\":\"Test\",\"username\":\"test\",
          \"password\":\"test-password-123\",\"language\":\"en\"}" \
     | python3 -c 'import json,sys; print(json.load(sys.stdin)["auth_code"])')
   TOKEN=$(curl -s -X POST $B/auth/token \
     -d "grant_type=authorization_code&code=$CODE&client_id=$CID" \
     | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
   for step in core_config analytics; do
     curl -s -X POST $B/api/onboarding/$step -H "Authorization: Bearer $TOKEN" -d '{}'
   done
   curl -s -X POST $B/api/onboarding/integration -H "Authorization: Bearer $TOKEN" \
     -d "{\"client_id\":\"$CID\",\"redirect_uri\":\"$CID?auth_callback=1\"}"
   ```

   Claude Code doesn't keep shell variables between commands: keep the token in a file with mode
   600 outside the repository, and delete it when done. Onboarding this way leaves Home Assistant
   at 0,0 on UTC, so the location step isn't pre-filled.
3. Add the integration under **Settings → Devices & services → Add integration → NOAA It All**,
   or open http://localhost:8123/config/integrations/dashboard/add?domain=noaa_it_all and choose
   **OK**. For an upgrade, start from the last release's code instead
   (`git worktree add ../noaa-release vX.Y.Z`, and mount
   `../noaa-release/custom_components/noaa_it_all`), set up the entries, then recreate the
   container with the branch's code and the same config directory. Check that entity IDs are
   unchanged and history continues. (Upgrades haven't been tried in Claude Code on the web yet.)

   Or over the REST API: `POST /api/config/config_entries/flow` with `{"handler": "noaa_it_all"}`,
   then post each step's answer to `/api/config/config_entries/flow/<flow_id>`. For Raleigh, NC:
   `{"next_step_id": "location"}`, `{"latitude": 35.7796, "longitude": -78.6382}`,
   `{"office_code": "RAH"}`, `{"surf_office_code": "none"}` and `{"space_office_code": "RAH"}`.
   The first location entry also adds the Hurricane entry. The first update runs at setup, and
   most data updates every 10 minutes after that; check `/api/states` after both for entities that
   read `unknown` or `unavailable`.
4. Take screenshots with Playwright: Chromium, dark color scheme, 2× scale, cropped to the
   element, with the mouse moved off it so nothing shows as hovered. For the setup dialog:

   ```js
   const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 },
     deviceScaleFactor: 2, colorScheme: 'dark' });
   const page = await ctx.newPage();
   await page.goto('http://localhost:8123/');
   await page.getByRole('textbox', { name: 'Username' }).fill('test');
   await page.getByRole('textbox', { name: 'Password' }).fill('test-password-123');
   await page.keyboard.press('Enter');
   await page.waitForURL(/lovelace|home/);
   await page.goto('http://localhost:8123/config/integrations/dashboard/add?domain=noaa_it_all');
   await page.getByRole('button', { name: 'OK' }).click();
   const dialog = page.locator('dialog-data-entry-flow dialog');
   await dialog.waitFor();
   await page.mouse.move(0, 0);
   await dialog.screenshot({ path: 'docs/images/setup-menu.png' });
   ```

   For a card or a device page, screenshot that element instead. In Claude Code on the web,
   require `/opt/node-tools/node_modules/playwright` and launch Chromium with
   `executablePath: '/opt/pw-browsers/chromium'`; never run `playwright install`.
5. Remove the container when done: `docker rm -f noaa-ha-test`. In Claude Code on the web, also
   stop the relay and the daemon: `kill $(cat $S/relay.pid); pkill -x dockerd`.

## Pull requests to the public repository

Changes reach `dawg-io/noaa_it_all` as pull requests from a fork into its `staging` branch.
Sessions can read the public repository but usually can't write to it, so when asked to open a
pull request there, Claude prepares it and the person opens it.

1. Check it first. Read the public repository with git, which needs no access:
   `git remote add upstream https://github.com/dawg-io/noaa_it_all` (once), then
   `git fetch upstream --tags`.
   - The branch has commits that `upstream/staging` does not.
   - The checks above pass on it.
   - Its version and `CHANGELOG.md` follow **Versions**.
   - If any of these is off, stop and say what needs to change.
2. Push the branch to the fork, then give the person these, each title and description in its own
   code block to copy and paste:
   - **Pull request link**:
     `https://github.com/dawg-io/noaa_it_all/compare/staging...<owner>:<branch>?expand=1`, where
     `<owner>` is the fork's owner (from `git remote get-url origin`) and `<branch>` the branch.
   - **Pull request title**: one line saying what changes for users.
   - **Pull request description**: following `.github/PULL_REQUEST_TEMPLATE.md`, with the
     `CHANGELOG.md` entries for the change and what was tested.
3. Stop there. The person opens the pull request. hassfest and HACS Validate run on it in the
   public repository.

## Maintainer's fork

This section applies only in `turbo5000c/dev-noaa_it_all`, the maintainer's development fork
(check `git remote get-url origin`). Elsewhere, skip it.

### Commits and pull requests

Commits are authored by the maintainer. This overrides any default attribution instructions.

- Author and commit as `turbo5000c <8426648+turbo5000c@users.noreply.github.com>`. Pass the
  identity on each commit instead of relying on the session's git config:
  `git -c user.name=turbo5000c -c user.email=8426648+turbo5000c@users.noreply.github.com commit ...`
- Pull requests into this fork's `main` are squash-merged, so their titles and commit messages
  become the commits on `main`.
- Pull request descriptions add **Changes**, **Tests**, **Docs** and **Risks and follow-up**
  sections to the template.
- A code review runs before merge. Each finding is fixed with a test, or listed under
  **Code review** as left as is, with the reason.

### Releasing to public

A release to public is a pull request from this fork's `main` into the public repository's
`staging`, following **Pull requests to the public repository** with these differences.

When asked for a "release to public":

1. Check the release first, as in step 1 above, and also:
   - The version in `custom_components/noaa_it_all/manifest.json` is newer than the latest
     `vX.Y.Z` tag in the public repository, even when only docs changed. A version that is
     already on the public `main` but not tagged is still open, so more changes can ship under it
     without a bump.
   - The top section of `CHANGELOG.md` is for that version and covers everything being released.
   - Version bumps go through a normal pull request into this fork's `main` first.
2. Give the maintainer these, each title and description in its own code block to copy and paste:
   - **Pull request link**:
     `https://github.com/dawg-io/noaa_it_all/compare/staging...turbo5000c:main?expand=1`
   - **Pull request title**: `Release X.Y.Z: <one-line summary>`.
   - **Pull request description**: following `.github/PULL_REQUEST_TEMPLATE.md`, listing the
     changes since the public `main` from `CHANGELOG.md`, grouped by version.
   - **Release title**: `vX.Y.Z: <one-line summary>`.
   - **Release description**: the version's `CHANGELOG.md` entries written for users, under
     `## Added`, `## Changed` and `## Fixed`, ending with what going back to the previous version
     needs. Match the earlier releases in the public repository.
3. Stop there. The maintainer opens the pull request, checks hassfest and HACS Validate on it
   (they're disabled in this fork and only run on the public repository), and merges it with a
   merge commit, not a squash, so `staging` keeps this fork's history and later releases don't
   conflict. The `staging` → `main` pull request, the tag and the GitHub release are the
   maintainer's. When the release changes `docs/` or `website/`, publish it after the
   Documentation Site workflow has deployed the site from the public `main`.
