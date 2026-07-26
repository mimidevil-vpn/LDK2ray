# -*- coding: utf-8 -*-
"""Пути приложения и сохранение/загрузка данных.

Запись атомарная (сначала во временный файл, затем замена) — если приложение
уронят или выключат питание в момент сохранения, старый файл остаётся целым.
Все сбои записи пишутся в app.log рядом с данными и всплывают в UI, чтобы
«ничего не сохраняется» больше не происходило молча.
"""

import os
import sys
import json
import time
import tempfile
from dataclasses import asdict, fields

from parsing import Server

APP_FOLDER = "LDK2ray"          # имя папки данных (не меняем — иначе потеряются
                                # настройки у тех, кто уже пользуется приложением)

_last_error = ""                # последняя ошибка записи — показываем в UI


def app_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def _writable(path: str) -> bool:
    """Папка годится, только если в неё реально получается писать."""
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write-test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


_data_dir_cache = ""


def data_dir() -> str:
    """Пользовательские данные храним в %APPDATA%\\LDK2ray — эта папка всегда
    доступна на запись, поэтому настройки/серверы сохраняются независимо от того,
    куда установлено приложение (Program Files, флешка, только-для-чтения и т.п.).
    Если по какой-то причине она недоступна — спускаемся к запасным вариантам."""
    global _data_dir_cache
    if _data_dir_cache:
        return _data_dir_cache

    candidates = []
    if os.name == "nt":
        for env in ("APPDATA", "LOCALAPPDATA", "USERPROFILE"):
            base = os.environ.get(env)
            if base:
                candidates.append(os.path.join(base, APP_FOLDER))
    candidates.append(os.path.join(app_dir(), "data"))
    candidates.append(os.path.join(tempfile.gettempdir(), APP_FOLDER))

    for c in candidates:
        if _writable(c):
            _data_dir_cache = c
            return c

    # совсем безнадёжный случай — отдаём первый вариант, ошибки уйдут в лог
    _data_dir_cache = candidates[0]
    return _data_dir_cache


def SERVERS_FILE():
    return os.path.join(data_dir(), "servers.json")


def SETTINGS_FILE():
    return os.path.join(data_dir(), "settings.json")


def LOG_FILE():
    return os.path.join(data_dir(), "app.log")


LOG_MAX_BYTES = 1_000_000        # больше мегабайта смысла не хранит


def log(msg: str) -> None:
    """Пишем в app.log — единственный источник правды, когда что-то пошло не так."""
    path = LOG_FILE()
    try:
        # чтобы файл не рос бесконечно, при переполнении оставляем свежий хвост
        if os.path.getsize(path) > LOG_MAX_BYTES:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(LOG_MAX_BYTES // 2)
                f.readline()
                tail = f.read()
            _atomic_write(path, tail)
    except Exception:
        pass
    try:
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        with open(path, "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (stamp, msg))
    except Exception:
        pass


def last_error() -> str:
    return _last_error


DEFAULT_SETTINGS = {
    "socks_port": 10808,
    "http_port": 10809,
    "system_proxy": True,       # режим «Прокси» — системный прокси Windows
    "tun_mode": False,          # режим «Туннель» — весь трафик через TUN (нужен админ)
    "xray_path": "",
    "subscription_url": "",
    "sub_info": {},             # upload/download/total/expire из заголовка панели
    "sub_updated": 0,           # когда подписка обновлялась в последний раз
    "theme": "auto",            # auto (следует теме системы) | light | dark
    "lang": "ru",
    "intro_done": False,        # интро-экран показывается только один раз
    "local_id": "",             # локальный идентификатор профиля (генерируется)
    "rating": 0,                # пользовательская оценка приложения (0..5)
    "minimize_to_tray": True,   # при закрытии сворачивать в трей, а не выходить
    "start_minimized": False,   # запускать сразу свёрнутым в трей
    "high_priority": False,     # высокий приоритет процесса (лечит вялый старт)
    "tun_dns": "1.1.1.1",       # DNS, который отдаём внутрь туннеля
    # ---- маршрутизация ----
    "route_mode": "global",     # global (всё через VPN) | rules (RU напрямую) | direct
    "direct_sites": [],         # сайты и IP в обход VPN
    "block_sites": [],          # сайты и IP, которым режем доступ
    # ---- привязанный Telegram ----
    "tg_username": "",
    "tg_name": "",
    "tg_avatar": "",            # data:image/... — храним прямо в настройках
    # ---- эмодзи возле названия (меняется раз в час) ----
    "emoji": "",
    "emoji_ts": 0,
}


def _atomic_write(path: str, text: str) -> bool:
    """Пишем через временный файл в той же папке + os.replace (атомарно на NTFS)."""
    global _last_error
    tmp = ""
    try:
        folder = os.path.dirname(path) or "."
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        _last_error = ""
        return True
    except Exception as e:
        _last_error = f"{os.path.basename(path)}: {e}"
        log(f"[storage] НЕ УДАЛОСЬ СОХРАНИТЬ {path}: {e}")
        try:
            if tmp and os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        return False


def load_settings() -> dict:
    s = dict(DEFAULT_SETTINGS)
    path = SETTINGS_FILE()
    try:
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            s.update(loaded)
    except FileNotFoundError:
        log("[storage] settings.json ещё нет — стартуем с настроек по умолчанию")
    except Exception as e:
        log(f"[storage] settings.json повреждён ({e}) — беру настройки по умолчанию")
        _backup_broken(path)
    return s


def save_settings(settings: dict) -> bool:
    ok = _atomic_write(SETTINGS_FILE(),
                       json.dumps(settings, ensure_ascii=False, indent=2))
    if ok:
        log("[storage] настройки сохранены")
    return ok


def load_servers() -> list:
    result = []
    path = SERVERS_FILE()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        allowed = {fld.name for fld in fields(Server)}
        for item in raw:
            if not isinstance(item, dict):
                continue
            clean = {k: v for k, v in item.items() if k in allowed}
            try:
                result.append(Server(**clean))
            except Exception as e:
                log(f"[storage] пропускаю битую запись сервера: {e}")
    except FileNotFoundError:
        log("[storage] servers.json ещё нет — список серверов пуст")
    except Exception as e:
        log(f"[storage] servers.json повреждён ({e}) — список серверов пуст")
        _backup_broken(path)
    return result


def save_servers(servers: list) -> bool:
    try:
        data = [asdict(s) for s in servers]
    except Exception as e:
        log(f"[storage] не смог сериализовать серверы: {e}")
        return False
    ok = _atomic_write(SERVERS_FILE(),
                       json.dumps(data, ensure_ascii=False, indent=2))
    if ok:
        log(f"[storage] сохранено серверов: {len(data)}")
    return ok


def _backup_broken(path: str) -> None:
    """Битый файл не удаляем, а отодвигаем — вдруг данные ещё можно достать."""
    try:
        if os.path.exists(path):
            os.replace(path, path + ".broken")
    except Exception:
        pass
