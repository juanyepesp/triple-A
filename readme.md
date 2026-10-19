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

# In another terminal, install the optional human interaction recorder
python -m pip install -r scripts/requirements.txt
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

### Control VoiceOver remotely

When using a VM or SSH, the keyboard helper can translate ordinary keyboard input into GuideCore VoiceOver commands. It does not require pressing the VoiceOver `Control+Option` modifier:

```zsh
cd guidecore
python scripts/keystrokes.py \
  --url "https://example.com" \
  --impairment low_vision
```

The helper starts the GuideCore browser and VoiceOver instances, then maps:

- `Right Arrow` to `voiceover.next`
- `Left Arrow` to `voiceover.previous`
- `Shift+Down Arrow` to `voiceover.startInteracting`
- `Shift+Up Arrow` to `voiceover.stopInteracting`
- `Space` to the focused item's default action
- `h` / `H` to next/previous heading
- `m` / `M` to next/previous landmark
- `l` / `L` to next/previous link
- `w` to return to web content
- `e` or `Escape` to escape the current VoiceOver context
- `t` to enter text for `voiceover.type`

Commands are sent through the existing GuideCore Unix socket, so Guidepup executes them in the VM. Use `--debug-keys` to inspect the keys received by the VM. Navigation commands use a low-latency path without waiting for speech
capture or a screenshot refresh, and repeated pending arrow commands are
coalesced so stale navigation does not build up. Press `Ctrl+C` to stop
VoiceOver and the browser.

The controller automatically starts an interaction recording with the supplied
URL and impairment. Every resulting VoiceOver RPC action is recorded in the
JSONL file with `source: "human"` for controller commands or
`source: "agent"` for Python-agent commands; raw terminal input is not
persisted. Agent and human actions can therefore appear in the same recording.
The output path is printed when recording starts and when it is finalized.

LangGraph nodes use a bounded retry policy: a failed node is retried up to
three total attempts with exponential backoff (capped at four seconds),
including the VoiceOver tool node. Existing model-output retries remain in
place.

The Python agent also owns its recording when it starts a run without an
existing recording. It finalizes the VoiceOver/browser session and writes the
`recording.stopped` entry on normal completion, `Ctrl+C`, `SIGTERM`, and
uncaught Python errors. If a human controller already owns the recording, the
agent adds its actions to that recording but does not stop it. Each JSONL entry
is flushed to disk immediately, so completed interactions remain available even
if the agent process is terminated before cleanup can run, such as with
`SIGKILL`.

The controller reads the SSH terminal's stdin rather than using a global
keyboard listener, so it does not depend on macOS Input Monitoring or
VoiceOver exposing its `Control+Option` events. Run it from an interactive SSH
terminal. Use debug mode to inspect the terminal escape sequences:

```zsh
python scripts/keystrokes.py \
  --url "https://example.com" \
  --impairment low_vision \
  --debug-keys
```

If an arrow combination does not execute, inspect the sequence printed by
`--debug-keys`; terminal emulators can use different Shift+arrow sequences.

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