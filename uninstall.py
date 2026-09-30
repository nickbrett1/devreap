#!/usr/bin/env python3
"""Uninstall devreap: remove the CLI, its LaunchAgent and ~/.devreap.

Run it standalone:
    curl -fsSL https://raw.githubusercontent.com/nickbrett1/devreap/main/uninstall.py | python3

Your containers, workspaces and ~/DevOpen/devreap checkout are left alone
(they're your data) — remove the checkout with `rm -rf ~/DevOpen/devreap`.
"""

import os
import subprocess

LABEL = "com.nickbrett1.devreap"


def rm(path):
    if os.path.exists(path):
        print(f"Removing {path}")
        if os.path.isdir(path):
            import shutil
            shutil.rmtree(path)
        else:
            os.remove(path)
    else:
        print(f"Not present: {path}")


def main():
    home = os.path.expanduser("~")
    uid = os.getuid()
    plist = os.path.join(home, "Library", "LaunchAgents", f"{LABEL}.plist")

    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True, text=True)
    subprocess.run(["launchctl", "bootout", f"gui/{uid}", plist],
                   capture_output=True, text=True)

    rm("/usr/local/bin/devreap")
    rm(plist)
    rm(os.path.join(home, ".devreap"))
    print("\ndevreap uninstalled. Containers and workspaces untouched.")


if __name__ == "__main__":
    main()
