from __future__ import annotations

import pytest

from sdocs_mcp.config import SshModuleConfig
from sdocs_mcp.ssh_tools import _validate_command


def test_ssh_rejects_empty() -> None:
    cfg = SshModuleConfig(
        enabled=False,
        hosts=[],
        forbidden_substrings=[],
        forbidden_regex=[],
        merge_recommended_substring_blocklist=False,
    )
    with pytest.raises(ValueError, match="non-empty"):
        _validate_command(cfg, "   ")


def test_ssh_rejects_shell_ops_when_disabled() -> None:
    cfg = SshModuleConfig(
        enabled=False,
        hosts=[],
        forbidden_substrings=[],
        forbidden_regex=[],
        allow_shell_operators=False,
        merge_recommended_substring_blocklist=False,
    )
    with pytest.raises(ValueError, match="shell operators"):
        _validate_command(cfg, "echo a; echo b")


def test_ssh_builtin_blocks_sudo() -> None:
    cfg = SshModuleConfig(
        enabled=False,
        hosts=[],
        forbidden_substrings=[],
        forbidden_regex=[],
        builtin_safety_filter=True,
        merge_recommended_substring_blocklist=False,
    )
    with pytest.raises(ValueError, match="builtin safety"):
        _validate_command(cfg, "sudo ls")


def test_ssh_recommended_blocks_rm_rf_when_merge_on() -> None:
    cfg = SshModuleConfig(
        enabled=False,
        hosts=[],
        forbidden_substrings=[],
        forbidden_regex=[],
        builtin_safety_filter=False,
        merge_recommended_substring_blocklist=True,
    )
    with pytest.raises(ValueError, match="rm -rf"):
        _validate_command(cfg, "rm -rf /tmp/x")


def test_ssh_builtin_blocks_shell_dash_c() -> None:
    cfg = SshModuleConfig(
        enabled=False,
        hosts=[],
        forbidden_substrings=[],
        forbidden_regex=[],
        builtin_safety_filter=True,
        merge_recommended_substring_blocklist=False,
    )
    with pytest.raises(ValueError, match="shell -c"):
        _validate_command(cfg, "bash -c id")
