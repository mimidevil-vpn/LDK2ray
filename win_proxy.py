# -*- coding: utf-8 -*-
"""Включение/выключение системного прокси Windows (реестр + WinINet)."""

import os

IS_WIN = os.name == "nt"
_INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _refresh():
    """Сообщает Windows, что настройки прокси изменились."""
    try:
        import ctypes
        wininet = ctypes.windll.Wininet
        wininet.InternetSetOptionW(0, 39, 0, 0)  # SETTINGS_CHANGED
        wininet.InternetSetOptionW(0, 37, 0, 0)  # REFRESH
    except Exception:
        pass


def set_proxy(host_port: str):
    """host_port вида '127.0.0.1:10809' (HTTP inbound Xray)."""
    if not IS_WIN:
        return False, "Системный прокси доступен только в Windows."
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS,
                             0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, host_port)
        winreg.SetValueEx(key, "ProxyOverride", 0, winreg.REG_SZ,
                          "localhost;127.*;10.*;172.16.*;192.168.*;<local>")
        winreg.CloseKey(key)
        _refresh()
        return True, ""
    except Exception as e:
        return False, str(e)


def disable_proxy():
    if not IS_WIN:
        return False, "Системный прокси доступен только в Windows."
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _INTERNET_SETTINGS,
                             0, winreg.KEY_WRITE)
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        _refresh()
        return True, ""
    except Exception as e:
        return False, str(e)
