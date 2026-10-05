from state.schema import DaemonSnapshot, VoiceOverInfo
from pprint import pprint

# current structure retrieved:

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

# a possible structure from js daemon:
# dict (2 keys)
# ├── 'ok': bool
# ├── 'daemon_state': 🆗
#   dict (2 keys)
#   ├── 'version': int ✅
#   ├── 'context': 🆗 -> didnt quite name it "context"
#     dict (6 keys)
#     ├── 'page': ✅
#       dict (3 keys)
#       ├── 'url': str (len=53) ✅
#       ├── 'title': str (len=52) ✅
#       ├── 'screenshotPath': str (len=58) ✅
#     ├── 'relevantNodes': ✅
#       dict (2 keys)
#       ├── 'active': list (1 items) ✅
#       ├── 'pressed': list (1 items) ✅
#     ├── 'a11y': 
#       dict (1 keys)
#       ├── 'tree': list (1 items) TODO this needs to return only relevant nodes, not all of them because it will become a mess
#     ├── 'voiceover': ✅
#       dict (3 keys)
#       ├── 'running': bool ✅
#       ├── 'mode': str (len=6) ✅
#       ├── 'lastSpokenPhrase': str (len=239) ✅
#     ├── 'ready': bool ✅
#     ├── 'events': list (5 items) ✅


# PAGE
# Title: Accessible University
# URL: http://localhost:3000

# CURRENT LOCATION

# VO Last Spoken Phrase: TODO
# "You are currently on a _". To interact with this item ...

# Browser focus:
#   link "Skip to main content"
#   ref=e4

# VoiceOver and browser focus: DIFFERENT

# CURSOR PATH !! TODO
# this is very useful and i think it is easily done using the a11y tree
# document
#  → banner
#    → heading "Accessible University"

# PREVIOUS THREE ? VOICEOVER UTTERANCES OR VO LOG TODO
# ["You are currently on a _. To interact with this item ...", ...]


# PAGE LANDMARKS
# TODO check where I can get this information
# - banner
# - navigation "Demo site menu"
# - main
# - contentinfo

# INTERACTIVE ELEMENTS
# TODO check where i can get this information
# - link "Home"
# - link "Before"
# - link "After"
# - textbox "Search"
# - button "Submit"


def parse_daemon_snapshot(raw: dict) -> DaemonSnapshot:
    describe(raw)
    print('-'*30)
    pprint(raw['daemon_state']['context']['browserFocus'])
    print('-'*30)
    pprint(raw['daemon_state']['context']['voiceoverFocus'])
    print('-'*30)
    pprint(raw['daemon_state']['context']['focusComparison'])
    
    # TODO im working here    
    input()

    daemon = raw['daemon_state']

    voiceover_raw = daemon['voiceOver']

    voiceover = VoiceOverInfo(
        running=voiceover_raw['running'],
        mode=voiceover_raw['mode'],
        cursor_description=voiceover_raw['cursorDescription']
    )

    return DaemonSnapshot(
        version=daemon['version'],
        ready=daemon['ready'],
        page_url=daemon['page']['url'],
        page_title=daemon['page']['title'],
        accessibility_tree=daemon['page']['accessibilityTree'],
        screenshot_path=daemon['page']['screenshotPath'],
        voiceover=voiceover,
    )