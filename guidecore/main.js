import { mkdirSync } from "node:fs";
import { join } from "node:path";
import pino, { destination as _destination } from "pino";

import createStateManager from "./state/daemon-state.js";
import createBrowserService from "./services/browser.js";
import createVoiceOverService from "./services/voiceover.js";

import createHandlers from "./handlers/index.js";
import createRpcServer from "./rpc/server.js";

const socketPath = "/tmp/guidecore.sock";

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

// TODO maybe this way of declarating state is not ideal for maintaining consistency
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
    commit
  });

const voiceOverService =
  createVoiceOverService({
    daemonState,
    commit
  });

const handlers =
  createHandlers({
    daemonState,
    buildSnapshot,
    browserService,
    voiceOverService,
  });

const rpcServer =
  createRpcServer({
    socketPath,
    handlers,
    logger,
  });


async function start() {
  await rpcServer.start();
  console.log(
    `GUIDECORE INFO: RPC daemon listening on ${socketPath}`
  );
}

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