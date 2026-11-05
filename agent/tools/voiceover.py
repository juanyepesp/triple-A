from langchain_core.tools import tool
from tools import actions

@tool
def voiceover_act() -> str:
    """
    Perform the default action for the item in the VoiceOver cursor.
    Keyboard equivalent: VO-Space bar
    """
    return actions.voiceover_act()


@tool
def voiceover_next() -> str:
    """
    Move VoiceOver to the next navigable element.
    Keyboard equivalent: VO + Right Arrow
    """
    return actions.voiceover_next()


@tool
def voiceover_previous() -> str:
    """
    Move VoiceOver to the previous navigable element.
    Keyboard equivalent: VO + Left Arrow
    """
    return actions.voiceover_previous()


@tool
def voiceover_start_interacting() -> str:
    """
    Enter the currently focused group or container.
    Keyboard equivalent: VO + Shift + Down Arrow
    """
    return actions.voiceover_start_interacting()


@tool
def voiceover_stop_interacting() -> str:
    """
    Leave the currently focused group or container.
    Keyboard equivalent: VO + Shift + Up Arrow
    """
    return actions.voiceover_stop_interacting()


@tool
def voiceover_go_to_web_content() -> str:
    """
    Hotkey to return to web content. It is a hotkey pre-established for this environment, not native to base VoiceOver, and it is useful if you are lost. Do not use this as a substitute for normal next/previous navigation.
    """
    return actions.voiceover_go_to_web_content()


@tool
def voiceover_escape() -> str:
    """Press Escape in VoiceOver to leave the current interaction."""
    return actions.voiceover_escape()


@tool
def voiceover_type(text: str) -> str:
    """Type text into the currently focused VoiceOver item."""
    return actions.voiceover_type(text)

@tool
def voiceover_next_heading() -> str:
    """
    Move VoiceOver to the next heading.
    """
    return actions.voiceover_next_heading()

@tool
def voiceover_previous_heading() -> str:
    """Move VoiceOver to the previous heading."""
    return actions.voiceover_previous_heading()

@tool
def voiceover_next_landmark() -> str:
    """Move VoiceOver to the next landmark."""
    return actions.voiceover_next_landmark()

@tool
def voiceover_previous_landmark() -> str:
    """Move VoiceOver to the previous landmark."""
    return actions.voiceover_previous_landmark()

@tool
def voiceover_next_link() -> str:
    """Move VoiceOver to the next link."""
    return actions.voiceover_next_link()

@tool
def voiceover_previous_link() -> str:
    """Move VoiceOver to the previous link."""
    return actions.voiceover_previous_link()


voiceover_tools = [
    voiceover_act,
    voiceover_next,
    voiceover_previous,
    voiceover_next_heading,
    voiceover_previous_heading,
    voiceover_next_landmark,
    voiceover_previous_landmark,
    voiceover_next_link,
    voiceover_previous_link,
    voiceover_start_interacting,
    voiceover_stop_interacting,
    voiceover_go_to_web_content,
    voiceover_escape,
    # voiceover_type is intentionally not registered: no current task needs typing.
]