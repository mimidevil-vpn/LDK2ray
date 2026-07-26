# -*- coding: utf-8 -*-
"""Разбор ссылок протоколов и подписок в единую структуру Server."""

import json
import base64
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlparse, parse_qs, unquote


@dataclass
class Server:
    name: str = "Server"
    protocol: str = "vless"        # vless | vmess | trojan | shadowsocks
    address: str = ""
    port: int = 443
    uuid: str = ""
    password: str = ""
    method: str = ""               # шифр shadowsocks
    alter_id: int = 0              # vmess
    network: str = "tcp"           # tcp | ws | grpc | h2 | xhttp | httpupgrade
    security: str = "none"         # none | tls | reality
    sni: str = ""
    host: str = ""                 # Host-заголовок ws/h2/xhttp
    path: str = ""                 # путь ws / serviceName grpc
    flow: str = ""                 # vless flow (напр. xtls-rprx-vision)
    fingerprint: str = ""          # uTLS fingerprint
    public_key: str = ""           # reality pbk
    short_id: str = ""             # reality sid
    spider_x: str = ""             # reality spx
    mode: str = ""                 # режим xhttp: auto | packet-up | stream-up ...
    extra: str = ""                # доп. параметры xhttp (JSON-строка)
    alpn: str = ""
    allow_insecure: bool = False
    raw: str = ""


def _b64decode(s: str) -> bytes:
    s = s.strip().replace("-", "+").replace("_", "/")
    pad = len(s) % 4
    if pad:
        s += "=" * (4 - pad)
    return base64.b64decode(s)


def _one(q, key, default=""):
    v = q.get(key)
    return v[0] if v else default


def _parse_vless(link: str) -> Server:
    u = urlparse(link)
    q = parse_qs(u.query)
    s = Server(protocol="vless", raw=link)
    s.uuid = unquote(u.username or "")
    s.address = u.hostname or ""
    s.port = u.port or 443
    s.name = unquote(u.fragment) if u.fragment else s.address
    s.network = _one(q, "type", "tcp")
    s.security = _one(q, "security", "none")
    s.sni = _one(q, "sni") or _one(q, "peer")
    s.flow = _one(q, "flow")
    s.fingerprint = _one(q, "fp")
    s.public_key = _one(q, "pbk")
    s.short_id = _one(q, "sid")
    s.spider_x = unquote(_one(q, "spx"))
    s.host = _one(q, "host")
    s.path = unquote(_one(q, "path")) or _one(q, "serviceName")
    s.mode = _one(q, "mode")
    s.extra = unquote(_one(q, "extra"))
    s.alpn = _one(q, "alpn")
    s.allow_insecure = _one(q, "allowInsecure", "0") in ("1", "true", "True")
    return s


def _parse_vmess(link: str) -> Server:
    payload = link[len("vmess://"):]
    data = json.loads(_b64decode(payload).decode("utf-8", "ignore"))
    s = Server(protocol="vmess", raw=link)
    s.name = str(data.get("ps") or data.get("add") or "vmess")
    s.address = str(data.get("add", ""))
    s.port = int(data.get("port") or 443)
    s.uuid = str(data.get("id", ""))
    s.alter_id = int(data.get("aid") or 0)
    s.network = str(data.get("net") or "tcp")
    s.host = str(data.get("host") or "")
    s.path = str(data.get("path") or "")
    tls = str(data.get("tls") or "")
    s.security = "tls" if tls in ("tls", "reality") else "none"
    s.sni = str(data.get("sni") or data.get("host") or "")
    s.fingerprint = str(data.get("fp") or "")
    s.alpn = str(data.get("alpn") or "")
    return s


def _parse_trojan(link: str) -> Server:
    u = urlparse(link)
    q = parse_qs(u.query)
    s = Server(protocol="trojan", raw=link)
    s.password = unquote(u.username or "")
    s.address = u.hostname or ""
    s.port = u.port or 443
    s.name = unquote(u.fragment) if u.fragment else s.address
    s.network = _one(q, "type", "tcp")
    sec = _one(q, "security", "tls")
    s.security = "tls" if sec in ("", "none") else sec
    s.sni = _one(q, "sni") or _one(q, "peer") or s.address
    s.host = _one(q, "host")
    s.path = unquote(_one(q, "path")) or _one(q, "serviceName")
    s.fingerprint = _one(q, "fp")
    s.alpn = _one(q, "alpn")
    s.allow_insecure = _one(q, "allowInsecure", "0") in ("1", "true", "True")
    return s


def _parse_ss(link: str) -> Server:
    body = link[len("ss://"):]
    name = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        name = unquote(frag)
    s = Server(protocol="shadowsocks", raw=link)

    if "@" in body:
        userinfo, hostport = body.rsplit("@", 1)
        method, password = "", ""
        try:
            dec = _b64decode(userinfo).decode("utf-8", "ignore")
            if ":" in dec:
                method, password = dec.split(":", 1)
            else:
                method = dec
        except Exception:
            u = unquote(userinfo)
            if ":" in u:
                method, password = u.split(":", 1)
            else:
                method = u
    else:
        dec = _b64decode(body).decode("utf-8", "ignore")
        creds, _, hostport = dec.rpartition("@")
        method, _, password = creds.partition(":")

    hostport = hostport.split("/")[0].split("?")[0]
    host, _, port = hostport.partition(":")
    s.method = method
    s.password = password
    s.address = host
    s.port = int(port or 8388)
    s.name = name or host
    return s


def parse_link(link: str):
    link = (link or "").strip()
    try:
        if link.startswith("vless://"):
            return _parse_vless(link)
        if link.startswith("vmess://"):
            return _parse_vmess(link)
        if link.startswith("trojan://"):
            return _parse_trojan(link)
        if link.startswith("ss://"):
            return _parse_ss(link)
    except Exception:
        return None
    return None


def parse_many(text: str) -> list:
    servers = []
    for line in (text or "").replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        srv = parse_link(line)
        if srv:
            servers.append(srv)
    return servers


def parse_subscription(content: str) -> list:
    """Подписка бывает base64 всего списка либо plain-текст."""
    content = (content or "").strip()
    text = content
    try:
        dec = _b64decode(content).decode("utf-8", "ignore")
        if "://" in dec:
            text = dec
    except Exception:
        pass
    return parse_many(text)


def parse_userinfo(header: str) -> dict:
    """Разбирает заголовок subscription-userinfo от панели провайдера.

    Формат общепринятый: «upload=1234; download=5678; total=107374182400;
    expire=1735689600». Любое поле может отсутствовать; total=0 или expire=0
    означают «безлимит» / «бессрочно».
    """
    info = {}
    for part in (header or "").replace(",", ";").split(";"):
        key, _, value = part.strip().partition("=")
        key = key.strip().lower()
        if key not in ("upload", "download", "total", "expire"):
            continue
        try:
            info[key] = int(float(value.strip()))
        except Exception:
            pass
    return info


def fetch_subscription(url: str, timeout: float = 15.0) -> tuple:
    """Возвращает (содержимое, инфо о подписке).

    Панели (Marzban, 3x-ui, Remnawave и прочие) кладут лимиты и срок действия
    в заголовки ответа — оттуда и берём остаток трафика и дату окончания.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "HappX/1.0 (Xray client)"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "ignore")
        headers = resp.headers
        info = parse_userinfo(headers.get("subscription-userinfo", ""))

        title = _maybe_base64(headers.get("profile-title", ""))
        if title:
            info["title"] = title
        # объявление провайдера («нажмите обновить, если не работает» и т.п.)
        announce = _maybe_base64(headers.get("announce", ""))
        if announce:
            info["announce"] = announce
        support = (headers.get("support-url", "") or "").strip()
        if support:
            info["support_url"] = support
        try:
            refill = int(headers.get("subscription-refill-date", "") or 0)
            if refill:
                info["refill"] = refill        # когда провайдер обнулит трафик
        except Exception:
            pass
        return body, info


def _maybe_base64(value: str) -> str:
    """Панели присылают заголовки либо как есть, либо с префиксом base64:."""
    v = (value or "").strip()
    if v.lower().startswith("base64:"):
        try:
            return _b64decode(v[7:]).decode("utf-8", "ignore").strip()
        except Exception:
            return ""
    return v
