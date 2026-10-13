"""Discord desktop IPC over a single synchronous named-pipe owner thread.

Windows synchronous pipe handles must NOT be read on one thread while written
from another: Python CRT serializes operations on the same synchronous handle.
PeekNamedPipe makes receiving nonblocking; all I/O occurs on the caller thread.
"""
from __future__ import annotations
import ctypes
from ctypes import wintypes
import json
import msvcrt
import queue
import struct
import time
import uuid

MAX_PACKET = 8 * 1024 * 1024

_kernel = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel.PeekNamedPipe.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p
]
_kernel.PeekNamedPipe.restype = wintypes.BOOL


class RPCError(RuntimeError):
    pass


def _read_exact(pipe, length):
    result = bytearray()
    while len(result) < length:
        part = pipe.read(length - len(result))
        if not part:
            raise EOFError("Discord RPC closed the IPC pipe")
        result.extend(part)
    return bytes(result)


def _write_frame(pipe, opcode: int, payload: dict):
    packet = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(packet) > MAX_PACKET:
        raise RPCError("Discord RPC outgoing frame too long")
    pipe.write(struct.pack("<II", opcode, len(packet)) + packet)
    pipe.flush()


def _available(pipe):
    available = wintypes.DWORD(0)
    handle = wintypes.HANDLE(msvcrt.get_osfhandle(pipe.fileno()))
    if not _kernel.PeekNamedPipe(handle, None, 0, None,
                                 ctypes.byref(available), None):
        raise ctypes.WinError(ctypes.get_last_error())
    return available.value


class DiscordRPC:
    def __init__(self, client_id: str):
        self.client_id = client_id
        self.pipe = None
        self.events = queue.Queue(maxsize=100)
        self._incoming = bytearray()
        self._replies = {}
        self._closed = False

    def connect(self):
        for index in range(10):
            try:
                pipe = open(r"\\.\pipe\discord-ipc-" + str(index), "r+b", buffering=0)
            except OSError:
                continue
            try:
                _write_frame(pipe, 0, {"v": 1, "client_id": self.client_id})
                opcode, length = struct.unpack("<II", _read_exact(pipe, 8))
                if opcode != 1 or not 1 <= length <= MAX_PACKET:
                    raise RPCError("Discord RPC handshake malformed")
                data = json.loads(_read_exact(pipe, length))
                if data.get("evt") != "READY":
                    raise RPCError("Discord RPC handshake rejected the application")
                self.pipe = pipe
                self._closed = False
                return
            except (OSError, EOFError, ValueError, RPCError):
                pipe.close()
        raise RPCError("Discord IPC unavailable; run the desktop Discord client")

    def poll(self):
        """Read only available bytes, then dispatch full frames (never block)."""
        if not self.pipe or self._closed:
            raise RPCError("Discord RPC is disconnected")
        while True:
            waiting = _available(self.pipe)
            if not waiting:
                break
            part = self.pipe.read(min(waiting, 65536))
            if not part:
                raise RPCError("Discord RPC pipe disconnected")
            self._incoming.extend(part)
            if len(self._incoming) > MAX_PACKET + 8:
                raise RPCError("Discord RPC incoming data too long")

        while len(self._incoming) >= 8:
            opcode, size = struct.unpack_from("<II", self._incoming, 0)
            if size > MAX_PACKET:
                raise RPCError("Discord RPC packet too large")
            if len(self._incoming) < 8 + size:
                break
            raw = bytes(self._incoming[8:8 + size])
            del self._incoming[:8 + size]
            data = json.loads(raw)
            if opcode == 3:
                _write_frame(self.pipe, 4, data)  # Respond to PING promptly.
                continue
            if opcode == 2:
                raise RPCError("Discord closed the RPC connection")
            if opcode != 1:
                continue
            nonce = data.get("nonce")
            if nonce:
                self._replies[nonce] = data
                if len(self._replies) > 24:
                    self._replies.pop(next(iter(self._replies)))
            else:
                if self.events.full():
                    self.events.get_nowait()
                self.events.put_nowait(data)

    def call(self, cmd: str, args: dict | None = None, *,
             event: str | None = None, timeout: float = 20.0):
        if not self.pipe:
            raise RPCError("Not connected")
        nonce = uuid.uuid4().hex
        request = {"cmd": cmd, "nonce": nonce, "args": args or {}}
        if event:
            request["evt"] = event
        # No competing read thread can lock this synchronous Windows handle.
        _write_frame(self.pipe, 1, request)

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.poll()
            response = self._replies.pop(nonce, None)
            if response is not None:
                if response.get("evt") == "ERROR":
                    data = response.get("data") or {}
                    raise RPCError(
                        f"Discord refused {cmd} (code {data.get('code', '?')}): "
                        f"{data.get('message', 'no details')}"
                    )
                return response.get("data")
            time.sleep(0.03)
        raise RPCError(f"Discord RPC timed out waiting for {cmd}")

    def close(self):
        self._closed = True
        pipe, self.pipe = self.pipe, None
        if pipe:
            pipe.close()
