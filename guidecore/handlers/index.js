function createHandlers({
  buildSnapshot,
  browserService,
  voiceOverService,
}) {
  return {
    async ping() {
      return {
        ok: true,
        time: Date.now(),
      };
    },

    async "daemonstate.snapshot"() {
      return {
        ok: true,
        daemon_state: buildSnapshot(),
      };
    },

    // -----------------------------
    // Browser
    // -----------------------------

    async "browser.start"({ url }) {
      await browserService.start(url);
      return { ok: true };
    },

    async "browser.stop"() {
      await browserService.stop();
      return { ok: true };
    },

    async "browser.aom"() {
      return browserService.getAom();
    },

    // -----------------------------
    // VoiceOver
    // -----------------------------

    async "voiceover.start"() {
      await voiceOverService.start();
      return { ok: true };
    },

    async "voiceover.goToWebContent"() {
      await voiceOverService.goToWebContent();
      return { ok: true };
    },

    async "voiceover.stop"() {
      await voiceOverService.stop();
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

    // -----------------------------
    // Rotor
    // -----------------------------

    async "voiceover.rotor.open"() {
      await voiceOverService.openRotor();
      return { ok: true };
    },

    async "voiceover.rotor.nextCategory"() {
      await voiceOverService.rotorNextCategory();
      return { ok: true };
    },

    async "voiceover.rotor.previousCategory"() {
      await voiceOverService.rotorPreviousCategory();
      return { ok: true };
    },

    async "voiceover.rotor.nextItem"() {
      await voiceOverService.rotorNextItem();
      return { ok: true };
    },

    async "voiceover.rotor.previousItem"() {
      await voiceOverService.rotorPreviousItem();
      return { ok: true };
    },

    async "voiceover.rotor.find"({ text }) {
      await voiceOverService.rotorFind(text);
      return { ok: true };
    },

    async "voiceover.rotor.activate"() {
      await voiceOverService.rotorActivate();
      return { ok: true };
    },
  };
}

export default createHandlers;