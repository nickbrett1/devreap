"""Find the last build a *human* triggered for a Buildkite pipeline.

The whole premise of devreap is that "when did you last trigger a build for
this project" is a better signal of active work than CPU or memory. That
means we have to tell your builds apart from Dependabot's — which Buildkite
makes easy, because every build carries the *commit author*:

    human:      "author": {"name": "Nick Brett", "email": "nick@fintechnick.com"}
    dependabot: "author": {"name": "dependabot[bot]", "email": "49699...+dependabot[bot]@users.noreply.github.com"}

A merge of a Dependabot PR onto main has *you* as the author, so it counts
as you being active — which is right. A "Rebuild" from the UI has no author
but a real `creator`, so that counts too.

Pure stdlib (urllib) — matches devopen's no-dependencies style.
"""

import json
import re
import subprocess
import urllib.parse

API = "https://api.buildkite.com/v2"

# Anything that looks like an unattended actor. Kept deliberately broad: a
# false "automated" only makes us *more* reluctant to reap, which is the safe
# direction.
BOT_RE = re.compile(r"(\[bot\]|dependabot|renovate|github-actions|snyk-)", re.I)


class BuildkiteError(RuntimeError):
    pass


def _get(path, token, params=None, timeout=30):
    """GET a Buildkite API path.

    Shells out to curl with the config (including the token) on stdin, the
    way devopen does for GitHub: the python3 that ships on this Mac (pyenv
    3.11) has a broken `_ssl` — openssl@1.1 is gone — so urllib cannot do
    https at all ("unknown url type: https"). curl doesn't care, and keeping
    the token out of argv keeps it out of `ps`.
    """
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    config = (
        f'url = "{url}"\n'
        f'header = "Authorization: Bearer {token}"\n'
        'header = "Accept: application/json"\n'
        "silent\nshow-error\n"
        f"max-time = {timeout}\n"
        'write-out = "\\n%{http_code}"\n'
    )
    try:
        r = subprocess.run(
            ["curl", "-sS", "--config", "-"],
            input=config, capture_output=True, text=True, timeout=timeout + 15,
        )
    except FileNotFoundError as e:
        raise BuildkiteError("curl is required but not installed") from e
    except subprocess.SubprocessError as e:
        raise BuildkiteError(f"could not reach Buildkite: {e}") from e

    body, _, code = r.stdout.rpartition("\n")
    code = code.strip()
    if r.returncode != 0 and not code:
        raise BuildkiteError(f"could not reach Buildkite: {r.stderr.strip() or r.returncode}")
    if code == "404":
        return None
    if code != "200":
        raise BuildkiteError(f"HTTP {code or '?'} for {url}: {body.strip()[:200]}")
    try:
        return json.loads(body) if body.strip() else None
    except ValueError as e:
        raise BuildkiteError(f"unexpected response from Buildkite: {body[:200]}") from e


def is_automated(build):
    """True if this build was not triggered by a human."""
    who = " ".join(
        str((build.get("author") or {}).get(k) or "")
        for k in ("username", "name", "email")
    )
    who += " " + str((build.get("creator") or {}).get("email") or "")
    if BOT_RE.search(who):
        return True
    branch = build.get("branch") or ""
    if branch.startswith(("dependabot/", "renovate/")):
        return True
    message = build.get("message") or ""
    if "dependabot[bot]" in message or "Signed-off-by: dependabot" in message:
        return True
    if build.get("source") == "schedule":
        return True
    return False


def last_human_build(org, slug, token, pages=2, page_size=100, timeout=30):
    """Newest non-automated build for a pipeline.

    Returns a dict {created_at, number, branch, author} or None if the
    pipeline has no human builds in the window we looked at. Raises
    BuildkiteError if the pipeline does not exist or the API is unhappy.
    """
    for page in range(1, pages + 1):
        builds = _get(
            f"/organizations/{org}/pipelines/{urllib.parse.quote(slug)}/builds",
            token,
            params={"per_page": page_size, "page": page, "exclude_jobs": "true"},
            timeout=timeout,
        )
        if builds is None:
            raise BuildkiteError(f"pipeline '{slug}' not found in org '{org}'")
        if not builds:
            return None
        for build in builds:
            if not is_automated(build):
                author = build.get("author") or {}
                return {
                    "created_at": build.get("created_at"),
                    "number": build.get("number"),
                    "branch": build.get("branch"),
                    "author": author.get("name") or author.get("username") or "you",
                }
        if len(builds) < page_size:
            break
    return None


def list_pipelines(org, token, timeout=30):
    """Slugs of every pipeline in the org (used as a sanity check)."""
    out = []
    page = 1
    while True:
        items = _get(f"/organizations/{org}/pipelines", token,
                     params={"per_page": 100, "page": page}, timeout=timeout)
        if not items:
            break
        out.extend(p.get("slug") for p in items)
        if len(items) < 100:
            break
        page += 1
    return out
