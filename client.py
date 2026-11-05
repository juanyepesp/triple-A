from __future__ import annotations
import json
import socket
import threading
from dataclasses import dataclass
from typing import Any, Optional
from pprint import pprint

# documentation:
# this is my testing client. i use it only to check things are going well. it's not crucial to the project at all. (well it is crucial to me anyways)

@dataclass
class RpcError(Exception):
    code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class GuidecoreClient:
    def __init__(self, path: str = "/tmp/guidecore.sock") -> None:
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
    
def describe(obj, indent=0):
    prefix = "  " * indent

    if isinstance(obj, dict):
        print(f"{prefix}dict ({len(obj)} keys)")
        for key, value in obj.items():
            print(f"{prefix}├── {key!r}: ", end="")
            if isinstance(value, dict):
                print()
                describe(value, indent + 1)
            elif isinstance(value, (list, tuple, set)):
                print(f"{type(value).__name__} ({len(value)} items)")
            elif isinstance(value, str):
                print(f"str (len={len(value)})")
            else:
                print(type(value).__name__)

    elif isinstance(obj, (list, tuple, set)):
        print(f"{type(obj).__name__} ({len(obj)} items)")

    else:
        print(type(obj).__name__)

client = GuidecoreClient()

client.ping()

client.call(
    "browser.start",
    {
        'url': 'https://playwright.dev/docs/api/class-elementhandle',
        'impairment': 'low vision'
    }
)

client.call(
    "voiceover.start",
)

# accion
client.call("voiceover.goToWebContent")
print('\nGO TO WEB CONTENT')

res = client.call(
    "voiceover.startInteracting"
)
print('\nSTART INTERACTING')
input("\ncontinue?")
action = 'next'

while True:
# accion
    if action == 'next': 
        res = client.call(
            "voiceover.next"
        )
    elif action == 'heading': 
            res = client.call(
                "voiceover.nextHeading"
            )
    elif action == 'headingp': 
            res = client.call(
                "voiceover.previousHeading"
            )
    elif action == 'link': 
            res = client.call(
                "voiceover.nextLink"
            )
    elif action == 'linkp': 
            res = client.call(
                "voiceover.previousLink"
            )
    elif action == 'landmark': 
            res = client.call(
                "voiceover.nextLandmark"
            )
    elif action == 'landmarkp': 
            res = client.call(
                "voiceover.previousLandmark"
            )
    elif action == 'prev': 
        res = client.call(
            "voiceover.previous"
        )
    elif action == 'start': 
        res = client.call(
            "voiceover.startInteracting"
        )
    res = client.call("daemonstate.snapshot")
    print('-'*30)
    describe(res)
    print('-'*30)
    describe(res['daemon_state']['context']['relevantNodes'])
    print('-'*30)
    pprint(res['daemon_state']['context']['browserFocus'])
    print('-'*30)
    pprint(res['daemon_state']['context']['voiceoverFocus'])
    print('-'*30)
    pprint(res['daemon_state']['context']['focusComparison'])
    action = input("\nsay action?")
    if action == '':
        action = 'next'
    if action == 'esc':
        break

# # client.call(
# #     "voiceover.stop",
# # )

# # client.call(
# #     "browser.stop",
# # )