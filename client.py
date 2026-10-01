from __future__ import annotations
import json
import socket
import threading
from dataclasses import dataclass
from typing import Any, Optional
from pprint import pprint

@dataclass
class RpcError(Exception):
    code: int
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class GuidepupClient:
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
    


client = GuidepupClient()

client.ping()


client.call(
    "browser.start",
    {
        'url': 'https://playwright.dev/docs/api/class-elementhandle'
    }
)



client.call(
    "voiceover.start",
)

# AOM primero
# res = client.call("browser.activeNodes")
# print('\nactiveNodes')
# pprint(res['elements'])
# input("continue?")



# # viewport bounds
# res = client.call(
#     "browser.viewportLocation"
# )
# print('Viewport Bounds')
# print(res['playwright'])


# accion
client.call("voiceover.goToWebContent")
print('\nGO TO WEB CONTENT')
# res = client.call("browser.activeNodes")
# print('\nactiveNodes')
# pprint(res['elements'])
input("continue?")


# # snapshot
# res = client.call("daemonstate.snapshot")
# print('--------------------------------------------------')
# print('\nVO utterance:', res['daemon_state']['voiceOver']['cursorDescription'])

# # bounds
# res = client.call(
#     "voiceover.cursorLocation"
# )
# print(res)


# accion
res = client.call(
    "voiceover.startInteracting"
)
print('\nSTART INTERACTING')
# res = client.call("browser.activeNodes")
# print('\nactiveNodes')
# pprint(res['elements'])
input("continue?")



# # snapshot
# res = client.call("daemonstate.snapshot")
# print('--------------------------------------------------')
# print('\nVO utterance:', res['daemon_state']['voiceOver']['cursorDescription'])

# # bounds
# res = client.call(
#     "voiceover.cursorLocation"
# )
# print(res)

while True:
# accion
    res = client.call(
        "voiceover.next"
    )
    print('\nNEXT')
    res = client.call("daemonstate.snapshot")
    print('\nVO utterance:', res['daemon_state']['voiceOver']['cursorDescription'])
    res = client.call("browser.activeNodes")
    print('\nactiveNodes')
    pprint(res['elements'])
    input("continue?")


# # client.call("voiceover.next")
# # print('h')

# # snap = client.call("daemonstate.snapshot")
# # print('i', snap)

# # # client.call("voiceover.next")
# # # client.call("voiceover.next")


# # client.call(
# #     "voiceover.stop",
# # )

# # client.call(
# #     "browser.stop",
# # )