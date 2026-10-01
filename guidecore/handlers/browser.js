export function createBrowserHandlers({ browserService }) {
  return {
    async "browser.start"({ url }) {
      await browserService.start(url);
      return { ok: true };
    },

    async "browser.viewportLocation"() {
      return {
        ok: true,
        playwright: await browserService.viewportLocation(),
      };
    },

    async "browser.stop"() {
      await browserService.stop();
      return { ok: true };
    },

    async "browser.ariaSnapshot"() {
      return {
        ok: true,
        snapshot: await browserService.ariaSnapshot(),
      };
    },

    async "browser.activeNodes"() {
      return {
        ok: true,
        elements: await browserService.activeNodes(),
      };
    },
  };
}
