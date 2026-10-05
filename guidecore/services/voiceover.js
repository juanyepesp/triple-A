import { execFile } from "node:child_process";
import { randomUUID } from "node:crypto";
import { promisify } from "node:util";
import {
  MacOSKeyCodes,
  MacOSModifiers,
  voiceOver,
} from "@guidepup/guidepup";

const execFileAsync = promisify(execFile);

function parseCursorBounds(value) {
  const numbers = String(value)
    .match(/-?\d+(?:\.\d+)?/g)
    ?.map(Number);

  if (!numbers || numbers.length < 4) {
    return null;
  }

  const [left, top, right, bottom] = numbers;
  return {
    x: left,
    y: top,
    width: right - left,
    height: bottom - top,
    coordinateSpace: "screen",
  };
}

function normalizeText(value) {
  return String(value ?? "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function textSimilarity(browserFocus, lastSpokenPhrase, itemTextLog) {
  const focusText = normalizeText(browserFocus?.name);
  if (!focusText) {
    return 0;
  }

  const candidates = [lastSpokenPhrase, ...(itemTextLog ?? [])]
    .map(normalizeText)
    .filter(Boolean);

  if (candidates.some((candidate) => candidate.includes(focusText))) {
    return 1;
  }

  const focusWords = new Set(focusText.split(" "));
  return Math.max(
    0,
    ...candidates.map((candidate) => {
      const candidateWords = new Set(candidate.split(" "));
      const overlap = [...focusWords].filter((word) =>
        candidateWords.has(word),
      ).length;
      return overlap / Math.max(focusWords.size, candidateWords.size);
    }),
  );
}

function dimensionSimilarity(browserFocus, voiceoverBounds) {
  const first = browserFocus?.bounds;
  const second = voiceoverBounds;
  if (!first || !second) {
    return 0;
  }

  const widthSimilarity =
    Math.min(first.width, second.width) / Math.max(first.width, second.width);
  const heightSimilarity =
    Math.min(first.height, second.height) /
    Math.max(first.height, second.height);
  return (widthSimilarity + heightSimilarity) / 2;
}

function compareFocus(browserFocus, voiceoverBounds, lastSpokenPhrase, itemTextLog) {
  const textScore = textSimilarity(
    browserFocus,
    lastSpokenPhrase,
    itemTextLog,
  );
  const roleMatches = Boolean(
    browserFocus?.role &&
      normalizeText(lastSpokenPhrase).startsWith(normalizeText(browserFocus.role)),
  );
  const dimensionsScore = dimensionSimilarity(browserFocus, voiceoverBounds);
  const similarityScore =
    textScore * 0.6 + (roleMatches ? 0.15 : 0) + dimensionsScore * 0.25;

  return {
    browserFocusIsInVoiceoverCursor: similarityScore >= 0.6,
    similarityScore,
    textSimilarity: textScore,
    roleMatches,
    dimensionsSimilarity: dimensionsScore,
  };
}

export function createVoiceOverService({
  daemonState,
  commit,
  getPage,
  collectAccessibilityState,
}) {
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
    return daemonState.context.voiceover.mode;
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
    return parseCursorBounds(stdout.trim());
  }

  async function refreshState(fromAction, parameters = null) {
    const page = getPage();

    if (!page) {
      throw new Error(
        `Cannot refresh VoiceOver state for ${fromAction}: no browser page is active`,
      );
    }

    const lastSpokenPhrase = await voiceOver
      .lastSpokenPhrase()
      .catch(() => null);
    const itemTextLog = await voiceOver.itemTextLog().catch(() => []);
    const accessibilityState = await collectAccessibilityState();
    const voiceoverBounds = await getCursorBounds().catch(() => null);
    const pageScreenshotPath = `.././screenshots/${randomUUID()}.jpeg`;
    await page.screenshot({ path: pageScreenshotPath });
    const mode = resolveMode(fromAction);
    const nextRunningState =
      fromAction === "voiceover.start"
        ? true
        : fromAction === "voiceover.stop"
          ? false
          : daemonState.context.voiceover.running;

    const history = lastSpokenPhrase
      ? [
          ...daemonState.context.voiceoverFocus.history,
          lastSpokenPhrase,
        ].slice(-3)
      : daemonState.context.voiceoverFocus.history;

    commit(
      {
        context: {
          page: {
            ...daemonState.context.page,
            screenshotPath: pageScreenshotPath,
          },
          a11y: {
            tree: accessibilityState.tree,
          },
          relevantNodes: accessibilityState.relevantNodes,
          browserFocus: accessibilityState.browserFocus,
          cursorPath: accessibilityState.cursorPath,
          voiceoverFocus: {
            bounds: voiceoverBounds,
            lastSpokenPhrase,
            history,
            itemTextLog,
          },
          focusComparison: {
            ...compareFocus(
              accessibilityState.browserFocus,
              voiceoverBounds,
              lastSpokenPhrase,
              itemTextLog,
            ),
          },
          voiceover: {
            ...daemonState.context.voiceover,
            running: nextRunningState,
            mode,
            lastSpokenPhrase,
          },
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
    if (daemonState.context.voiceover.mode === "rotor") {
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

  async function shutdown() {
    await voiceOver.stop();
  }

  async function stop() {
    await voiceOver.stop();
    await refreshState("voiceover.stop");
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
