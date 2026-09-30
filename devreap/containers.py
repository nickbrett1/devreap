"""Enumerate devcontainers, spot live sessions, stop containers.

A "devcontainer" here means any container carrying the devcontainer
`local_folder` label (what the devcontainer CLI / devopen / the VS Code
extension set). That deliberately excludes watchtower, dozzle, buildx
builder daemons and anything else that happens to be running.
"""

import json
import shlex
import subprocess

LABEL = "devcontainer.local_folder"


class DockerError(RuntimeError):
    pass


def _run(args, timeout=30):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)


def docker_available():
    try:
        r = _run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=20)
        return r.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def _inspect(container_id, fmt, timeout=20):
    r = _run(["docker", "inspect", "-f", fmt, container_id], timeout=timeout)
    if r.returncode != 0:
        return ""
    return r.stdout.strip()


def list_devcontainers():
    """[{id, name, workspace, running, started_at}] for every devcontainer.

    `workspace` is the host path from the devcontainer label; its basename is
    the workspace/project name we join Buildkite pipelines on.
    """
    r = _run(["docker", "ps", "-a", "-q", "--filter", f"label={LABEL}"])
    if r.returncode != 0:
        raise DockerError((r.stderr or "docker ps failed").strip())

    out = []
    for cid in r.stdout.split():
        workspace = _inspect(cid, '{{index .Config.Labels "' + LABEL + '"}}')
        if not workspace:
            continue
        out.append({
            "id": cid,
            "name": _inspect(cid, "{{.Name}}").lstrip("/"),
            "workspace": workspace,
            "running": _inspect(cid, "{{.State.Running}}") == "true",
            "started_at": _inspect(cid, "{{.State.StartedAt}}"),
        })
    return out


def _exec(container_id, argv, timeout=15):
    """Run argv inside the container; '' if the binary is missing or it fails."""
    try:
        r = _run(["docker", "exec", container_id] + argv, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def active_session(container_id):
    """(bool, evidence) — is a human sitting in this container right now?

    Deliberately narrow. We check for *interactive terminal* sessions:
    logins (`who`), attached tmux clients, and established ssh connections.
    We do NOT count a mere open VS Code window — windows stay open for days,
    and if we vetoed on those, nothing would ever be reaped. (devreap closes
    the window itself when it stops the container.)
    """
    evidence = []

    who = _exec(container_id, ["sh", "-c", "who 2>/dev/null | grep -v '^$'"])
    if who:
        evidence.append("login: " + who.replace("\n", "; "))

    clients = _exec(container_id, ["sh", "-c", "tmux list-clients 2>/dev/null"])
    if clients:
        evidence.append("tmux: " + clients.replace("\n", "; "))

    ssh = _exec(container_id, [
        "sh", "-c",
        "ss -Htn state established '( sport = :22 )' 2>/dev/null | wc -l | tr -d ' '",
    ])
    if ssh and ssh != "0":
        evidence.append(f"ssh: {ssh} established")

    return (bool(evidence), " | ".join(evidence))


def stop(container_id, timeout=60):
    """Gracefully stop (never remove) a container.

    `docker stop` keeps the container and its volumes — `docker start` (or
    reopening from devopen/VS Code) brings it straight back, so nothing is
    lost but the RAM it was holding.
    """
    r = _run(["docker", "stop", "-t", "10", container_id], timeout=timeout)
    return r.returncode == 0, (r.stdout + r.stderr).strip()
