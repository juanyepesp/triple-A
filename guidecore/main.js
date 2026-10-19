import { mkdirSync, rmSync } from "node:fs";
import { join } from "node:path";
import pino, { destination as createDestination } from "pino";
// handlers
import { createCoreHandlers } from "./handlers/core.js";
import { createBrowserHandlers } from "./handlers/browser.js";
import { createVoiceOverHandlers } from "./handlers/voiceover.js";
// core
import { createRpcServer } from "./rpc/server.js";
// state
import { createStateManager } from "./state/daemon-state.js";
// services
import { createBrowserService } from "./services/browser.js";
import { createVoiceOverService } from "./services/voiceover.js";

// -----------------------------------------------------------
// GLOBALS
// -----------------------------------------------------------

const socketPath = "/tmp/guidecore.sock";
const logsDirectory = join(process.cwd(), "logs");
const screenshotsDirectory = join(process.cwd(), "..", "screenshots");
const sessionLogPath = join(
  logsDirectory,
  `logs-${process.pid}-${Date.now()}.log`,
);

mkdirSync(logsDirectory, { recursive: true });

const logger = pino(
  { name: "guidecore-daemon" },
  createDestination(sessionLogPath),
);

// -----------------------------------------------------------
// STATE
// Single source of truth for all browser and VO actions
// -----------------------------------------------------------

const state = createStateManager({ logger });

// -----------------------------------------------------------
// SERVICES
// Browser and VO functions
// -----------------------------------------------------------

const browserService = createBrowserService({
  daemonState: state.daemonState,
  commit: state.commit,
  logger,
});
const voiceOverService = createVoiceOverService({
  daemonState: state.daemonState,
  commit: state.commit,
  getPage: browserService.getPage,
  collectAccessibilityState: browserService.collectNodesFromA11yTree,
  captureScreenshot: browserService.captureScreenshot,
});

// -----------------------------------------------------------
// HANDLERS
// Each one of these handlers is a function that will be called by the python agent. 
// They update the state to keep a single unified source of truth.
// They're dependent on the services.
// -----------------------------------------------------------

const handlers = {
  ...createCoreHandlers({
  buildSnapshot: state.buildSnapshot,
  }),
  ...createBrowserHandlers({ browserService }),
  ...createVoiceOverHandlers({ voiceOverService }),
};

// -----------------------------------------------------------
// CORE
// RPC server management.
// -----------------------------------------------------------

const rpcServer = createRpcServer({
  socketPath,
  handlers,
  logger,
});

async function start() {
  await rpcServer.start();
  console.log(`GUIDECORE INFO: RPC daemon listening on ${socketPath}`);
}

async function shutdown() {
  try {
    await voiceOverService.shutdown();
  } catch (err) {
    logger.error({ err }, "Failed to stop VoiceOver during shutdown");
  }

  try {
    await rpcServer.close();
  } finally {
    rmSync(screenshotsDirectory, { recursive: true, force: true });
    process.exit(0);
  }
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

start().catch((err) => {
  logger.error({ err }, "Failed to start daemon");
  process.exit(1);
});
