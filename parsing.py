# -*- coding: utf-8 -*-
"""Разбор ссылок протоколов и подписок в единую структуру Server."""

import json
import base64
import ssl
import urllib.request
import urllib.error
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


def _parse_ssr(link: str) -> Server:
    """ShadowsocksR: ssr://base64url(server:port:protocol:method:obfs:pass64/?params)."""
    body = link[len("ssr://"):]
    try:
        dec = _b64decode(body).decode("utf-8", "ignore")
    except Exception:
        return None
    base, _, params = dec.partition("/?")
    parts = base.split(":")
    if len(parts) < 6:
        return None
    server, port, _protocol, method, _obfs = parts[0], parts[1], parts[2], parts[3], parts[4]
    password_b64 = parts[5]
    try:
        password = _b64decode(password_b64).decode("utf-8", "ignore")
    except Exception:
        password = password_b64
    s = Server(protocol="shadowsocks", raw=link)
    s.address = server
    try:
        s.port = int(port)
    except Exception:
        s.port = 8388
    s.method = method
    s.password = password
    q = parse_qs(params)
    name = _one(q, "remarks")
    if name:
        try:
            s.name = _b64decode(name).decode("utf-8", "ignore")
        except Exception:
            s.name = name
    else:
        s.name = server
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
        if link.startswith("ssr://"):
            return _parse_ssr(link)
    except Exception:
        return None
    return None


def _strip_quotes(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _clash_entry_to_server(e: dict) -> Server:
    """Одна запись «- name: ...» из Clash YAML в структуру Server."""
    typ = (e.get("type") or "").lower()
    srv = Server()
    srv.name = e.get("name") or e.get("server") or "Server"
    srv.address = e.get("server") or ""
    try:
        srv.port = int(e.get("port") or 443)
    except Exception:
        srv.port = 443
    srv.network = e.get("network") or "tcp"
    srv.fingerprint = e.get("client-fingerprint") or ""
    srv.flow = e.get("flow") or ""
    srv.sni = e.get("servername") or e.get("sni") or ""
    srv.public_key = e.get("reality-opts.public-key") or ""
    srv.short_id = e.get("reality-opts.short-id") or ""
    srv.host = (e.get("ws-opts.headers.Host") or e.get("http-opts.headers.Host")
                or e.get("grpc-opts.headers.Host") or e.get("h2-opts.headers.Host") or "")
    srv.path = (e.get("ws-opts.path") or e.get("http-opts.path")
                or e.get("grpc-opts.grpc-service-name") or e.get("h2-opts.path") or "")
    if e.get("reality-opts.public-key") or e.get("reality-opts") is not None:
        srv.security = "reality"
    elif e.get("tls") in ("true", "True", "1", "yes"):
        srv.security = "tls"
    if typ == "vless":
        srv.protocol = "vless"
        srv.uuid = e.get("uuid") or ""
    elif typ == "vmess":
        srv.protocol = "vmess"
        srv.uuid = e.get("uuid") or ""
        try:
            srv.alter_id = int(e.get("alterId") or 0)
        except Exception:
            srv.alter_id = 0
    elif typ == "trojan":
        srv.protocol = "trojan"
        srv.password = e.get("password") or ""
    elif typ == "ss":
        srv.protocol = "shadowsocks"
        srv.password = e.get("password") or ""
        srv.method = e.get("cipher") or "aes-256-gcm"
    else:
        return None
    return srv


def _parse_clash(content: str) -> list:
    """Минимальный парсер Clash YAML: только секция proxies (список «- name:»)."""
    entries = []
    cur = None
    prefix_stack = []
    for raw in (content or "").splitlines():
        line = raw.replace("\t", "    ").rstrip()
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        text = line.strip()
        if text.startswith("- "):
            if cur:
                entries.append(cur)
            cur = {}
            prefix_stack = [(indent, "")]
            text = text[2:].strip()
        elif cur is None:
            continue
        else:
            while prefix_stack and indent <= prefix_stack[-1][0]:
                prefix_stack.pop()
        if not text or ":" not in text:
            continue
        key, _, value = text.partition(":")
        key = key.strip()
        value = _strip_quotes(value.strip())
        if not value:
            if key.endswith(":"):
                key = key[:-1]
            prefix_stack.append((indent, key + "."))
            continue
        pfx = prefix_stack[-1][1] if prefix_stack else ""
        cur[pfx + key] = value
    if cur:
        entries.append(cur)
    out = []
    for e in entries:
        srv = _clash_entry_to_server(e)
        if srv:
            srv.raw = "clash:" + (e.get("name") or srv.name)
            out.append(srv)
    return out


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
    """Разбирает подписку в любом виде: Clash YAML, base64 всего списка,
    base64 построчно или plain-текст с прямыми ссылками."""
    content = (content or "").strip()
    if not content:
        return []

    low = content.lower()
    if "proxies:" in low and ("- name:" in low or "- type:" in low):
        clash = _parse_clash(content)
        if clash:
            return clash

    servers = parse_many(content)
    if servers:
        return servers

    try:
        dec = _b64decode(content).decode("utf-8", "ignore")
        if "://" in dec:
            servers = parse_many(dec)
            if servers:
                return servers
    except Exception:
        pass

    out = []
    for line in content.replace("\r", "\n").split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            dec = _b64decode(line).decode("utf-8", "ignore")
            if "://" in dec:
                out.extend(parse_many(dec))
        except Exception:
            continue
    return out


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


_SUB_USER_AGENTS = [
    "HappX/1.0 (Xray client)",
    "v2rayN/6.0",
    "ClashForAndroid/2.5.12",
]


def _make_ssl_context(verify=True):
    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _is_html_body(text: str) -> bool:
    """Проверяет, является ли тело ответа HTML-страницей (а не подпиской)."""
    low = text.strip()[:500].lower()
    return ("<html" in low or "<body" in low or "<!doctype" in low
            or "<head" in low or "<title" in low)


def fetch_subscription(url: str, timeout: float = 15.0) -> tuple:
    """Возвращает (содержимое, инфо о подписке).

    Панели (Marzban, 3x-ui, Remnawave и прочие) кладут лимиты и срок действия
    в заголовки ответа — оттуда и берём остаток трафика и дату окончания.
    """
    last_err = None
    for attempt, ua in enumerate(_SUB_USER_AGENTS):
        for verify in (True, False):
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            try:
                ctx = _make_ssl_context(verify)
                handler = urllib.request.ProxyHandler({})
                https = urllib.request.HTTPSHandler(context=ctx)
                opener = urllib.request.build_opener(handler, https)
                with opener.open(req, timeout=timeout) as resp:
                    body = resp.read().decode("utf-8", "ignore")
                if _is_html_body(body):
                    raise ValueError("html_response")
                headers = resp.headers
                info = parse_userinfo(headers.get("subscription-userinfo", ""))

                title = _maybe_base64(headers.get("profile-title", ""))
                if title:
                    info["title"] = title
                announce = _maybe_base64(headers.get("announce", ""))
                if announce:
                    info["announce"] = announce
                support = (headers.get("support-url", "") or "").strip()
                if support:
                    info["support_url"] = support
                try:
                    refill = int(headers.get("subscription-refill-date", "") or 0)
                    if refill:
                        info["refill"] = refill
                except Exception:
                    pass
                return body, info
            except urllib.error.URLError as e:
                last_err = e
                if verify:
                    continue
            except ValueError:
                raise
            except Exception as e:
                last_err = e
                if verify:
                    continue
    raise last_err or ValueError("unknown_error")


def _maybe_base64(value: str) -> str:
    """Панели присылают заголовки либо как есть, либо с префиксом base64:."""
    v = (value or "").strip()
    if v.lower().startswith("base64:"):
        try:
            return _b64decode(v[7:]).decode("utf-8", "ignore").strip()
        except Exception:
            return ""
    return v
