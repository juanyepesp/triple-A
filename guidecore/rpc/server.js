import { createServer } from "node:net";
import { existsSync, unlinkSync } from "node:fs";

function createRpcServer({
  socketPath,
  handlers,
  logger,
}) {
  if (existsSync(socketPath)) {
    unlinkSync(socketPath);
  }

  function writeMessage(socket, message) {
    socket.write(JSON.stringify(message) + "\n");
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

        if (!line) {
          continue;
        }

        let request;

        try {
          request = JSON.parse(line);
        } catch {
          writeMessage(socket, {
            jsonrpc: "2.0",
            id: null,
            error: {
              code: -32700,
              message: "Parse error",
            },
          });
          continue;
        }

        const {
          id,
          method,
          params = {},
        } = request;

        if (!method) {
          writeMessage(socket, {
            jsonrpc: "2.0",
            id: id ?? null,
            error: {
              code: -32600,
              message: "Invalid Request",
            },
          });
          continue;
        }

        const handler = handlers[method];

        if (!handler) {
          writeMessage(socket, {
            jsonrpc: "2.0",
            id,
            error: {
              code: -32601,
              message: `Method not found: ${method}`,
            },
          });
          continue;
        }

        try {
          const result = await handler(params);

          if (id !== undefined && id !== null) {
            writeMessage(socket, {
              jsonrpc: "2.0",
              id,
              result,
            });
          }
        } catch (err) {
          logger.error(
            {
              err,
              id,
              method,
              params,
            },
            "RPC handler failed"
          );

          writeMessage(socket, {
            jsonrpc: "2.0",
            id: id ?? null,
            error: {
              code: -32000,
              message:
                err?.message || "Internal error",
            },
          });
        }
      }
    });

    socket.on("error", (err) => {
      logger.error(
        { err },
        "Socket error"
      );
    });
  });

  function start() {
    return new Promise((resolve) => {
      server.listen(socketPath, () => {
        resolve();
      });
    });
  }

  function close() {
    return new Promise((resolve) => {
      server.close(() => {
        try {
          if (existsSync(socketPath)) {
            unlinkSync(socketPath);
          }
        } catch (err) {
          logger.error(
            { err },
            "Failed to unlink socket"
          );
        }

        resolve();
      });
    });
  }

  return {
    server,
    start,
    close,
  };
}

export default createRpcServer;