"""Test the documented Discord IPC HANDSHAKE without authorization or tokens."""
import json
import struct

CLIENT_ID = "1559606305025556480"
MAX_MESSAGE = 1024 * 1024

def read_exact(pipe, n):
    buf = bytearray()
    while len(buf) < n:
        item = pipe.read(n - len(buf))
        if not item:
            raise EOFError("Discord closed the IPC pipe")
        buf.extend(item)
    return bytes(buf)

def main():
    handshake = json.dumps({"v": 1, "client_id": CLIENT_ID},
                           separators=(",", ":")).encode("utf-8")
    packet = struct.pack("<II", 0, len(handshake)) + handshake
    for index in range(10):
        path = r"\\.\pipe\discord-ipc-" + str(index)
        try:
            with open(path, "r+b", buffering=0) as pipe:
                pipe.write(packet)
                op, length = struct.unpack("<II", read_exact(pipe, 8))
                if length < 1 or length > MAX_MESSAGE:
                    print(f"IPC {index}: invalid frame length {length}")
                    return 2
                reply = json.loads(read_exact(pipe, length))
                if op == 1 and reply.get("evt") == "READY":
                    print(f"IPC {index}: READY; Discord RPC handshake accepted")
                    print("Authorization has not been requested.")
                    return 0
                error = reply.get("data", {})
                print(f"IPC {index}: opcode={op}, event={reply.get('evt')},"
                      f" error_code={error.get('code', 'N/A') if isinstance(error,dict) else 'N/A'}")
                return 3
        except (OSError, EOFError, ValueError) as error:
            print(f"IPC {index}: unavailable ({type(error).__name__})")
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
