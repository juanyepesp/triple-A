# Triple-A Accessibility Agent

An accessibility agent that uses LangGraph, Playwright, and macOS VoiceOver to navigate a website.

## Prerequisites

- macOS with VoiceOver enabled
- Python 3.11 or later
- Node.js and npm
- An `OPENAI_API_KEY` environment variable

## Installation

From the repository root:

```zsh
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cd ../guidepup
npm install
npx playwright install chromium
```

## Run

Use two terminals from the repository root.

**Terminal 1: start the Guidepup daemon**

```zsh
cd guidepup
npm start
```

This starts the RPC server at `/tmp/guidepup.sock`.

**Terminal 2: start the Python agent**

```zsh
cd agent
source venv/bin/activate
python main.py
```

When the test Chrome window opens, pause the agent and configure the VoiceOver hotspot:

1. Use VoiceOver to move to the web content until it announces “web content”.
2. Set that location as hotspot 1 with `VO + Shift + 1`.
