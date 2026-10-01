function createDaemonState() {
  return {
    browser: null,
    context: null,
    page: null,
    pageInfo: {
      url: null,
      title: null,
      screenshotPath: null,
      accessibilityTree: null,
    },
    voiceOver: {
      running: false,
      mode: null,
      cursorDescription: null,
    },
    ready: false,
    events: [],
    version: 0,
  };
}

export function createStateManager({ logger }) {
  const daemonState = createDaemonState();

  function commit(patch, event = null) {
    logger.child({ patch, event }).info("daemon_state commit");

    Object.assign(daemonState, patch);
    daemonState.version += 1;

    if (event) {
      daemonState.events.push({
        ts: Date.now(),
        ...event,
      });
    }
  }

  function buildSnapshot() {
    return {
      version: daemonState.version,
      ready: daemonState.ready,
      page: { ...daemonState.pageInfo },
      voiceOver: { ...daemonState.voiceOver },
    };
  }

  return {
    daemonState,
    commit,
    buildSnapshot,
  };
}
