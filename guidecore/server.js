import { createServer } from 'node:net'
import { mkdirSync, existsSync, unlinkSync } from 'node:fs'
import { randomUUID } from 'crypto'
import { join } from 'node:path'
import pino, { destination as _destination } from 'pino'
import { chromium } from 'playwright'
import { voiceOver, MacOSKeyCodes, MacOSModifiers } from '@guidepup/guidepup'

import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);


const sessionLogPath = join(
  process.cwd(),
  `logs/logs-${process.pid}-${Date.now()}.log`
)
const logsDirectory = join(process.cwd(), 'logs')
mkdirSync(logsDirectory, { recursive: true })
const destination = _destination(sessionLogPath)
const logger = pino(
  { name: 'guidecore-daemon' },
  destination
)

const socket_path = "/tmp/guidecore.sock"

// -----------------------------------------------------------
// DAEMON STATE
// Single source of truth for all browser and voice over actions
// -----------------------------------------------------------

const daemon_state = {
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


// -----------------------------------------------------------
// HELPER FUNCTIONS
// -----------------------------------------------------------

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function commit(patch, event = null) {
  const log = logger.child({ patch: patch, event: event })
  log.info("daemon_state commit")

  Object.assign(daemon_state, patch);
  daemon_state.version += 1;

  if (event) {
    daemon_state.events.push({
      ts: Date.now(),
      ...event,
    });
  }
}

function buildSnapshot() {
  return {
    version: daemon_state.version,
    ready: daemon_state.ready,
    page: { ...daemon_state.pageInfo },
    voiceOver: { ...daemon_state.voiceOver },
  };
}

function bindPageEvents(page) {
  page.on("framenavigated", async () => {
    commit({
      pageInfo: {
        ...daemon_state.pageInfo,
        url: page.url(),
        title: await page.title().catch(() => null),
      },
    }, {
      fromAction: "browser.navigation",
      url: page.url(),
    });
  });

  page.on("load", async () => {
    commit({
      pageInfo: {
        ...daemon_state.pageInfo,
        url: page.url(),
        title: await page.title().catch(() => null),
        accessibilityTree: await page.ariaSnapshot({ mode: 'ai', boxes: true }).catch(() => null),
      },
    }, {
      fromAction: "browser.load",
      url: page.url(),
    });
  });

  page.on("close", () => {
    commit(
      {
        page: null,
        context: null,
        browser: null,
        ready: false,
      },
      { fromAction: "browser.closed" }
    );
  });
}

function resolveVoiceOverMode(fromAction) {
  if (fromAction === 'voiceover.stop') {
    return null;
  }

  if (fromAction.startsWith('voiceover.rotor.')) {
    return 'rotor';
  }

  if (fromAction.startsWith('voiceover.')) {
    return 'normal';
  }

  return daemon_state.voiceOver.mode;
}

async function getVoiceOverCursorBounds() {
  const script = `
tell application "VoiceOver"
    return bounds of vo cursor
end tell
`;

  const { stdout } = await execFileAsync(
    "/usr/bin/osascript",
    ["-e", script]
  );

  return stdout.trim();
}

function compareBoxes(a, b) {
  const centerA = {
    x: a.x + a.width / 2,
    y: a.y + a.height / 2,
  };

  const centerB = {
    x: b.x + b.width / 2,
    y: b.y + b.height / 2,
  };

  const centerDistance = Math.hypot(
    centerA.x - centerB.x,
    centerA.y - centerB.y
  );

  const left = Math.max(a.x, b.x);
  const top = Math.max(a.y, b.y);
  const right = Math.min(
    a.x + a.width,
    b.x + b.width
  );
  const bottom = Math.min(
    a.y + a.height,
    b.y + b.height
  );

  const intersectionWidth = Math.max(0, right - left);
  const intersectionHeight = Math.max(0, bottom - top);
  const intersection =
    intersectionWidth * intersectionHeight;

  const areaA = a.width * a.height;
  const areaB = b.width * b.height;

  const union =
    areaA + areaB - intersection;

  return {
    centerDistance,
    iou: union > 0 ? intersection / union : 0,
    widthDifference: Math.abs(a.width - b.width),
    heightDifference: Math.abs(a.height - b.height),
  };
}


async function getVoiceOverCursorDescription() {
  const repeatLastSpokenPhraseCommand = {
    keyCode: MacOSKeyCodes.z,
    modifiers: [MacOSModifiers.Control, MacOSModifiers.Option, MacOSModifiers],
    description: "Repeat Last Spoken Phrase",
    representation: "VO-Z"
  }
  await voiceOver.perform(repeatLastSpokenPhraseCommand).catch(() => null);

  // await voiceOver.perform(VoiceOverCommanderCommands.DESCRIBE_ITEM_IN_VOICEOVER_CURSOR).catch(() => null);
  const itemDescription = await voiceOver.lastSpokenPhrase()
  return itemDescription
}

async function ensureBrowser() {
  if (daemon_state.browser) return;

  daemon_state.browser = await chromium.launch({
    headless: false,
    args: ["--start-maximized"],
  });

  daemon_state.context = await daemon_state.browser.newContext();
  daemon_state.page = await daemon_state.context.newPage();

  bindPageEvents(daemon_state.page);
}

async function refreshVoiceOverState(fromAction, parameters = null) {
  const lastSpokenPhrase = await voiceOver.lastSpokenPhrase().catch(() => null);
  const itemTextLog = await voiceOver.itemTextLog().catch(() => []);
  const pageScreenshotPath = await Promise.resolve(`.././screenshots/${randomUUID()}.jpeg`);
  await daemon_state.page.screenshot({ path: pageScreenshotPath });
  const mode = resolveVoiceOverMode(fromAction);
  const nextRunningState =
    fromAction == 'voiceover.start'
      ? true
      : fromAction == 'voiceover.stop'
        ? false
        : daemon_state.voiceOver.running;
  const nextCursorDescription =
    fromAction == 'voiceover.stop' || mode === 'rotor'
      ? null
      : await getVoiceOverCursorDescription();

  commit({
    pageInfo: {
      ...daemon_state.pageInfo,
      screenshotPath: pageScreenshotPath,
    },
    voiceOver: {
      ...daemon_state.voiceOver,
      running: nextRunningState,
      mode,
      cursorDescription: nextCursorDescription,
    },
  }, {
    fromAction: fromAction,
    parameters: parameters,
    voiceoverCursor: {
      speech: lastSpokenPhrase,
      itemTextLog: itemTextLog
    }
  });
}

function assertNotRotorMode(action) {
  if (daemon_state.voiceOver.mode === "rotor") {
    throw new Error(`${action} is unavailable while rotor is open`)
  }
}

async function typeVoiceOverText(text) {
  if (typeof voiceOver.type === 'function') {
    await voiceOver.type(text)
    return
  }

  const characterMap = {
    ' ': 'Space',
    '\n': 'Enter',
    '\t': 'Tab',
  }

  for (const character of text) {
    await sleep(1);
    await voiceOver.press(characterMap[character] ?? character);
  }
}

// -----------------------------------------------------------
// HANDLERS
// 
// Each one of these handlers is a function that will be called by the python agent. 
// They update the state to keep a single unified source of truth.
// -----------------------------------------------------------

if (existsSync(socket_path)) {
  unlinkSync(socket_path); // if there is a socket path linked already, unlink
}

const handlers = {

  // CORE
  async ping() {
    return { ok: true, time: Date.now() };
  },

  async "daemonstate.snapshot"() {
    return {
      ok: true,
      daemon_state: buildSnapshot(),
    }
  },

  // BROWSER LIFECYCLE

  async "browser.start"({ url }) {
    await ensureBrowser();
    await daemon_state.page.goto(url, {
      waitUntil: "load",
    });
    commit({
      ready: true,
      pageInfo: {
        ...daemon_state.pageInfo,
        url: daemon_state.page.url(),
        title: await daemon_state.page.title().catch(() => null),
      },
    }, {
      fromAction: "browser.start"
    })
    return { ok: true };
  },

  async "browser.viewportLocation"() {
    const viewport = await daemon_state.page.evaluate(() => ({
      screenX: window.screenX,
      screenY: window.screenY,
      devicePixelRatio: window.devicePixelRatio,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    }));
    // TODO compare the boxes
    return {ok: true, playwright: viewport};
  },

  async "voiceover.cursorLocation"(){
    let bounds = await getVoiceOverCursorBounds()
    return {ok: true, VOCursorLocation: bounds}
  },

  async "browser.stop"() {
    await daemon_state.browser.close()
    commit({
      ready: false,
      pageInfo: {
        ...daemon_state.pageInfo,
        url: null,
        title: null,
        accessibilityTree: null,
        screenshotPath: null,
      },
    }, {
      fromAction: "browser.stop"
    })
    return { ok: true };
  },

  // BROWSER ACTIONS
  async "browser.aom"() {
    const snapshot = await daemon_state.page.ariaSnapshot(({
                mode: "ai",
                boxes: true,
              }));
    return { ok: true, snapshot: snapshot }
  },

  // VOICEOVER LIFECYCLE

  async "voiceover.start"() {
    await voiceOver.start({
      capture: true
    });

    await voiceOver.clearItemTextLog();
    await voiceOver.clearSpokenPhraseLog();

    await refreshVoiceOverState('voiceover.start');
    return { ok: true };
  },

  async "voiceover.goToWebContent"() {
    // ! For this command to work properly, you have to set the hot spot to the webcontent
    // refer to README.md on project root
    const moveToNextHotspotCommand = {
      keyCode: MacOSKeyCodes.RightSquareBracket,
      modifiers: [MacOSModifiers.Control, MacOSModifiers.Option, MacOSModifiers.Shift],
      description: "Move to next hot spot",
      representation: "VO-Shift-}"
    }
    await voiceOver.perform(moveToNextHotspotCommand);
    await refreshVoiceOverState('voiceover.setup');
    return { ok: true }
  },

  async "voiceover.stop"() {
    await voiceOver.stop();
    await refreshVoiceOverState('voiceover.stop');
    return { ok: true };
  },

  // VOICEOVER ACTIONS

  async "voiceover.next"() {
    assertNotRotorMode("voiceover.next")
    await voiceOver.next();
    await refreshVoiceOverState('voiceover.next');
    return { ok: true };
  },

  async "voiceover.previous"() {
    assertNotRotorMode("voiceover.previous")
    await voiceOver.previous();
    await refreshVoiceOverState('voiceover.previous');
    return { ok: true };
  },

  async "voiceover.startInteracting"({ }) {
    // entering a group, VO-Shift-DownArrow
    assertNotRotorMode("voiceover.startInteracting")
    await voiceOver.perform(voiceOver.commanderCommands.START_INTERACTING_WITH_ITEM);
    await refreshVoiceOverState('voiceover.startInteracting');
    return { ok: true };
  },

  async "voiceover.stopInteracting"() {
    // exiting a group, VO-Shift-UpArrow
    assertNotRotorMode("voiceover.stopInteracting")
    await voiceOver.stopInteracting();
    await refreshVoiceOverState('voiceover.stopInteracting');
    return { ok: true };
  },

  async "voiceover.perform"({ command }) {
    assertNotRotorMode(`voiceover.perform(${command})`)
    await voiceOver.perform(voiceOver.commanderCommands[command])
    await refreshVoiceOverState('voiceover.perform', command);
    return { ok: true };
  },

  async "voiceover.escape"() {
    await voiceOver.perform(voiceOver.commanderCommands.ESCAPE);
    await refreshVoiceOverState('voiceover.escape');
    return { ok: true };
  },

  async "voiceover.type"({ text }) {
    assertNotRotorMode(`voiceover.type(${text})`)
    await typeVoiceOverText(text)
    await refreshVoiceOverState('voiceover.type', text);
    return { ok: true };
  },

  async "voiceover.press"({ key }) {
    assertNotRotorMode(`voiceover.press(${key})`)
    await voiceOver.press(key);
    await refreshVoiceOverState('voiceover.press', key);
    return { ok: true };
  },

  async "voiceover.rotor.open"() {
    await voiceOver.perform(voiceOver.commanderCommands.ROTOR);
    await refreshVoiceOverState('voiceover.rotor.open');
    return { ok: true };
  },

  async "voiceover.rotor.nextCategory"() {
    await voiceOver.press('ArrowRight');
    await refreshVoiceOverState('voiceover.rotor.nextCategory');
    return { ok: true };
  },

  async "voiceover.rotor.previousCategory"() {
    await voiceOver.press('ArrowLeft');
    await refreshVoiceOverState('voiceover.rotor.previousCategory');
    return { ok: true };
  },

  async "voiceover.rotor.nextItem"() {
    await voiceOver.press('ArrowDown');
    await refreshVoiceOverState('voiceover.rotor.nextItem');
    return { ok: true };
  },

  async "voiceover.rotor.previousItem"() {
    await voiceOver.press('ArrowUp');
    await refreshVoiceOverState('voiceover.rotor.previousItem');
    return { ok: true };
  },

  async "voiceover.rotor.find"({ text }) {
    await typeVoiceOverText(text)
    await refreshVoiceOverState('voiceover.rotor.find', text);
    return { ok: true };
  },

  async "voiceover.rotor.activate"() {
    await voiceOver.press('Space');
    await refreshVoiceOverState('voiceover.rotor.activate');
    return { ok: true };
  },

};

// -----------------------------------------------------------
// LOGIC
// 
// The following code has the logic to handle each interaction the server gets; from 
// printing errors to sending the information
// -----------------------------------------------------------


function writeMessage(socket, msg) {
  socket.write(JSON.stringify(msg) + "\n");
}

const server = createServer((socket) => {
  socket.setEncoding("utf8");
  let buffer = "";

  socket.on("data", async (chunk) => {
    buffer += chunk;

    let index;
    while ((index = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, index).trim();
      buffer = buffer.slice(index + 1);

      if (!line) continue;

      let req;
      try {
        req = JSON.parse(line);
      } catch (err) {
        writeMessage(socket, {
          jsonrpc: "2.0",
          id: null,
          error: { code: -32700, message: "Parse error" },
        });
        continue;
      }

      const { id, method, params = {} } = req;

      // if request is not valid (not standard)
      if (!method) {
        writeMessage(socket, {
          jsonrpc: "2.0",
          id: id ?? null,
          error: { code: -32600, message: "Invalid Request" },
        });
        continue;
      }

      // if the handler is not found
      const handler = handlers[method];
      if (!handler) {
        writeMessage(socket, {
          jsonrpc: "2.0",
          id,
          error: { code: -32601, message: `Method not found: ${method}` },
        });
        continue;
      }

      // if any handler doesn't work
      try {
        const result = await handler(params);
        if (id !== undefined && id !== null) {
          writeMessage(socket, { jsonrpc: "2.0", id, result });
        }
      } catch (err) {
        logger.error(
          { err, id, method, params },
          "RPC handler failed"
        );
        writeMessage(socket, {
          jsonrpc: "2.0", id: id ?? null,
          error: { code: -32000, message: err?.message || "Internal error", },
        });
      }
    }
  });

  socket.on("error", (err) => {
    logger.error({ err }, "Socket error");
  });
});

server.listen(socket_path, () => {
  console.log(`GUIDECORE INFO: RPC daemon listening on ${socket_path}`)
})

async function stopVoiceOverOnShutdown() {
  try {
    await voiceOver.stop()
  } catch (err) {
    logger.error({ err }, "Failed to stop VoiceOver during shutdown")
  }
}

process.on("SIGINT", async () => {
  await stopVoiceOverOnShutdown()

  server.close(() => {
    try {
      if (existsSync(socket_path)) {
        unlinkSync(socket_path)
      }
    } catch {
      console.error("GUIDEPUP ERROR: Socket was not unlinked correctly")
      process.exit(1)
    }
    process.exit(0)
  })
})