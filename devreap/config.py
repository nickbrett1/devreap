"""Configuration handling for devreap.

Config lives at ~/.devreap/config.json (mode 600):

    {
      "install_dir":       "~/DevOpen/devreap",
      "workspaces_dir":    "~/DevOpen/workspaces",
      "buildkite_org":     "nick-brett",
      "buildkite_token":   "<read-only API token>",
      "days":              3,        # reap when last human build is older than this
      "min_container_age_hours": 0,  # extra rail: never reap a container younger than this
      "close_windows":     true,     # close the workspace's VS Code window after stopping
      "keep":              [],       # workspace names to never reap
      "ignore":            [],       # workspace names to not even look at
      "pipeline_map":      {},       # workspace basename -> buildkite pipeline slug (override)
      "unknown_policy":    "keep"    # keep | reap  — when no pipeline/build is known
    }
"""

import json
import os

CONFIG_DIR_NAME = ".devreap"
CONFIG_FILE_NAME = "config.json"


def config_dir(home=None):
    home = home or os.path.expanduser("~")
    return os.path.join(home, CONFIG_DIR_NAME)


def config_path(home=None):
    return os.path.join(config_dir(home), CONFIG_FILE_NAME)


def _defaults(home=None):
    home = home or os.path.expanduser("~")
    devopen_home = os.environ.get("DEVOPEN_HOME") or os.path.join(home, "DevOpen")
    return {
        "install_dir": os.path.join(devopen_home, "devreap"),
        "workspaces_dir": os.environ.get("DEVOPEN_WORKSPACES") or os.path.join(devopen_home, "workspaces"),
        "buildkite_org": "nick-brett",
        "buildkite_token": "",
        "days": 3,
        "min_container_age_hours": 0,
        "close_windows": True,
        "keep": [],
        "ignore": [],
        "pipeline_map": {},
        "unknown_policy": "keep",
    }


def save(cfg, home=None):
    """Atomically write config with 0600 permissions."""
    path = config_path(home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
        f.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def load(home=None):
    """Load config, creating a default one if missing."""
    cfg = _defaults(home)
    path = config_path(home)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
        except (OSError, ValueError) as e:
            raise RuntimeError(f"Could not read {path}: {e}") from e
    save(cfg, home=home)
    return cfg
