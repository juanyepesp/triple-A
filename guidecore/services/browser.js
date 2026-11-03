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

// Overlays use backdrop-filter / gradients instead of a filter on <html>, because a filter on the
// root turns it into the containing block of position:fixed elements (the overlay would scroll,
// be blurred itself and be sized to the whole document instead of the viewport).
function visionFilterStyles(impairment) {
  const overlay = (css) => `
#guidecore-vision-overlay {
  position: fixed !important;
  inset: 0 !important;
  width: 100vw !important;
  height: 100vh !important;
  z-index: 2147483647 !important;
  pointer-events: none !important;
  display: block !important;
  ${css}
}`;
  if (COLOR_VISION_MATRICES[impairment]) {
    return "html { filter: url(#guidecore-vision-color-filter) !important; }";
  }
  if (impairment === "blur" || impairment === "low_vision") {
    return overlay("backdrop-filter: blur(5px) !important; -webkit-backdrop-filter: blur(5px) !important;");
  }
  if (impairment === "tunnel_vision") {
    return overlay(
      `background: radial-gradient(ellipse 33.333vw 33.333vh at var(--gx, 50%) var(--gy, 50%), transparent 0 99%, black 100%) !important;
  backdrop-filter: blur(2px) !important; -webkit-backdrop-filter: blur(2px) !important;`,
    );
  }
  return "";
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
    bounds: node.box ?? null,
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
        window.__guidecoreVisionObserver?.disconnect();
        const ids = [
          "guidecore-vision-filter",
          "guidecore-vision-filter-defs",
          "guidecore-vision-overlay",
        ];

        const install = () => {
          const root = document.documentElement;
          if (!root) return;
          const needsOverlay = ["blur", "low_vision", "tunnel_vision"].includes(impairment);

          if (!document.getElementById("guidecore-vision-filter")) {
            const style = document.createElement("style");
            style.id = "guidecore-vision-filter";
            style.textContent = styles;
            root.appendChild(style);
          }
          if (matrix && !document.getElementById("guidecore-vision-filter-defs")) {
            const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
            svg.id = "guidecore-vision-filter-defs";
            svg.setAttribute("aria-hidden", "true");
            svg.style.cssText = "position:fixed;width:0;height:0";
            svg.innerHTML = `<filter id="guidecore-vision-color-filter"><feColorMatrix type="matrix" values="${matrix}" /></filter>`;
            root.appendChild(svg);
          }
          if (needsOverlay && !document.getElementById("guidecore-vision-overlay")) {
            const overlay = document.createElement("div");
            overlay.id = "guidecore-vision-overlay";
            overlay.setAttribute("aria-hidden", "true");
            root.appendChild(overlay);
            window.__guidecoreApplyGaze?.();
          }
        };

        window.__guidecoreApplyGaze = () => {
          const overlay = document.getElementById("guidecore-vision-overlay");
          const gaze = window.__guidecoreGaze;
          if (!overlay) return;
          overlay.style.setProperty("--gx", gaze ? `${gaze.x}px` : "50%");
          overlay.style.setProperty("--gy", gaze ? `${gaze.y}px` : "50%");
        };

        ids.forEach((id) => document.getElementById(id)?.remove());
        install();
        window.__guidecoreApplyGaze();
        // SPAs and hydration can wipe our nodes; put them back.
        const observer = new MutationObserver(() => {
          if (ids.some((id) => !document.getElementById(id) && (id !== "guidecore-vision-filter-defs" || matrix) && (id !== "guidecore-vision-overlay" || ["blur", "low_vision", "tunnel_vision"].includes(impairment)))) {
            install();
          }
        });
        observer.observe(document.documentElement, { childList: true });
        window.__guidecoreVisionObserver = observer;
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

    page.on("domcontentloaded", () => {
      applyVisionFilter().catch(() => {});
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

  // The screenshot is what the vision model sees, so mark the focused element in it: the VoiceOver
  // cursor (screen coordinates), falling back to the DOM-focused element. The marker is removed
  // right after the capture so it never affects the page.
  async function captureScreenshot(outputPath, voiceoverBounds = null) {
    const page = daemonState.page;
    const marked = await page
      .evaluate((bounds) => {
        const chromeHeight = window.outerHeight - window.innerHeight;
        let rect = null;
        if (bounds && bounds.width > 0 && bounds.height > 0) {
          rect = {
            x: bounds.x - window.screenX,
            y: bounds.y - window.screenY - chromeHeight,
            width: bounds.width,
            height: bounds.height,
          };
        }
        const inView = (r) =>
          r && r.width > 0 && r.height > 0 &&
          r.x + r.width > 0 && r.y + r.height > 0 && r.x < window.innerWidth && r.y < window.innerHeight;
        if (!inView(rect)) {
          const el = document.activeElement;
          rect = el && el !== document.body && el !== document.documentElement
            ? el.getBoundingClientRect()
            : null;
        }
        if (!inView(rect)) return false;
        const box = document.createElement("div");
        box.id = "guidecore-focus-marker";
        box.style.cssText = [
          "position:fixed", "pointer-events:none", "z-index:2147483647", "box-sizing:border-box",
          `left:${rect.x - 3}px`, `top:${rect.y - 3}px`,
          `width:${rect.width + 6}px`, `height:${rect.height + 6}px`,
          "border:3px solid #ff00ff", "outline:2px solid #ffffff", "border-radius:3px",
        ].join(";");
        document.documentElement.appendChild(box);
        return true;
      }, voiceoverBounds)
      .catch(() => false);
    try {
      await page.screenshot({ path: outputPath });
    } finally {
      if (marked) {
        await page.evaluate(() => document.getElementById("guidecore-focus-marker")?.remove()).catch(() => {});
      }
    }
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

  // Tunnel vision follows the user's gaze: the VoiceOver cursor (screen coordinates), falling back
  // to the DOM-focused element, then to the page centre.
  async function setGaze(voiceoverBounds = null) {
    const page = daemonState.page;
    if (!page || visionImpairment !== "tunnel_vision") {
      return;
    }
    await page.evaluate((bounds) => {
      const chromeHeight = window.outerHeight - window.innerHeight;
      const center = (rect) => ({
        x: rect.x + rect.width / 2,
        y: rect.y + rect.height / 2,
      });
      const visible = (point) =>
        point.x >= 0 && point.y >= 0 && point.x <= window.innerWidth && point.y <= window.innerHeight;

      let gaze = null;
      if (bounds && bounds.width > 0 && bounds.height > 0) {
        const point = center({
          x: bounds.x - window.screenX,
          y: bounds.y - window.screenY - chromeHeight,
          width: bounds.width,
          height: bounds.height,
        });
        if (visible(point)) gaze = point;
      }
      if (!gaze) {
        const el = document.activeElement;
        if (el && el !== document.body && el !== document.documentElement) {
          const point = center(el.getBoundingClientRect());
          if (visible(point)) gaze = point;
        }
      }
      window.__guidecoreGaze = gaze;
      window.__guidecoreApplyGaze?.();
    }, voiceoverBounds).catch(() => {});
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
    setGaze,
    getPage: () => daemonState.page,
  };
}
