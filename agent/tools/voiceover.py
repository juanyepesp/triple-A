from langchain_core.tools import tool
from tools import actions

# TODO revisar las descripciones de texto, estas afectan el prompting


@tool
def voiceover_next() -> str:
    """Move VoiceOver to the next navigable element."""
    return actions.voiceover_next()


@tool
def voiceover_previous() -> str:
    """Move VoiceOver to the previous navigable element."""
    return actions.voiceover_previous()


@tool
def voiceover_start_interacting() -> str:
    """Enter the currently focused group or container."""
    return actions.voiceover_start_interacting()


@tool
def voiceover_stop_interacting() -> str:
    """Leave the currently focused group or container."""
    return actions.voiceover_stop_interacting()


@tool
def rotor_open() -> str:
    """Open the VoiceOver Rotor."""
    return actions.rotor_open()

normal_tools = [
    voiceover_next,
    voiceover_previous,
    voiceover_start_interacting,
    voiceover_stop_interacting,
    rotor_open,
]