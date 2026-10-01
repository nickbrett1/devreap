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
import time

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


def windows_for(workspaces, process=PROCESS):
    """(set of workspace paths that have a window open, error or None).

    One System Events round-trip for the whole list rather than one per
    workspace: a listing UI asks about every project at once, and each call
    is a separate osascript process. Returns paths, preserving the caller's
    spelling, so ids line up with the rows they came from.
    """
    titles, err = list_window_titles(process)
    open_paths = {
        ws for ws in workspaces
        if any(_title_matches(t, ws) for t in titles)
    }
    return open_paths, err


def _close_once(title, process, use_keystroke):
    """One close attempt at a named window: raise it first, then either the AX
    close button or ⌘⇧W (Close Window).

    Raising matters: without it `click button 1` can land on whichever window is
    actually frontmost. ⌘⇧W, not ⌘W — ⌘W closes the active *editor tab*, which
    silently leaves the window open and reports success.
    """
    safe = title.replace('"', '\\"')
    if use_keystroke:
        action = 'keystroke "w" using {command down, shift down}'
    else:
        action = f'click button 1 of window "{safe}"'
    script = (
        f'tell application "System Events" to tell process "{process}"\n'
        f'  set frontmost to true\n'
        f'  perform action "AXRaise" of window "{safe}"\n'
        f'  delay 0.4\n'
        f'  {action}\n'
        f'end tell'
    )
    return _osascript(script)


def _gone(workspace, process, seconds):
    """Wait for no window to match `workspace` any more."""
    deadline = time.time() + seconds
    while True:
        titles, _ = list_window_titles(process)
        if not any(_title_matches(t, workspace) for t in titles):
            return True
        if time.time() >= deadline:
            return False
        time.sleep(0.4)


def _close_and_wait(title, workspace, process):
    """Close one window and confirm it actually went away."""
    for use_keystroke, budget in ((False, 5.0), (True, 5.0)):
        _close_once(title, process, use_keystroke)
        if _gone(workspace, process, budget):
            return True
    # A "save your changes?" sheet keeps the window open; dismiss it so it does
    # not sit in front of every later close attempt.
    _osascript('tell application "System Events" to key code 53')
    time.sleep(0.3)
    return _gone(workspace, process, 1.0)


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

    closed, left_open = [], []
    for title in matches:
        (closed if _close_and_wait(title, workspace, process) else left_open).append(title)

    if closed and not left_open:
        return True, "closed: " + "; ".join(closed)
    if closed:
        return True, "closed: " + "; ".join(closed) + " | left open: " + "; ".join(left_open)
    return False, "window still open after close (unsaved changes?)"
