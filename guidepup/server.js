const net = require('node:net')
const fs = require('node:fs')
const crypto = require('crypto')
const path = require('node:path')
const pino = require('pino')
const { chromium } = require('playwright')
const { voiceOver } = require('@guidepup/guidepup')
const { ok } = require('node:assert');
const destination = pino.destination('logs.log') // TODO could we make these per session?
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
  spokenPhraseLog: [],
  itemTextLog: [],
  lastSpokenPhrase: null,
  screenshotPath: null,

  pageUrl: null,
  pageTitle: null,
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
  const screenshotPath = await Promise.resolve(`./screenshots/${crypto.randomUUID()}.jpeg`)
  await daemon_state.page.screenshot({path:screenshotPath}); 

  commit({
    lastSpokenPhrase,
    itemTextLog,
    spokenPhraseLog: lastSpokenPhrase
      ? [...daemon_state.spokenPhraseLog, lastSpokenPhrase]
      : daemon_state.spokenPhraseLog,
    screenshotPath
  }, {
    fromAction: fromAction,
    parameters: parameters
  });
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
    return {
      ok: true,
      daemon_state: {
        version: daemon_state.version,
        ready: daemon_state.ready,
        pageUrl: daemon_state.pageUrl,
        pageTitle: daemon_state.pageTitle,
        voiceOverRunning: daemon_state.voiceOverRunning,
        lastSpokenPhrase: daemon_state.lastSpokenPhrase,
        spokenPhraseLog: [...daemon_state.spokenPhraseLog],
        itemTextLog: [...daemon_state.itemTextLog],
        events: [...daemon_state.events],
      }
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
    },{
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
    },{
      fromAction: "browser.stop"
    })
    return { ok: true };
  },

  // BROWSER ACTIONS

  async "browser.reload"(){

  },

  async "browser.goto"(){

  },

  // VOICEOVER LIFECYCLE

  async "voiceover.start"() {
    await voiceOver.start({
      capture: true
    });
    await refreshVoiceOverState('voiceover.start');
    return { ok: true };
  },

  async "voiceover.stop"() {
    await voiceOver.stop();
    await refreshVoiceOverState('voiceover.stop');
    return { ok: true };
  },

  // VOICEOVER ACTIONS

  async "voiceover.next"({ button }) {
    await voiceOver.next(button);
    await refreshVoiceOverState('voiceover.next', button);
    return { ok: true };
  },

  async "voiceover.previous"({ button }) {
    await voiceOver.previous(button);
    await refreshVoiceOverState('voiceover.previous', button);
    return { ok: true };
  },

  async "voiceover.perform"({ command }) {
    await voiceOver.perform(voiceOver.commanderCommands[command])
    await refreshVoiceOverState('voiceover.perform', command);
    return { ok: true };
  },

  async "voiceover.type"({ text }) {
    // TODO check for special characters
    for (const element of text) {
      await sleep(500);
      await voiceOver.press(element);
    }
    // await voiceOver.type(text)
    await refreshVoiceOverState('voiceover.type', text);
    return { ok: true };
  },

  async "voiceover.press"({ key }) {
    await voiceOver.press(key);
    await refreshVoiceOverState('voiceover.press', key);
    return { ok: true };
  },

};

// -----------------------------------------------------------
// RPC SERVER LOGIC
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
        writeMessage(socket, {
          jsonrpc: "2.0", id: id ?? null,
          error: { code: -32000, message: err?.message || "Internal error", },
        });
      }
    }
  });

  socket.on("error", () => { });
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