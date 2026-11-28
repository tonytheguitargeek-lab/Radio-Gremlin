"""Radio Gremlin V0.2 USB configuration engine."""
# SPDX-License-Identifier: GPL-3.0-only

import os
import json
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from datetime import datetime

import yaml
import gremlin_settings as g

from meshtastic.serial_interface import SerialInterface
from meshtastic.__main__ import export_config


class QuickBackup:
    """Export configuration without slow optional queries."""

    def __init__(self, radio):
        self.radio = radio

    def __getattr__(self, name):
        return getattr(self.radio, name)

    def getCannedMessage(self):
        return None

    def getRingtone(self):
        return None


def progress(message):
    print(datetime.now().strftime("%H:%M:%S") + " PROGRESS: " + message, flush=True)


def connect():
    s = g.load()

    if s.radio_type != "serial":
        raise RuntimeError("USB connection required.")

    if any(g.pid_alive(s.pid_file(n))
           for n in ("gremlin", "watchdog")):
        raise RuntimeError("Stop Gremlin and watchdog first.")

    if not g.radio_reachable(s):
        raise RuntimeError("USB radio unavailable.")

    busy = subprocess.run(
        ["/usr/sbin/lsof", "-t", "--", s.serial_port],
        capture_output=True, text=True, timeout=5
    )

    if busy.stdout.strip() or busy.returncode not in (0, 1):
        raise RuntimeError("Radio busy or availability check failed.")

    progress("Connecting to radio")

    return SerialInterface(
        devPath=s.serial_port,
        noNodes=True,
        timeout=30
    )


def read_settings(radio):
    node = radio.localNode
    c = node.localConfig
    m = node.moduleConfig

    return {
        "bluetooth.enabled": c.bluetooth.enabled,
        "network.wifi_enabled": c.network.wifi_enabled,
        "mqtt.enabled": m.mqtt.enabled,
        "lora.region": c.lora.region,
        "lora.modem_preset": c.lora.modem_preset,
        "lora.use_preset": c.lora.use_preset,
        "lora.tx_power": c.lora.tx_power,
        "lora.hop_limit": c.lora.hop_limit,
        "lora.tx_enabled": c.lora.tx_enabled,
    }


def backup(radio, quick=True):
    progress("Creating quick backup" if quick
             else "Creating full backup")

    text = export_config(
        QuickBackup(radio) if quick else radio
    )

    data = yaml.safe_load(text)
    required = {"config", "module_config", "channel_url"}

    if not isinstance(data, dict) or not required.issubset(data):
        raise RuntimeError("Backup validation failed.")

    if quick:
        text = (
            "# Radio Gremlin QUICK BACKUP\n"
            "# Excludes canned message text and ringtone.\n"
            + text
        )

    os.umask(0o077)
    folder = Path.home() / "RadioBackups"
    folder.mkdir(mode=0o700, exist_ok=True)
    folder.chmod(0o700)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    kind = "Quick" if quick else "Full"

    fd, name = tempfile.mkstemp(
        prefix=f"Gremlin-{kind}-{stamp}-",
        suffix=".partial",
        dir=folder
    )

    temp = Path(name)
    final = temp.with_suffix(".yaml")

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())

        temp.chmod(0o600)
        temp.rename(final)
    finally:
        if temp.exists():
            temp.unlink()

    progress("Backup saved")
    return final



def apply_bluetooth(desired, expected):
    start = time.monotonic()
    radio = connect()

    try:
        progress("Checking current configuration")
        current = read_settings(radio)

        if current["bluetooth.enabled"] != expected:
            raise RuntimeError("Settings changed. Reload configuration.")

        if desired and current["network.wifi_enabled"]:
            raise RuntimeError("Wi-Fi must be disabled first.")

        if current["bluetooth.enabled"] == desired:
            print("NO_CHANGES", flush=True)
            return

        backup(radio, quick=True)

        progress("Writing Bluetooth configuration")
        node = radio.localNode
        node.localConfig.bluetooth.enabled = desired
        node.writeConfig("bluetooth")
        time.sleep(2)

    finally:
        radio.close()

    for remaining in range(40, 0, -1):
        progress(f"Radio recovery: {remaining}s remaining")
        time.sleep(1)

    progress("Recovery wait complete")

    for attempt in range(3):
        progress(f"Verifying configuration ({attempt+1}/3)")
        verify = None

        try:
            verify = connect()
            actual = read_settings(verify)
            progress("Bluetooth readback: " + str(actual["bluetooth.enabled"]))

            if actual["bluetooth.enabled"] == desired:
                print("WRITE_VERIFIED", flush=True)
                print(f"COMPLETE: {time.monotonic()-start:.2f}s",
                      flush=True)
                return

        except Exception:
            progress("Radio not ready")

        finally:
            if verify is not None:
                verify.close()

        time.sleep(5)

    raise RuntimeError("Write not verified. Read radio before retrying.")



def apply_settings(desired, expected):
    from meshtastic.protobuf import config_pb2

    start = time.monotonic()

    if not isinstance(desired, dict) or not isinstance(expected, dict):
        raise RuntimeError("Invalid configuration arguments.")

    bool_fields = {
        "bluetooth.enabled",
        "network.wifi_enabled",
        "mqtt.enabled",
        "lora.tx_enabled",
        "lora.use_preset",
    }

    limits = {
        "lora.hop_limit": set(range(8)),
        "lora.region": set(
            config_pb2.Config.LoRaConfig.RegionCode.values()
        ) - {0},
        "lora.modem_preset": set(
            config_pb2.Config.LoRaConfig.ModemPreset.values()
        ),
    }

    for key, value in desired.items():
        if key in bool_fields:
            if type(value) is not bool:
                raise RuntimeError("Invalid boolean setting.")
        elif key in limits:
            if type(value) is not int or value not in limits[key]:
                raise RuntimeError("Invalid numeric setting.")
        else:
            raise RuntimeError("Unsupported setting.")

    radio = connect()

    try:
        progress("Checking current configuration")
        current = read_settings(radio)

        if any(key not in expected for key in desired):
            raise RuntimeError("Missing original configuration.")

        if any(key not in current or current[key] != value
               for key, value in expected.items()):
            raise RuntimeError("Settings changed. Reload configuration.")

        changes = {
            key: value for key, value in desired.items()
            if current[key] != value
        }

        if not changes:
            print("NO_CHANGES", flush=True)
            return

        target = dict(current)
        target.update(changes)

        if target["bluetooth.enabled"] and target["network.wifi_enabled"]:
            raise RuntimeError("Bluetooth and Wi-Fi cannot both be enabled.")

        if ("lora.modem_preset" in changes
                and not target["lora.use_preset"]):
            raise RuntimeError("Enable modem presets first.")

        backup(radio, quick=True)

        node = radio.localNode
        sections = set()

        for key, value in changes.items():
            section, field = key.split(".", 1)
            config = (node.moduleConfig if section == "mqtt"
                      else node.localConfig)

            setattr(getattr(config, section), field, value)
            sections.add(section)

        ordered = sorted(sections)
        progress("Writing configuration")

        if len(ordered) > 1:
            node.beginSettingsTransaction()

        for section in ordered:
            progress("Writing " + section)
            node.writeConfig(section)

        if len(ordered) > 1:
            node.commitSettingsTransaction()

        time.sleep(2)

    finally:
        radio.close()

    for remaining in range(40, 0, -1):
        progress(f"Radio recovery: {remaining}s remaining")
        time.sleep(1)

    progress("Recovery wait complete")

    for attempt in range(3):
        progress(f"Verifying configuration ({attempt+1}/3)")
        verify = None
        matched = False

        try:
            verify = connect()
            actual = read_settings(verify)

            matched = all(
                actual.get(key) == value
                for key, value in target.items()
            )

            for key in changes:
                progress(f"{key}: {actual.get(key)}")

        except Exception:
            progress("Radio not ready")

        finally:
            if verify is not None:
                verify.close()

        if matched:
            print("WRITE_VERIFIED", flush=True)
            print(f"COMPLETE: {time.monotonic()-start:.2f}s",
                  flush=True)
            return

        time.sleep(5)

    raise RuntimeError("Write not verified. Reload configuration.")


def main():
    start = time.monotonic()
    mode = sys.argv[1] if len(sys.argv) > 1 else "read"



    if mode == "apply":
        if len(sys.argv) != 4:
            raise RuntimeError("Invalid apply arguments.")

        apply_settings(
            json.loads(sys.argv[2]),
            json.loads(sys.argv[3])
        )
        return

    if mode == "apply-bluetooth":
        if len(sys.argv) != 4 or any(
            v not in ("true", "false") for v in sys.argv[2:]
        ):
            raise RuntimeError("Invalid Bluetooth arguments.")

        apply_bluetooth(
            sys.argv[2] == "true",
            sys.argv[3] == "true"
        )
        return

    if mode not in ("read", "quick-backup", "full-backup"):
        raise RuntimeError("Unsupported operation.")

    radio = connect()

    try:
        progress("Reading configuration")
        values = read_settings(radio)

        for key, value in values.items():
            print(f"{key}: {value}", flush=True)

        if mode != "read":
            path = backup(radio, quick=(mode == "quick-backup"))
            print("BACKUP_OK", flush=True)
            print(path.name, flush=True)

    finally:
        radio.close()

    print(f"COMPLETE: {time.monotonic()-start:.2f}s", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}", flush=True)
        sys.exit(1)
