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

def voiceover_start_interacting() -> Any:
    return client.call("voiceover.startInteracting")

def voiceover_stop_interacting() -> Any:
    return client.call("voiceover.stopInteracting")

def voiceover_escape() -> Any:
    return client.call("voiceover.escape")

def voiceover_press(key: str) -> Any:
    return client.call("voiceover.press", {"key": key})

def voiceover_rotor_open() -> Any:
    return client.call("voiceover.rotor.open")

def voiceover_rotor_next_category() -> Any:
    return client.call("voiceover.rotor.nextCategory")

def voiceover_rotor_previous_category() -> Any:
    return client.call("voiceover.rotor.previousCategory")

def voiceover_rotor_next_item() -> Any:
    return client.call("voiceover.rotor.nextItem")

def voiceover_rotor_previous_item() -> Any:
    return client.call("voiceover.rotor.previousItem")

def voiceover_rotor_find( text: str) -> Any:
    return client.call("voiceover.rotor.find", {"text": text})

def voiceover_rotor_activate() -> Any:
    return client.call("voiceover.rotor.activate")
