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
            context: {
              page: {
                url: page.url(),
                title: await page.title().catch(() => null),
              },
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
        const accessibilityState = await collectNodesFromA11yTree();

        commit(
          {
            context: {
              page: {
                url: page.url(),
                title: await page.title().catch(() => null),
              },
              a11y: {
                tree: accessibilityState.tree,
              },
              relevantNodes: accessibilityState.relevantNodes,
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
          browserContext: null,
          browser: null,
          context: {
            ready: false,
          },
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
    daemonState.browserContext = await daemonState.browser.newContext();
    daemonState.page = await daemonState.browserContext.newPage();
    bindPageEvents(daemonState.page);
  }

  async function start(url) {
    await ensureBrowser();
    await daemonState.page.goto(url, { waitUntil: "load" });

    await pageEventQueue;

    commit(
      {
        context: {
          ready: true,
          page: {
            url: daemonState.page.url(),
            title: await daemonState.page.title().catch(() => null),
          },
        },
      },
      { fromAction: "browser.start" },
    );
  }

  async function stop() {
    await daemonState.browser.close();

    commit(
      {
        context: {
          ready: false,
          page: {
            url: null,
            title: null,
            screenshotPath: null,
          },
          a11y: {
            tree: null,
          },
          relevantNodes: {
            active: [],
            pressed: [],
          },
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

  async function collectNodesFromA11yTree() {
    const page = daemonState.page;

    if (!page) {
      throw new Error(
        "Cannot collect accessibility state because no browser page is active",
      );
    }

    const snapshot = await ariaSnapshot();

    return {
      tree: snapshot,
      relevantNodes: {
        active: findNodesWhereFlagIsTrue(snapshot, "active"), // knowing this is key, because any element on this list, if VO- space is pressed, thats the action to take.
        pressed: findNodesWhereFlagIsTrue(snapshot, "pressed"),

        // ? maybe in the future if they are useful
        // selected: findNodesWhereFlagIsTrue(snapshot, "selected"),
        // checked: findNodesWhereFlagIsTrue(snapshot, "checked"),
        // expanded: findNodesWhereFlagIsTrue(snapshot, "expanded"),
        // level: findNodesWhereFlagIsTrue(snapshot, "level"),
      },
    };
  }

  async function activeNodes() {
    const { relevantNodes } = await collectNodesFromA11yTree();

    return [
      relevantNodes.active,
      relevantNodes.pressed,
      // accessibilityNodes.selected,
      // accessibilityNodes.checked,
      // accessibilityNodes.expanded,
      // accessibilityNodes.level,
    ];
  }

  return {
    start,
    stop,
    viewportLocation,
    ariaSnapshot,
    collectNodesFromA11yTree,
    activeNodes,
    getPage: () => daemonState.page,
  };
}
