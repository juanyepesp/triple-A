from __future__ import annotations

from typing import Any
from .client import GuidepupClient

client = GuidepupClient()

def snapshot() -> dict[str, Any]:
    return client.call("daemonstate.snapshot")

def browser_start(url: str) -> Any:
    return client.call("browser.start", {"url": url})

def browser_stop() -> Any:
    return client.call("browser.stop")

def voiceover_start() -> Any:
    return client.call("voiceover.start")

def voiceover_go_to_web_content() -> Any:
    return client.call("voiceover.goToWebContent")

def voiceover_stop() -> Any:
    return client.call("voiceover.stop")

def voiceover_next() -> Any:
    return client.call("voiceover.next")

def voiceover_previous() -> Any:
    return client.call("voiceover.previous")

def voiceover_next_heading() -> Any:
    return client.call("voiceover.nextHeading")

def voiceover_previous_heading() -> Any:
    return client.call("voiceover.previousHeading")

def voiceover_next_landmark() -> Any:
    return client.call("voiceover.nextLandmark")

def voiceover_previous_landmark() -> Any:
    return client.call("voiceover.previousLandmark")

def voiceover_next_link() -> Any:
    return client.call("voiceover.nextLink")

def voiceover_previous_link() -> Any:
    return client.call("voiceover.previousLink")

def voiceover_start_interacting() -> Any:
    return client.call("voiceover.startInteracting")

def voiceover_stop_interacting() -> Any:
    return client.call("voiceover.stopInteracting")

def voiceover_escape() -> Any:
    return client.call("voiceover.escape")

def voiceover_press(key: str) -> Any:
    return client.call("voiceover.press", {"key": key})
