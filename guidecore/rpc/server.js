import { createServer } from "node:net";
import { existsSync, unlinkSync } from "node:fs";

export function createRpcServer({ socketPath, handlers, logger, onAction }) {
  let requestQueue = Promise.resolve();

  function removeExistingSocket() {
    if (existsSync(socketPath)) {
      unlinkSync(socketPath);
    }
  }

  function writeMessage(socket, message) {
    socket.write(`${JSON.stringify(message)}\n`);
  }

  async function handleLine(socket, line) {
    let request;

    try {
      request = JSON.parse(line);
    } catch {
      writeMessage(socket, {
        jsonrpc: "2.0",
        id: null,
        error: { code: -32700, message: "Parse error" },
      });
      return;
    }

    const { id, method, params = {} } = request;

    if (!method) {
      writeMessage(socket, {
        jsonrpc: "2.0",
        id: id ?? null,
        error: { code: -32600, message: "Invalid Request" },
      });
      return;
    }

    const handler = handlers[method];
    if (!handler) {
      writeMessage(socket, {
        jsonrpc: "2.0",
        id,
        error: { code: -32601, message: `Method not found: ${method}` },
      });
      return;
    }

    try {
      const result = await handler(params);
      onAction?.({ method, params, result });

      if (id !== undefined && id !== null) {
        writeMessage(socket, { jsonrpc: "2.0", id, result });
      }
    } catch (err) {
      logger.error({ err, id, method, params }, "RPC handler failed");
      writeMessage(socket, {
        jsonrpc: "2.0",
        id: id ?? null,
        error: {
          code: -32000,
          message: err?.message || "Internal error",
        },
      });
    }
  }

  const server = createServer((socket) => {
    socket.setEncoding("utf8");
    let buffer = "";

    socket.on("data", (chunk) => {
      buffer += chunk;

      let index;
      while ((index = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, index).trim();
        buffer = buffer.slice(index + 1);

        if (line) {
          requestQueue = requestQueue
            .then(() => handleLine(socket, line))
            .catch((err) => {
              logger.error({ err }, "RPC request processing failed");
            });
        }
      }
    });

    socket.on("error", (err) => {
      logger.error({ err }, "Socket error");
    });
  });

  function start() {
    removeExistingSocket();

    return new Promise((resolve, reject) => {
      server.once("error", reject);
      server.listen(socketPath, resolve);
    });
  }

  function close() {
    return new Promise((resolve, reject) => {
      if (!server.listening) {
        removeExistingSocket();
        resolve();
        return;
      }

      server.close((err) => {
        if (err) {
          reject(err);
          return;
        }

        removeExistingSocket();
        resolve();
      });
    });
  }

  return {
    start,
    close,
  };
}
