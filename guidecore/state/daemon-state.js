function createDaemonState() {
  return {
    // active state of the tools
    browser: null,
    browserContext: null,
    page: null,

    // retrieved state
    context: {
      page: {
        url: null,
        title: null,
        screenshotPath: null,
      },
      relevantNodes : {
        active: null,
        pressed: [],
      },
      a11y: {
        tree: null,
      },
      voiceover: {
        running: false,
        mode: null,
        lastSpokenPhrase: null,
      },
      ready: false,
      events: [],
    },
    version: 0,
  };
}

export function createStateManager({ logger }) {
  const daemonState = createDaemonState();

  function commit(patch, event = null) {
    logger.child({ patch, event }).info("daemon_state commit");

    const { context: contextPatch, ...activePatch } = patch;
    Object.assign(daemonState, activePatch);

    if (contextPatch) {
      if (contextPatch.page) {
        Object.assign(daemonState.context.page, contextPatch.page);
      }
      if (contextPatch.relevantNodes) {
        Object.assign(
          daemonState.context.relevantNodes,
          contextPatch.relevantNodes,
        );
      }
      if (contextPatch.a11y) {
        Object.assign(daemonState.context.a11y, contextPatch.a11y);
      }
      if (contextPatch.voiceover) {
        Object.assign(daemonState.context.voiceover, contextPatch.voiceover);
      }
      if (contextPatch.ready !== undefined) {
        daemonState.context.ready = contextPatch.ready;
      }
    }

    daemonState.version += 1;

    if (event) {
      daemonState.context.events.push({
        ts: Date.now(),
        ...event,
      });
    }
  }

  function buildSnapshot() {
    return {
      version: daemonState.version,
      context: {
        page: { ...daemonState.context.page },
        relevantNodes: {
          ...daemonState.context.relevantNodes,
          active: [...(daemonState.context.relevantNodes.active ?? [])],
          pressed: [...daemonState.context.relevantNodes.pressed],
        },
        a11y: { ...daemonState.context.a11y },
        voiceover: { ...daemonState.context.voiceover },
        ready: daemonState.context.ready,
        events: [...daemonState.context.events],
      },
    };
  }

  return {
    daemonState,
    commit,
    buildSnapshot,
  };
}
