import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { promisify } from "node:util";
import {
  MacOSKeyCodes,
  MacOSModifiers,
  voiceOver,
} from "@guidepup/guidepup";

const execFileAsync = promisify(execFile);

export function createVoiceOverService({ daemonState, commit, getPage }) {
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

  async function getCursorBounds() {
    const script = `
tell application "VoiceOver"
    return bounds of vo cursor
end tell
`;
    const { stdout } = await execFileAsync("/usr/bin/osascript", [
      "-e",
      script,
    ]);
    return stdout.trim();
  }

  async function getCursorDescription() {
    const repeatLastSpokenPhraseCommand = {
      keyCode: MacOSKeyCodes.z,
      modifiers: [
        MacOSModifiers.Control,
        MacOSModifiers.Option,
        MacOSModifiers,
      ],
      description: "Repeat Last Spoken Phrase",
      representation: "VO-Z",
    };
    await voiceOver.perform(repeatLastSpokenPhraseCommand).catch(() => null);
    return voiceOver.lastSpokenPhrase();
  }

  async function refreshState(fromAction, parameters = null) {
    const lastSpokenPhrase = await voiceOver
      .lastSpokenPhrase()
      .catch(() => null);
    const itemTextLog = await voiceOver.itemTextLog().catch(() => []);
    const pageScreenshotPath = `.././screenshots/${randomUUID()}.jpeg`;
    await getPage().screenshot({ path: pageScreenshotPath });
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
        pageInfo: {
          ...daemonState.pageInfo,
          screenshotPath: pageScreenshotPath,
        },
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
      },
    );
  }

  function assertNotRotorMode(action) {
    if (daemonState.voiceOver.mode === "rotor") {
      throw new Error(`${action} is unavailable while rotor is open`);
    }
  }

  async function type(text) {
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
      await new Promise((resolve) => setTimeout(resolve, 1));
      await voiceOver.press(characterMap[character] ?? character);
    }
  }

  async function start() {
    await voiceOver.start({ capture: true });
    await voiceOver.clearItemTextLog();
    await voiceOver.clearSpokenPhraseLog();
    await refreshState("voiceover.start");
  }

  async function goToWebContent() {
    // ! for this function to work, you need to set the web content inside chrome as the first shortcut
    const nextHotSpotCommand = {
      keyCode: MacOSKeyCodes.RightSquareBracket,
      modifiers: [
        MacOSModifiers.Control,
        MacOSModifiers.Option,
        MacOSModifiers.Shift,
      ],
      description: "Move to next hot spot",
      representation: "VO-Shift-}",
    };
    await voiceOver.perform(nextHotSpotCommand);
    await refreshState("voiceover.goToWebContent");
  }

  async function stop() {
    await voiceOver.stop();
    await refreshState("voiceover.stop");
  }

  async function shutdown() {
    await voiceOver.stop();
  }

  async function action(name, operation, parameter) {
    assertNotRotorMode(parameter === undefined ? name : `${name}(${parameter})`);
    await operation();
    await refreshState(name, parameter);
  }

  return {
    getCursorBounds,
    start,
    goToWebContent,
    stop,
    shutdown,
    next: () => action("voiceover.next", () => voiceOver.next()),
    previous: () => action("voiceover.previous", () => voiceOver.previous()),
    startInteracting: () =>
      action("voiceover.startInteracting", () =>
        voiceOver.perform(voiceOver.commanderCommands.START_INTERACTING_WITH_ITEM),
      ),
    stopInteracting: () =>
      action("voiceover.stopInteracting", () => voiceOver.stopInteracting()),
    perform: (command) =>
      action(
        "voiceover.perform",
        () => voiceOver.perform(voiceOver.commanderCommands[command]),
        command,
      ),
    escape: () =>
      action("voiceover.escape", () =>
        voiceOver.perform(voiceOver.commanderCommands.ESCAPE),
      ),
    type: (text) => action("voiceover.type", () => type(text), text),
    press: (key) => action("voiceover.press", () => voiceOver.press(key), key),
    openRotor: () =>
      voiceOver
        .perform(voiceOver.commanderCommands.ROTOR)
        .then(() => refreshState("voiceover.rotor.open")),
    rotorNextCategory: () =>
      voiceOver
        .press("ArrowRight")
        .then(() => refreshState("voiceover.rotor.nextCategory")),
    rotorPreviousCategory: () =>
      voiceOver
        .press("ArrowLeft")
        .then(() => refreshState("voiceover.rotor.previousCategory")),
    rotorNextItem: () =>
      voiceOver
        .press("ArrowDown")
        .then(() => refreshState("voiceover.rotor.nextItem")),
    rotorPreviousItem: () =>
      voiceOver
        .press("ArrowUp")
        .then(() => refreshState("voiceover.rotor.previousItem")),
    rotorFind: (text) =>
      type(text).then(() => refreshState("voiceover.rotor.find", text)),
    rotorActivate: () =>
      voiceOver
        .press("Space")
        .then(() => refreshState("voiceover.rotor.activate")),
  };
}
