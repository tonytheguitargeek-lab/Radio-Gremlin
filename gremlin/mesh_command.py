# Mesh Command API V1.4 — part of Radio Gremlin
# Copyright (C) 2026 Bad Audio Guy
# SPDX-License-Identifier: GPL-3.0-only
#
# Runs inside the Meshing Around bot process (started from mesh_bot.py) and serves a small,
# read-only HTTP API with live mesh status for Mesh Command (CYD touchscreen) and Mesh Observatory.
# It never transmits on the mesh.
#
# By default it listens on 127.0.0.1 only. Setting [api] bind in gremlin.ini to a LAN address makes
# /status, /nodes and /traffic readable by ANY device on that network WITHOUT AUTHENTICATION
# (/traffic includes broadcast message text). /mapnodes (positions) stays limited to this computer.
#
# This program is free software: you can redistribute it and/or modify it under the terms of the GNU
# General Public License version 3. It is distributed WITHOUT ANY WARRANTY. See LICENSE.

import json
import time
import threading
from collections import deque

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pubsub import pub

import gremlin_settings

_settings = gremlin_settings.load()
HOST = _settings.api_bind
PORT = _settings.api_port
# /mapnodes (node positions) is only served to this computer, and to the bind address itself
MAPNODE_CLIENTS = {"127.0.0.1", "::1"} | ({HOST} - {"0.0.0.0", "::", ""})

lock = threading.Lock()
started = time.time()

radio = None
rf_history = {}

state = {
    "station": "Radio Gremlin",
    "version": "1.4",
    "packets": 0,
    "rf_packets": 0,
    "direct_packets": 0,
    "relayed_packets": 0,
    "unknown_rf_packets": 0,
    "last_route": None,
    "last_hops": None,
    "last_relay": None,
    "other_packets": 0,
    "nodes": None,
    "rssi": None,
    "snr": None,
    "last_sender": "",
    "last_rf_sender": "",
    "last_rx": None,
    "last_rf_rx": None
}



def packet_route(packet):
    start = packet.get("hopStart")
    limit = packet.get("hopLimit")
    relay = packet.get("relayNode")
    transport = str(
        packet.get("transportMechanism") or "UNKNOWN"
    ).upper()

    rssi = packet.get("rxRssi")
    is_rf = isinstance(rssi, (int, float)) and rssi < 0

    hops = None

    if (
        isinstance(start, int)
        and isinstance(limit, int)
        and 0 <= limit <= start <= 7
    ):
        hops = start - limit

    if packet.get("viaMqtt") or "MQTT" in transport:
        route = "MQTT"
    elif "UDP" in transport:
        route = "GATEWAY"
    elif is_rf:
        if hops == 0:
            route = "DIRECT"
        elif hops is not None:
            route = "RELAYED"
        else:
            route = "RF UNKNOWN"
    else:
        route = "UNKNOWN"

    relay_id = None
    if isinstance(relay, int) and relay & 0xFF:
        relay_id = f"{relay & 0xFF:02X}"

    return {
        "route": route,
        "hops": hops,
        "hop_start": start,
        "hop_limit": limit,
        "relay": relay_id,
        "transport": transport
    }


def receive_packet(packet, interface):
    global radio

    try:
        with lock:
            radio = interface
            now = int(time.time())

            state["packets"] += 1
            state["last_rx"] = now

            nodes = getattr(interface, "nodes", {}) or {}
            state["nodes"] = len(nodes)

            sender = packet.get("fromId", "")
            node = nodes.get(sender, {})
            user = node.get("user", {})
            name = user.get("shortName", sender)

            state["last_sender"] = name

            rssi = packet.get("rxRssi")
            snr = packet.get("rxSnr")

            if rssi is not None and rssi < 0:

                state["rf_packets"] += 1

                route = packet_route(packet)
                state["last_route"] = route["route"]
                state["last_hops"] = route["hops"]
                state["last_relay"] = route["relay"]

                if route["route"] == "DIRECT":
                    state["direct_packets"] += 1
                elif route["route"] == "RELAYED":
                    state["relayed_packets"] += 1
                else:
                    state["unknown_rf_packets"] += 1
                state["rssi"] = rssi
                state["snr"] = snr
                state["last_rf_sender"] = name
                state["last_rf_rx"] = now

                hop_start = packet.get("hopStart")
                hop_limit = packet.get("hopLimit")

                direct = (
                    hop_start is not None
                    and hop_limit is not None
                    and hop_start == hop_limit
                )

                if sender and direct and route["route"] == "DIRECT":
                    rf_history[sender] = {
                        "rssi": rssi,
                        "snr": snr,
                        "last_rf_rx": now
                    }

            else:
                state["other_packets"] += 1

    except Exception as error:
        print("Mesh Command RX:", error)


def node_position(node):
    pos = node.get("position") or {}
    lat = pos.get("latitude")
    lon = pos.get("longitude")

    if lat is None and pos.get("latitudeI") is not None:
        lat = pos["latitudeI"] / 10000000

    if lon is None and pos.get("longitudeI") is not None:
        lon = pos["longitudeI"] / 10000000

    if not isinstance(lat, (int, float)):
        return None
    if not isinstance(lon, (int, float)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None

    return {
        "latitude": lat,
        "longitude": lon,
        "altitude": pos.get("altitude"),
        "position_time": pos.get("time"),
        "precision_bits": pos.get("precisionBits")
    }


def get_nodes(include_positions=False):

    now = int(time.time())

    with lock:
        interface = radio
        history = dict(rf_history)

    if interface is None:
        return []

    nodes = getattr(interface, "nodes", {}) or {}

    my_info = getattr(interface, "myInfo", None)
    local_num = getattr(my_info, "my_node_num", None)

    result = []

    for node_id, node in list(nodes.items()):

        user = node.get("user", {})
        metrics = node.get("deviceMetrics", {})

        node_num = node.get("num")
        last_heard = node.get("lastHeard")

        rf = history.get(node_id, {})
        last_rf = rf.get("last_rf_rx")

        result.append({
            "id": node_id,
            "short_name": user.get("shortName", node_id),
            "long_name": user.get("longName", node_id),
            "hardware": user.get("hwModel", "UNKNOWN"),
            "role": user.get("role", "UNKNOWN"),
            "local": (
                local_num is not None
                and node_num == local_num
            ),
            "last_heard": last_heard,
            "age": (
                max(0, now - last_heard)
                if last_heard else None
            ),
            "rssi": rf.get("rssi"),
            "snr": rf.get("snr"),
            "rf_age": (
                max(0, now - last_rf)
                if last_rf else None
            ),
            "reported_snr": node.get("snr"),
            "battery": metrics.get("batteryLevel"),
            "voltage": metrics.get("voltage"),
            "hops_away": node.get("hopsAway"),
            **({"position": node_position(node)}
               if include_positions else {})
        })

    result.sort(
        key=lambda n: (
            not n["local"],
            n["age"] if n["age"] is not None else 999999999
        )
    )

    return result



# TRAFFIC V1.4

traffic_lock = threading.Lock()
traffic_history = deque(maxlen=100)
traffic_sequence = 0


def record_traffic(packet, interface):
    global traffic_sequence

    try:
        decoded = packet.get("decoded", {}) or {}
        port = str(decoded.get("portnum", "UNKNOWN"))
        sender = packet.get("fromId")
        if not sender or sender in ("--", "UNKNOWN"):
            number = packet.get("from")
            if isinstance(number, int) and number > 0:
                sender = f"!{number:08x}"
            else:
                sender = "UNKNOWN"

        nodes = getattr(interface, "nodes", {}) or {}
        node = nodes.get(sender, {})
        user = node.get("user", {})
        name = user.get("shortName", sender)

        rssi = packet.get("rxRssi")
        snr = packet.get("rxSnr")

        is_rf = (
            isinstance(rssi, (int, float))
            and rssi < 0
        )

        destination = packet.get("to")
        broadcast = (
            destination == 4294967295
            or packet.get("toId") == "^all"
        )

        is_text = port == "TEXT_MESSAGE_APP"

        if is_text:
            if broadcast:
                summary = str(decoded.get("text", ""))[:200]
            else:
                summary = "[Private message]"
        else:
            summary = port.replace("_APP", "").replace("_", " ")

        with traffic_lock:
            traffic_sequence += 1

            traffic_history.appendleft({
                "seq": traffic_sequence,
                "timestamp": int(time.time()),
                "time": time.strftime("%H:%M:%S"),
                "sender": name,
                "sender_id": sender,
                "type": port,
                "summary": summary,
                "text": is_text,
                "rf": is_rf,
                "rssi": rssi if is_rf else None,
                "snr": snr if is_rf else None,
                "private": is_text and not broadcast,
                **packet_route(packet)
            })

    except Exception as error:
        print("Traffic recorder:", error)


def get_traffic():
    with traffic_lock:
        events = list(traffic_history)

    return {
        "version": "1.4",
        "count": len(events),
        "capacity": 100,
        "events": events
    }


class Handler(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/status":

            with lock:
                data = dict(state)

            now = int(time.time())

            data["uptime"] = int(time.time() - started)
            data["api_online"] = True

            data["rf_age"] = (
                now - data["last_rf_rx"]
                if data["last_rf_rx"] is not None
                else None
            )

        elif self.path == "/traffic":
            data = get_traffic()

        elif self.path == "/mapnodes":
            if self.client_address[0] not in MAPNODE_CLIENTS:
                self.send_error(403)
                return
            nodes = get_nodes(include_positions=True)
            data = {
                "count": len(nodes),
                "nodes": nodes
            }
        elif self.path == "/nodes":

            try:
                nodes = get_nodes()

                data = {
                    "version": "1.4",
                    "count": len(nodes),
                    "nodes": nodes
                }

            except Exception as error:
                print("Mesh Command nodes:", error)
                self.send_error(500)
                return

        else:
            self.send_error(404)
            return

        body = json.dumps(data).encode("utf-8")

        self.send_response(200)
        self.send_header(
            "Content-Type", "application/json"
        )
        self.send_header(
            "Content-Length", str(len(body))
        )
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass


def start():

    server = ThreadingHTTPServer((HOST, PORT), Handler)

    pub.subscribe(
        receive_packet, "meshtastic.receive"
    )

    pub.subscribe(
        record_traffic, "meshtastic.receive"
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True
    ).start()

    print(f"Mesh Command V1.4 online: http://{HOST}:{PORT}")
