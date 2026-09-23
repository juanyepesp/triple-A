# Triple-A Accessibility Agent

A multimodal accessibility agent that uses a screen reader to navigate a website.

<!-- TODO maybe add a logo or more branding -->

## Prerequisites

- macOS with VoiceOver enabled
- Python 3.11 or later
- Node.js and npm
- An `OPENAI_API_KEY` environment variable
- `Guidecore` module (lives inside the repository, for now)


> [!NOTE]
> **Guidecore** is a node project that is implemented also as a part of this project. Right now, it lives inside the repository, but it may be de-coupled in the future, and extended to a screen-reader testing suite. It controls VoiceOver using a library named Guidepup, while orchestrating the runtime using Playwright.


## Installation

From the repository root:

```zsh
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd ../guidecore
npm install
npx playwright install chromium
```

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


## Recommendations

- Since testing on VoiceOver can be time consuming and resource intensive, privind a virtual environment such as a VM can be very useful
- My current setup is a macOS VM using UTM, to which I copy the files every time they chagne using a shell script that uses the fswatch command. And I execute the program connecting via SSH to the VM. To learn more on fswatch, take a look [here](https://emcrisostomo.github.io/fswatch/). The shell script lives on `watch.sh`, and is executable by using `sh watch.sh`
- This makes the tests run much more smoothly and faster.
- To debug each part of the graph, I made the following command available: `python -u main.py --step`. This only makes sense in this setup, where you can actually hit enter from an ssh connection terminal, and see the outputs on the VM.