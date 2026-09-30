#!/usr/bin/env python3
"""Install the devreap CLI (and its nightly LaunchAgent).

Run it standalone (no clone needed):
    curl -fsSL https://raw.githubusercontent.com/nickbrett1/devreap/main/install.py | python3

Overrides (env): DEVOPEN_HOME (default ~/DevOpen), DEVOPEN_WORKSPACES,
DEVREAP_SKIP_UPDATE=1 (skip git pull of an existing checkout),
DEVREAP_SKIP_AGENT=1 (don't install/load the LaunchAgent).
"""

import json
import os
import shutil
import subprocess
import sys

REPO_URL = "https://github.com/nickbrett1/devreap.git"
LABEL = "com.nickbrett1.devreap"


def sh(cmd, check=True):
    print("$ " + " ".join(cmd), flush=True)
    return subprocess.run(cmd, check=check)


def _install_script(src, dest):
    print(f"Installing {src} → {dest}")
    try:
        shutil.copyfile(src, dest)
        os.chmod(dest, 0o755)
    except PermissionError:
        print(f"⚠️  Cannot write {dest} (permissions). Run with sudo or copy manually:")
        print(f"    sudo cp {src} {dest} && sudo chmod 755 {dest}")


def _write_json_600(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def _install_agent(install_dir, config_dir):
    src = os.path.join(install_dir, "launchd", f"{LABEL}.plist")
    if not os.path.isfile(src):
        print("⚠️  launchd template missing — skipping the nightly agent.")
        return
    os.makedirs(config_dir, exist_ok=True)
    log_path = os.path.join(config_dir, "devreap.log")
    dest = os.path.expanduser(f"~/Library/LaunchAgents/{LABEL}.plist")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(src, encoding="utf-8") as f:
        body = f.read().replace("__DEVREAP_LOG__", log_path)
    with open(dest, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"LaunchAgent written: {dest}")
    uid = os.getuid()
    # bootout ignores a not-yet-loaded job; bootstrap then loads it.
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/{LABEL}"],
                   capture_output=True, text=True)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", dest],
                       capture_output=True, text=True)
    if r.returncode == 0:
        print(f"LaunchAgent loaded — devreap runs daily, logs to {log_path}")
    else:
        print("⚠️  Could not load the LaunchAgent automatically. Load it with:")
        print(f"    launchctl bootstrap gui/{uid} {dest}")


def main():
    home = os.path.expanduser("~")
    devopen_home = os.environ.get("DEVOPEN_HOME") or os.path.join(home, "DevOpen")
    install_dir = os.path.join(devopen_home, "devreap")
    workspaces_dir = os.environ.get("DEVOPEN_WORKSPACES") or os.path.join(devopen_home, "workspaces")
    config_dir = os.path.join(home, ".devreap")
    config_path = os.path.join(config_dir, "config.json")

    print(f"Installing devreap (CLI + nightly LaunchAgent)…\n"
          f"  install dir:   {install_dir}\n"
          f"  workspaces:    {workspaces_dir}")

    os.makedirs(devopen_home, exist_ok=True)
    if not os.path.isdir(os.path.join(install_dir, ".git")):
        print("\n[1/5] Cloning devreap repository…")
        sh(["git", "clone", REPO_URL, install_dir])
    elif os.environ.get("DEVREAP_SKIP_UPDATE") != "1":
        print("\n[1/5] Updating devreap repository…")
        sh(["git", "-C", install_dir, "pull", "--ff-only"], check=False)
    else:
        print("\n[1/5] Skipping repo update (DEVREAP_SKIP_UPDATE=1).")

    print("\n[2/5] Installing CLI script…")
    _install_script(os.path.join(install_dir, "scripts", "devreap"), "/usr/local/bin/devreap")

    print("\n[3/5] Writing config…")
    os.makedirs(config_dir, exist_ok=True)
    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            pass
    cfg.setdefault("install_dir", install_dir)
    cfg.setdefault("workspaces_dir", workspaces_dir)
    cfg.setdefault("buildkite_org", "nick-brett")
    cfg.setdefault("buildkite_token", "")
    cfg["install_dir"] = install_dir
    _write_json_600(config_path, cfg)
    print(f"Config written to {config_path} (mode 600).")

    print("\n[4/5] Checking docker…")
    if shutil.which("docker") is None:
        print("⚠️  docker CLI not found — devreap needs it (OrbStack/Docker Desktop).")
    else:
        print(f"docker found: {shutil.which('docker')}")

    print("\n[5/5] LaunchAgent…")
    if os.environ.get("DEVREAP_SKIP_AGENT") == "1":
        print("Skipped (DEVREAP_SKIP_AGENT=1).")
    else:
        _install_agent(install_dir, config_dir)

    print()
    print("=" * 62)
    print("  devreap installed 🧹")
    print("=" * 62)
    print()
    print("Try it (changes nothing):")
    print("  devreap --dry-run")
    print()
    print("Before it can decide anything it needs a Buildkite API token in")
    print(f"  {config_path}  →  \"buildkite_token\": \"<read-only token>\"")
    print("Until then every container is kept (that's the safe default).")


if __name__ == "__main__":
    main()
