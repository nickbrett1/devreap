# devreap

Stop the devcontainers you're **not actually working on** — and close their
VS Code windows — so they stop eating RAM.

It's the sibling of [devopen](https://github.com/nickbrett1/devopen): devopen
opens a project's devcontainer in a VS Code window; devreap closes the ones
you've gone quiet on.

```
[nightly, or whenever you run it]
    devreap
      │ for each running devcontainer
      │ 1. read its devcontainer.local_folder label      → project
      │ 2. ask Buildkite for the last build YOU triggered → days ago
      │ 3. older than 3 days, nobody logged in?          → docker stop
      │ 4. close that project's VS Code window
      ▼
[quiet devcontainers stopped]  [~6 GiB of RAM back]
```

## The signal (why not CPU or memory)

CPU and memory are the wrong measure: you can open a container, wander off,
and it looks *identical* to one you've been driving all day. The honest
signal is **"when did I last trigger a build for this project?"** — that's
when you were actively working in it, and it's the moment you might want to
jump back in. Roughly 3 days of quiet is a good cutoff.

Dependabot must not count. Buildkite makes the distinction easy: every build
carries the *commit author*.

| | human build | Dependabot build |
|---|---|---|
| `author.name` | `Nick Brett` | `dependabot[bot]` |
| `author.email` | `nick@fintechnick.com` | `49699…+dependabot[bot]@users.noreply.github.com` |
| `branch` | `chore/…`, `main` | `dependabot/npm_and_yarn/…` |

So a merge of a Dependabot PR onto `main` still counts as *you* (you're the
author of the merge), while the PR's own builds don't. A UI "Rebuild" counts
too — it has no author but a real `creator`.

devreap treats a build as automated if any of these are true: the author or
creator looks like a bot (`[bot]`, `dependabot`, `renovate`,
`github-actions`), the branch starts with `dependabot/` or `renovate/`, the
message carries a Dependabot sign-off, or `source == "schedule"`. Being
wrong here only ever makes it *more* reluctant to reap.

## What it will and won't do

- **Stops, never removes.** `docker stop` keeps the container *and* its
  volumes. `docker start` (or reopening from devopen/VS Code) brings it
  straight back — you lose the RAM it held, nothing else.
- **Only touches devcontainers.** Anything carrying a
  `devcontainer.local_folder` label. Watchtower, dozzle and the buildx
  builder daemons are invisible to it.
- **Vetoes a live terminal session.** If `who` shows a login, a tmux client
  is attached, or there's an established ssh connection, it's left alone.
  (An open VS Code window is deliberately *not* a veto — windows stay open
  for days; if they counted, nothing would ever be reaped.)
- **Never reaps a container younger than 12h.** Even if the project has been
  quiet for days, a container started in the last 12 hours is one you just
  opened — `min_container_age_hours` (default 12, set `0` to disable).
- **Closes the VS Code window** it leaves behind (see below).
- **Keeps everything it's unsure about.** No Buildkite token, no pipeline, no
  history → `keep`.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/nickbrett1/devreap/main/install.py | python3
```

That clones to `~/DevOpen/devreap`, installs `/usr/local/bin/devreap`, writes
`~/.devreap/config.json` (mode 600), and loads the nightly LaunchAgent.

## Configure

`~/.devreap/config.json`:

```json
{
  "install_dir": "/Users/you/DevOpen/devreap",
  "workspaces_dir": "/Users/you/DevOpen/workspaces",
  "buildkite_org": "nick-brett",
  "buildkite_token": "",
  "days": 3,
  "min_container_age_hours": 12,
  "close_windows": true,
  "keep": [],
  "ignore": [],
  "pipeline_map": {},
  "unknown_policy": "keep"
}
```

- **`buildkite_token`** — a **read-only** Buildkite API token (scopes:
  `read_builds`, `read_pipelines`). The agent token in
  `/opt/homebrew/etc/buildkite-agent/buildkite-agent.cfg` will *not* work —
  it's job-scoped. Without a token devreap keeps everything.
  (`BUILDKITE_API_TOKEN` in the environment overrides it.)
- **`days`** — the quiet threshold. Default 3.
- **`min_container_age_hours`** — rail: never reap a container that started
  less than this many hours ago. Default **12**, which covers "I opened it a
  few minutes ago and haven't triggered a build yet" — the case the
  time-since-last-build signal can't see. Set `0` to disable.
- **`close_windows`** — close the workspace's VS Code window after stopping.
- **`keep` / `ignore`** — workspace names to always keep, or to not even look
  at. No project is special-cased out of the box.
- **`pipeline_map`** — workspace name → Buildkite pipeline slug, when they
  differ. By default the container's workspace basename *is* the pipeline
  slug, which happens to match every repo here.

## Use

```bash
devreap                    # do it
devreap --dry-run          # show the table, touch nothing
devreap --days 5           # quieter threshold for this run
devreap --only ftn         # just one project
devreap --no-close-windows # stop containers, leave windows alone
devreap --json             # machine-readable decisions
devreap --list-windows     # diagnostic: can we see VS Code windows at all?
```

Dry run:

```
devreap — dry run (threshold: 3 days)

WORKSPACE              PIPELINE    LAST HUMAN BUILD                AGE    VERDICT  WHY
---------------------  ----------  ------------------------------  -----  -------  ---------------------------
a2a-goose              a2a-goose   #12 (Nick Brett, main)          6.2d   REAP     quiet 6.2d (> 3d)
ftn                    ftn         #194 (Nick Brett, main)         0.1d   KEEP     active — last human build 2.4h ago
netwatch-dash          netwatch-dash  #8 (Nick Brett, main)        1.0d   KEEP     active — last human build 1.0d ago
pshelf                 pshelf      #5 (Nick Brett, main)           6.1d   KEEP     live session (login: node pts/0)

4 container(s) would be stopped.
```

## Closing the VS Code window

devopen opens a window with a host-path URI
(`vscode-remote://dev-container+<hex-json>/…`). Closing it is the one part
that isn't a clean API call: **VS Code implements no AppleScript suite** —
`tell application "Visual Studio Code" to count windows` just times out — so
devreap goes through System Events: it reads the window titles, matches the
one whose title contains the workspace name (whole-token, so
`galactic-unicorn` never matches `galactic-unicorn-remote`), and clicks its
close button (falling back to ⌘W).

That needs two things:

1. **Accessibility permission** for whatever runs devreap — Terminal when you
   run it by hand, and the LaunchAgent (`/usr/local/bin/devreap`) for the
   nightly run. System Settings → Privacy & Security → Accessibility.
2. **A GUI login session.** Run from a daemon/headless context it will see no
   windows.

Check with `devreap --list-windows`. If it prints nothing, the permission
isn't granted. Failing to close a window is never fatal — the container is
stopped either way and the log says `window left open (…)`.

## Nightly run

`install.py` writes `~/Library/LaunchAgents/com.nickbrett1.devreap.plist` and
loads it. It runs once a day (10:00) as you, in your GUI session, logging to
`~/.devreap/devreap.log`.

```bash
launchctl kickstart -k gui/$(id -u)/com.nickbrett1.devreap   # run it now
tail -f ~/.devreap/devreap.log                               # watch it
launchctl bootout gui/$(id -u)/com.nickbrett1.devreap        # stop it
```

## Project layout

```
devreap/
├── install.py / uninstall.py        # curl | python3 installers
├── devreap/
│   ├── config.py                    # ~/.devreap/config.json handling
│   ├── buildkite.py                 # last human-triggered build per pipeline
│   ├── containers.py                # enumerate devcontainers, session veto, stop
│   ├── vscode.py                    # close the workspace's VS Code window
│   ├── reap.py                      # plan + execute + report table
│   └── __main__.py                  # CLI
├── launchd/com.nickbrett1.devreap.plist
└── scripts/devreap                  # → /usr/local/bin/devreap
```

Pure stdlib — no venv, no dependencies, same as devopen.

## Ideas

- Reap on demand instead of on a clock: when a heavy build queues and the
  OrbStack VM is short on RAM, stop the *coldest* container immediately.
- Adopt orphaned `devcontainer.local_folder` values whose workspace is gone.
- Prune the workspace from VS Code's `windowsState.openedWindows` so a dead
  window isn't restored on the next launch.
