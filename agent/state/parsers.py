from state.schema import DaemonSnapshot, VoiceOverInfo


def parse_daemon_snapshot(raw: dict) -> DaemonSnapshot:
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