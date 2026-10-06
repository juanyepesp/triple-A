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

function containsCue(text, cue) {
  return cue.includes(" ")
    ? text.includes(cue)
    : new RegExp(`\\b${cue}\\b`).test(text);
}

function resolveWebContentScope(
  currentValue,
  lastSpokenPhrase,
  itemTextLog = [],
) {
  const outsideCues = [
    "google chrome",
    "chrome",
    "tab",
    "toolbar",
    "address bar",
    "address and search bar",
    "bookmarks bar",
    "window",
    "menu bar",
    "dock",
    "desktop",
  ];
  const insideCues = [
    "web content",
    "webpage",
    "web page",
    "heading",
    "link",
    "button",
    "checkbox",
    "combobox",
    "textbox",
    "search field",
    "form",
    "landmark",
    "banner",
    "navigation",
    "main",
    "contentinfo",
    "group",
    "paragraph",
    "article",
    "image",
    "table",
    "list",
  ];

  const observations = [
    lastSpokenPhrase,
    ...(Array.isArray(itemTextLog) ? itemTextLog.slice(-1) : []),
  ]
    .map(normalizeText)
    .filter(Boolean);

  if (
    observations.some((text) =>
      outsideCues.some((cue) => containsCue(text, cue)),
    )
  ) {
    return true;
  }

  if (
    observations.some((text) =>
      insideCues.some((cue) => containsCue(text, cue)),
    )
  ) {
    return false;
  }

  return currentValue;
}

function textSimilarity(browserFocus, lastSpokenPhrase) {
  const focusText = normalizeText(browserFocus?.name);
  if (!focusText) {
    return 0;
  }

  const spokenText = normalizeText(lastSpokenPhrase);

  if (!spokenText) {
    return 0;
  }

  if (spokenText.includes(focusText)) {
    return 1;
  }

  const focusWords = new Set(focusText.split(" "));
  const spokenWords = new Set(spokenText.split(" "));
  const overlap = [...focusWords].filter((word) => spokenWords.has(word)).length;
  return overlap / Math.max(focusWords.size, spokenWords.size);
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

function compareFocus(browserFocus, voiceoverBounds, lastSpokenPhrase) {
  const textScore = textSimilarity(browserFocus, lastSpokenPhrase);
  const roleMatches = Boolean(
    browserFocus?.role &&
      normalizeText(lastSpokenPhrase).startsWith(normalizeText(browserFocus.role)),
  );
  const dimensionsScore = dimensionSimilarity(browserFocus, voiceoverBounds);
  const similarityScore =
    textScore * 0.6 + (roleMatches ? 0.05 : 0) + dimensionsScore * 0.35; // ? heurisitically chosen.

  return {
    VOCursorBrowserFocusAreSimilarEnough: similarityScore >= 0.9,
    similarityScore,
    textSimilarity: [textScore, lastSpokenPhrase],
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
    const itemTextLog = (await voiceOver.itemTextLog().catch(() => [])).slice(-5);
    const accessibilityState = await collectAccessibilityState();
    const voiceoverBounds = await getCursorBounds().catch(() => null);
    const pageScreenshotPath = `.././screenshots/${randomUUID()}.jpeg`;
    await page.screenshot({ path: pageScreenshotPath });
    const nextRunningState =
      fromAction === "voiceover.start"
        ? true
        : fromAction === "voiceover.stop"
          ? false
          : daemonState.context.voiceover.running;
    const isOutsideWebContent = resolveWebContentScope(
      daemonState.context.voiceoverFocus.isOutsideWebContent,
      lastSpokenPhrase,
      itemTextLog,
    );

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
            isOutsideWebContent,
            itemTextLog,
          },
          focusComparison: {
            ...compareFocus(
              accessibilityState.browserFocus,
              voiceoverBounds,
              lastSpokenPhrase,
            ),
          },
          voiceover: {
            ...daemonState.context.voiceover,
            running: nextRunningState,
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
    await voiceOver.start({
      capture: true,
      retries: 3,
      timeout: 10000,
    });
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
    nextHeading: () => action("voiceover.nextHeading", () => voiceOver.nextHeading()),
    previousHeading: () => action("voiceover.previousHeading",() => voiceOver.previousHeading()),
    nextLandmark: () => action("voiceover.nextLandmark", () => voiceOver.nextLandmark()),
    previousLandmark: () => action("voiceover.previousLandmark", () => voiceOver.previousLandmark()),
    nextLink: () => action("voiceover.nextLink", () => voiceOver.nextLink()),
    previousLink: () => action("voiceover.previousLink", () => voiceOver.previousLink(),),
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
  };
}
