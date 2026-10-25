# SPDX-License-Identifier: GPL-3.0-or-later
"""Minimal client for Unreal Engine's Python remote execution protocol.

Unreal (Python Editor Script Plugin, "Enable Remote Execution" in Project
Settings > Plugins > Python) listens on a UDP multicast group for discovery
and connects back to a TCP server we open to receive commands.
"""

import json
import socket
import time
import uuid

PROTOCOL_VERSION = 1
PROTOCOL_MAGIC = "ue_py"


class RemoteError(Exception):
    pass


class UnrealRemote:
    def __init__(self, group="239.0.0.1", port=6766, bind="127.0.0.1", ttl=0, timeout=5.0):
        self.group = group
        self.port = port
        self.bind = bind
        self.ttl = ttl
        self.timeout = timeout
        self.node_id = str(uuid.uuid4())
        self._udp = None

    # ---------------------------------------------------------------- helpers

    def _message(self, kind, dest=None, data=None):
        msg = {"version": PROTOCOL_VERSION, "magic": PROTOCOL_MAGIC, "type": kind, "source": self.node_id}
        if dest:
            msg["dest"] = dest
        if data is not None:
            msg["data"] = data
        return json.dumps(msg, ensure_ascii=False).encode("utf-8")

    def _parse(self, raw):
        try:
            msg = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
        if msg.get("magic") != PROTOCOL_MAGIC or msg.get("version") != PROTOCOL_VERSION:
            return None
        if msg.get("source") == self.node_id:
            return None
        return msg

    def _open_udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_LOOP, 1)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, self.ttl)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(self.bind))
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                        socket.inet_aton(self.group) + socket.inet_aton(self.bind))
        try:
            sock.bind((self.bind, self.port))
        except OSError:
            sock.bind(("", self.port))
        sock.settimeout(0.1)
        self._udp = sock

    def close(self):
        if self._udp is not None:
            try:
                self._udp.close()
            except OSError:
                pass
            self._udp = None

    def __enter__(self):
        self._open_udp()
        return self

    def __exit__(self, *exc):
        self.close()

    def _send(self, payload):
        self._udp.sendto(payload, (self.group, self.port))

    # ---------------------------------------------------------------- API

    def discover(self, wait=None):
        """Ping the group and return {node_id: pong data} for every Unreal editor that answers."""
        wait = self.timeout if wait is None else wait
        nodes = {}
        deadline = time.time() + wait
        next_ping = 0.0
        while time.time() < deadline:
            if time.time() >= next_ping:
                self._send(self._message("ping"))
                next_ping = time.time() + 1.0
            try:
                raw, _ = self._udp.recvfrom(65536)
            except socket.timeout:
                if nodes and time.time() > deadline - wait + 1.5:
                    break
                continue
            msg = self._parse(raw)
            if msg and msg.get("type") == "pong" and msg.get("dest") == self.node_id:
                nodes[msg["source"]] = msg.get("data", {})
        return nodes

    def run(self, node, code, unattended=True):
        """Execute ``code`` on ``node``; returns the command_result data dict."""
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self.bind, 0))
        server.listen(1)
        server.settimeout(self.timeout)
        host, port = server.getsockname()
        conn = None
        try:
            self._send(self._message("open_connection", node, {"command_ip": host, "command_port": port}))
            try:
                conn, _ = server.accept()
            except socket.timeout as exc:
                raise RemoteError("Unreal did not connect back (check the multicast bind address)") from exc
            conn.settimeout(max(self.timeout, 60.0))
            conn.sendall(self._message("command", node, {
                "command": code, "unattended": unattended, "exec_mode": "ExecuteFile"}))
            buf = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    raise RemoteError("Connection closed by Unreal")
                buf += chunk
                msg = self._parse(buf)
                if msg is None:
                    continue
                if msg.get("type") == "command_result":
                    return msg.get("data", {})
                buf = b""
        finally:
            try:
                self._send(self._message("close_connection", node))
            except OSError:
                pass
            if conn is not None:
                conn.close()
            server.close()


def send(code, group="239.0.0.1", port=6766, bind="127.0.0.1", timeout=5.0, project_hint=""):
    """Discover an editor and run ``code``. Returns (ok, message)."""
    try:
        with UnrealRemote(group, port, bind, timeout=timeout) as remote:
            nodes = remote.discover()
            if not nodes:
                return False, "No Unreal Editor found (enable Python remote execution)"
            node = next(iter(nodes))
            if project_hint:
                for nid, data in nodes.items():
                    if project_hint.lower() in str(data.get("project_name", "")).lower():
                        node = nid
                        break
            result = remote.run(node, code)
    except (OSError, RemoteError) as exc:
        return False, str(exc)
    output = "\n".join(o.get("output", "") for o in result.get("output", []) if isinstance(o, dict))
    if not result.get("success"):
        return False, (result.get("result") or output or "Python error in Unreal").strip()
    return True, output.strip()
