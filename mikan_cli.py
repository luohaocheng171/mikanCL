#!/usr/bin/env python3
"""MikanCL 命令行接口（mikan-cli）。

例子::

    python mikan_cli.py status
    python mikan_cli.py install 1.20.1 --loader fabric --mods sodium,iris --wait
    python mikan_cli.py launch 1.20.1
    python mikan_cli.py api list -q seed
    python mikan_cli.py api call java_scan --args '[false]'
    python mikan_cli.py chat "帮我把 1.20 版本的存档里所有附魔拉满到 255，然后启动游戏"
    python mikan_cli.py chat "..." --world "D:/mc/.minecraft/saves/MyWorld" --execute --yes
    python mikan_cli.py events tail --limit 20
    python mikan_cli.py events webhook https://example.com/hook --enable
    python mikan_cli.py game players
    python mikan_cli.py uri "mikan://chat?text=启动%201.20.1"

网关未启动时，``--offline`` 只提供本地只读能力（版本、URI 解析、接口清单
需要网关，写操作一律拒绝）。退出码：0 成功、1 接口返回失败、2 参数或连接错误。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

try:
    from mc_launcher import APP_VERSION
except Exception:  # noqa: BLE001
    APP_VERSION = "?"

GATEWAY_FILE = ROOT / "data" / "api_gateway.json"
EXIT_OK, EXIT_API, EXIT_USAGE = 0, 1, 2


def _discover() -> dict:
    """优先读运行时数据目录（打包成 exe 时源码路径是临时解包目录）。"""
    candidates = []
    try:
        from mc_launcher.config import DATA_DIR

        candidates.append(Path(DATA_DIR) / "api_gateway.json")
    except Exception:  # noqa: BLE001
        pass
    candidates.append(GATEWAY_FILE)
    for path in candidates:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
    return {}


def _base_url(args) -> str:
    url = str(getattr(args, "gateway", "") or "").strip()
    if not url:
        info = _discover()
        if info.get("port"):
            url = f"http://127.0.0.1:{info['port']}"
    return url.rstrip("/")


def _token(args) -> str:
    token = str(getattr(args, "token", "") or "").strip()
    if token:
        return token
    return str(_discover().get("token") or "")


def _request(args, path: str, payload: dict | None = None) -> dict:
    base = _base_url(args)
    if not base:
        raise RuntimeError("找不到运行中的 API 网关：请先启动 MikanCL 并在设置里开启 API 网关，或用 --gateway http://127.0.0.1:<port>")
    url = base + path
    headers = {"X-Mikan-Token": _token(args), "Accept": "application/json"}
    data = None
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    request = urllib.request.Request(url, data=data, headers=headers,
                                     method="POST" if data else "GET")
    with urllib.request.urlopen(request, timeout=float(getattr(args, "timeout", 15) or 15)) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _rpc(args, method: str, rpc_args: list | None = None, kwargs: dict | None = None) -> dict:
    return _request(args, "/rpc", {"method": method, "args": rpc_args or [],
                                   "kwargs": kwargs or {}, "id": "cli"})


def _print(data, args) -> None:
    if getattr(args, "json", False):
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return
    if not isinstance(data, dict):
        print(data)
        return
    if "reply" in data:
        print(data["reply"])
    for key in ("message", "error", "note"):
        if data.get(key):
            print(f"{key}: {data[key]}")
    if "plan" in data:
        for index, item in enumerate(data["plan"], 1):
            flag = "✓" if item.get("ready") else "· 需补参数"
            print(f"  {index}. [{item.get('risk')}] {item.get('method')} — {item.get('explain')} {flag}")
        if data.get("token"):
            print(f"  token: {data['token']}  (execute=true 才执行)")
    if "candidates" in data and data["candidates"]:
        print("  候选接口：" + "、".join(item["name"] for item in data["candidates"]))
    if "steps" in data:
        for step in data["steps"]:
            state = "OK" if step.get("ok") else "FAIL"
            print(f"  [{state}] {step.get('method')}" +
                  (f" — {step.get('error')}" if step.get("error") else ""))
    for key in ("result", "items", "players", "findings", "events", "deliveries", "groups"):
        value = data.get(key)
        if value is None:
            continue
        if isinstance(value, list):
            if key == "items" and value and isinstance(value[0], dict) and "name" in value[0]:
                for item in value[:40]:
                    print(f"  {item['name']:<38} {item.get('group', '')}  {item.get('doc', '')}")
                print(f"  共 {data.get('matched', len(value))} 项 / 全部 {data.get('total', '?')} 项")
            else:
                for item in value[:40]:
                    print("  " + (json.dumps(item, ensure_ascii=False, default=str)
                                  if isinstance(item, (dict, list)) else str(item)))
                if not value:
                    print(f"  {key}: (空)")
        elif isinstance(value, dict):
            print(f"  {key}: " + json.dumps(value, ensure_ascii=False, default=str)[:900])
        else:
            print(f"  {key}: {value}")
    if getattr(args, "json", False) is False and len(data) <= 3 and not any(
            k in data for k in ("plan", "steps", "items", "result", "message", "reply")):
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))


def _die(message: str, code: int = EXIT_USAGE) -> int:
    print(f"错误：{message}", file=sys.stderr)
    return code


def _wait_job(args, job_id: str) -> dict:
    deadline = time.time() + float(getattr(args, "wait_seconds", 600) or 600)
    while time.time() < deadline:
        response = _rpc(args, "tasks")
        rows = response.get("result") if isinstance(response.get("result"), list) else []
        for row in rows:
            if row.get("id") == job_id:
                state = row.get("state")
                if state in ("ok", "failed", "cancelled"):
                    return {"ok": state == "ok", "state": state, "job": row}
        time.sleep(1.0)
    return {"ok": False, "state": "timeout", "message": "等待任务超时"}


def _first_project_id(project: dict) -> str:
    for key in ("project_id", "id", "slug", "projectId"):
        value = project.get(key)
        if value:
            return str(value)
    return ""


def _first_version_id(item, index: int) -> str:
    if isinstance(item, str):
        return item
    if isinstance(item, dict):
        for key in ("version_id", "id", "versionId", "number"):
            if item.get(key):
                return str(item[key])
    return f"index:{index}"


# ---------------------------------------------------------------------------
# 命令实现
# ---------------------------------------------------------------------------
def cmd_status(args) -> int:
    base = _base_url(args)
    if not base:
        print(f"MikanCL {APP_VERSION} · API 网关未启动（data/api_gateway.json 不存在）")
        print("在启动器「设置 → API 网关」开启后即可使用全部 CLI 命令。")
        return EXIT_OK
    try:
        health = _request(args, "/health")
        status = _rpc(args, "api_status")
        payload = status.get("result", status)
        print(f"MikanCL {payload.get('version', APP_VERSION)} · 网关 {base}")
        print(f"  接口 {payload.get('total', '?')} 个 · 端口 {payload.get('port', '?')} · 运行 {health.get('running')}")
        print(f"  WebSocket: ws://127.0.0.1:{payload.get('port', '?')}/ws?token=<token>")
        return EXIT_OK
    except Exception as exc:  # noqa: BLE001
        return _die(str(exc))


def cmd_api(args) -> int:
    try:
        if args.api_action == "list":
            result = _rpc(args, "api_list", [args.query, args.group, args.limit])
        elif args.api_action == "call":
            rpc_args = json.loads(args.args or "[]")
            kwargs = json.loads(args.kwargs or "{}")
            result = _rpc(args, "api_call", [args.method, rpc_args, kwargs])
        elif args.api_action == "describe":
            result = _rpc(args, "api_describe", [args.method])
        elif args.api_action == "schema":
            result = _request(args, "/schema")
        else:
            return _die("未知的 api 子命令")
        payload = result.get("result", result)
        _print(payload if isinstance(payload, dict) else {"result": payload}, args)
        return EXIT_OK if (result.get("ok") and (not isinstance(payload, dict) or payload.get("ok", True))) else EXIT_API
    except (ValueError, urllib.error.URLError, RuntimeError) as exc:
        return _die(str(exc))


def cmd_install(args) -> int:
    try:
        loader_version = getattr(args, "loader_version", "") or ""
        result = _rpc(args, "install_version", [args.version, args.loader, loader_version])
        payload = result.get("result", {})
        if not payload.get("ok"):
            return _die(payload.get("message") or "安装请求失败", EXIT_API)
        print(f"已提交安装：{args.version}" + (f" + {args.loader}" if args.loader else ""))
        job_id = payload.get("job", "")
        if args.wait and job_id:
            state = _wait_job(args, job_id)
            print(f"  任务状态：{state.get('state')}")
            if not state.get("ok"):
                return EXIT_API
        mods = [item.strip() for item in (args.mods or "").split(",") if item.strip()]
        failed = []
        for name in mods:
            found = _rpc(args, "search_content",
                         ["modrinth", "mod", name, args.version, args.loader, 0, ""])
            projects = (found.get("result") or {}).get("projects") or []
            project = next((p for p in projects if _first_project_id(p)), None)
            if project is None:
                failed.append(f"{name}（未搜索到项目）")
                continue
            pid = _first_project_id(project)
            versions = _rpc(args, "content_project_versions", ["modrinth", pid])
            rows = (versions.get("result") or {}).get("versions") or []
            vid = _first_version_id(rows[0], 0) if rows else ""
            if not vid:
                failed.append(f"{name}（无兼容版本）")
                continue
            installed = _rpc(args, "install_content",
                             ["modrinth", pid, vid, "mod", "", "new", args.version])
            if not (installed.get("result") or {}).get("ok"):
                failed.append(f"{name}（提交失败）")
            else:
                print(f"  Mod：{name} → {pid} / {vid}")
        if failed:
            print("  未能安装：" + "；".join(failed))
            return EXIT_API
        print(f"完成：{args.version}" + (f"，{len(mods)} 个 Mod 已提交" if mods else ""))
        return EXIT_OK
    except (urllib.error.URLError, RuntimeError) as exc:
        return _die(str(exc))


def cmd_launch(args) -> int:
    try:
        result = _rpc(args, "launch", [args.version, "", bool(args.force)])
        _print(result.get("result", result), args)
        return EXIT_OK if (result.get("result") or {}).get("ok") else EXIT_API
    except (urllib.error.URLError, RuntimeError) as exc:
        return _die(str(exc))


def cmd_chat(args) -> int:
    try:
        payload = {"text": args.text, "version": args.version,
                   "world": args.world, "execute": False}
        first = _request(args, "/chat", payload)
        if not first.get("ok"):
            return _die(first.get("message") or "解析失败", EXIT_API)
        _print(first, args)
        if not args.execute:
            return EXIT_OK
        if not args.yes:
            print("要真正执行请再加 --yes（默认 dry-run，避免误操作）。")
            return EXIT_OK
        confirm = {"text": args.text, "version": args.version, "world": args.world,
                   "execute": True, "token": args.token or first.get("token", "")}
        second = _request(args, "/chat", confirm)
        _print(second, args)
        return EXIT_OK if second.get("ok") else EXIT_API
    except (urllib.error.URLError, RuntimeError, ValueError) as exc:
        return _die(str(exc))


def cmd_uri(args) -> int:
    try:
        from mc_launcher.chat_api import parse_mikan_uri

        parsed = parse_mikan_uri(args.uri)
        if not parsed.get("ok"):
            return _die(parsed["message"])
        args.text = parsed.get("text", "")
        args.version = args.version or parsed.get("version", "")
        args.world = args.world or parsed.get("world", "")
        args.execute = args.execute or bool(parsed.get("execute"))
        args.token = getattr(args, "token", "") or parsed.get("token", "")
        if not args.text:
            return _die("URI 里没有 text 参数")
        return cmd_chat(args)
    except RuntimeError as exc:
        return _die(str(exc))


def cmd_events(args) -> int:
    try:
        if args.events_action == "tail":
            result = _request(args, f"/events?limit={int(args.limit)}&event={urllib.parse.quote(args.event)}")
            _print({"ok": True, "events": result.get("items", [])}, args)
            return EXIT_OK
        if args.events_action == "test":
            result = _rpc(args, "webhook_test", [args.url])
            _print(result.get("result", result), args)
            return EXIT_OK if result.get("ok") else EXIT_API
        if args.events_action == "webhook":
            result = _rpc(args, "webhook_set",
                          [args.url, (args.enable if args.enable is not None else True),
                           args.events.split(",") if args.events else [], args.secret])
            _print(result.get("result", result), args)
            return EXIT_OK if result.get("ok") else EXIT_API
        return _die("未知的 events 子命令")
    except (urllib.error.URLError, RuntimeError) as exc:
        return _die(str(exc))


def cmd_game(args) -> int:
    get = lambda key, default="": getattr(args, key, default)  # noqa: E731
    mapping = {
        "players": ("game_player_state", [get("world"), get("player")]),
        "scan": ("game_scan_anomalies", [get("world")]),
        "cmd": ("game_rcon_command", [get("command")]),
        "tp": ("game_teleport", [get("player"), get("x", 0), get("y", 0), get("z", 0)]),
        "kick": ("game_kick", [get("player"), get("reason") or ""]),
        "list": ("game_list_players", []),
        "caps": ("game_capabilities", []),
    }
    method, rpc_args = mapping[args.game_action]
    try:
        result = _rpc(args, method, rpc_args)
        _print(result.get("result", result), args)
        return EXIT_OK if (result.get("result") or {}).get("ok", result.get("ok")) else EXIT_API
    except (urllib.error.URLError, RuntimeError) as exc:
        return _die(str(exc))


# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mikan", description=f"MikanCL {APP_VERSION} 命令行接口",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：mikan install 1.20.1 --loader fabric --mods sodium,iris --wait")
    parser.add_argument("--gateway", default="", help="网关地址，默认读 data/api_gateway.json")
    parser.add_argument("--token", default="", help="X-Mikan-Token，默认读 data/api_gateway.json")
    parser.add_argument("--timeout", type=float, default=15, help="HTTP 超时秒数")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出")
    parser.add_argument("--offline", action="store_true", help="离线模式（只读，不连网关）")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="启动器与网关状态")
    sub.add_parser("version", help="显示版本")

    api = sub.add_parser("api", help="调用 / 查询接口")
    api_sub = api.add_subparsers(dest="api_action")
    p = api_sub.add_parser("list", help="列出接口")
    p.add_argument("query", nargs="?", default="")
    p.add_argument("-g", "--group", default="")
    p.add_argument("--limit", type=int, default=60)
    p = api_sub.add_parser("call", help="调用任意接口")
    p.add_argument("method")
    p.add_argument("--args", default="[]", help="JSON 数组")
    p.add_argument("--kwargs", default="{}", help="JSON 对象")
    p = api_sub.add_parser("describe", help="查看接口签名")
    p.add_argument("method")
    api_sub.add_parser("schema", help="导出 OpenAPI 3 描述")

    p = sub.add_parser("install", help="安装游戏版本与可选 Mod")
    p.add_argument("version")
    p.add_argument("--loader", default="")
    p.add_argument("--loader-version", default="")
    p.add_argument("--mods", default="", help="逗号分隔的 Mod 名称（走内容中心搜索）")
    p.add_argument("--wait", action="store_true", help="等待安装任务完成")
    p.add_argument("--wait-seconds", type=int, default=600)

    p = sub.add_parser("launch", help="启动游戏")
    p.add_argument("version")
    p.add_argument("--force", action="store_true")

    p = sub.add_parser("chat", help="对话式指令（默认只出计划）")
    p.add_argument("text")
    p.add_argument("--version", default="")
    p.add_argument("--world", default="")
    p.add_argument("--execute", action="store_true", help="确认执行（还需 --yes）")
    p.add_argument("--yes", action="store_true", help="跳过人工确认")
    p.add_argument("--token", dest="chat_token", default="", help="已有的计划 token")

    p = sub.add_parser("uri", help="解析 mikan://chat?text=...")
    p.add_argument("uri")
    p.add_argument("--version", default="")
    p.add_argument("--world", default="")
    p.add_argument("--execute", action="store_true")
    p.add_argument("--yes", action="store_true")
    p.add_argument("--token", dest="chat_token", default="")

    ev = sub.add_parser("events", help="事件与 Webhook")
    ev_sub = ev.add_subparsers(dest="events_action")
    p = ev_sub.add_parser("tail", help="最近事件")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--event", default="")
    p = ev_sub.add_parser("test", help="发测试事件")
    p.add_argument("url", nargs="?", default="")
    p = ev_sub.add_parser("webhook", help="设置回调地址")
    p.add_argument("url", nargs="?", default="")
    p.add_argument("--enable", dest="enable", action="store_true", default=None)
    p.add_argument("--disable", dest="enable", action="store_false")
    p.add_argument("--events", default="", help="逗号分隔的事件名，留空=默认全部")
    p.add_argument("--secret", default="", help="HMAC-SHA256 密钥")

    game = sub.add_parser("game", help="游戏联动（存档 NBT / RCON）")
    game_sub = game.add_subparsers(dest="game_action")
    p = game_sub.add_parser("players", help="读取存档玩家状态")
    p.add_argument("--world", default="")
    p.add_argument("--player", default="")
    p = game_sub.add_parser("scan", help="扫描属性异常")
    p.add_argument("--world", default="")
    p = game_sub.add_parser("cmd", help="执行 RCON 命令")
    p.add_argument("command")
    p = game_sub.add_parser("tp", help="传送玩家（需要 RCON）")
    p.add_argument("player")
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p.add_argument("z", type=float)
    p = game_sub.add_parser("kick", help="踢出玩家（需要 RCON）")
    p.add_argument("player")
    p.add_argument("reason", nargs="?", default="")
    game_sub.add_parser("list", help="在线玩家（需要 RCON）")
    game_sub.add_parser("caps", help="能力边界说明")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return EXIT_OK
    if args.command == "version":
        print(APP_VERSION)
        return EXIT_OK
    if args.command == "chat":
        args.token = getattr(args, "chat_token", "")
    if getattr(args, "offline", False) and args.command not in ("status", "version", "uri"):
        return _die("离线模式只支持 status / version / uri；写操作必须连接运行中的网关")
    handlers = {
        "status": cmd_status, "api": cmd_api, "install": cmd_install,
        "launch": cmd_launch, "chat": cmd_chat, "uri": cmd_uri,
        "events": cmd_events, "game": cmd_game,
    }
    handler = handlers.get(args.command)
    if handler is None:
        parser.print_help()
        return EXIT_USAGE
    try:
        return handler(args)
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
