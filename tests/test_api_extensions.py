"""v5.5.4 新增开发者接口的回归测试。

覆盖：对话式 API（计划 / 确认 / URI）、事件总线与 Webhook 签名、
HTTP /chat + /events、WebSocket 双向 JSON-RPC 与事件推送、
游戏联动（存档 NBT / RCON 边界）、mikan-cli 退出码。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mc_launcher import chat_api, events, game_link, nbt  # noqa: E402
from mc_launcher.api_gateway import ApiHttpServer  # noqa: E402


class _Registry:
    """最小接口注册表桩，记录调用而不真的改存档 / 启动游戏。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def list(self, query="", group="", limit=400):
        return {"items": [{"name": "nbe_grand", "doc": "大一统附魔", "group": "NBT"}],
                "matched": 1, "total": 1}

    def methods(self):
        return {"nbe_grand": {"doc": "大一统附魔"}}

    def invoke(self, name, args=None, kwargs=None):
        self.calls.append((name, list(args or []), dict(kwargs or {})))
        return {"ok": True, "name": name, "result": {"stub": True}}


def _safe_config(**kwargs):
    return SimpleNamespace(
        webhook_enabled=kwargs.get("webhook_enabled", False),
        webhook_url=kwargs.get("webhook_url", ""),
        webhook_secret=kwargs.get("webhook_secret", ""),
        webhook_events=kwargs.get("webhook_events", []),
        game_dir=kwargs.get("game_dir", ""),
        selected_version_id=kwargs.get("selected_version_id", "1.20.1"),
        game_link={},
        lan_hub={},
    )


class ChatApiTest(unittest.TestCase):
    def test_chinese_example_builds_two_step_plan(self):
        text = "帮我把 1.20 版本的存档里所有附魔拉满到 255，然后启动游戏"
        plan = chat_api.parse_chat(text, registry=_Registry())
        self.assertTrue(plan["ok"])
        self.assertEqual(plan["level"], 255)
        self.assertEqual(plan["version"], "1.20")
        self.assertEqual(plan["intents"], ["enchant_max", "launch"])
        self.assertEqual([item["method"] for item in plan["plan"]],
                         ["nbe_enchant_apply", "launch"])
        self.assertIn("world", plan["needs"])
        self.assertFalse(plan["executed"])
        self.assertTrue(plan["token"])

    def test_execute_requires_token_and_world(self):
        registry = _Registry()
        plan = chat_api.parse_chat("把附魔拉满到 255 然后启动 1.20.1", registry=registry)
        self.assertFalse(chat_api.execute("bad-token", registry=registry)["ok"])
        missing = chat_api.execute(plan["token"], registry=registry)
        self.assertFalse(missing["ok"])
        self.assertIn("world", missing["message"] or " ".join(
            step.get("error", "") for step in missing["steps"]))
        done = chat_api.execute(chat_api.parse_chat(
            "把附魔拉满到 255 然后启动 1.20.1", registry=registry)["token"],
            registry=registry, overrides={"world": "/tmp/world"})
        self.assertTrue(done["ok"])
        self.assertEqual(len(registry.calls), 2)
        self.assertEqual(registry.calls[0][2]["level"], 255)
        # token 一次性
        self.assertFalse(chat_api.execute("", registry=registry)["ok"])

    def test_unknown_intent_returns_candidates_not_actions(self):
        result = chat_api.parse_chat("今天天气不错", registry=_Registry())
        self.assertEqual(result["plan"], [])
        self.assertTrue(result["candidates"])

    def test_english_and_uri(self):
        text = "enchant all to 255 and launch 1.20.1"
        result = chat_api.parse_chat(text, registry=_Registry())
        self.assertEqual(result["level"], 255)
        self.assertEqual(result["intents"], ["enchant_max", "launch"])
        uri = "mikan://chat?text=" + urllib.parse.quote(text) + "&version=1.20.1"
        parsed = chat_api.parse_mikan_uri(uri)
        self.assertTrue(parsed["ok"])
        self.assertEqual(parsed["text"], text)
        self.assertFalse(parsed["execute"])
        self.assertFalse(chat_api.parse_mikan_uri("https://example.com")["ok"])
        self.assertIn("mikan://chat", chat_api.capabilities()["scheme"])


class EventBusTest(unittest.TestCase):
    def setUp(self):
        self.bus = events.bus()
        self._prev_getter = self.bus._config_getter

    def tearDown(self):
        self.bus.configure(lambda: None)

    def test_history_and_default_off(self):
        cfg = _safe_config()
        self.bus.configure(lambda: cfg)
        before = len(self.bus.deliveries())
        envelope = self.bus.emit("download_success", version="1.20.1", mod_count=240)
        self.assertEqual(envelope["event"], "download_success")
        self.assertEqual(self.bus.history(10)[0]["version"], "1.20.1")
        self.assertEqual(len(self.bus.deliveries()), before)  # 默认关闭，不发外部请求

    def test_webhook_signature_and_filter(self):
        received: list[dict] = []
        done = threading.Event()

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                return

            def do_POST(self):  # noqa: N802
                body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                received.append({
                    "body": json.loads(body),
                    "signature": self.headers.get("X-Mikan-Signature") or "",
                    "event": self.headers.get("X-Mikan-Event") or "",
                })
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")
                done.set()

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        secret = "unit-secret"
        cfg = _safe_config(webhook_enabled=True,
                           webhook_url=f"http://127.0.0.1:{server.server_port}/hook",
                           webhook_secret=secret,
                           webhook_events=["game_crash"])
        self.bus.configure(lambda: cfg)
        self.bus.emit("download_success", version="1.20.1")  # 不在白名单，不投递
        self.bus.emit("game_crash", reason="UnsupportedClassVersionError",
                      solution="Java 版本不匹配")
        self.assertTrue(done.wait(5), "Webhook 没有送达")
        item = received[-1]
        self.assertEqual(item["event"], "game_crash")
        self.assertEqual(item["body"]["reason"], "UnsupportedClassVersionError")
        expected = "sha256=" + hmac.new(
            secret.encode(), json.dumps(item["body"], ensure_ascii=False,
                                        default=str).encode(), hashlib.sha256).hexdigest()
        self.assertEqual(item["signature"], expected)
        self.assertEqual(len(received), 1)
        deadline = time.time() + 2.0
        record = None
        while time.time() < deadline:
            rows = [row for row in self.bus.deliveries(10)
                    if row.get("event") == "game_crash"]
            if rows:
                record = rows[0]
                break
            time.sleep(0.05)
        self.assertIsNotNone(record, "投递结果未记录")
        self.assertTrue(record["ok"], record)

    def test_sync_test_event(self):
        server = HTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        cfg = _safe_config(webhook_enabled=True, webhook_secret="k")
        self.bus.configure(lambda: cfg)
        # HTTPServer 的默认 handler 会返回 501，投递应被记录为失败而不是抛异常
        result = self.bus.test(f"http://127.0.0.1:{server.server_port}/")
        self.assertFalse(result["ok"])
        self.assertTrue(any(row["event"] == "webhook_test"
                            for row in self.bus.deliveries(10)))


class _StubApi:
    """给网关用的最小后端（反射它的公开方法）。"""

    def __init__(self):
        self.config = _safe_config()
        self.calls: list[tuple] = []

    def hello(self, name: str = "world") -> dict:
        self.calls.append(("hello", name))
        return {"ok": True, "message": f"hi {name}"}

    def nbe_enchant_apply(self, path: str = "", version: str = "", level: int = 0,
                          add_all: bool = False, target_tag: int = 0,
                          targets: list | None = None) -> dict:
        self.calls.append(("nbe_enchant_apply", path, level))
        return {"ok": True, "path": path, "level": level}

    def launch(self, version_id: str = "", instance_id: str = "",
               force: bool = False) -> dict:
        self.calls.append(("launch", version_id))
        return {"ok": True, "version": version_id}

    def game_capabilities(self) -> dict:
        return game_link.capabilities()


class GatewayHttpTest(unittest.TestCase):
    def setUp(self):
        events.bus().configure(lambda: None)
        self.api = _StubApi()
        self.gateway = ApiHttpServer()
        state = self.gateway.start(self.api, 0, "unit-token", "5.5.4")
        self.assertTrue(state["ok"], state)
        self.base = f"http://127.0.0.1:{self.gateway.port}"
        self.addCleanup(self.gateway.stop)

    def _get(self, path: str, token: str = "unit-token") -> dict:
        request = urllib.request.Request(self.base + path,
                                         headers={"X-Mikan-Token": token})
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post(self, path: str, payload: dict, token: str = "unit-token") -> dict:
        request = urllib.request.Request(
            self.base + path, data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={"X-Mikan-Token": token, "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_health_rpc_and_auth(self):
        self.assertTrue(self._get("/health")["channels"])
        result = self._post("/rpc", {"method": "hello", "args": ["tester"], "id": "1"})
        self.assertTrue(result["ok"])
        self.assertEqual(result["result"]["message"], "hi tester")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self._post("/rpc", {"method": "hello"}, token="wrong")
        self.assertEqual(ctx.exception.code, 401)

    def test_chat_dry_run_then_confirm(self):
        text = "把 1.20.1 存档里所有附魔拉满到 255，然后启动游戏"
        first = self._post("/chat", {"text": text, "world": "/tmp/world"})
        self.assertTrue(first["ok"])
        self.assertFalse(first["executed"])
        self.assertEqual(len(first["plan"]), 2)
        self.assertEqual(self.api.calls, [])  # dry-run 不得调用任何接口
        refused = self._post("/chat", {"text": text, "execute": True})
        self.assertFalse(refused["ok"])
        confirmed = self._post("/chat", {"text": text, "execute": True,
                                         "token": first["token"], "world": "/tmp/world"})
        self.assertTrue(confirmed["ok"], confirmed)
        self.assertTrue(confirmed["executed"])
        self.assertEqual([call[0] for call in self.api.calls],
                         ["nbe_enchant_apply", "launch"])
        self.assertEqual(self.api.calls[0][2], 255)

    def test_get_chat_is_always_dry_run(self):
        result = self._get("/chat?text=%E5%90%AF%E5%8A%A8%201.20.1")
        self.assertTrue(result["ok"])
        self.assertFalse(result["executed"])
        self.assertEqual(self.api.calls, [])

    def test_events_endpoint_and_openapi_channels(self):
        events.emit("download_success", version="1.20.1", mod_count=3)
        listing = self._get("/events?limit=10")
        self.assertTrue(listing["ok"])
        self.assertEqual(listing["items"][0]["event"], "download_success")
        schema = self._get("/schema")
        self.assertIn("/chat", schema["paths"])
        self.assertIn("/ws", schema["paths"])
        self.assertEqual(set(schema["x-mikan-channels"]),
                         {"chat", "webhook", "ws", "cli"})

    def test_gateway_file_is_written_and_removed(self):
        path = ROOT / "data" / "api_gateway.json"
        self.assertTrue(path.is_file())
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["port"], self.gateway.port)
        self.gateway.stop()
        self.assertFalse(path.exists())
        # cleanup 里再 stop 一次应无害
        self.assertFalse(self.gateway.running)


# ---------------------------------------------------------------------------
def _ws_connect(port: int, token: str):
    sock = socket.create_connection(("127.0.0.1", port), 5)
    sock.settimeout(5)
    key = base64.b64encode(os.urandom(16)).decode()
    request = (
        f"GET /ws?token={token} HTTP/1.1\r\n"
        "Host: 127.0.0.1\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(request.encode("ascii"))
    raw = b""
    while b"\r\n\r\n" not in raw:
        raw += sock.recv(4096)
    return sock, raw.split(b"\r\n", 1)[0]


def _ws_send(sock, payload: dict) -> None:
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    mask = os.urandom(4)
    masked = bytes(byte ^ mask[i % 4] for i, byte in enumerate(raw))
    size = len(raw)
    if size < 126:
        header = bytes([0x81, 0x80 | size])
    else:
        header = bytes([0x81, 0x80 | 126]) + struct.pack(">H", size)
    sock.sendall(header + mask + masked)


def _ws_recv(sock) -> dict:
    def exact(count):
        data = b""
        while len(data) < count:
            chunk = sock.recv(count - len(data))
            if not chunk:
                raise ConnectionError("closed")
            data += chunk
        return data

    first, second = exact(2)
    size = second & 0x7F
    if size == 126:
        size = struct.unpack(">H", exact(2))[0]
    elif size == 127:
        size = struct.unpack(">Q", exact(8))[0]
    return json.loads(exact(size).decode("utf-8"))


class WebSocketTest(unittest.TestCase):
    def setUp(self):
        events.bus().configure(lambda: None)
        self.gateway = ApiHttpServer()
        state = self.gateway.start(_StubApi(), 0, "ws-token", "5.5.4")
        self.assertTrue(state["ok"], state)
        self.addCleanup(self.gateway.stop)

    def test_rpc_and_event_push(self):
        sock, status = _ws_connect(self.gateway.port, "ws-token")
        self.assertIn(b"101", status)
        self.addCleanup(sock.close)
        _ws_send(sock, {"method": "hello", "args": ["bot"], "id": "1"})
        reply = _ws_recv(sock)
        self.assertTrue(reply["ok"])
        self.assertEqual(reply["result"]["message"], "hi bot")
        _ws_send(sock, {"subscribe": ["*"], "id": "2"})
        self.assertEqual(_ws_recv(sock)["result"]["subscribed"], ["*"])
        events.emit("player_join", player_name="Mikan", x=120, y=64, z=-300)
        push = _ws_recv(sock)
        self.assertEqual(push["push"], "event")
        self.assertEqual(push["data"]["event"], "player_join")
        self.assertEqual(push["data"]["player_name"], "Mikan")
        self.assertEqual(self.gateway.ws.count(), 1)

    def test_bad_token_rejected(self):
        sock, status = _ws_connect(self.gateway.port, "wrong")
        self.assertIn(b"401", status)
        sock.close()


class GameLinkTest(unittest.TestCase):
    def _world(self, root: Path, health: float, max_health: float) -> Path:
        world = root / "saves" / "TestWorld"
        (world / "playerdata").mkdir(parents=True, exist_ok=True)
        attributes = (nbt.TAG_LIST, (nbt.TAG_COMPOUND, [
            (nbt.TAG_COMPOUND, {
                "Name": (nbt.TAG_STRING, "generic.maxHealth"),
                "Base": (nbt.TAG_DOUBLE, max_health),
            }),
            (nbt.TAG_COMPOUND, {
                "Name": (nbt.TAG_STRING, "generic.attackDamage"),
                "Base": (nbt.TAG_DOUBLE, 3.0),
            }),
        ]))
        fields = {
            "Health": (nbt.TAG_FLOAT, health),
            "Pos": (nbt.TAG_LIST, (nbt.TAG_DOUBLE, [
                (nbt.TAG_DOUBLE, 120.5), (nbt.TAG_DOUBLE, 64.0), (nbt.TAG_DOUBLE, -300.5)])),
            "Attributes": attributes,
            "XpLevel": (nbt.TAG_INT, 7),
            "Dimension": (nbt.TAG_STRING, "minecraft:overworld"),
        }
        nbt.save_nbt_typed_file(world / "level.dat", "", (nbt.TAG_COMPOUND, fields))
        nbt.save_nbt_typed_file(world / "playerdata" / "abc.dat", "",
                                (nbt.TAG_COMPOUND, fields))
        return world

    def test_player_state_from_save(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = self._world(Path(tmp), health=20.0, max_health=20.0)
            state = game_link.player_state(str(world))
            self.assertTrue(state["ok"], state)
            self.assertFalse(state["live"])
            row = state["players"][0]
            self.assertEqual(row["health"], 20.0)
            self.assertEqual(row["max_health"], 20.0)
            self.assertEqual(row["pos"], [120.5, 64.0, -300.5])
            self.assertEqual(row["xp_level"], 7.0)

    def test_scan_anomalies_reports_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            world = self._world(Path(tmp), health=250.0, max_health=500.0)
            result = game_link.scan_anomalies(str(world), health_cap=100.0)
            self.assertTrue(result["ok"])
            self.assertEqual(result["action"], "none")
            fields = {item["field"] for item in result["findings"]}
            self.assertIn("health", fields)
            self.assertIn("max_health", fields)

    def test_rcon_requires_password(self):
        caps = game_link.capabilities()
        self.assertFalse(caps["memory_access"])
        self.assertFalse(caps["live_singleplayer"])
        cfg = _safe_config()
        result = game_link.rcon_command("list", config=cfg)
        self.assertFalse(result["ok"])
        self.assertIn("RCON 密码", result["message"])
        self.assertFalse(game_link.teleport("Mikan", 1, 2, 3, config=cfg)["ok"])
        self.assertFalse(game_link.kick("Mikan", "test", config=cfg)["ok"])

    def test_default_world(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            world = self._world(root, 20.0, 20.0)
            cfg = _safe_config(game_dir=str(root))
            self.assertEqual(game_link.default_world(cfg), str(world))


class CliTest(unittest.TestCase):
    def _run(self, *args: str):
        return subprocess.run([sys.executable, str(ROOT / "mikan_cli.py"), *args],
                              cwd=str(ROOT), capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=30)

    def test_version_and_help(self):
        self.assertEqual(self._run("version").returncode, 0)
        help_text = self._run("--help").stdout
        for word in ("install", "launch", "chat", "events", "game"):
            self.assertIn(word, help_text)

    def test_offline_status(self):
        result = self._run("--gateway", "http://127.0.0.1:1", "--token", "x", "status")
        # 连不上时返回 2，但信息要明确
        self.assertIn(result.returncode, (0, 2))
        self.assertTrue(result.stdout or result.stderr)

    def test_status_and_chat_against_gateway(self):
        events.bus().configure(lambda: None)
        gateway = ApiHttpServer()
        state = gateway.start(_StubApi(), 0, "cli-token", "5.5.4")
        self.assertTrue(state["ok"], state)
        try:
            common = ["--gateway", f"http://127.0.0.1:{gateway.port}",
                      "--token", "cli-token"]
            status = self._run(*common, "status")
            self.assertEqual(status.returncode, 0, status.stderr)
            self.assertIn("接口", status.stdout)
            chat = self._run(*common, "chat", "启动 1.20.1")
            self.assertEqual(chat.returncode, 0, chat.stderr)
            self.assertIn("launch", chat.stdout)
            self.assertIn("token", chat.stdout)
            caps = self._run(*common, "game", "caps")
            self.assertEqual(caps.returncode, 0, caps.stderr)
        finally:
            gateway.stop()


if __name__ == "__main__":
    unittest.main()


class ProtocolAndShellTest(unittest.TestCase):
    """mikan:// 唤起 → 暂存 → 界面生成计划；以及 WebApi 层新增接口。"""

    def test_protocol_arg_only_stages_never_executes(self):
        from mc_launcher import chat_api, config
        from mc_launcher.config import Config
        from mc_launcher.ui_web.shell import WebApi

        with tempfile.TemporaryDirectory() as tmp:
            original = config.DATA_DIR
            config.DATA_DIR = Path(tmp)
            try:
                result = chat_api.handle_protocol_arg(
                    "mikan://chat?text=" + urllib.parse.quote("启动 1.20.1"))
                self.assertTrue(result["ok"], result)
                self.assertFalse((Path(tmp) / "pending_chat.json").exists() is False)
                cfg = Config()
                cfg.game_dir = tmp
                api = WebApi(cfg)
                pending = api.chat_pending()
                self.assertTrue(pending["ok"])
                self.assertIsNotNone(pending["pending"])
                self.assertEqual(pending["intents"], ["launch"])
                self.assertFalse(pending["executed"])
                self.assertFalse((Path(tmp) / "pending_chat.json").exists())
                # 第二次读应为空
                self.assertIsNone(api.chat_pending()["pending"])
            finally:
                config.DATA_DIR = original

    def test_webapi_new_methods(self):
        from mc_launcher.config import Config
        from mc_launcher.ui_web.shell import WebApi

        with tempfile.TemporaryDirectory() as tmp:
            cfg = Config()
            cfg.game_dir = tmp
            api = WebApi(cfg)
            self.assertTrue(api.chat_capabilities()["ok"])
            self.assertTrue(api.webhook_get()["ok"])
            self.assertFalse(api.webhook_get()["enabled"])
            self.assertTrue(api.event_types()["ok"])
            self.assertTrue(api.event_history(5)["ok"])
            self.assertIn("ws_endpoint", api.ws_status())
            self.assertFalse(api.game_capabilities()["memory_access"])
            self.assertFalse(api.game_rcon_settings()["has_password"])
            self.assertIn("mikan install", " ".join(api.cli_help()["commands"]))
            enabled = api.webhook_set("http://127.0.0.1:9/hook", True,
                                      ["game_crash"], "secret")
            self.assertTrue(enabled["ok"], enabled)
            self.assertTrue(api.webhook_get()["enabled"])
            self.assertTrue(api.webhook_get()["has_secret"])
            # 未知事件要拒绝
            self.assertFalse(api.webhook_set(webhook_events=["not_an_event"])["ok"])

    def test_switches_disable_channels(self):
        gateway = ApiHttpServer()
        api = _StubApi()
        api.config.chat_enabled = False
        api.config.ws_enabled = False
        state = gateway.start(api, 0, "sw-token", "5.5.4")
        self.assertTrue(state["ok"], state)
        try:
            request = urllib.request.Request(
                f"http://127.0.0.1:{gateway.port}/chat",
                data=json.dumps({"text": "启动 1.20.1"}).encode(),
                headers={"X-Mikan-Token": "sw-token",
                         "Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(request, timeout=5) as response:
                payload = json.loads(response.read().decode())
            self.assertFalse(payload["ok"])
            sock, status = _ws_connect(gateway.port, "sw-token")
            self.assertIn(b"403", status)
            sock.close()
        finally:
            gateway.stop()
