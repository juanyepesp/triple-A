import argparse
import json
import os
import queue
import select
import signal
import socket
import sys
import termios
import threading
import tty


TERMINAL_KEYS = {
    " ": ("voiceover.perform", {"command": "performDefaultActionForItem"}),
    "\x1b": ("voiceover.escape", {}),
    "e": ("voiceover.escape", {}),
    "w": ("voiceover.goToWebContent", {}),
    "h": ("voiceover.nextHeading", {}),
    "H": ("voiceover.previousHeading", {}),
    "m": ("voiceover.nextLandmark", {}),
    "M": ("voiceover.previousLandmark", {}),
    "l": ("voiceover.nextLink", {}),
    "L": ("voiceover.previousLink", {}),
    "\x1b[C": ("voiceover.next", {}),
    "\x1bOC": ("voiceover.next", {}),
    "\x1b[D": ("voiceover.previous", {}),
    "\x1bOD": ("voiceover.previous", {}),
    "\x1b[1;2A": ("voiceover.stopInteracting", {}),
    "\x1b[1;2B": ("voiceover.startInteracting", {}),
    "\x1b[1;2C": ("voiceover.next", {}),
    "\x1b[1;2D": ("voiceover.previous", {}),
}


class GuidecoreClient:
    def __init__(self, path="/tmp/guidecore.sock"):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(path)
        self.next_id = 1
        self.lock = threading.Lock()

    def call(self, method, params=None):
        with self.lock:
            request = {
                "jsonrpc": "2.0",
                "id": self.next_id,
                "method": method,
                "params": {**(params or {}), "_source": "human"},
            }
            self.next_id += 1
            self.sock.sendall((json.dumps(request) + "\n").encode("utf-8"))
            data = b""
            while not data.endswith(b"\n"):
                chunk = self.sock.recv(4096)
                if not chunk:
                    raise RuntimeError("GuideCore socket closed")
                data += chunk

            response = json.loads(data.decode("utf-8"))
            if "error" in response:
                raise RuntimeError(response["error"]["message"])
            return response["result"]

    def close(self):
        self.sock.close()


def command_worker(client, commands):
    while True:
        command = commands.get()
        try:
            if command is None:
                return
            method, params = command
            client.call(method, params)
            print(f"Executed {method}", flush=True)
        except Exception as error:
            print(f"Failed to execute VoiceOver command: {error}", flush=True)
        finally:
            commands.task_done()


def enqueue_command(commands, command):
    if command[0] in {
        "voiceover.next",
        "voiceover.previous",
    }:
        while True:
            try:
                queued = commands.get_nowait()
            except queue.Empty:
                break
            commands.task_done()
            if queued is None:
                commands.put(None)
                break
    commands.put(command)


def read_terminal_key(fd):
    first = os.read(fd, 1)
    if not first:
        return None
    if first != b"\x1b":
        return first.decode("utf-8", errors="replace")

    sequence = first
    while select.select([fd], [], [], 0.1)[0]:
        sequence += os.read(fd, 1)
        decoded = sequence.decode("ascii", errors="replace")
        if decoded in TERMINAL_KEYS:
            return decoded
        if len(sequence) >= 8:
            break
    return sequence.decode("ascii", errors="replace")


def main():
    parser = argparse.ArgumentParser(
        description="Control GuideCore VoiceOver through an SSH terminal."
    )
    parser.add_argument("--url", required=True, help="URL to open in GuideCore")
    parser.add_argument(
        "--impairment",
        required=True,
        help="Vision impairment to apply to the browser",
    )
    parser.add_argument(
        "--debug-keys",
        action="store_true",
        help="Print terminal escape sequences received from SSH",
    )
    args = parser.parse_args()

    if not sys.stdin.isatty():
        raise RuntimeError("The VoiceOver controller must run in an interactive SSH terminal")

    client = GuidecoreClient()
    commands = queue.Queue()
    worker = threading.Thread(
        target=command_worker,
        args=(client, commands),
        daemon=True,
    )
    worker.start()

    browser_started = False
    voiceover_started = False
    recording_started = False
    try:
        recording = client.call(
            "recording.start",
            {"url": args.url, "impairment": args.impairment},
        )
        recording_started = True
        client.call(
            "browser.start",
            {"url": args.url, "impairment": args.impairment},
        )
        browser_started = True
        client.call("voiceover.start", {"mode": "human"})
        voiceover_started = True
        print(
            f"Recording interactions to {recording['recording']['path']}",
            flush=True,
        )
    except Exception:
        if voiceover_started:
            client.call("voiceover.stop")
        if browser_started:
            client.call("browser.stop")
        if recording_started:
            client.call("recording.stop")
        commands.put(None)
        client.close()
        raise

    stopping = False

    def stop(*_):
        nonlocal stopping
        if stopping:
            return
        stopping = True
        try:
            commands.join()
            if voiceover_started:
                client.call("voiceover.stop")
            if browser_started:
                client.call("browser.stop")
            if recording_started:
                recording = client.call("recording.stop")
                print(
                    f"Recording saved to {recording['recording']['path']}",
                    flush=True,
                )
        finally:
            commands.put(None)
            worker.join(timeout=2)
            client.close()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(
        "GuideCore VoiceOver controller started over the terminal. "
        "Right/Left navigate; Shift+Down/Up enters or exits interaction; "
        "Space activates the focused item. Press Ctrl+C to stop.",
        flush=True,
    )

    terminal_fd = sys.stdin.fileno()
    original_settings = termios.tcgetattr(terminal_fd)
    try:
        tty.setcbreak(terminal_fd)
        while not stopping:
            key = read_terminal_key(terminal_fd)
            if key is None or key == "\x03":
                break
            if args.debug_keys:
                print(f"Received terminal input: {key!r}", flush=True)
            if key == "t":
                termios.tcsetattr(terminal_fd, termios.TCSADRAIN, original_settings)
                try:
                    text = input("Text to type: ")
                finally:
                    tty.setcbreak(terminal_fd)
                enqueue_command(commands, ("voiceover.type", {"text": text}))
                continue
            command = TERMINAL_KEYS.get(key)
            if command:
                enqueue_command(commands, command)
            elif args.debug_keys:
                print(f"Ignored terminal input: {key!r}", flush=True)
    finally:
        termios.tcsetattr(terminal_fd, termios.TCSADRAIN, original_settings)
        stop()


if __name__ == "__main__":
    main()
