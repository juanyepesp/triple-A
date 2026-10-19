# Triple-A: Adaptive Accessibility Assessments

<!-- A multimodal accessibility agent that uses a screen reader to navigate a website. -->

<!-- TODO maybe add a logo or more branding -->
<!-- TODO explicar que hace cada cosa, que guidecore es el sistema principal -->

## Prerequisites

- macOS with VoiceOver enabled
- Python 3.11 or later
- Node.js and npm
- An `OPENAI_API_KEY` environment variable
- `Guidecore` module (lives inside the repository, for now)


> [!NOTE]
> **Guidecore** is a node project that is implemented also as a part of this project. Right now, it lives inside the repository, but it may be de-coupled in the future, and extended to a screen-reader testing suite. It controls VoiceOver using a library named Guidepup, while orchestrating the runtime using Playwright.
>
>
> Guidecore's browser service applies the configured vision impairment directly to the live page rendering. The person operating VoiceOver sees the same simulation that is captured for the Python agent, while interaction and replay continue to target the unmodified page DOM.


## Installation

From the repository root:

```zsh
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd ../guidecore
npm ci
npx playwright install chromium
npx @guidepup/setup setup
npx @guidepup/setup install
```

Install the Guidecore dependencies on the machine where the daemon will run.
Do not copy `guidecore/node_modules` between machines; native packages and
platform-specific Guidepup assets must be installed locally.

## Run

Use two terminals from the repository root.

**Terminal 1: start the Guidecore daemon**
```zsh
cd guidecore
npm start
```

This starts the RPC server at `/tmp/guidecore.sock`.

**Terminal 2: start the Python agent**

```zsh
cd agent
source venv/bin/activate
python main.py
```

When the test Chrome window opens, pause the agent and configure the VoiceOver hotspot:

1. Use VoiceOver to move to the web content until it announces “web content”.
2. Set that location as hotspot 1 with `VO + Shift + 1`.

Vision inspection reports are written as self-contained HTML files under
`agent/vision_outputs/`. Each report contains the exact rendered screenshot
sent to the model, the selected impairment, the screenshot hash, and the
model's description. The latest report path is also stored in the agent's
`vision` state as `report_path`.

## Review tasks side by side

To manually check whether a student's task is supported by the website, open the
first website and task/checklist in two side-by-side Google Chrome windows:

```zsh
python notebooks/review_tasks.py
```

The script reads `notebooks/data/website-task-bank.csv`, starts at row 1, and
places the website on the left and the task on the right. Use these commands
while reviewing:

- `n`: save edits if needed and move to the next task
- `p`: move to the previous task
- `e`: edit the task goal or the student's reported completion
- `s`: save all edits to the CSV
- `q`: quit, with a save prompt if there are unsaved edits

To start at a particular task:

```zsh
python notebooks/review_tasks.py --row 12
```

The CSV is read and written as UTF-8 (with optional UTF-8 BOM support), so
Spanish accents and other non-ASCII characters are preserved. Saving replaces
the CSV only after the complete temporary file has been written.

The default screen size is 1440x900. Override it when needed with
`--screen-width` and `--screen-height`. Chromium can be used instead of Chrome
with `--browser Chromium`. This reviewer is independent of the Guidecore daemon
and is intended for manual task-quality checking; it does not change the CSV.


## Recommendations

- Since testing on VoiceOver can be time consuming and resource intensive, providing a virtual environment such as a VM is the recommended alternative. 
- My current setup is a macOS VM using UTM, to which I copy the files every time they chagne using a shell script that uses the fswatch command. And I execute the program connecting via SSH to the VM. To learn more on fswatch, take a look [here](https://emcrisostomo.github.io/fswatch/). The shell script lives on `watch.sh`, and is executable by using `sh watch.sh`
- This makes the tests run much more smoothly and faster.
- To debug each part of the graph, I made the following command available: `python -u main.py --step`. This only makes sense in this setup, where you can actually hit enter from an ssh connection terminal, and see the outputs on the VM.