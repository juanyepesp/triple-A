import { mkdirSync } from "node:fs";
import { join } from "node:path";
import pino, { destination as _destination } from "pino";

import createStateManager from "./state/daemon-state.js";
import createBrowserService from "./services/browser.js";
import createVoiceOverService from "./services/voiceover.js";

import createHandlers from "./handlers/index.js";
import createRpcServer from "./rpc/server.js";


// -----------------------------------------------------------
// CONFIG
// -----------------------------------------------------------

const socketPath = "/tmp/guidecore.sock";


// -----------------------------------------------------------
// LOGGER
// -----------------------------------------------------------

const sessionLogPath = join(
  process.cwd(),
  `logs/logs-${process.pid}-${Date.now()}.log`
);

const logsDirectory = join(
  process.cwd(),
  "logs"
);

mkdirSync(logsDirectory, {
  recursive: true,
});

const destination =
  _destination(sessionLogPath);

const logger = pino(
  {
    name: "guidecore-daemon",
  },
  destination
);


// -----------------------------------------------------------
// STATE
// -----------------------------------------------------------

const {
  daemonState,
  commit,
  buildSnapshot,
} = createStateManager({
  logger,
});


// -----------------------------------------------------------
// SERVICES
// -----------------------------------------------------------

const browserService =
  createBrowserService({
    daemonState,
    commit,
    logger,
  });

const voiceOverService =
  createVoiceOverService({
    daemonState,
    commit,
    logger,
  });


// -----------------------------------------------------------
// HANDLERS
// -----------------------------------------------------------

const handlers =
  createHandlers({
    daemonState,
    buildSnapshot,
    browserService,
    voiceOverService,
  });


// -----------------------------------------------------------
// RPC SERVER
// -----------------------------------------------------------

const rpcServer =
  createRpcServer({
    socketPath,
    handlers,
    logger,
  });


// -----------------------------------------------------------
// START
// -----------------------------------------------------------

async function start() {
  await rpcServer.start();

  console.log(
    `GUIDECORE INFO: RPC daemon listening on ${socketPath}`
  );
}


// -----------------------------------------------------------
// SHUTDOWN
// -----------------------------------------------------------

async function shutdown() {
  try {
    await voiceOverService.stop();
  } catch (err) {
    logger.error(
      {
        err,
      },
      "Failed to stop VoiceOver during shutdown"
    );
  }

  await rpcServer.close();

  process.exit(0);
}

process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);

start().catch((err) => {
  logger.error(
    {
      err,
    },
    "Failed to start daemon"
  );

  process.exit(1);
});