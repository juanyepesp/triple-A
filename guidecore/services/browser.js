import { chromium } from "playwright";

function createBrowserService({ daemonState, commit }) {
  function bindPageEvents(page) {
    page.on("framenavigated", async () => {
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
        }
      );
    });

    page.on("load", async () => {
      commit(
        {
          pageInfo: {
            ...daemonState.pageInfo,
            url: page.url(),
            title: await page.title().catch(() => null),
            accessibilityTree: await page
              .ariaSnapshot({
                mode: "ai",
                boxes: true,
              })
              .catch(() => null),
          },
        },
        {
          fromAction: "browser.load",
          url: page.url(),
        }
      );
    });

    page.on("close", () => {
      commit(
        {
          page: null,
          context: null,
          browser: null,
          ready: false,
        },
        {
          fromAction: "browser.closed",
        }
      );
    });
  }

  async function ensureBrowser() {
    if (daemonState.browser) {
      return;
    }

    const browser = await chromium.launch({
      headless: false,
      args: ["--start-maximized"],
    });

    const context = await browser.newContext();
    const page = await context.newPage();

    daemonState.browser = browser;
    daemonState.context = context;
    daemonState.page = page;

    bindPageEvents(page);
  }

  async function start(url) {
    await ensureBrowser();

    await daemonState.page.goto(url, {
      waitUntil: "load",
    });

    commit(
      {
        ready: true,
        pageInfo: {
          ...daemonState.pageInfo,
          url: daemonState.page.url(),
          title: await daemonState.page.title().catch(() => null),
        },
      },
      {
        fromAction: "browser.start",
      }
    );
  }

  async function stop() {
    if (daemonState.browser) {
      await daemonState.browser.close();
    }

    commit(
      {
        ready: false,
        browser: null,
        context: null,
        page: null,

        pageInfo: {
          ...daemonState.pageInfo,
          url: null,
          title: null,
          accessibilityTree: null,
          screenshotPath: null,
        },
      },
      {
        fromAction: "browser.stop",
      }
    );
  }

  async function getAom() {
    if (!daemonState.page) {
      throw new Error("Browser is not running");
    }

    return daemonState.page.ariaSnapshot();
  }

  return {
    ensureBrowser,
    start,
    stop,
    getAom,
  };
}

export default createBrowserService;