import { voiceOver, MacOSKeyCodes, MacOSModifiers } from '@guidepup/guidepup'

function createVoiceOverService({
  daemonState,
  commit,
}) {
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function resolveMode(fromAction) {
    if (fromAction === "voiceover.stop") {
      return null;
    }

    if (fromAction.startsWith("voiceover.rotor.")) {
      return "rotor";
    }

    if (fromAction.startsWith("voiceover.")) {
      return "normal";
    }

    return daemonState.voiceOver.mode;
  }

  async function getCursorDescription() {
    const repeatLastSpokenPhraseCommand = {
      keyCode: MacOSKeyCodes.z,
      modifiers: [
        MacOSModifiers.Control,
        MacOSModifiers.Option,
      ],
      description: "Repeat Last Spoken Phrase",
      representation: "VO-Z",
    };

    await voiceOver
      .perform(repeatLastSpokenPhraseCommand)
      .catch(() => null);

    return voiceOver.lastSpokenPhrase().catch(() => null);
  }

  async function refreshState(fromAction, parameters = null) {
    const lastSpokenPhrase =
      await voiceOver.lastSpokenPhrase().catch(() => null);

    const itemTextLog =
      await voiceOver.itemTextLog().catch(() => []);

    const mode = resolveMode(fromAction);

    const nextRunningState =
      fromAction === "voiceover.start"
        ? true
        : fromAction === "voiceover.stop"
          ? false
          : daemonState.voiceOver.running;

    const nextCursorDescription =
      fromAction === "voiceover.stop" || mode === "rotor"
        ? null
        : await getCursorDescription();

    commit(
      {
        voiceOver: {
          ...daemonState.voiceOver,
          running: nextRunningState,
          mode,
          cursorDescription: nextCursorDescription,
        },
      },
      {
        fromAction,
        parameters,
        voiceoverCursor: {
          speech: lastSpokenPhrase,
          itemTextLog,
        },
      }
    );
  }

  function assertNotRotorMode(action) {
    if (daemonState.voiceOver.mode === "rotor") {
      throw new Error(
        `${action} is unavailable while rotor is open`
      );
    }
  }

  async function typeText(text) {
    if (typeof voiceOver.type === "function") {
      await voiceOver.type(text);
      return;
    }

    const characterMap = {
      " ": "Space",
      "\n": "Enter",
      "\t": "Tab",
    };

    for (const character of text) {
      await sleep(1);
      await voiceOver.press(
        characterMap[character] ?? character
      );
    }
  }

  async function start() {
    await voiceOver.start({
      capture: true,
    });

    await voiceOver.clearItemTextLog();
    await voiceOver.clearSpokenPhraseLog();

    await refreshState("voiceover.start");
  }

  async function stop() {
    await voiceOver.stop();
    await refreshState("voiceover.stop");
  }

  async function next() {
    assertNotRotorMode("voiceover.next");
    await voiceOver.next();
    await refreshState("voiceover.next");
  }

  async function previous() {
    assertNotRotorMode("voiceover.previous");
    await voiceOver.previous();
    await refreshState("voiceover.previous");
  }

  async function startInteracting() {
    assertNotRotorMode("voiceover.startInteracting");

    await voiceOver.perform(
      voiceOver.commanderCommands.START_INTERACTING_WITH_ITEM
    );

    await refreshState("voiceover.startInteracting");
  }

  async function stopInteracting() {
    assertNotRotorMode("voiceover.stopInteracting");

    await voiceOver.stopInteracting();
    await refreshState("voiceover.stopInteracting");
  }

  async function perform(command) {
    assertNotRotorMode(`voiceover.perform(${command})`);

    await voiceOver.perform(
      voiceOver.commanderCommands[command]
    );

    await refreshState("voiceover.perform", command);
  }

  async function escape() {
    await voiceOver.perform(
      voiceOver.commanderCommands.ESCAPE
    );

    await refreshState("voiceover.escape");
  }

  async function type(text) {
    assertNotRotorMode(`voiceover.type(${text})`);

    await typeText(text);
    await refreshState("voiceover.type", text);
  }

  async function press(key) {
    assertNotRotorMode(`voiceover.press(${key})`);

    await voiceOver.press(key);
    await refreshState("voiceover.press", key);
  }

  async function openRotor() {
    await voiceOver.perform(
      voiceOver.commanderCommands.ROTOR
    );

    await refreshState("voiceover.rotor.open");
  }

  async function rotorNextCategory() {
    await voiceOver.press("ArrowRight");
    await refreshState("voiceover.rotor.nextCategory");
  }

  async function rotorPreviousCategory() {
    await voiceOver.press("ArrowLeft");
    await refreshState("voiceover.rotor.previousCategory");
  }

  async function rotorNextItem() {
    await voiceOver.press("ArrowDown");
    await refreshState("voiceover.rotor.nextItem");
  }

  async function rotorPreviousItem() {
    await voiceOver.press("ArrowUp");
    await refreshState("voiceover.rotor.previousItem");
  }

  async function rotorFind(text) {
    await typeText(text);
    await refreshState("voiceover.rotor.find", text);
  }

  async function rotorActivate() {
    await voiceOver.press("Space");
    await refreshState("voiceover.rotor.activate");
  }

  async function goToWebContent() {
    const command = {
      keyCode: MacOSKeyCodes.RightSquareBracket,
      modifiers: [
        MacOSModifiers.Control,
        MacOSModifiers.Option,
        MacOSModifiers.Shift,
      ],
      description: "Move to next hot spot",
      representation: "VO-Shift-}",
    };

    await voiceOver.perform(command);

    await refreshState("voiceover.setup");
  }

  return {
    start,
    stop,
    next,
    previous,
    startInteracting,
    stopInteracting,
    perform,
    escape,
    type,
    press,
    openRotor,
    rotorNextCategory,
    rotorPreviousCategory,
    rotorNextItem,
    rotorPreviousItem,
    rotorFind,
    rotorActivate,
    goToWebContent,
    refreshState,
    assertNotRotorMode,
  };
}

export default createVoiceOverService;