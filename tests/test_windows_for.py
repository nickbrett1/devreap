"""windows_for() must map window titles back onto the caller's paths."""

from devreap import vscode


def test_matches_whole_tokens_only(monkeypatch):
    monkeypatch.setattr(
        vscode, "list_window_titles",
        lambda process=vscode.PROCESS: (
            ["sshd_config — galactic-unicorn-remote", "README.md — galactic-unicorn"], None,
        ),
    )
    open_paths, err = vscode.windows_for(
        ["/w/galactic-unicorn", "/w/galactic-unicorn-remote", "/w/pshelf"]
    )
    assert err is None
    # both match, and never each other's title
    assert open_paths == {"/w/galactic-unicorn", "/w/galactic-unicorn-remote"}


def test_no_windows_and_permission_error_are_not_exceptions(monkeypatch):
    monkeypatch.setattr(vscode, "list_window_titles", lambda process=vscode.PROCESS: ([], "denied"))
    open_paths, err = vscode.windows_for(["/w/pshelf"])
    assert open_paths == set() and err == "denied"
