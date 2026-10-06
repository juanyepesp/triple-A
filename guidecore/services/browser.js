import { chromium } from "playwright";

const LANDMARK_ROLES = new Set([
  "banner",
  "complementary",
  "contentinfo",
  "form",
  "main",
  "navigation",
  "region",
  "search",
]);

const HEADING_ROLES = new Set(["heading"]);
const LINK_ROLES = new Set(["link"]);

function getA11yStructure(node) {
  if (Array.isArray(node)) {
    return node.map(getA11yStructure);
  }

  if (!node || typeof node !== "object") {
    return null;
  }

  return {
    role: node.role ?? null,
    children: (node.children ?? []).map(getA11yStructure),
  };
}

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

function compactNode(node) {
  return {
    role: node.role ?? null,
    name: node.name ?? null,
    text: node.text ?? null,
    ref: node.ref ?? null,
    bounds: node.box ?? null, // TODO
    active: node.active === true,
  };
}

function compactNodeInScreenCoordinates(node, viewportLocation) {
  const compact = compactNode(node);

  if (!compact.bounds || !viewportLocation) {
    return compact;
  }

  return {
    ...compact,
    bounds: {
      ...compact.bounds,
      x:
        compact.bounds.x +
        viewportLocation.screenX,
      y:
        compact.bounds.y +
        viewportLocation.screenY,
    },
    coordinateSpace: "screen",
  };
}

function findNodesByRole(tree, roles) {
  const results = [];

  function visit(node) {
    if (Array.isArray(node)) {
      node.forEach(visit);
      return;
    }

    if (!node || typeof node !== "object") {
      return;
    }

    if (roles.has(node.role)) {
      results.push(compactNode(node));
    }

    for (const child of node.children ?? []) {
      visit(child);
    }
  }

  visit(tree);
  return results;
}

function findActivePath(tree) {
  function visit(node, ancestors) {
    if (Array.isArray(node)) {
      for (const child of node) {
        const result = visit(child, ancestors);
        if (result) {
          return result;
        }
      }
      return null;
    }

    if (!node || typeof node !== "object") {
      return null;
    }

    const path = [...ancestors, compactNode(node)];
    if (node.active === true) {
      return path;
    }

    for (const child of node.children ?? []) {
      const result = visit(child, path);
      if (result) {
        return result;
      }
    }

    return null;
  }

  return visit(tree, []) ?? [];
}

export function createBrowserService({ daemonState, commit, logger }) {
  let pageEventQueue = Promise.resolve();
  let a11yStructure = null;
  let cachedA11yElements = {
    landmarks: [],
    headings: [],
    links: [],
  };

  function resetA11yStructure() {
    a11yStructure = null;
    cachedA11yElements = {
      landmarks: [],
      headings: [],
      links: [],
    };
  }

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
        const accessibilityState = await collectNodesFromA11yTree();
        const viewportLocation = accessibilityState.viewportLocation;

        commit(
          {
            context: {
              page: {
                url: page.url(),
                title: await page.title().catch(() => null),
                viewportLocation,
              },
              browserFocus: accessibilityState.browserFocus,
              cursorPath: accessibilityState.cursorPath,
              a11y: {
                tree: accessibilityState.tree,
              },
              relevantNodes: accessibilityState.relevantNodes,
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
                viewportLocation: accessibilityState.viewportLocation,
              },
              browserFocus: accessibilityState.browserFocus,
              cursorPath: accessibilityState.cursorPath,
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
      resetA11yStructure();
      commit(
        {
          page: null,
          browserContext: null,
          browser: null,
          context: {
            ready: false,
            browserFocus: null,
            cursorPath: [],
            a11y: { tree: null },
            relevantNodes: {
              active: [],
              pressed: [],
              landmarks: [],
              headings: [],
              links: [],
            },
            page: {
              viewportLocation: null,
            },
            focusComparison: {
              VOCursorBrowserFocusAreSimilarEnough: null,
              similarityScore: null,
              textSimilarity: null,
              roleMatches: null,
              dimensionsSimilarity: null,
            },
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
    resetA11yStructure();
    await daemonState.page.goto(url, { waitUntil: "load" });

    await pageEventQueue;
    const accessibilityState = await collectNodesFromA11yTree();

    commit(
      {
        context: {
          ready: true,
          page: {
            url: daemonState.page.url(),
            title: await daemonState.page.title().catch(() => null),
            viewportLocation: accessibilityState.viewportLocation,
          },
          browserFocus: accessibilityState.browserFocus,
          cursorPath: accessibilityState.cursorPath,
          a11y: {
            tree: accessibilityState.tree,
          },
          relevantNodes: accessibilityState.relevantNodes,
        },
      },
      { fromAction: "browser.start" },
    );
  }

  async function stop() {
    resetA11yStructure();
    await daemonState.browser.close();

    commit(
      {
        context: {
          ready: false,
          page: {
            url: null,
            title: null,
            screenshotPath: null,
            viewportLocation: null,
          },
          a11y: {
            tree: null,
          },
          relevantNodes: {
            active: [],
            pressed: [],
            landmarks: [],
            headings: [],
            links: [],
          },
          browserFocus: null,
          focusComparison: {
            VOCursorBrowserFocusAreSimilarEnough: null,
            similarityScore: null,
            textSimilarity: null,
            roleMatches: null,
            dimensionsSimilarity: null,
          },
          cursorPath: [],
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
      coordinateSpace: "screen-origin-plus-viewport",
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
    const activeNodes = findNodesWhereFlagIsTrue(snapshot, "active");
    const nextA11yStructure = getA11yStructure(snapshot);
    const structureChanged =
      JSON.stringify(nextA11yStructure) !== JSON.stringify(a11yStructure);

    if (structureChanged) {
      cachedA11yElements = {
        landmarks: findNodesByRole(snapshot, LANDMARK_ROLES),
        headings: findNodesByRole(snapshot, HEADING_ROLES),
        links: findNodesByRole(snapshot, LINK_ROLES),
      };
      a11yStructure = nextA11yStructure;
    }
    const viewportLocation = await page.evaluate(() => ({
      screenX: window.screenX,
      screenY: window.screenY,
      devicePixelRatio: window.devicePixelRatio,
      coordinateSpace: "screen-origin-plus-viewport",
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    }));

    return {
      tree: snapshot,
      relevantNodes: {
        active: activeNodes, // knowing this is key, because any element on this list, if VO- space is pressed, thats the action to take.
        pressed: findNodesWhereFlagIsTrue(snapshot, "pressed"),
        ...cachedA11yElements,
      },
      cursorPath: findActivePath(snapshot),
      browserFocus: activeNodes[0]
        ? compactNodeInScreenCoordinates(activeNodes[0], viewportLocation)
        : null,
      viewportLocation,
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
