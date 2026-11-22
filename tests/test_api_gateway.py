"""统一 API 网关的回归测试（含本机 HTTP JSON-RPC 实跑）。

直接运行：``python tests/test_api_gateway.py``
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from mc_launcher import api_gateway  # noqa: E402

PASS = 0
FAIL = 0


def check(label, fn, expect=None):
    global PASS, FAIL
    try:
        value = fn()
        if expect is not None:
            assert value == expect, f"期望 {expect!r}，实际 {value!r}"
        print(f"[OK]   {label}: {value}")
        PASS += 1
        return value
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] {label}: {type(exc).__name__}: {exc}")
        FAIL += 1
        return None


class FakeApi:
    """模拟 WebApi 的一小部分公开方法。"""

    config = {"theme": "dark"}

    def launch_game(self, version: str = "1.20.1", memory: int = 4096) -> dict:
        """启动指定版本"""
        return {"launched": version, "memory": memory}

    def nbt_read(self, path: str) -> dict:
        """读取 NBT"""
        return {"path": path, "ok": True}

    def backup_overview(self) -> dict:
        """备份中心概览"""
        return {"worlds": 3}

    def terracotta_status(self) -> dict:
        """陶瓦联机状态"""
        return {"online": False}

    def eval(self) -> str:
        """危险名应被排除"""
        return "blocked"

    def _private(self) -> str:
        return "private"


def http(url: str, payload=None, token: str = "", method: str = "GET"):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    if token:
        request.add_header("X-Mikan-Token", token)
    if data:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def main() -> int:
    api = FakeApi()
    registry = api_gateway.ApiRegistry(api)
    check("反射到的公开方法数", lambda: len(registry.methods()), 4)
    check("私有方法被排除", lambda: "_private" in registry.methods(), False)
    check("危险名被排除", lambda: "eval" in registry.methods(), False)
    check("陶瓦接口仍在清单中", lambda: registry.has("terracotta_status"), True)
    check("分组正确", lambda: registry.get("nbt_read")["group"], "NBT / 存档数据")
    check("签名去掉 self", lambda: registry.get("launch_game")["signature"],
          "launch_game(version: str = '1.20.1', memory: int = 4096)")
    check("参数解析", lambda: len(registry.get("launch_game")["params"]), 2)
    check("describe 返回文档", lambda: registry.describe("launch_game")["doc"], "启动指定版本")
    check("invoke 传位置参数", lambda: registry.invoke(
        "launch_game", ["1.21.4", 6144])["result"],
        {"launched": "1.21.4", "memory": 6144})
    check("invoke 传关键字参数", lambda: registry.invoke(
        "backup_overview", [], {})["result"], {"worlds": 3})
    check("未知接口被拒绝", lambda: registry.invoke("_private")["ok"], False)
    check("参数类型错误给出签名", lambda: "signature" in registry.invoke(
        "launch_game", [1, 2, 3]), True)
    check("list 查询过滤", lambda: registry.list(query="nbt")["matched"], 1)
    check("list 分组统计", lambda: len(registry.list()["groups"]) >= 2, True)

    schema = registry.openapi("9.9.9")
    check("OpenAPI 版本", lambda: schema["info"]["version"], "9.9.9")
    check("OpenAPI 路径数", lambda: len(schema["paths"]), 4)
    check("OpenAPI 条目带中文说明", lambda: schema["paths"][
        "/rpc/nbt_read"]["post"]["summary"], "读取 NBT")

    gateway = api_gateway.ApiHttpServer()
    started = gateway.start(api, port=0, token="test-token-123", version="9.9.9")
    check("HTTP 服务启动", lambda: started["ok"], True)
    check("只监听回环地址", lambda: started["host"], "127.0.0.1")
    base = f"http://127.0.0.1:{gateway.port}"
    try:
        check("health 无需鉴权", lambda: http(base + "/health")[0], 200)
        check("未带 token 返回 401", lambda: http(base + "/rpc", {"method": "backup_overview"})[0], 401)
        check("错误 token 返回 401", lambda: http(
            base + "/rpc", {"method": "backup_overview"}, token="wrong")[0], 401)
        code, body = http(base + "/rpc", {"id": "r1", "method": "launch_game",
                                          "args": ["1.20.1", 2048]}, token="test-token-123", method="POST")
        check("合法调用返回 200", lambda: code, 200)
        check("JSON-RPC 结果正确", lambda: body["result"],
              {"launched": "1.20.1", "memory": 2048})
        check("请求 id 原样回传", lambda: body["id"], "r1")
        check("私有方法经 HTTP 被拒绝", lambda: http(
            base + "/rpc", {"method": "_private"}, token="test-token-123", method="POST")[1]["ok"], False)
        check("/api 返回接口清单", lambda: http(
            base + "/api", token="test-token-123")[1]["total"], 4)
        check("/describe 返回签名", lambda: http(
            base + "/describe/backup_overview", token="test-token-123")[1]["signature"],
            "backup_overview()")
        check("空请求体返回 400", lambda: http(
            base + "/rpc", None, token="test-token-123", method="POST")[0], 400)
    finally:
        stopped = gateway.stop()
        check("HTTP 服务已停止", lambda: stopped["running"], False)

    print(f"\n结果：{PASS} 通过 / {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
