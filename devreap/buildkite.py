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
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.buildkite.com/v2"

# Anything that looks like an unattended actor. Kept deliberately broad: a
# false "automated" only makes us *more* reluctant to reap, which is the safe
# direction.
BOT_RE = re.compile(r"(\[bot\]|dependabot|renovate|github-actions|snyk-)", re.I)


class BuildkiteError(RuntimeError):
    pass


def _get(path, token, params=None, timeout=30):
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        raise BuildkiteError(f"HTTP {e.code} for {url}: {detail}") from e
    except urllib.error.URLError as e:
        raise BuildkiteError(f"could not reach Buildkite: {e}") from e


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
