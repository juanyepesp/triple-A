const net = require('node:net')
const fs = require('node:fs')
const crypto = require('crypto')
const path = require('node:path')
const pino = require('pino')
const { chromium } = require('playwright')
const { voiceOver, VoiceOverCommanderCommands, MacOSKeyCodes, MacOSModifiers } = require('@guidepup/guidepup')
const { ok } = require('node:assert');
const { CommanderCommands } = require('@guidepup/guidepup/lib/macOS/VoiceOver/CommanderCommands')
const { describe } = require('node:test')
const { VoiceOver } = require('@guidepup/guidepup/lib/macOS/VoiceOver/VoiceOver')
const sessionLogPath = path.join(
  process.cwd(),
  `logs/logs-${process.pid}-${Date.now()}.log`
)
const logsDirectory = path.join(process.cwd(), 'logs')
fs.mkdirSync(logsDirectory, { recursive: true })
const destination = pino.destination(sessionLogPath)
const logger = pino(
  { name: 'guidepup-daemon' },
  destination
)

const socket_path = "/tmp/guidepup.sock"

// -----------------------------------------------------------
// DAEMON STATE
// Single source of truth for all browser and voice over actions
// -----------------------------------------------------------

const daemon_state = {
  browser: null,
  context: null,
  page: null,

  voiceOverRunning: false,
  currentVoiceOverCursorDescription: null,
  voiceOverMode: null,
  // TODO maybe add a rotor information

  pageUrl: null,
  pageTitle: null,
  pageScreenshotPath: null,
  accessibilityTree: null,
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

function bindPageEvents(page) {
  page.on("framenavigated", async () => {
    commit({
      pageUrl: page.url(),
      pageTitle: await page.title().catch(() => null),
    }, {
      fromAction: "browser.navigation",
      url: page.url(),
    });
  });

  page.on("load", async () => {
    commit({
      pageUrl: page.url(),
      pageTitle: await page.title().catch(() => null),
      accessibilityTree: await page.ariaSnapshot().catch(() => null)
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

  return daemon_state.voiceOverMode;
}

async function getVoiceOverCursorDescription() {
  await voiceOver.perform(VoiceOverCommanderCommands.DESCRIBE_ITEM_IN_VOICEOVER_CURSOR).catch(() => null)
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
  const pageScreenshotPath = await Promise.resolve(`.././screenshots/${crypto.randomUUID()}.jpeg`);
  await daemon_state.page.screenshot({ path: pageScreenshotPath });
  const mode = resolveVoiceOverMode(fromAction);
  // ? const cursorScreenshotPath = await voiceOver.takeCursorScreenshot(); 
  const inRotor = daemon_state.voiceOverMode === "rotor";

  commit({
    pageScreenshotPath,
    voiceOverRunning:
      fromAction == 'voiceover.start'
        ? true
        : fromAction == 'voiceover.stop'
          ? false
          : daemon_state.voiceOverRunning,
    voiceOverMode: mode,    
    currentVoiceOverCursorDescription:
      fromAction == 'voiceover.stop' || mode === 'rotor'
        ? null
        : await getVoiceOverCursorDescription() 
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
  if (daemon_state.voiceOverMode === "rotor") {
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

if (fs.existsSync(socket_path)) {
  fs.unlinkSync(socket_path); // if there is a socket path linked already, unlink
}

const handlers = {

  // CORE
  async ping() {
    return { ok: true, time: Date.now() };
  },

  async "daemonstate.snapshot"() {
    const snapshot = {
      version: daemon_state.version,
      ready: daemon_state.ready,
      pageUrl: daemon_state.pageUrl,
      pageTitle: daemon_state.pageTitle,
      accessibilityTree: daemon_state.accessibilityTree,
      pageScreenshotPath: daemon_state.pageScreenshotPath,
      events: [...daemon_state.events],
      voiceOverInfo: {
        voiceOverRunning: daemon_state.voiceOverRunning,
        voiceOverMode: daemon_state.voiceOverMode,
        currentVoiceOverCursorDescription: daemon_state.currentVoiceOverCursorDescription,
      },
    }

    return {
      ok: true,
      daemon_state: snapshot
    }
  },

  // BROWSER LIFECYCLE

  async "browser.start"({ url }) {
    await ensureBrowser();
    await daemon_state.page.goto(url, {
      waitUntil: "load",
    });
    commit({
      pageUrl: daemon_state.page.url(),
      pageTitle: await daemon_state.page.title().catch(() => null),
      ready: true,
    }, {
      fromAction: "browser.start"
    })
    return { ok: true };
  },

  async "browser.stop"() {
    await daemon_state.browser.close()
    commit({
      pageUrl: null,
      pageTitle: null,
      ready: false,
    }, {
      fromAction: "browser.stop"
    })
    return { ok: true };
  },

  // BROWSER ACTIONS
  async "browser.aom"() {
    const snapshot = await daemon_state.page.ariaSnapshot();
    return snapshot
  },

  // VOICEOVER LIFECYCLE

  async "voiceover.start"() {
    await voiceOver.start({
      capture: "initial"
    });
    await refreshVoiceOverState('voiceover.start');
    return { ok: true };
  },

  async "voiceover.goToWebContent"() {
    // ! For this command to work properly, you have to set the hot spot to the webcontent
    const moveToNextHotspotCommand = {
      keyCode: MacOSKeyCodes.RightSquareBracket,
      modifiers: [MacOSModifiers.Control, MacOSModifiers.Option, MacOSModifiers.Shift],
      description: "Move to next hot spot",
      depresentation: "VO-}"
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
    await voiceOver.perform(CommanderCommands.START_INTERACTING_WITH_ITEM);
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
    await voiceOver.perform(CommanderCommands.ESCAPE);
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
    await voiceOver.perform(CommanderCommands.ROTOR);
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

const server = net.createServer((socket) => {
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
  console.log(`GUIDEPUP INFO: RPC daemon listening on ${socket_path}`)
})

process.on("SIGINT", async () => {
  server.close(() => {
    try {
      if (fs.existsSync(socket_path)) {
        fs.unlinkSync(socket_path)
      }
    } catch {
      console.error("GUIDEPUP ERROR: Socket was not unlinked correctly")
      process.exit(1)
    }
    process.exit(0);
  })
})