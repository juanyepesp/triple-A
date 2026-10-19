export function createCoreHandlers({ buildSnapshot, recorder }) {
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

    async "recording.start"(params) {
      return { ok: true, recording: recorder.start(params) };
    },

    async "recording.stop"() {
      return { ok: true, recording: recorder.stop() };
    },

    async "recording.status"() {
      return { ok: true, recording: recorder.status() };
    },

    async "recording.event"(event) {
      if (!recorder.record({ source: "human", ...event })) {
        throw new Error("No recording is active");
      }
      return { ok: true };
    },
  };
}
