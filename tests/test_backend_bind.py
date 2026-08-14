"""Backend public CLI bind contract."""

from __future__ import annotations

import socket

import pytest

from cli import _select_port


def test_default_port_is_os_assigned() -> None:
    port = _select_port("127.0.0.1", 0)
    assert isinstance(port, int)
    assert port > 0

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", port))


def test_explicit_port_is_honoured() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    assert _select_port("127.0.0.1", port) == port


def test_occupied_port_fails_closed() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen(1)
        with pytest.raises(OSError):
            _select_port("127.0.0.1", int(holder.getsockname()[1]))
