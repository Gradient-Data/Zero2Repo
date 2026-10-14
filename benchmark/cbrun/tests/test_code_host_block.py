"""Code-host blocking: host lists and the CLI flag (no docker)."""

from __future__ import annotations

from cbrun import denylist
from cbrun.cli import _parse_args
from cbrun.docker_env import Container


def test_block_list_covers_code_hosts_and_mirrors():
    hosts = set(denylist.CODE_HOST_BLOCK_HOSTS)
    assert set(denylist.GITHUB_BLOCK_HOSTS) <= hosts
    for host in (
        "github.com",
        "codeload.github.com",
        "raw.githubusercontent.com",
        "objects.githubusercontent.com",
        "gist.githubusercontent.com",
        "gitlab.com",
        "gitee.com",
        "bitbucket.org",
        "sourcegraph.com",
        "ghproxy.com",
        "hub.fastgit.org",
        "kkgithub.com",
        "gitclone.com",
    ):
        assert host in hosts, host
    assert len(hosts) == len(denylist.CODE_HOST_BLOCK_HOSTS), "duplicates"


def test_package_registries_stay_reachable():
    registry_words = ("pypi", "pythonhosted", "npmjs", "npmmirror", "golang", "goproxy", "crates", "yarnpkg", "rubygems")
    for host in denylist.CODE_HOST_BLOCK_HOSTS:
        assert not any(word in host for word in registry_words), host


def test_block_flag_and_alias():
    assert _parse_args(["--case", "x"]).block_github is True
    assert _parse_args(["--case", "x", "--no-block-github"]).block_github is False
    assert _parse_args(["--case", "x", "--no-block-code-hosts"]).block_github is False
    assert _parse_args(["--case", "x", "--block-code-hosts"]).block_github is True


def test_hosts_reach_docker_run():
    argv = Container.build_run_argv("img", block_hosts=denylist.CODE_HOST_BLOCK_HOSTS)
    for host in ("github.com", "gitlab.com", "ghproxy.com"):
        assert f"{host}:0.0.0.0" in argv


def test_run_trial_blocks_the_full_list():
    import inspect

    from cbrun import run_case

    source = inspect.getsource(run_case.run_trial)
    assert "CODE_HOST_BLOCK_HOSTS if block_github" in source
