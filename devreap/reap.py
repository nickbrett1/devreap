"""The reaper: decide, then act.

The rule, in one line: stop a project's devcontainer when it has been
`days` (default 3) since you last triggered a build from that project.
Everything else in this file is the safety rails around that sentence.
"""

import datetime as dt
import os

from . import buildkite, containers, vscode


def _parse_iso(value):
    """Buildkite timestamps are UTC ISO-8601 with a Z. Parse without fussing
    over fractional-second width across Python versions."""
    if not value:
        return None
    try:
        return dt.datetime.strptime(value[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def _parse_docker_time(value):
    """Docker's StartedAt: '2026-09-30T11:01:15.691234567Z' (nanoseconds)."""
    return _parse_iso(value)


def _age_days(when, now):
    if when is None:
        return None
    return (now - when).total_seconds() / 86400.0


def _fmt_age(days):
    if days is None:
        return "—"
    if days < 1:
        return f"{days * 24:.1f}h"
    return f"{days:.1f}d"


def _pipeline_for(workspace, cfg):
    base = os.path.basename(workspace.rstrip("/"))
    return (cfg.get("pipeline_map") or {}).get(base, base)


def plan(cfg, days=None, only=None, now=None):
    """Compute one decision per devcontainer. No side effects."""
    days = cfg.get("days", 3) if days is None else days
    now = now or dt.datetime.now(dt.timezone.utc)
    keep = set(cfg.get("keep") or [])
    ignore = set(cfg.get("ignore") or [])
    token = cfg.get("buildkite_token") or os.environ.get("BUILDKITE_API_TOKEN") or ""
    org = cfg.get("buildkite_org") or "nick-brett"
    min_age_hours = cfg.get("min_container_age_hours") or 0

    decisions = []
    for c in containers.list_devcontainers():
        base = os.path.basename(c["workspace"].rstrip("/"))
        d = {
            "workspace": base,
            "path": c["workspace"],
            "container": c["name"],
            "container_id": c["id"],
            "running": c["running"],
            "pipeline": _pipeline_for(c["workspace"], cfg),
            "last_build": None,
            "last_build_label": "—",
            "age_days": None,
            "verdict": "keep",
            "reason": "",
        }

        if only and base != only:
            continue
        if base in ignore:
            d["verdict"], d["reason"] = "skip", "on the ignore list"
            decisions.append(d)
            continue
        if not c["running"]:
            d["verdict"], d["reason"] = "skip", "already stopped"
            decisions.append(d)
            continue
        if base in keep:
            d["verdict"], d["reason"] = "keep", "on the keep list"
            decisions.append(d)
            continue

        # --- the signal -------------------------------------------------
        if not token:
            d["verdict"] = "keep"
            d["reason"] = "no Buildkite token configured (set buildkite_token)"
        else:
            last = None
            try:
                last = buildkite.last_human_build(org, d["pipeline"], token)
            except buildkite.BuildkiteError as e:
                d["reason"] = f"buildkite error: {e}"
            if last:
                d["last_build"] = last["created_at"]
                d["last_build_label"] = f"#{last['number']} ({last['author']}, {last['branch']})"
                d["age_days"] = _age_days(_parse_iso(last["created_at"]), now)

            if d["age_days"] is None:
                d["verdict"] = "keep" if cfg.get("unknown_policy", "keep") == "keep" else "reap"
                d["reason"] = d["reason"] or f"no human-triggered build found for '{d['pipeline']}'"
                decisions.append(d)
                continue

            if d["age_days"] < days:
                d["verdict"] = "keep"
                d["reason"] = f"active — last human build {_fmt_age(d['age_days'])} ago"
                decisions.append(d)
                continue

            # --- safety rails -------------------------------------------
            started = _parse_docker_time(c["started_at"])
            start_age_h = None
            if started:
                start_age_h = (now - started).total_seconds() / 3600.0
                if min_age_hours and start_age_h < min_age_hours:
                    d["verdict"] = "keep"
                    d["reason"] = f"container started {start_age_h:.1f}h ago (< {min_age_hours}h)"
                    decisions.append(d)
                    continue

            active, evidence = containers.active_session(c["id"])
            if active:
                d["verdict"] = "keep"
                d["reason"] = f"live session ({evidence})"
                decisions.append(d)
                continue

            d["verdict"] = "reap"
            d["reason"] = f"quiet {_fmt_age(d['age_days'])} (> {days}d)"

        decisions.append(d)

    return decisions


def execute(decisions, cfg, dry_run=False, close_windows=True, log=print):
    """Stop the containers that plan() marked. Returns the same list, with
    'stopped' / 'window' filled in."""
    for d in decisions:
        d["stopped"] = None
        d["window"] = None
        if d["verdict"] != "reap":
            continue
        if dry_run:
            d["stopped"] = "would stop"
            d["window"] = "(would close)" if (close_windows and cfg.get("close_windows", True)) else ""
            continue

        ok, out = containers.stop(d["container_id"])
        d["stopped"] = "stopped" if ok else f"FAILED ({out})"
        log(f"[devreap] {'stopped' if ok else 'could not stop'} {d['container']} ({d['workspace']})")

        if close_windows and cfg.get("close_windows", True):
            ok_w, detail = vscode.close_workspace_window(d["path"])
            d["window"] = "closed" if ok_w else f"left open ({detail})"
            log(f"[devreap] window {d['window']}")
    return decisions


def render(decisions):
    """A fixed-width table, because this output gets read by a human."""
    heads = ["WORKSPACE", "PIPELINE", "LAST HUMAN BUILD", "AGE", "VERDICT", "WHY"]
    rows = []
    for d in decisions:
        why = d["reason"] or ""
        if d.get("stopped"):
            why = f"{why} → {d['stopped']}"
        if d.get("window"):
            why = f"{why}; window {d['window']}"
        rows.append([
            d["workspace"], d["pipeline"], d["last_build_label"],
            _fmt_age(d["age_days"]), d["verdict"].upper(), why,
        ])
    widths = [len(h) for h in heads]
    for r in rows:
        for i, cell in enumerate(r):
            widths[i] = max(widths[i], len(cell))
    line = "  ".join(h.ljust(widths[i]) for i, h in enumerate(heads))
    out = [line, "  ".join("-" * w for w in widths)]
    for r in rows:
        out.append("  ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)))
    return "\n".join(out)
