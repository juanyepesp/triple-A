from state.schema import DaemonSnapshot, VoiceOverInfo

def parse_daemon_snapshot(raw: dict) -> DaemonSnapshot:
    daemon = raw['daemon_state']

    voiceover_raw = daemon['voiceOverInfo']

    voiceover = VoiceOverInfo(
        running=voiceover_raw['voiceOverRunning'],
        mode=['voiceOverMode'],
        cursor_description=voiceover_raw['currentVoiceOverCursorDescription']
    )

    return DaemonSnapshot(
        version=daemon['version'],
        ready=daemon['ready'],
        page_url=daemon['pageUrl'],
        page_title=daemon['pageTitle'],
        accessibility_tree=daemon['accessibilityTree'],
        screenshot_path=daemon['pageScreenshotPath'],
        voiceover=voiceover,
        events=daemon['events'],
    )