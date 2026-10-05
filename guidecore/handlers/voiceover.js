export function createVoiceOverHandlers({ voiceOverService }) {
  return {
    async "voiceover.cursorLocation"() {
      return {
        ok: true,
        VOCursorLocation: await voiceOverService.getCursorBounds(),
      };
    },

    async "voiceover.start"() {
      await voiceOverService.start();
      return { ok: true };
    },

    async "voiceover.stop"() {
      await voiceOverService.stop();
      return { ok: true };
    },

    async "voiceover.goToWebContent"() {
      await voiceOverService.goToWebContent();
      return { ok: true };
    },

    async "voiceover.next"() {
      await voiceOverService.next();
      return { ok: true };
    },

    async "voiceover.previous"() {
      await voiceOverService.previous();
      return { ok: true };
    },

    async "voiceover.startInteracting"() {
      await voiceOverService.startInteracting();
      return { ok: true };
    },

    async "voiceover.stopInteracting"() {
      await voiceOverService.stopInteracting();
      return { ok: true };
    },

    async "voiceover.perform"({ command }) {
      await voiceOverService.perform(command);
      return { ok: true };
    },

    async "voiceover.escape"() {
      await voiceOverService.escape();
      return { ok: true };
    },

    async "voiceover.type"({ text }) {
      await voiceOverService.type(text);
      return { ok: true };
    },

    async "voiceover.press"({ key }) {
      await voiceOverService.press(key);
      return { ok: true };
    },

    async "voiceover.nextHeading"() {
      await voiceOverService.nextHeading();
      return { ok: true };
    },

    async "voiceover.previousHeading"() {
      await voiceOverService.previousHeading();
      return { ok: true };
    },

    async "voiceover.nextLandmark"() {
      await voiceOverService.nextLandmark();
      return { ok: true };
    },

    async "voiceover.previousLandmark"() {
      await voiceOverService.previousLandmark();
      return { ok: true };
    },

    async "voiceover.nextLink"() {
      await voiceOverService.nextLink();
      return { ok: true };
    },

    async "voiceover.previousLink"() {
      await voiceOverService.previousLink();
      return { ok: true };
    },
  };
}
