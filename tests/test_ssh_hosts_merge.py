from __future__ import annotations

from pathlib import Path

import pytest


def test_load_config_merges_ssh_hosts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    main = tmp_path / "main.yaml"
    main.write_text(
        "modules:\n"
        "  ssh:\n"
        "    enabled: true\n"
        "    default_private_key_path: ~/.ssh/id_test\n"
        "    hosts:\n"
        "      - id: a\n"
        "        hostname: 1.1.1.1\n"
        "        username: u\n"
        "        port: 22\n",
        encoding="utf-8",
    )
    frag = tmp_path / "more.yaml"
    frag.write_text(
        "- id: b\n  hostname: 2.2.2.2\n  username: u\n  port: 22\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("STACK_MCP_CONFIG", str(main))
    monkeypatch.setenv("STACK_MCP_SSH_HOSTS_FILE", str(frag))

    from stack_mcp.config import load_config

    cfg = load_config()
    assert len(cfg.modules.ssh.hosts) == 2
    assert cfg.modules.ssh.hosts[0].id == "a"
    assert cfg.modules.ssh.hosts[1].id == "b"
