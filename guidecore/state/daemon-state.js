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
        viewportLocation: null,
      },
      browserFocus: null,
      voiceoverFocus: {
        bounds: null,
        lastSpokenPhrase: null,
        isOutsideWebContent: true,
        itemTextLog: [],
      },
      focusComparison: {
        VOCursorBrowserFocusAreSimilarEnough: null,
        similarityScore: null,
        textSimilarity: null,
        roleMatches: null,
        dimensionsSimilarity: null,
      },
      cursorPath: [],
      relevantNodes: {
        active: [],
        pressed: [],
        landmarks: [],
        interactive: [],
      },
      a11y: {
        tree: null, // TODO this needs to return only relevant nodes, not all of them because it will become a mess
      },
      voiceover: {
        running: false,
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
      for (const field of [
        "browserFocus",
        "focusComparison",
        "relevantNodes",
        "a11y",
        "voiceoverFocus",
        "voiceover",
      ]) {
        if (contextPatch[field] !== undefined) {
          if (
            contextPatch[field] === null ||
            field === "browserFocus" ||
            Array.isArray(contextPatch[field])
          ) {
            daemonState.context[field] = contextPatch[field];
          } else {
            Object.assign(daemonState.context[field], contextPatch[field]);
          }
        }
      }
      if (contextPatch.cursorPath) {
        daemonState.context.cursorPath = contextPatch.cursorPath;
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
        browserFocus: daemonState.context.browserFocus
          ? { ...daemonState.context.browserFocus }
          : null,
        voiceoverFocus: {
          ...daemonState.context.voiceoverFocus,
          itemTextLog: [...daemonState.context.voiceoverFocus.itemTextLog],
        },
        focusComparison: { ...daemonState.context.focusComparison },
        cursorPath: [...daemonState.context.cursorPath],
        relevantNodes: {
          ...daemonState.context.relevantNodes,
          active: [...daemonState.context.relevantNodes.active],
          pressed: [...daemonState.context.relevantNodes.pressed],
          landmarks: [...daemonState.context.relevantNodes.landmarks],
          interactive: [...daemonState.context.relevantNodes.interactive],
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
