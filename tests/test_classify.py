"""The one bit of devreap that must be exactly right: telling your builds
apart from Dependabot's. Fixtures are real Buildkite build objects.

    python3 -m pytest tests/            # if you have pytest
    python3 tests/test_classify.py      # otherwise
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from devreap import buildkite  # noqa: E402

# ftn build #193 — you, on a chore branch (source: webhook)
HUMAN = {
    "branch": "chore/security-advisories-brace-fasturi-undici",
    "source": "webhook",
    "message": "chore(deps): bump vulnerable transitive deps via overrides",
    "author": {"email": "nick@fintechnick.com", "name": "Nick Brett"},
    "creator": {"email": "nick.brett1@gmail.com", "name": "Nick Brett"},
}

# ftn build #194 — you merging a Dependabot PR onto main. Counts as you.
HUMAN_MERGE = {
    "branch": "main",
    "source": "webhook",
    "message": "Merge pull request #4102 from nickbrett1/chore/security-advisories\n",
    "author": {"email": "nick@fintechnick.com", "name": "Nick Brett"},
    "creator": {"email": "nick.brett1@gmail.com", "name": "Nick Brett"},
}

# ftn build #198 — Dependabot, verbatim shape.
DEPENDABOT = {
    "branch": "dependabot/npm_and_yarn/webapp/dev-minor-and-patch-cb30fba5a4",
    "source": "webhook",
    "message": "chore(deps-dev): bump the dev-minor-and-patch group\n\n"
               "Signed-off-by: dependabot[bot] <support@github.com>",
    "author": {
        "email": "49699333+dependabot[bot]@users.noreply.github.com",
        "name": "dependabot[bot]",
        "username": "dependabot[bot]",
    },
    "creator": {"email": "", "name": ""},
}

# A UI "Rebuild": no author, but a real creator.
UI_REBUILD = {
    "branch": "main",
    "source": "ui",
    "message": "Rebuild of #193",
    "creator": {"email": "nick.brett1@gmail.com", "name": "Nick Brett"},
}

# A nightly schedule.
SCHEDULED = {
    "branch": "main",
    "source": "schedule",
    "message": "Nightly",
    "creator": {"email": "", "name": ""},
}

# Renovate, for good measure.
RENOVATE = {
    "branch": "renovate/lodash-4.x",
    "source": "webhook",
    "message": "chore(deps): update lodash",
    "author": {"email": "29139614+renovate[bot]@users.noreply.github.com",
               "name": "renovate[bot]", "username": "renovate[bot]"},
}

CASES = [
    (HUMAN, False, "your own build"),
    (HUMAN_MERGE, False, "you merging a Dependabot PR onto main"),
    (DEPENDABOT, True, "Dependabot PR build"),
    (UI_REBUILD, False, "a UI rebuild by you"),
    (SCHEDULED, True, "a scheduled nightly"),
    (RENOVATE, True, "Renovate"),
]


def main():
    failures = 0
    for build, expected, label in CASES:
        got = buildkite.is_automated(build)
        ok = got == expected
        failures += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'}  automated={got!s:<5} expected={expected!s:<5}  {label}")
    print()
    print("all good" if not failures else f"{failures} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
