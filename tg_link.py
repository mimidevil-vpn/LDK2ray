# -*- coding: utf-8 -*-
"""Привязка Telegram-аккаунта по @username.

Своего сервера у приложения нет, поэтому берём то, что Telegram и так отдаёт
всем: публичную страницу t.me/<username>. С неё читаем отображаемое имя и
аватарку. Аватарка ужимается до 160px и кладётся прямо в настройки как data:URI,
чтобы профиль рисовался мгновенно и работал без интернета.
"""

import re
import io
import base64
import urllib.request

from storage import log

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def normalize_username(raw: str) -> str:
    """Из «@name», «t.me/name», «https://t.me/name?x=1» делает «name»."""
    u = (raw or "").strip()
    u = re.sub(r"^[a-z]+://", "", u, flags=re.I)
    u = re.sub(r"^(www\.)?(t\.me|telegram\.me|telegram\.dog)/", "", u, flags=re.I)
    u = u.split("?")[0].split("/")[0].strip().lstrip("@")
    return u


def _get(url: str, timeout=12.0) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "ru,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _meta(html: str, prop: str) -> str:
    m = re.search(
        r'<meta[^>]+property=["\']%s["\'][^>]+content=["\']([^"\']*)["\']' % prop,
        html, re.I)
    if not m:
        m = re.search(
            r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+property=["\']%s["\']' % prop,
            html, re.I)
    return m.group(1).strip() if m else ""


def _unescape(s: str) -> str:
    import html as _h
    return _h.unescape(s or "").strip()


# Символы-заполнители, из которых любят собирать «пустые» ники: заполнитель
# хангыля, вариационные селекторы, неразрывные и нулевой ширины пробелы.
_INVISIBLE = dict.fromkeys(
    [0x00A0, 0x1160, 0x3164, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF,
     0xFE0E, 0xFE0F, 0x180E, 0x2800] + list(range(0x2000, 0x200B)),
    " ")


def clean_name(raw: str) -> str:
    """Убирает невидимые символы и лишние пробелы из отображаемого имени.

    Имя вида «Ro ︎ ︎ ︎\\xa0ᅠ ︎ ︎» превращается в «Ro»: иначе в профиле видна
    пустота, и выглядит это как будто имя не подтянулось.
    """
    import unicodedata
    s = unicodedata.normalize("NFKC", raw or "")
    s = s.translate(_INVISIBLE)
    # прочие невидимые категории: форматирующие и управляющие
    s = "".join(ch if unicodedata.category(ch) not in ("Cf", "Cc") else " "
                for ch in s)
    return re.sub(r"\s+", " ", s).strip()


def _avatar_data_uri(url: str) -> str:
    """Скачивает аватарку и превращает в компактный data:URI (JPEG 160px)."""
    if not url:
        return ""
    try:
        raw = _get(url, timeout=15.0)
    except Exception as e:
        log(f"[tg] не удалось скачать аватар: {e}")
        return ""
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(raw))
        img = img.convert("RGB")
        img.thumbnail((160, 160), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=86, optimize=True)
        raw = buf.getvalue()
        mime = "image/jpeg"
    except Exception:
        # Pillow нет или картинка экзотическая — кладём как есть, если не огромная
        if len(raw) > 700_000:
            return ""
        mime = "image/jpeg"
    return "data:%s;base64,%s" % (mime, base64.b64encode(raw).decode("ascii"))


def fetch_profile(raw_username: str) -> dict:
    """Возвращает {'username','name','avatar'} либо {'error': '...'}.

    Ошибки: bad_username | not_found | network
    """
    username = normalize_username(raw_username)
    if not _USERNAME_RE.match(username):
        return {"error": "bad_username"}

    try:
        html = _get(f"https://t.me/{username}").decode("utf-8", "ignore")
    except Exception as e:
        log(f"[tg] страница профиля недоступна: {e}")
        return {"error": "network"}

    # у несуществующего аккаунта этого блока на странице нет
    m = re.search(r'class="tgme_page_title"[^>]*>\s*(?:<span[^>]*>)?(.*?)(?:</span>)?\s*</div>',
                  html, re.I | re.S)
    name = _unescape(re.sub(r"<[^>]+>", "", m.group(1))) if m else ""
    if not name:
        title = _meta(html, "og:title")
        if title and not title.lower().startswith("telegram"):
            name = _unescape(title)
    if not name:
        return {"error": "not_found"}

    # ник может целиком состоять из невидимых символов — тогда показываем @username
    name = clean_name(name) or ("@" + username)

    photo = ""
    m = re.search(r'<img[^>]+class="[^"]*tgme_page_photo_image[^"]*"[^>]+src="([^"]+)"',
                  html, re.I)
    if not m:
        m = re.search(r'<img[^>]+src="([^"]+)"[^>]+class="[^"]*tgme_page_photo_image[^"]*"',
                      html, re.I)
    if m:
        photo = _unescape(m.group(1))
    else:
        og = _meta(html, "og:image")
        if og and "/file/" in og:
            photo = _unescape(og)

    return {
        "username": username,
        "name": name,
        "avatar": _avatar_data_uri(photo),
    }
