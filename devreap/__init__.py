"""devreap — shut down devcontainers whose project has gone quiet.

"Quiet" is decided by *you*, not by CPU or memory: if it has been N days
since you last triggered a build for that project (Dependabot/Renovate/CI
builds don't count), you're probably not working on it, and its devcontainer
is just holding RAM. Stop it — and close its VS Code window so nothing is
left pointing at a dead container.

Sibling project to devopen (same shape: pure stdlib, curl|python3 installer).
"""

__version__ = "0.1.0"
