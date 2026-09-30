"""Close the VS Code window attached to a workspace (macOS, best-effort).

devopen opens a window with a *host-path* URI:

    vscode-remote://dev-container+<hex-json {"hostPath": ...}>/<path>

VS Code is not scriptable for windows: `tell application "Visual Studio
Code" to count windows` times out (it implements no AppleScript suite), so
the only lever is UI scripting via System Events, matching the window title
(which contains the workspace folder name) and clicking its close button.

Two honest caveats, both documented in the README:

  * System Events needs the *Accessibility* permission for whatever runs
    devreap (Terminal when you run it by hand, or the LaunchAgent when it
    runs nightly). Without it, System Events sees zero windows.
  * It must run inside your GUI login session. From a headless/daemon
    context it will see nothing.

Failing to close a window is never fatal: the container is stopped either
way, and reap.py logs that the window was left behind.
"""

import os
import re
import subprocess

APP = "Visual Studio Code"
PROCESS = "Code"


def _osascript(script, timeout=20):
    try:
        r = subprocess.run(["osascript", "-e", script],
                           capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError) as e:
        return None, str(e)
    if r.returncode != 0:
        return None, (r.stderr or r.stdout).strip()
    return r.stdout.strip(), None


def list_window_titles(process=PROCESS):
    """Window titles System Events can see for VS Code (may be [] without
    Accessibility permission). Comma-separated because AppleScript's
    `set AppleScript's text item delimiters` round-trip is overkill here."""
    out, err = _osascript(
        f'tell application "System Events" to tell process "{process}" '
        f'to return name of every window'
    )
    if out is None:
        return [], err
    if not out:
        return [], None
    return [t.strip() for t in out.split(",") if t.strip()], None


def _title_matches(title, workspace):
    """Does this window title belong to `workspace`?

    Whole-token match, so 'galactic-unicorn' never matches the
    'galactic-unicorn-remote' window.
    """
    base = os.path.basename(workspace.rstrip("/"))
    if not base:
        return False
    return re.search(rf"(?<![A-Za-z0-9_.-]){re.escape(base)}(?![A-Za-z0-9_.-])", title) is not None


def close_workspace_window(workspace, process=PROCESS):
    """(ok, detail) — close the VS Code window whose title is `workspace`."""
    titles, err = list_window_titles(process)
    if err:
        return False, f"System Events unavailable: {err}"
    if not titles:
        return False, "no windows visible to System Events (Accessibility permission / GUI session?)"

    matches = [t for t in titles if _title_matches(t, workspace)]
    if not matches:
        return False, "no open window for this workspace"

    closed, last_err = [], None
    for title in matches:
        safe = title.replace('"', '\\"')
        # Close button first; fall back to raising the window and hitting ⌘W.
        out, err = _osascript(
            f'tell application "System Events" to tell process "{process}"\n'
            f'  set frontmost to true\n'
            f'  click button 1 of window "{safe}"\n'
            f'end tell'
        )
        if err:
            out, err = _osascript(
                f'tell application "System Events" to tell process "{process}"\n'
                f'  set frontmost to true\n'
                f'  perform action "AXRaise" of window "{safe}"\n'
                f'  keystroke "w" using command down\n'
                f'end tell'
            )
        if err:
            last_err = err
        else:
            closed.append(title)

    if closed:
        return True, "closed: " + "; ".join(closed)
    return False, f"could not close window ({last_err})"
