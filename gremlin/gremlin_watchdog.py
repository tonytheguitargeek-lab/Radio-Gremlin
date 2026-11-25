# Gremlin Watchdog V1.0 — part of Radio Gremlin
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
#
# Starts the Meshing Around bot (mesh_bot.py), watches its TCP link to the radio and its log for
# connection errors, and restarts it when the link fails. It only ever stops the bot it started.
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License version 3. It is distributed WITHOUT ANY WARRANTY. See LICENSE.

import os
import time
import signal
import subprocess
import re
import fcntl
import shutil
import sys
from pathlib import Path
from datetime import datetime

import gremlin_settings

SETTINGS = gremlin_settings.load()
ROOT = Path(__file__).resolve().parent
RADIO = SETTINGS.radio_host
PORT = SETTINGS.radio_port
PYTHON = SETTINGS.python
BOTLOG = ROOT / "gremlin-live.log"
CHECK = SETTINGS.check_interval
LSOF = shutil.which("lsof") or "/usr/sbin/lsof"
PING = shutil.which("ping") or "/sbin/ping"
# ping's -W is milliseconds on macOS/BSD and seconds on Linux
PING_WAIT = ["-W", "1000"] if sys.platform == "darwin" else ["-W", "1"]

if not RADIO:
    raise SystemExit("No radio address: set [interface] type = tcp and hostname in config.ini "
                     "(or [radio] host in gremlin.ini)")
running = True
bot = None

lock = open(ROOT / "watchdog.lock", "a")
try:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit("Watchdog already running")

WATCHDOG_PID = SETTINGS.pid_file("watchdog")
BOT_PID = SETTINGS.pid_file("gremlin")
WATCHDOG_PID.write_text(str(os.getpid()))

def log(message):
    print(datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
          "|", message, flush=True)

def shutdown(*args):
    global running
    running = False

signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)

def stop_bot():
    global bot
    if bot is not None and bot.poll() is None:
        log("Stopping Gremlin")
        bot.terminate()
        BOT_PID.unlink(missing_ok=True)
        try:
            bot.wait(timeout=10)
        except subprocess.TimeoutExpired:
            bot.kill()
            bot.wait()
    bot = None

def start_bot():
    global bot
    with open(BOTLOG, "a") as output:
        offset = output.tell()
        bot = subprocess.Popen(
            [str(PYTHON), "-u", "mesh_bot.py"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=subprocess.STDOUT
        )
    BOT_PID.write_text(str(bot.pid))
    log(f"Gremlin started PID {bot.pid}")
    return offset

def connected():
    if bot is None or bot.poll() is not None:
        return False
    try:
        result = subprocess.run(
            [LSOF, "-nP", "-a",
             "-p", str(bot.pid),
             f"-iTCP@{RADIO}:{PORT}",
             "-sTCP:ESTABLISHED"],
            capture_output=True, text=True, timeout=5
        )
        return result.returncode == 0 and "ESTABLISHED" in result.stdout
    except Exception:
        return False

def reachable():
    try:
        result = subprocess.run(
            [PING, "-c", "1", *PING_WAIT, RADIO],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3
        )
        return result.returncode == 0
    except Exception:
        return False

def pause(seconds):
    end = time.monotonic() + seconds
    while running and time.monotonic() < end:
        time.sleep(1)

errors = re.compile(
    r"BrokenPipeError|Connection reset by peer|"
    r"Abrupt Disconnection of Interface|"
    r"terminating meshtastic reader",
    re.IGNORECASE
)

log("GREMLIN WATCHDOG V1.0 ONLINE")

try:
    while running:
        if not reachable():
            log("Radio unavailable - waiting")
            pause(30)
            continue

        if not running:
            break

        offset = start_bot()
        pause(45)
        failures = 0
        healthy = False

        while running:
            if bot.poll() is not None:
                log("Gremlin process exited")
                break

            with open(BOTLOG, "r", errors="replace") as f:
                f.seek(offset)
                recent = f.read()
                offset = f.tell()

            if errors.search(recent):
                log("Connection error detected in Gremlin log")
                break

            if connected():
                failures = 0
                if not healthy:
                    log("TCP connection healthy")
                    healthy = True
            else:
                failures += 1
                healthy = False
                log(f"TCP connection missing: {failures}/3")

            if failures >= 3:
                log("Sustained TCP failure - recovery required")
                break

            pause(CHECK)

        stop_bot()

        if running:
            log("Recovery retry in 30 seconds")
            pause(30)

finally:
    stop_bot()
    BOT_PID.unlink(missing_ok=True)
    WATCHDOG_PID.unlink(missing_ok=True)
    log("Watchdog stopped")
