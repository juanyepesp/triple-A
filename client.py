from __future__ import annotations
import json
import socket
import threading
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class RpcError(Exception):
    code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class GuidepupClient:
    def __init__(self, path: str = "/tmp/guidepup.sock") -> None:
        self.path = path
        self.sock: Optional[socket.socket] = None
        self.lock = threading.Lock()
        self.next_id = 1

    def connect(self) -> None:
        if self.sock is not None:
            return
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(self.path)
        self.sock = s

    def close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def call(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self.connect()
        assert self.sock is not None

        with self.lock:
            req_id = self.next_id
            self.next_id += 1

            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
                "params": params or {},
            }
            self.sock.sendall((json.dumps(payload) + "\n").encode("utf-8"))

            # Read one line response.
            data = b""
            while not data.endswith(b"\n"):
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise ConnectionError("Socket closed")
                data += chunk

            resp = json.loads(data.decode("utf-8").strip())

            if "error" in resp:
                raise RpcError(resp["error"]["code"], resp["error"]["message"])

            return resp["result"]

    def ping(self) -> Any:
        return self.call("ping")

    def voiceover_next(self) -> Any:
        return self.call("voiceover.next")
    


client = GuidepupClient()
client.ping()
client.call(
    "browser.start",
    {
        'url': 'https://projects.accesscomputing.uw.edu/au/after.html'
    }
)


client.call(
    "voiceover.start",
)



client.call("voiceover.goToWebContent")



res = client.call(
    "voiceover.startInteracting"
)

res = client.call(
    "voiceover.startInteracting"
)

client.call("voiceover.rotor.open")
client.call("voiceover.rotor.nextItem")
res = client.call("daemonstate.snapshot")
print(res)

client.call("voiceover.rotor.previousItem")
client.call("voiceover.rotor.nextCategory")
client.call("voiceover.rotor.previousCategory")
client.call(
    "voiceover.rotor.find",
    {
        "text": "help"
    }
)
client.call("voiceover.escape")


res = client.call("daemonstate.snapshot")
print(res)


client.call(
    "voiceover.stop",
)

client.call(
    "browser.stop",
)