# Radio Gremlin — shared settings loader
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
#
# Radio Gremlin is free software: you can redistribute it and/or modify it under the terms of the
# GNU General Public License version 3 as published by the Free Software Foundation. It is
# distributed WITHOUT ANY WARRANTY. See the LICENSE file for details.
"""Settings for the Radio Gremlin add-ons (Mesh Command API, Mesh Observatory, Gremlin Watchdog).

Values come from, in order of precedence:
  1. gremlin.ini next to this file (or the file named by $RADIO_GREMLIN_CONFIG)
  2. the radio address in Meshing Around's own config.ini ([interface] type = tcp, hostname = host[:port])
  3. the safe defaults below (everything local-only)
"""
import configparser
import os
import subprocess
import shutil
import stat
from pathlib import Path

HERE = Path(__file__).resolve().parent

DEFAULTS = {
    "radio": {
        "host": "",          # empty = read from config.ini [interface] hostname
        "port": "",          # empty = from hostname "host:port", else 4403
    },
    "api": {
        "bind": "127.0.0.1",  # 127.0.0.1 = this computer only. See README "LAN access for the CYD".
        "port": "8765",
    },
    "observatory": {
        "bind": "127.0.0.1",
        "port": "8766",
        "api_url": "",        # empty = http://127.0.0.1:<api port>
        "database": "observatory.db",
    },
    "watchdog": {
        "check_interval": "15",
        "python": "venv/bin/python",
    },
}


def _radio_from_meshing_around(ini_path):
    cp = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        cp.read(ini_path)
    except configparser.Error:
        return "", None
    if cp.get("interface", "type", fallback="").strip().lower() != "tcp":
        return "", None
    host = cp.get("interface", "hostname", fallback="").strip()
    port = None
    if ":" in host:
        maybe_host, maybe_port = host.rsplit(":", 1)
        if maybe_port.isdigit():
            host, port = maybe_host, int(maybe_port)
    return host, port


class Settings:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("RADIO_GREMLIN_CONFIG") or HERE / "gremlin.ini")
        self.root = self.path.parent
        cp = configparser.ConfigParser(interpolation=None)
        cp.read_dict(DEFAULTS)
        if self.path.exists():
            cp.read(self.path)
        self.cp = cp

        host = cp.get("radio", "host").strip()
        port = cp.get("radio", "port").strip()
        ma_host, ma_port = _radio_from_meshing_around(self.root / "config.ini")
        interface = configparser.ConfigParser(
            interpolation=None, strict=False)
        interface.read(self.root / "config.ini")
        self.radio_type = interface.get(
            "interface", "type", fallback="tcp"
        ).strip().lower()
        self.serial_port = interface.get(
            "interface", "port", fallback=""
        ).strip()
        self.radio_host = host or ma_host
        self.radio_port = int(port) if port.isdigit() else (ma_port or 4403)

        self.api_bind = cp.get("api", "bind").strip() or "127.0.0.1"
        self.api_port = cp.getint("api", "port")

        self.obs_bind = cp.get("observatory", "bind").strip() or "127.0.0.1"
        self.obs_port = cp.getint("observatory", "port")
        api_host = "127.0.0.1" if self.api_bind in ("0.0.0.0", "", "::") else self.api_bind
        self.api_url = (cp.get("observatory", "api_url").strip()
                        or "http://%s:%d" % (api_host, self.api_port)).rstrip("/")
        db = Path(cp.get("observatory", "database").strip() or "observatory.db")
        self.database = db if db.is_absolute() else self.root / db

        self.check_interval = cp.getint("watchdog", "check_interval")
        py = Path(cp.get("watchdog", "python").strip() or "venv/bin/python")
        self.python = py if py.is_absolute() else self.root / py

    def pid_file(self, name):
        return self.root / ("%s.pid" % name)


def load(path=None):
    return Settings(path)


def pid_alive(pid_file):
    """PID from a pid file if that process is still running, else None."""
    try:
        pid = int(Path(pid_file).read_text().strip())
        os.kill(pid, 0)
        return pid
    except (OSError, ValueError):
        return None


def radio_description(settings):
    if settings.radio_type == "serial":
        return settings.serial_port
    return "%s:%d" % (settings.radio_host, settings.radio_port)


def radio_reachable(settings):
    if settings.radio_type == "serial":
        try:
            return stat.S_ISCHR(
                Path(settings.serial_port).stat().st_mode)
        except OSError:
            return False
    if settings.radio_type != "tcp" or not settings.radio_host:
        return False
    import sys
    wait = "1000" if sys.platform == "darwin" else "1"
    try:
        result = subprocess.run(
            [shutil.which("ping") or "/sbin/ping",
             "-c", "1", "-W", wait, settings.radio_host],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3)
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def radio_connected(settings, pid):
    if not pid or int(pid) <= 0:
        return False
    cmd = [shutil.which("lsof") or "/usr/sbin/lsof",
           "-nP", "-a", "-p", str(pid)]
    if settings.radio_type == "serial":
        if not radio_reachable(settings):
            return False
        cmd += ["--", settings.serial_port]
    elif settings.radio_type == "tcp" and settings.radio_host:
        cmd += [
            "-iTCP@%s:%d" % (
                settings.radio_host, settings.radio_port),
            "-sTCP:ESTABLISHED"]
    else:
        return False
    try:
        result = subprocess.run(
            cmd, capture_output=True,
            text=True, timeout=5)
        return result.returncode == 0 and bool(
            result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def current_radio_connected():
    settings = load()
    pid = pid_alive(settings.pid_file("gremlin"))
    return radio_connected(settings, pid)
