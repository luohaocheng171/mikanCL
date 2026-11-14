"""Minecraft Server List Ping：直接按协议读取 MOTD、图标、版本与在线人数。

不再依赖 mcstatus.io 之类的第三方接口，服务器列表在断网/接口限流时也能工作。
支持 1.7+ 的 Status 协议，并兼容 1.6 及更早版本的 legacy ping（只能拿到
MOTD/版本/人数，没有图标）。
"""

from __future__ import annotations

import base64
import json
import re
import socket
import struct
import time
from dataclasses import dataclass, field

_MOTD_CODE = re.compile(r"§[0-9A-Fa-fK-ORk-or]")


@dataclass
class PingResult:
    latency: int = -1
    online: bool = False
    motd: str = ""
    version: str = ""
    players_online: int = 0
    players_max: int = 0
    icon_png: bytes = field(default_factory=bytes)
    error: str = ""

    @property
    def players_text(self) -> str:
        if not self.online:
            return ""
        return f"{self.players_online}/{self.players_max}"


def parse_address(text: str, default_port: int = 25565) -> tuple[str, int]:
    """把 127.0.0.1:25565 / example.com / [::1]:25565 解析为 (host, port)。

    解析失败时返回空 host，调用方据此提示用户。
    """
    raw = (text or "").strip()
    if not raw:
        return "", default_port
    if raw.startswith("["):  # IPv6 字面量
        head, _, tail = raw.partition("]")
        host = head[1:].strip()
        port = default_port
        if tail.startswith(":") and tail[1:].isdigit():
            port = int(tail[1:])
        return host, port
    if raw.count(":") == 1:
        host, _, port_text = raw.partition(":")
        if port_text.isdigit():
            port = int(port_text)
            return host.strip(), port if 0 < port < 65536 else default_port
        return host.strip() or raw, default_port
    return raw, default_port


def _varint(value: int) -> bytes:
    out = bytearray()
    value &= 0xFFFFFFFF
    while True:
        part = value & 0x7F
        value >>= 7
        if value:
            out.append(part | 0x80)
        else:
            out.append(part)
            return bytes(out)


def _read_varint(sock: socket.socket) -> int:
    result = 0
    for index in range(5):
        raw = sock.recv(1)
        if not raw:
            raise OSError("连接被服务器关闭")
        byte = raw[0]
        result |= (byte & 0x7F) << (7 * index)
        if not byte & 0x80:
            return result
    raise OSError("VarInt 过长")


def _read_exact(sock: socket.socket, count: int) -> bytes:
    chunks = bytearray()
    while len(chunks) < count:
        chunk = sock.recv(count - len(chunks))
        if not chunk:
            raise OSError("连接被服务器关闭")
        chunks.extend(chunk)
    return bytes(chunks)


def _strip_codes(text: str) -> str:
    return _MOTD_CODE.sub("", text or "").strip()


def _flatten_description(value) -> str:
    """把聊天组件（字符串或 {text, extra} 树）压平成纯文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return _strip_codes(value)
    if isinstance(value, list):
        return "".join(_flatten_description(item) for item in value)
    if isinstance(value, dict):
        parts = [_flatten_description(value.get("text"))]
        if value.get("translate"):
            parts.append(_flatten_description(value.get("translate")))
        for extra in value.get("extra") or []:
            parts.append(_flatten_description(extra))
        return "".join(parts).strip()
    return str(value)


def _decode_icon(value) -> bytes:
    if not isinstance(value, str) or not value.startswith("data:image/png;base64,"):
        return b""
    try:
        return base64.b64decode(value.split(",", 1)[1], validate=False)
    except (ValueError, TypeError):
        return b""


def _encode_host(host: str) -> bytes:
    try:
        return host.encode("idna")
    except UnicodeError:
        return host.encode("utf-8", "ignore")


def _legacy_ping(host: str, port: int, timeout: float) -> PingResult:
    """1.6 legacy ping：无图标，但能拿到 MOTD/版本/人数。"""
    started = time.perf_counter()
    with socket.create_connection((host, port), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall(b"\xfe\x01")
        raw = sock.recv(4096)
    latency = int((time.perf_counter() - started) * 1000)
    if not raw or raw[0] != 0xFF:
        raise OSError("服务器不支持 legacy ping")
    try:
        # 跳过 0xFF + 长度，再跳过 "\x00§1\x00"
        payload = raw[3:]
        if payload[:2] == b"\x00\x00":
            payload = payload[2:]
        fields = payload.split(b"\x00")
        version = fields[1].decode("utf-8", "ignore") if len(fields) > 1 else ""
        motd = fields[2].decode("utf-8", "ignore") if len(fields) > 2 else ""
        online = struct.unpack(">H", fields[3][:2])[0] if len(fields) > 3 else 0
        maximum = struct.unpack(">H", fields[4][:2])[0] if len(fields) > 4 else 0
    except (IndexError, struct.error) as exc:
        raise OSError(f"legacy 响应解析失败：{exc}") from exc
    return PingResult(
        latency=latency,
        online=True,
        motd=_strip_codes(motd),
        version=version,
        players_online=online,
        players_max=maximum,
        error="",
    )


def ping_server(host: str, port: int = 25565, timeout: float = 4.0) -> PingResult:
    """执行一次完整 Server List Ping；失败时尽量返回延迟/错误信息。"""
    host = host.strip()
    port = int(port)
    if not host:
        return PingResult(error="服务器地址为空")
    result = PingResult()
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            handshake = (
                _varint(0)
                + _varint(47)  # 1.8 的协议号，任何现代服务端都能响应状态请求
                + _varint(len(_encode_host(host)))
                + _encode_host(host)
                + struct.pack(">H", port)
                + _varint(1)  # next state: status
            )
            sock.sendall(_varint(len(handshake)) + handshake)
            sock.sendall(_varint(1) + b"\x00")  # status request
            length = _read_varint(sock)
            payload = _read_exact(sock, length)
            result.latency = int((time.perf_counter() - started) * 1000)
            # payload: varint packet id(0) + varint json 长度 + json
            index = 0
            packet_id = 0
            shift = 0
            while index < len(payload):
                byte = payload[index]
                index += 1
                packet_id |= (byte & 0x7F) << shift
                if not byte & 0x80:
                    break
                shift += 7
            json_len = 0
            shift = 0
            while index < len(payload):
                byte = payload[index]
                index += 1
                json_len |= (byte & 0x7F) << shift
                if not byte & 0x80:
                    break
                shift += 7
            raw_json = payload[index : index + json_len]
            data = json.loads(raw_json.decode("utf-8", "ignore"))
            result.online = True
            result.motd = _flatten_description(data.get("description"))
            version = data.get("version") or {}
            if isinstance(version, dict):
                result.version = str(version.get("name") or "")
            players = data.get("players") or {}
            if isinstance(players, dict):
                result.players_online = int(players.get("online") or 0)
                result.players_max = int(players.get("max") or 0)
            result.icon_png = _decode_icon(data.get("favicon"))
            if not result.motd:
                result.motd = "（无描述）"
            return result
    except Exception as exc:  # noqa: BLE001 - 网络异常统一返回失败信息
        if result.latency < 0:
            result.latency = int((time.perf_counter() - started) * 1000)
        # 现代协议失败时尝试 legacy ping（老服务端 / 部分代理）
        try:
            legacy = _legacy_ping(host, port, timeout)
            if legacy.online:
                return legacy
        except Exception:  # noqa: BLE001
            pass
        result.online = False
        result.error = str(exc) or "无法连接"
        return result


def probe_address(address: str, timeout: float = 4.0) -> PingResult:
    """探测一个「主机:端口」地址是否可用。

    先走完整 Server List Ping；若服务端不响应状态协议（例如部分 TCP 代理），
    再退化为纯 TCP 连通性检测，只判断端口能否握手成功。
    """
    host, port = parse_address(address)
    if not host:
        return PingResult(error="地址为空")
    result = ping_server(host, port, timeout=timeout)
    if result.online:
        return result
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            pass
        result.online = True
        result.latency = int((time.perf_counter() - started) * 1000)
        result.error = ""
        if not result.motd:
            result.motd = "端口可连通（未响应状态查询）"
    except (OSError, ValueError) as exc:
        result.online = False
        result.latency = -1
        result.error = str(exc) or "无法连接"
    return result
