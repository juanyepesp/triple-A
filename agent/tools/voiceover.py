from langchain_core.tools import tool
from tools import actions

# TODO revisar las descripciones de texto, estas afectan el prompting
# TODO ponerles los hotkeys para que identifique de lo que voiceover dice

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


# TODO
# @tool
def voiceover_type() -> str:
    return

@tool
def rotor_open() -> str:
    """
    Open the VoiceOver Rotor. Useful for navigating the website by semantic category, such as links, headings, form controls, landmarks. 
    Keyboard equivalent: VO + U
    """
    return actions.rotor_open()



normal_tools = [
    voiceover_next,
    voiceover_previous,
    voiceover_start_interacting,
    voiceover_stop_interacting,
    voiceover_go_to_web_content,
    rotor_open,
]