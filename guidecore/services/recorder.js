import {
  appendFileSync,
  closeSync,
  fsyncSync,
  mkdirSync,
  openSync,
} from "node:fs";
import { join } from "node:path";

function normalizeMetadata({ url, impairment }) {
  if (typeof url !== "string" || !url.trim()) {
    throw new Error("A URL is required to start a recording");
  }
  if (typeof impairment !== "string" || !impairment.trim()) {
    throw new Error("A vision impairment is required to start a recording");
  }
  return { url: url.trim(), impairment: impairment.trim() };
}

export function createRecorder({ recordingsDirectory, logger }) {
  let session = null;

  function write(entry) {
    if (!session) {
      return false;
    }
    appendFileSync(session.fd, `${JSON.stringify(entry)}\n`, "utf8");
    fsyncSync(session.fd);
    return true;
  }

  function start(metadata) {
    if (session) {
      throw new Error("A recording is already active");
    }
    const normalized = normalizeMetadata(metadata);
    mkdirSync(recordingsDirectory, { recursive: true });
    const startedAt = new Date().toISOString();
    const path = join(
      recordingsDirectory,
      `recording-${Date.now()}-${process.pid}.jsonl`,
    );
    const fd = openSync(path, "a");
    session = { fd, path, startedAt, ...normalized };
    write({
      type: "recording.started",
      timestamp: startedAt,
      url: session.url,
      impairment: session.impairment,
    });
    logger.info(
      { path, url: session.url, impairment: session.impairment },
      "Interaction recording started",
    );
    return { path, url: session.url, impairment: session.impairment };
  }

  function updateMetadata(metadata) {
    if (!session) {
      return;
    }
    if (typeof metadata.url === "string" && metadata.url.trim()) {
      session.url = metadata.url.trim();
    }
    if (typeof metadata.impairment === "string" && metadata.impairment.trim()) {
      session.impairment = metadata.impairment.trim();
    }
  }

  function record(event) {
    if (!session || !event || typeof event !== "object") {
      return false;
    }
    write({
      type: "interaction",
      timestamp: new Date().toISOString(),
      url: session.url,
      impairment: session.impairment,
      ...event,
    });
    return true;
  }

  function recordAgentAction({ method, params, source = "agent" }) {
    const parameters = params ?? {};
    if (method === "browser.start") {
      updateMetadata(parameters);
    }
    if (method.startsWith("browser.") || method.startsWith("voiceover.")) {
      record({
        source,
        method,
        parameters,
      });
    }
  }

  function stop() {
    if (!session) {
      throw new Error("No recording is active");
    }
    const finishedAt = new Date().toISOString();
    const result = {
      path: session.path,
      url: session.url,
      impairment: session.impairment,
      startedAt: session.startedAt,
      finishedAt,
    };
    write({ type: "recording.stopped", timestamp: finishedAt });
    closeSync(session.fd);
    session = null;
    return result;
  }

  function status() {
    if (!session) {
      return { active: false };
    }
    return {
      active: true,
      path: session.path,
      url: session.url,
      impairment: session.impairment,
      startedAt: session.startedAt,
    };
  }

  function shutdown() {
    if (session) {
      stop();
    }
  }

  return { start, stop, status, record, recordAgentAction, shutdown };
}