import { chromium } from "playwright";

const IMPAIRMENT_NAMES = new Set([
  "none",
  "original",
  "blur",
  "low_vision",
  "protanopia",
  "deuteranopia",
  "tritanopia",
  "tunnel_vision",
]);

const COLOR_VISION_MATRICES = {
  protanopia: [
    [0.567, 0.433, 0],
    [0.558, 0.442, 0],
    [0, 0.242, 0.758],
  ],
  deuteranopia: [
    [0.625, 0.375, 0],
    [0.7, 0.3, 0],
    [0, 0.3, 0.7],
  ],
  tritanopia: [
    [0.95, 0.05, 0],
    [0, 0.433, 0.567],
    [0, 0.475, 0.525],
  ],
};

function normalizeImpairment(impairment) {
  return String(impairment ?? "none")
    .toLowerCase()
    .replaceAll("-", "_")
    .replaceAll(" ", "_");
}

function validateImpairment(impairment) {
  const normalized = normalizeImpairment(impairment);
  if (!IMPAIRMENT_NAMES.has(normalized)) {
    throw new Error(
      `Unsupported impairment ${impairment}. Use none, blur, low_vision, protanopia, deuteranopia, tritanopia, or tunnel_vision.`,
    );
  }
  return normalized;
}

function colorMatrixValues(matrix) {
  return [
    ...matrix.flatMap((row) => [...row, 0, 0]),
    0,
    0,
    0,
    1,
    0,
  ].join(" ");
}

function visionFilterStyles(impairment) {
  const colorMatrix = COLOR_VISION_MATRICES[impairment];
  const pageFilter = colorMatrix
    ? "filter: url(#guidecore-vision-color-filter) !important;"
    : impairment === "blur" || impairment === "low_vision"
      ? "filter: blur(5px) !important;"
      : "";
  const tunnelOverlay =
    impairment === "tunnel_vision"
      ? `
#guidecore-vision-tunnel {
  position: fixed !important;
  inset: 0 !important;
  z-index: 2147483647 !important;
  pointer-events: none !important;
  background: radial-gradient(
    ellipse 33.333% 33.333% at center,
    transparent 0 99%,
    black 100%
  ) !important;
}`
      : "";

  return `
html { ${pageFilter} }
#guidecore-vision-tunnel { display: none; }
${tunnelOverlay}
`;
}

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
  let visionImpairment = "none";

  async function applyVisionFilter() {
    const page = daemonState.page;
    if (!page) {
      throw new Error("Cannot apply vision filter because no browser page is active");
    }

    const impairment = visionImpairment;
    const matrix = COLOR_VISION_MATRICES[impairment];
    await page.evaluate(
      ({ impairment, matrix, styles }) => {
        document
          .getElementById("guidecore-vision-filter")
          ?.remove();
        document
          .getElementById("guidecore-vision-filter-defs")
          ?.remove();
        document
          .getElementById("guidecore-vision-tunnel")
          ?.remove();

        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.id = "guidecore-vision-filter-defs";
        svg.setAttribute("aria-hidden", "true");
        svg.style.position = "fixed";
        svg.style.width = "0";
        svg.style.height = "0";
        svg.innerHTML = matrix
          ? `<filter id="guidecore-vision-color-filter"><feColorMatrix type="matrix" values="${matrix}" /></filter>`
          : "";
        document.documentElement.appendChild(svg);

        const style = document.createElement("style");
        style.id = "guidecore-vision-filter";
        style.textContent = styles;
        document.head.appendChild(style);

        if (impairment === "tunnel_vision") {
          const overlay = document.createElement("div");
          overlay.id = "guidecore-vision-tunnel";
          overlay.setAttribute("aria-hidden", "true");
          document.body.appendChild(overlay);
        }
      },
      {
        impairment,
        matrix: matrix ? colorMatrixValues(matrix) : null,
        styles: visionFilterStyles(impairment),
      },
    );
  }
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
        await applyVisionFilter();
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

  async function start(url, impairment = "none") {
    const normalizedImpairment = validateImpairment(impairment);
    await ensureBrowser();
    visionImpairment = normalizedImpairment;
    resetA11yStructure();
    await daemonState.page.goto(url, { waitUntil: "load" });
    await applyVisionFilter();

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

  async function captureScreenshot(outputPath) {
    await daemonState.page.screenshot({ path: outputPath });
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
    captureScreenshot,
    ariaSnapshot,
    collectNodesFromA11yTree,
    activeNodes,
    getPage: () => daemonState.page,
  };
}
