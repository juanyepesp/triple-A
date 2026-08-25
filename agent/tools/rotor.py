from langchain_core.tools import tool
from tools import actions

# TODO revisar las descripciones de texto, estas afectan el prompting

@tool
def rotor_next_category() -> str:
    """
    Move VoiceOver to the next available Rotor category.

    Valid only while the VoiceOver Rotor is active.
    The category order must not be assumed.
    Use this to navigate toward a semantic category relevant to the goal.
    """
    return actions.rotor_next_category()


@tool
def rotor_previous_category() -> str:
    """Move to the previous VoiceOver Rotor category."""
    return actions.rotor_previous_category()


@tool
def rotor_next_item() -> str:
    """Move to the next item in the selected Rotor category."""
    return actions.rotor_next_item()


@tool
def rotor_previous_item() -> str:
    """Move to the previous item in the selected Rotor category."""
    return actions.rotor_previous_item()


@tool
def rotor_find(text: str) -> str:
    """Search for an item using the active Rotor."""
    return actions.rotor_find(text)


@tool
def rotor_activate() -> str:
    """Activate the currently selected Rotor item."""
    return actions.rotor_activate()


@tool
def voiceover_escape() -> str:
    """Exit Rotor mode."""
    return actions.voiceover_escape()


rotor_tools = [
    rotor_next_category,
    rotor_previous_category,
    rotor_next_item,
    rotor_previous_item,
    rotor_find,
    rotor_activate,
    voiceover_escape,
]