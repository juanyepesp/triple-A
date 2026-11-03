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
python scripts/recorder.py \
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

Commands are sent through the existing GuideCore Unix socket, so Guidepup executes them in the VM. Use `--debug-keys` to inspect the keys received by the VM. Press `Ctrl+C` to stop VoiceOver and the browser.

```zsh
python scripts/recorder.py \
  --url "https://example.com" \
  --impairment low_vision \
  --debug-keys
```

If an arrow combination does not execute, inspect the sequence printed by `--debug-keys`; terminal emulators can use different Shift+arrow sequences.

**Terminal 2: start the Python agent**

```zsh
cd agent
source venv/bin/activate
python main.py
```

Vision inspection reports are written as self-contained HTML files under `agent/vision_outputs/`. Each report contains the exact rendered screenshot sent to the model, the selected impairment, the screenshot hash, and the model's description. The latest report path is also stored in the agent's `vision` state as `report_path`.

## Recommendations

- Since testing on VoiceOver can be time consuming and resource intensive, providing a virtual environment such as a VM is the recommended alternative. 
- My current setup is a macOS VM using UTM, to which I copy the files every time they chagne using a shell script that uses the fswatch command. And I execute the program connecting via SSH to the VM. To learn more on fswatch, take a look [here](https://emcrisostomo.github.io/fswatch/). The shell script lives on `watch.sh`, and is executable by using `sh watch.sh`
- This makes the tests run much more smoothly and faster.
- To debug each part of the graph, I made the following command available: `python -u main.py --step`. This only makes sense in this setup, where you can actually hit enter from an ssh connection terminal, and see the outputs on the VM.