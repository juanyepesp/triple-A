export function createCoreHandlers({ buildSnapshot }) {
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
  };
}
