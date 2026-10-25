"""账号系统：离线账号、微软正版（设备码登录）、第三方外置登录（authlib-injector）。"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import threading
import time
import urllib.parse
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import (
    AUTHLIB_INJECTOR_LATEST,
    DATA_DIR,
    DEFAULT_MICROSOFT_CLIENT_ID,
    Config,
)
from .net import Candidate, DownloadError, Http

ACCOUNTS_PATH = DATA_DIR / "accounts.json"
LIBS_DIR = DATA_DIR / "libs"

MS_DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MS_SCOPE = "XboxLive.signin offline_access"
# 旧版 Live Connect（Minecraft 官方客户端 ID），用于浏览器授权码/隐式登录
MS_LEGACY_CLIENT_ID = "00000000402b5328"
MS_LEGACY_AUTHORIZE_URL = "https://login.live.com/oauth20_authorize.srf"
MS_LEGACY_TOKEN_URL = "https://login.live.com/oauth20_token.srf"
MS_LEGACY_REDIRECT = "https://login.live.com/oauth20_desktop.srf"
MS_LEGACY_SCOPE = "service::user.auth.xboxlive.com::MBI_SSL"
XBL_URL = "https://user.auth.xboxlive.com/user/authenticate"
XSTS_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"
MC_LOGIN_URL = "https://api.minecraftservices.com/authentication/login_with_xbox"
MC_PROFILE_URL = "https://api.minecraftservices.com/minecraft/profile"
MC_SKIN_UPLOAD_URL = "https://api.minecraftservices.com/minecraft/profile/skins"

ACCOUNT_TYPES = {
    "offline": "离线账号",
    "microsoft": "微软正版",
    "authlib": "外置登录",
}


class AuthError(Exception):
    pass


def offline_uuid(player_name: str) -> str:
    import hashlib

    digest = bytearray(hashlib.md5(f"OfflinePlayer:{player_name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    hexed = digest.hex()
    return f"{hexed[0:8]}-{hexed[8:12]}-{hexed[12:16]}-{hexed[16:20]}-{hexed[20:32]}"


def format_uuid(raw: str) -> str:
    text = (raw or "").strip()
    if len(text) == 32 and "-" not in text:
        return f"{text[0:8]}-{text[8:12]}-{text[12:16]}-{text[16:20]}-{text[20:32]}"
    return text


def normalize_server(server: str) -> str:
    server = (server or "").strip().rstrip("/")
    if server and not server.lower().startswith(("http://", "https://")):
        server = "https://" + server
    return server


@dataclass
class Account:
    id: str
    type: str
    name: str
    uuid: str = ""
    access_token: str = ""
    refresh_token: str = ""
    client_token: str = ""
    auth_server: str = ""
    expires_at: float = 0.0
    last_refresh: float = 0.0
    skin_url: str = ""
    skin_path: str = ""
    note: str = ""
    token_endpoint: str = ""

    @property
    def type_label(self) -> str:
        return ACCOUNT_TYPES.get(self.type, self.type)

    @property
    def is_online(self) -> bool:
        return self.type == "microsoft" and bool(self.access_token)

    @property
    def token_expired(self) -> bool:
        return bool(self.expires_at) and self.expires_at - 120 < time.time()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "uuid": self.uuid,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "client_token": self.client_token,
            "auth_server": self.auth_server,
            "expires_at": self.expires_at,
            "last_refresh": self.last_refresh,
            "skin_url": self.skin_url,
            "skin_path": self.skin_path,
            "note": self.note,
            "token_endpoint": self.token_endpoint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        account_type = str(data.get("type") or "offline")
        name = str(data.get("name") or "Steve")
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            type=account_type,
            name=name,
            uuid=str(data.get("uuid") or (offline_uuid(name) if account_type == "offline" else "")),
            access_token=str(data.get("access_token") or ""),
            refresh_token=str(data.get("refresh_token") or ""),
            client_token=str(data.get("client_token") or ""),
            auth_server=str(data.get("auth_server") or ""),
            expires_at=float(data.get("expires_at") or 0.0),
            last_refresh=float(data.get("last_refresh") or 0.0),
            skin_url=str(data.get("skin_url") or ""),
            skin_path=str(data.get("skin_path") or ""),
            note=str(data.get("note") or ""),
            token_endpoint=str(data.get("token_endpoint") or ""),
        )


class AccountStore:
    """账号持久化。令牌保存在本地 data/accounts.json，请勿分享该文件。"""

    def __init__(self, path: Path = ACCOUNTS_PATH, default_name: str = "Steve"):
        self.path = Path(path)
        self.accounts: list[Account] = []
        self.selected_id: str = ""
        self._lock = threading.Lock()
        self._default_name = default_name or "Steve"
        self.load()

    def load(self) -> None:
        raw: dict = {}
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    raw = data
            except (OSError, ValueError):
                raw = {}
        accounts = []
        for item in raw.get("accounts") or []:
            if isinstance(item, dict):
                item = dict(item)
                for key in ("access_token", "refresh_token", "client_token"):
                    item[key] = unprotect_token(str(item.get(key) or ""))
                accounts.append(Account.from_dict(item))
        self.accounts = accounts
        self.selected_id = str(raw.get("selected_id") or "")
        if not self.accounts:
            self.accounts = [self._make_default_offline()]
        if not any(a.id == self.selected_id for a in self.accounts):
            self.selected_id = self.accounts[0].id
        self.save()

    def _make_default_offline(self) -> Account:
        name = self._default_name
        return Account(
            id="offline-" + uuid.uuid5(uuid.NAMESPACE_DNS, "mikancl-offline").hex[:8],
            type="offline",
            name=name,
            uuid=offline_uuid(name),
            note="默认离线账号",
        )

    def save(self) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "selected_id": self.selected_id,
                "accounts": [self._protected_dict(a) for a in self.accounts],
            }
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            os.replace(tmp, self.path)

    def _protected_dict(self, account: Account) -> dict:
        data = account.to_dict()
        for key in ("access_token", "refresh_token", "client_token"):
            data[key] = protect_token(str(data.get(key) or ""))
        return data

    def selected(self) -> Account:
        for account in self.accounts:
            if account.id == self.selected_id:
                return account
        if not self.accounts:
            self.accounts = [self._make_default_offline()]
        return self.accounts[0]

    def set_selected(self, account_id: str) -> None:
        if any(a.id == account_id for a in self.accounts):
            self.selected_id = account_id
            self.save()

    def get(self, account_id: str) -> Account | None:
        for account in self.accounts:
            if account.id == account_id:
                return account
        return None

    def add(self, account: Account) -> None:
        existing = self.get(account.id)
        if existing:
            self.update(account)
        else:
            self.accounts.append(account)
        self.selected_id = account.id
        self.save()

    def update(self, account: Account) -> None:
        for index, item in enumerate(self.accounts):
            if item.id == account.id:
                self.accounts[index] = account
                break
        self.save()

    def remove(self, account_id: str) -> None:
        if len(self.accounts) <= 1:
            raise AuthError("至少需要保留一个账号。")
        self.accounts = [a for a in self.accounts if a.id != account_id]
        if self.selected_id == account_id:
            self.selected_id = self.accounts[0].id
        self.save()

    def make_offline(self, name: str) -> Account:
        name = (name or "").strip() or "Steve"
        if len(name) > 16:
            raise AuthError("昵称不能超过 16 个字符。")
        return Account(
            id=f"offline-{uuid.uuid4().hex[:10]}",
            type="offline",
            name=name,
            uuid=offline_uuid(name),
            note="离线账号",
        )


# ---------------------------------------------------------------------------
# 微软正版登录（OAuth 2.0 设备码）
# ---------------------------------------------------------------------------
@dataclass
class DeviceFlow:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int = 900
    interval: int = 5
    message: str = ""
    started_at: float = field(default_factory=time.time)


class MicrosoftAuth:
    def __init__(self, client_id: str = "", http: Http | None = None):
        self.client_id = (client_id or DEFAULT_MICROSOFT_CLIENT_ID).strip()
        self.http = http or Http(timeout=30)

    def start_device_flow(self) -> DeviceFlow:
        try:
            data = self.http.post_form_url(
                MS_DEVICE_CODE_URL,
                {"client_id": self.client_id, "scope": MS_SCOPE},
            )
        except DownloadError as exc:
            raise AuthError(f"无法连接微软登录服务：{exc}") from exc
        if not isinstance(data, dict) or not data.get("device_code"):
            raise AuthError("微软登录服务返回了意外的数据。")
        return DeviceFlow(
            device_code=str(data["device_code"]),
            user_code=str(data.get("user_code") or ""),
            verification_uri=str(data.get("verification_uri") or "https://microsoft.com/link"),
            expires_in=int(data.get("expires_in") or 900),
            interval=max(2, int(data.get("interval") or 5)),
            message=str(data.get("message") or ""),
        )

    def poll(self, flow: DeviceFlow, cancel: threading.Event | None = None,
             log: Callable[[str], None] | None = None) -> Account:
        deadline = flow.started_at + flow.expires_in
        while time.time() < deadline:
            if cancel is not None and cancel.is_set():
                raise AuthError("登录已取消。")
            payload = {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "client_id": self.client_id,
                "device_code": flow.device_code,
            }
            try:
                data = self.http.post_form_url(MS_TOKEN_URL, payload)
            except DownloadError as exc:
                message = str(exc)
                # 设备码尚未确认时微软会返回 400，需要继续轮询
                if "authorization_pending" in message:
                    time.sleep(flow.interval)
                    continue
                if "slow_down" in message:
                    flow.interval += 2
                    time.sleep(flow.interval)
                    continue
                if "expired_token" in message or "code_expired" in message:
                    raise AuthError("设备码已过期，请重新发起登录。") from exc
                if "authorization_declined" in message:
                    raise AuthError("登录被拒绝。") from exc
                if "bad_verification_code" in message:
                    raise AuthError("设备码无效，请重新发起登录。") from exc
                raise AuthError(message) from exc
            if isinstance(data, dict) and data.get("access_token"):
                if log:
                    log("[登录] 微软账号授权成功，正在获取 Xbox / Minecraft 令牌…")
                return self._login_minecraft(str(data["access_token"]), str(data.get("refresh_token") or ""))
            if log:
                log("[登录] 等待你在浏览器中完成授权…")
            time.sleep(flow.interval)
        raise AuthError("登录超时，请重新发起登录。")

    @staticmethod
    def legacy_authorize_url() -> str:
        """旧版 Live Connect 授权地址（隐式流，令牌在跳转片段中返回）。"""
        query = {
            "client_id": MS_LEGACY_CLIENT_ID,
            "scope": MS_LEGACY_SCOPE,
            "response_type": "token",
            "redirect_uri": MS_LEGACY_REDIRECT,
            "prompt": "select_account",
        }
        return MS_LEGACY_AUTHORIZE_URL + "?" + urllib.parse.urlencode(query)

    def login_with_live_tokens(
        self, access_token: str, refresh_token: str, log: Callable[[str], None] | None = None
    ) -> Account:
        """用旧版浏览器登录拿到的 Live 令牌换取 Minecraft 档案。"""
        if not access_token:
            raise AuthError("浏览器登录未返回访问令牌。")
        if log:
            log("[登录] 已获取微软访问令牌，正在换取 Minecraft 档案…")
        account = self._login_minecraft(access_token, refresh_token)
        account.token_endpoint = MS_LEGACY_TOKEN_URL
        account.expires_at = time.time() + 3500
        return account

    def refresh(self, account: Account, log: Callable[[str], None] | None = None) -> Account:
        if not account.refresh_token:
            raise AuthError("该账号缺少刷新令牌，请重新登录。")
        legacy = account.token_endpoint == MS_LEGACY_TOKEN_URL
        client_id = MS_LEGACY_CLIENT_ID if legacy else self.client_id
        scope = MS_LEGACY_SCOPE if legacy else MS_SCOPE
        try:
            data = self.http.post_form_url(
                account.token_endpoint or MS_TOKEN_URL,
                {
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "refresh_token": account.refresh_token,
                    "scope": scope,
                },
            )
        except DownloadError as exc:
            raise AuthError(f"刷新登录状态失败，请重新登录：{exc}") from exc
        if not isinstance(data, dict) or not data.get("access_token"):
            raise AuthError("刷新登录状态失败，请重新登录。")
        if log:
            log("[登录] 令牌已刷新，正在获取 Minecraft 档案…")
        fresh = self._login_minecraft(
            str(data["access_token"]), str(data.get("refresh_token") or account.refresh_token)
        )
        fresh.id = account.id
        fresh.token_endpoint = account.token_endpoint
        return fresh

    def _login_minecraft(self, ms_token: str, refresh_token: str) -> Account:
        # 1. Xbox Live
        try:
            xbl = self.http.post_json_url(
                XBL_URL,
                {
                    "Properties": {"SiteName": "user.auth.xboxlive.com", "RpsTicket": f"d={ms_token}"},
                    "RelyingParty": "http://auth.xboxlive.com",
                    "TokenType": "JWT",
                },
            )
        except DownloadError as exc:
            raise AuthError(f"Xbox Live 认证失败：{exc}") from exc
        token = str((xbl or {}).get("Token") or "")
        uhs = ""
        try:
            uhs = str(xbl["DisplayClaims"]["xui"][0]["uhs"])  # type: ignore[index]
        except Exception:  # noqa: BLE001
            uhs = ""
        if not token or not uhs:
            raise AuthError("Xbox Live 返回数据异常。")
        # 2. XSTS
        try:
            xsts = self.http.post_json_url(
                XSTS_URL,
                {
                    "Properties": {"SandboxId": "RETAIL", "UserTokens": [token]},
                    "RelyingParty": "rp://api.minecraftservices.com/",
                    "TokenType": "JWT",
                },
            )
        except DownloadError as exc:
            message = str(exc)
            hints = {
                "2148916233": "该微软账号尚未创建 Xbox 档案，请先登录 xbox.com 创建档案。",
                "2148916235": "该账号所在地区不支持 Xbox Live。",
                "2148916238": "未成年账号需要先由家庭组批准。",
            }
            for code, hint in hints.items():
                if code in message:
                    raise AuthError(hint) from exc
            raise AuthError(f"XSTS 认证失败：{message}") from exc
        xsts_token = str((xsts or {}).get("Token") or "")
        xsts_uhs = ""
        try:
            xsts_uhs = str(xsts["DisplayClaims"]["xui"][0]["uhs"])  # type: ignore[index]
        except Exception:  # noqa: BLE001
            xsts_uhs = uhs
        if not xsts_token:
            raise AuthError("XSTS 返回数据异常。")
        # 3. Minecraft 登录
        try:
            login = self.http.post_json_url(
                MC_LOGIN_URL, {"identityToken": f"XBL3.0 x={xsts_uhs};{xsts_token}"}
            )
        except DownloadError as exc:
            raise AuthError(f"Minecraft 登录失败：{exc}") from exc
        mc_token = str((login or {}).get("access_token") or "")
        if not mc_token:
            raise AuthError("Minecraft 登录失败：未返回访问令牌。")
        # 4. 玩家档案
        try:
            profile = self.http.get_json_url(
                MC_PROFILE_URL, headers={"Authorization": f"Bearer {mc_token}"}
            )
        except DownloadError as exc:
            raise AuthError("该微软账号没有购买 Minecraft Java 版。") from exc
        if not isinstance(profile, dict) or not profile.get("id"):
            raise AuthError("无法读取 Minecraft 玩家档案。")
        name = str(profile.get("name") or "Player")
        skin_url = ""
        skins = profile.get("skins") or []
        if isinstance(skins, list) and skins and isinstance(skins[0], dict):
            skin_url = str(skins[0].get("url") or "")
        return Account(
            id=f"ms-{format_uuid(str(profile['id']))}",
            type="microsoft",
            name=name,
            uuid=format_uuid(str(profile["id"])),
            access_token=mc_token,
            refresh_token=refresh_token,
            expires_at=time.time() + 86400,
            last_refresh=time.time(),
            skin_url=skin_url,
            note="微软正版账号",
        )


# ---------------------------------------------------------------------------
# 第三方外置登录（authlib-injector / Yggdrasil）
# ---------------------------------------------------------------------------
def authlib_login(server: str, username: str, password: str, http: Http | None = None) -> Account:
    server = normalize_server(server)
    if not server:
        raise AuthError("请填写外置登录服务器地址。")
    if not username:
        raise AuthError("请填写用户名或邮箱。")
    http = http or Http(timeout=30)
    client_token = uuid.uuid4().hex
    payload = {
        "username": username,
        "password": password,
        "clientToken": client_token,
        "agent": {"name": "Minecraft", "version": 1},
        "requestUser": True,
    }
    try:
        data = http.post_json_url(server + "/authserver/authenticate", payload)
    except DownloadError as exc:
        raise AuthError(f"外置登录失败：{exc}") from exc
    if not isinstance(data, dict):
        raise AuthError("外置登录服务器返回数据异常。")
    if data.get("error"):
        raise AuthError(str(data.get("errorMessage") or data.get("error")))
    token = str(data.get("accessToken") or "")
    profile = data.get("selectedProfile") if isinstance(data.get("selectedProfile"), dict) else {}
    if not token or not profile:
        raise AuthError("登录成功但该账号没有可用角色。")
    name = str(profile.get("name") or username)
    return Account(
        id=f"authlib-{uuid.uuid4().hex[:10]}",
        type="authlib",
        name=name,
        uuid=format_uuid(str(profile.get("id") or "")),
        access_token=token,
        client_token=str(data.get("clientToken") or client_token),
        auth_server=server,
        note=f"外置登录 · {server}",
    )


def injector_jar_path() -> Path:
    """authlib-injector 的默认缓存路径。"""
    return LIBS_DIR / "authlib-injector.jar"


def ensure_authlib_injector(
    config: Config, log: Callable[[str], None] | None = None
) -> Path:
    """下载并缓存 authlib-injector，供外置登录启动时作为 javaagent 使用。"""
    LIBS_DIR.mkdir(parents=True, exist_ok=True)
    cached = Path(config.authlib_injector_path) if config.authlib_injector_path else LIBS_DIR / "authlib-injector.jar"
    if cached.exists() and cached.stat().st_size > 1024:
        return cached
    url = config.authlib_injector_url or AUTHLIB_INJECTOR_LATEST
    http = Http(timeout=30)
    try:
        meta = http.get_json_url(url)
    except DownloadError as exc:
        raise AuthError(f"无法获取 authlib-injector 信息：{exc}") from exc
    download_url = ""
    if isinstance(meta, dict):
        download_url = str(meta.get("download_url") or meta.get("url") or "")
    if not download_url:
        raise AuthError("authlib-injector 下载地址为空，请检查镜像设置。")
    if log:
        log(f"[外置登录] 正在下载 authlib-injector：{download_url}")
    try:
        http.download([Candidate(download_url)], cached, size=None, sha1=None)
    except DownloadError as exc:
        raise AuthError(f"下载 authlib-injector 失败：{exc}") from exc
    config.authlib_injector_path = str(cached)
    config.save()
    return cached


# ---------------------------------------------------------------------------
# 皮肤
# ---------------------------------------------------------------------------
def _png_size(data: bytes) -> tuple[int, int]:
    import struct

    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return (0, 0)
    return struct.unpack(">II", data[16:24])


def validate_skin_file(path: str | Path) -> tuple[int, int]:
    """校验皮肤文件（PNG、64x64 或 64x32、不超过 24KB），返回尺寸。"""
    file = Path(path)
    if not file.exists():
        raise AuthError("皮肤文件不存在。")
    data = file.read_bytes()
    if len(data) > 24576:
        raise AuthError("皮肤文件超过 24 KB，请压缩后再上传。")
    width, height = _png_size(data)
    if not width:
        raise AuthError("皮肤必须是 PNG 格式。")
    if width != 64 or height not in (32, 64):
        raise AuthError(f"皮肤尺寸应为 64×64 或 64×32，当前为 {width}×{height}。")
    return width, height


def upload_skin(
    account: Account,
    image: str | Path,
    slim: bool = False,
    log: Callable[[str], None] | None = None,
) -> str:
    """为微软正版账号上传皮肤，返回新的皮肤地址。"""
    if account.type != "microsoft" or not account.access_token:
        raise AuthError("只有微软正版账号支持上传皮肤，请先登录正版账号。")
    path = Path(image)
    validate_skin_file(path)
    if log:
        log(f"[皮肤] 正在上传 {path.name}（{'纤细' if slim else '经典'} 模型）…")
    try:
        data = Http(timeout=45).post_multipart_url(
            MC_SKIN_UPLOAD_URL,
            {"variant": "slim" if slim else "classic"},
            {"file": (path.name, path.read_bytes(), "image/png")},
            headers={"Authorization": f"Bearer {account.access_token}"},
        )
    except DownloadError as exc:
        raise AuthError(f"上传皮肤失败：{exc}") from exc
    skin_url = ""
    if isinstance(data, dict):
        skins = data.get("skins") or []
        if isinstance(skins, list):
            for item in skins:
                if isinstance(item, dict) and item.get("state") == "ACTIVE":
                    skin_url = str(item.get("url") or "")
                    break
            if not skin_url and skins and isinstance(skins[0], dict):
                skin_url = str(skins[0].get("url") or "")
    account.skin_url = skin_url or account.skin_url
    if log:
        log("[皮肤] 上传成功，重新进入游戏即可看到新皮肤。")
    return account.skin_url


MOJANG_PROFILE_URL = "https://api.mojang.com/users/profiles/minecraft/{name}"
MOJANG_SESSION_URL = "https://sessionserver.mojang.com/session/minecraft/profile/{uuid}"


def lookup_skin_by_name(name: str, http: Http | None = None) -> dict:
    """通过正版账号名查询其皮肤（无需登录），返回 uuid/name/skin_url/model/cape_url。"""
    keyword = (name or "").strip()
    if not keyword:
        raise AuthError("请输入要查询的正版账号名。")
    client = http or Http(timeout=20)
    try:
        profile = client.get_json_url(
            MOJANG_PROFILE_URL.format(name=urllib.parse.quote(keyword))
        )
    except DownloadError as exc:
        raise AuthError(f"未找到正版账号 {keyword}：{exc}") from exc
    if not isinstance(profile, dict) or not profile.get("id"):
        raise AuthError(f"未找到正版账号 {keyword}。")
    raw_uuid = str(profile.get("id") or "")
    textures: dict = {}
    try:
        session = client.get_json_url(MOJANG_SESSION_URL.format(uuid=raw_uuid))
        if isinstance(session, dict):
            for prop in session.get("properties") or []:
                if isinstance(prop, dict) and prop.get("name") == "textures":
                    try:
                        payload = base64.b64decode(str(prop.get("value") or ""))
                        decoded = json.loads(payload.decode("utf-8"))
                    except (ValueError, UnicodeDecodeError):
                        decoded = {}
                    if isinstance(decoded, dict):
                        textures = decoded.get("textures") or {}
                    break
    except DownloadError:
        textures = {}
    skin = textures.get("SKIN") if isinstance(textures.get("SKIN"), dict) else {}
    cape = textures.get("CAPE") if isinstance(textures.get("CAPE"), dict) else {}
    metadata = skin.get("metadata") if isinstance(skin.get("metadata"), dict) else {}
    return {
        "uuid": format_uuid(raw_uuid),
        "name": str(profile.get("name") or keyword),
        "skin_url": str(skin.get("url") or ""),
        "model": str(metadata.get("model") or "classic"),
        "cape_url": str(cape.get("url") or ""),
    }


def download_skin_image(url: str, dest: str | Path, http: Http | None = None) -> Path:
    """下载皮肤 PNG 到本地。"""
    target = Path(dest)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (http or Http(timeout=30)).request(url)
    if not raw:
        raise AuthError("皮肤下载结果为空。")
    target.write_bytes(raw)
    return target


def apply_local_skin(account: Account, game_dir: str | Path) -> str:
    """把离线账号的本地皮肤写入 CustomSkinLoader 的本地皮肤目录（尽力而为）。"""
    source = Path(account.skin_path) if account.skin_path else None
    if source is None or not source.is_file():
        return ""
    folder = Path(game_dir) / "CustomSkinLoader" / "LocalSkin" / "skins"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{account.name}.png"
    try:
        if not target.exists() or target.stat().st_size != source.stat().st_size:
            shutil.copy2(source, target)
    except OSError as exc:
        raise AuthError(f"写入本地皮肤失败：{exc}") from exc
    return str(target)


SKIN_PACK_NAME = "MikanCL-离线皮肤.zip"
# 覆盖经典/纤细两种模型在各个版本中的默认皮肤路径
SKIN_PACK_ENTRIES = (
    "assets/minecraft/textures/entity/steve.png",
    "assets/minecraft/textures/entity/alex.png",
    "assets/minecraft/textures/entity/player/wide/steve.png",
    "assets/minecraft/textures/entity/player/slim/alex.png",
)


def _enable_resource_pack(game_dir: Path) -> None:
    """把材质包写入 options.txt 的已启用列表，避免玩家手动勾选。"""
    options = game_dir / "options.txt"
    entry = f"file/{SKIN_PACK_NAME}"
    try:
        lines = options.read_text(encoding="utf-8", errors="replace").splitlines() if options.is_file() else []
        updated = False
        result: list[str] = []
        for line in lines:
            if not line.startswith("resourcePacks:"):
                result.append(line)
                continue
            try:
                packs = json.loads(line.split(":", 1)[1])
            except ValueError:
                packs = []
            if not isinstance(packs, list):
                packs = []
            if entry in packs:
                updated = True
                result.append(line)
                continue
            packs.append(entry)
            result.append("resourcePacks:" + json.dumps(packs, ensure_ascii=False))
            updated = True
        if not updated:
            result.append("resourcePacks:" + json.dumps(["vanilla", entry], ensure_ascii=False))
        options.write_text("\n".join(result) + "\n", encoding="utf-8")
    except OSError:
        pass


def apply_skin_resourcepack(account: Account, game_dir: str | Path) -> str:
    """把离线皮肤做成资源包，替换默认玩家皮肤（仅影响本机单人游戏）。"""
    import zipfile

    source = Path(account.skin_path) if account.skin_path else None
    if source is None or not source.is_file():
        return ""
    root = Path(game_dir)
    folder = root / "resourcepacks"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / SKIN_PACK_NAME
    try:
        if not target.is_file() or target.stat().st_mtime < source.stat().st_mtime:
            image = source.read_bytes()
            meta = {
                "pack": {
                    "pack_format": 15,
                    "description": f"MikanCL 离线皮肤 · {account.name}",
                    "supported_formats": {"min_inclusive": 1, "max_inclusive": 99},
                }
            }
            with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("pack.mcmeta", json.dumps(meta, ensure_ascii=False, indent=2))
                for name in SKIN_PACK_ENTRIES:
                    archive.writestr(name, image)
        _enable_resource_pack(root)
    except (OSError, ValueError) as exc:
        raise AuthError(f"生成本地皮肤资源包失败：{exc}") from exc
    return str(target)


# ----------------------------------------------------------------------
# 令牌保护：Windows 下使用 DPAPI 加密，其他平台退化为明文存储
# ----------------------------------------------------------------------
_TOKEN_PREFIX = "dpapi:"


def _dpapi(data: bytes, decrypt: bool = False) -> bytes | None:
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DataBlob(ctypes.Structure):
            _fields_ = [
                ("cbData", wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_char)),
            ]

        buffer = ctypes.create_string_buffer(data, len(data))
        blob_in = DataBlob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char)))
        blob_out = DataBlob()
        crypt32 = ctypes.windll.crypt32
        if decrypt:
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
            )
        else:
            ok = crypt32.CryptProtectData(
                ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out)
            )
        if not ok:
            return None
        try:
            return ctypes.string_at(blob_out.pbData, blob_out.cbData)
        finally:
            ctypes.windll.kernel32.LocalFree(blob_out.pbData)
    except Exception:  # noqa: BLE001 - 加密失败时由调用方回退明文
        return None


def protect_token(value: str) -> str:
    if not value or value.startswith(_TOKEN_PREFIX):
        return value
    encrypted = _dpapi(value.encode("utf-8"))
    if encrypted is None:
        return value
    return _TOKEN_PREFIX + base64.b64encode(encrypted).decode("ascii")


def unprotect_token(value: str) -> str:
    if not value or not value.startswith(_TOKEN_PREFIX):
        return value
    try:
        encrypted = base64.b64decode(value[len(_TOKEN_PREFIX):])
    except ValueError:
        return value
    plain = _dpapi(encrypted, decrypt=True)
    if plain is None:
        return ""
    try:
        return plain.decode("utf-8")
    except UnicodeDecodeError:
        return ""

