import { chromium } from "playwright";

function findNodesWhereFlagIsTrue(tree, flag) {
  const results = [];

  function visit(node) {
    if (Array.isArray(node)) {
      node.forEach(visit);
      return;
    }

    if (!node || typeof node !== "object") {
      return;
    }

    if (node[flag] === true) {
      results.push(node);
    }

    for (const child of node.children ?? []) {
      visit(child);
    }
  }

  visit(tree);
  return results;
}

export function createBrowserService({ daemonState, commit, logger }) {
  let pageEventQueue = Promise.resolve();

  function bindPageEvents(page) {
    function enqueuePageEvent(task) {
      pageEventQueue = pageEventQueue
        .then(task)
        .catch((err) => {
          logger.error({ err }, "Browser event handling failed");
        });
    }

    page.on("framenavigated", async () => {
      enqueuePageEvent(async () => {
        commit(
          {
            pageInfo: {
              ...daemonState.pageInfo,
              url: page.url(),
              title: await page.title().catch(() => null),
            },
          },
          {
            fromAction: "browser.navigation",
            url: page.url(),
          },
        );
      });
    });

    page.on("load", async () => {
      enqueuePageEvent(async () => {
        commit(
          {
            pageInfo: {
              ...daemonState.pageInfo,
              url: page.url(),
              title: await page.title().catch(() => null),
              accessibilityTree: await page
                .ariaSnapshot({ mode: "ai", boxes: true })
                .catch(() => null),
            },
          },
          {
            fromAction: "browser.load",
            url: page.url(),
          },
        );
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
        { fromAction: "browser.closed" },
      );
    });
  }

  async function ensureBrowser() {
    if (daemonState.browser) {
      return;
    }

    daemonState.browser = await chromium.launch({
      headless: false,
      args: ["--start-maximized"],
    });
    daemonState.context = await daemonState.browser.newContext();
    daemonState.page = await daemonState.context.newPage();
    bindPageEvents(daemonState.page);
  }

  async function start(url) {
    await ensureBrowser();
    await daemonState.page.goto(url, { waitUntil: "load" });

    await pageEventQueue;

    commit(
      {
        ready: true,
        pageInfo: {
          ...daemonState.pageInfo,
          url: daemonState.page.url(),
          title: await daemonState.page.title().catch(() => null),
        },
      },
      { fromAction: "browser.start" },
    );
  }

  async function stop() {
    await daemonState.browser.close();

    commit(
      {
        ready: false,
        pageInfo: {
          ...daemonState.pageInfo,
          url: null,
          title: null,
          accessibilityTree: null,
          screenshotPath: null,
        },
      },
      { fromAction: "browser.stop" },
    );
  }

  async function viewportLocation() {
    return daemonState.page.evaluate(() => ({
      screenX: window.screenX,
      screenY: window.screenY,
      devicePixelRatio: window.devicePixelRatio,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    }));
  }

  async function ariaSnapshot() {
    return daemonState.page.ariaSnapshotJSON({
      mode: "ai",
      boxes: true,
    });
  }

  async function activeNodes() {
    const snapshot = await ariaSnapshot();
    return [
      findNodesWhereFlagIsTrue(snapshot, "active"),
      findNodesWhereFlagIsTrue(snapshot, "pressed"),
      findNodesWhereFlagIsTrue(snapshot, "selected"),
      findNodesWhereFlagIsTrue(snapshot, "checked"),
      findNodesWhereFlagIsTrue(snapshot, "expanded"),
      findNodesWhereFlagIsTrue(snapshot, "level"),
    ];
  }

  return {
    start,
    stop,
    viewportLocation,
    ariaSnapshot,
    activeNodes,
    getPage: () => daemonState.page,
  };
}
