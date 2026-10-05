export function createBrowserHandlers({ browserService }) {
  return {
    // ? check if I need more handlers
    
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
  };
}
