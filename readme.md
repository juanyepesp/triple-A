# Triple-A Accessibility Agent

# How to install

- Create a python venv and install all requirements.txt. On the root
```zsh
cd agent
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

- Install node and node packages. On the root
```zsh
cd guidepup
npm install
npx playwright install chromium
npm start
```

# Usage

Create two terminals. First initialise the RPC socket on the guidepup daemon. On the root

```
cd guidepup
node server.js
```

When Google Chrome for testing opens, you need to interrupt execution and directly add this keyboard shortcut. Using voiceover, navigate directly to the web content (that is until you hear "web content") and set the hotspot to 1. That is by pressing VO + shift + 1