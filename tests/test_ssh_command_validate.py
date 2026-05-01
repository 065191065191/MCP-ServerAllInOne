from __future__ import annotations

import pytest

from stack_mcp.config import SshModuleConfig
from stack_mcp.ssh_tools import _validate_command


def test_ssh_rejects_empty() -> None:
    cfg = SshModuleConfig(enabled=False, hosts=[], forbidden_substrings=[], forbidden_regex=[])
    with pytest.raises(ValueError, match="non-empty"):
        _validate_command(cfg, "   ")


def test_ssh_rejects_shell_ops_when_disabled() -> None:
    cfg = SshModuleConfig(
        enabled=False,
        hosts=[],
        forbidden_substrings=[],
        forbidden_regex=[],
        allow_shell_operators=False,
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
    )
    with pytest.raises(ValueError, match="builtin safety"):
        _validate_command(cfg, "sudo ls")
