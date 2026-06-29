---
name: happycapy-slack
description: "Connect HappyCapy AI agent to Slack. Messages to the bot in any Slack channel get answered by HappyCapy with full tool access — run code, search web, create files, use skills. No public URL needed (Socket Mode). Use when user wants Slack bot, connect Slack, HappyCapy on Slack, or says /slack."
---

# HappyCapy Slack

Connect the HappyCapy AI agent to Slack via Socket Mode — no public URL required. Every message sent to the bot (DM or @mention in a channel) gets answered by a full HappyCapy agent with access to all tools: Bash, file operations, web search, image/video generation, and every installed skill.

## Launch Instructions

When this skill is triggered, follow these steps IN ORDER:

### Step 1: Install Dependencies (first time only)

Check if `slack-bolt` is installed. Run:

```bash
bash ~/.claude/skills/happycapy-slack/scripts/setup.sh
```

### Step 2: Create a Slack App (first time only)

Check if `~/.happycapy-slack/config.json` exists. If NOT, walk the user through app creation, then run the setup wizard.

#### Slack App Creation (exact steps)

Tell the user to follow these steps at **https://api.slack.com/apps**:

**A. Create the App**
1. Click **"Create New App"** → choose **"From scratch"**
2. Enter a name (e.g. "HappyCapy") and select your workspace
3. Click **"Create App"**

**B. Enable Socket Mode**
1. In the left sidebar, click **"Socket Mode"** (under Settings)
2. Toggle **"Enable Socket Mode"** to ON
3. When prompted to create an App-Level Token:
   - Token name: `happycapy-socket`
   - Scope: `connections:write`
   - Click **"Generate"**
4. Copy the token — it starts with **`xapp-`** — save it somewhere

**C. Add Bot Scopes**
1. In the left sidebar, click **"OAuth & Permissions"**
2. Scroll to **"Bot Token Scopes"** and click **"Add an OAuth Scope"**
3. Add all of these scopes:
   - `app_mentions:read` — see when the bot is @mentioned
   - `chat:write` — send messages
   - `channels:history` — read channel message history
   - `im:history` — read DM history
   - `im:read` — see DMs
   - `im:write` — open DM conversations
   - `reactions:write` — add loading indicator emoji

**D. Enable Events**
1. In the left sidebar, click **"Event Subscriptions"**
2. Toggle **"Enable Events"** to ON
3. Under **"Subscribe to bot events"**, add:
   - `message.im` — direct messages to the bot
   - `app_mention` — @mentions in channels

**E. Install to Workspace**
1. In the left sidebar, click **"OAuth & Permissions"**
2. Click **"Install to Workspace"** → click **"Allow"**
3. Copy the **Bot User OAuth Token** — it starts with **`xoxb-`**

You now have two tokens:
- App-Level Token: `xapp-...` (Socket Mode)
- Bot Token: `xoxb-...` (sending messages, reading events)

### Step 3: Interactive Setup Wizard

After the user has their tokens, use AskUserQuestion to gather credentials and access settings.

#### Question 1: Tokens

Use AskUserQuestion:
- header: "Slack Setup — Tokens"
- question: "Paste your two Slack tokens below. Bot token starts with xoxb- and App-Level token starts with xapp-. Enter them as: xoxb-TOKEN xapp-TOKEN (separated by a space, or on two lines)."
- options:
  - "I have both tokens ready"
  - "I need help finding my tokens" — explain: Bot token is at OAuth & Permissions; App-Level token is at Settings > Basic Information > App-Level Tokens
- multiSelect: false

Parse the user's text input to extract both tokens.

#### Question 2: Access and workspace name

Use AskUserQuestion:
- header: "Slack Setup — Access"
- question: "Who should be allowed to use the bot, and what's your Slack workspace name? (Workspace name shown in top-left of Slack, e.g. 'MyCompany')"
- options:
  - "Everyone in the workspace (Recommended)" — allowed_users: []
  - "Only specific people" — follow up asking for Slack User IDs (found in member profiles)
  - "Just me (admin only)" — follow up asking for the user's Slack User ID
- multiSelect: false

#### Question 3 (conditional): Specific User IDs

If user chose "Only specific people" or "Just me", ask:
- header: "Slack Setup — Allowed Users"
- question: "Paste the Slack User IDs of people who can use the bot. These look like U012AB3CD. Find them at: Slack → click a member's name → View full profile → three-dot menu → Copy member ID."
- options: (free text via "Other")
- multiSelect: false

Parse comma- or space-separated IDs.

#### Save config

After gathering all required fields, save the config:

```python
import json, os
from pathlib import Path

config_dir = Path.home() / ".happycapy-slack"
config_dir.mkdir(parents=True, exist_ok=True)
config_dir.chmod(0o700)

config = {
    "bot_token": "<xoxb-... from user>",
    "app_token": "<xapp-... from user>",
    "workspace": "<workspace name from user>",
    "allowed_users": [],            # [] = everyone; or ["U012AB3CD", "U987ZY6WX"]
    "model": "claude-sonnet-4-6",
    "max_history": 20,
    "reply_in_thread": True,
    "log_level": "INFO"
}

config_path = config_dir / "config.json"
config_path.write_text(json.dumps(config, indent=2))
config_path.chmod(0o600)
print("Config saved.")
```

Then confirm back to the user with a summary:
```
Your Slack bot is configured:
- Workspace: <name>
- Access: Everyone / Specific users
- Model: claude-sonnet-4-6
- Thread replies: ON (keeps channels clean)
- History: 20 messages per thread

Starting the bridge now...
```

### Step 4: Start the Bridge

```bash
bash ~/.claude/skills/happycapy-slack/scripts/start.sh daemon
```

Daemon management:
```bash
bash ~/.claude/skills/happycapy-slack/scripts/start.sh status    # Check if running
bash ~/.claude/skills/happycapy-slack/scripts/start.sh stop      # Stop
bash ~/.claude/skills/happycapy-slack/scripts/start.sh restart   # Restart
```

Logs:
```bash
tail -f ~/.happycapy-slack/bridge.log
```

### Step 5: Test the Bot

Tell the user:
1. **DM the bot**: In Slack, find your bot under Apps or search its name → send any message
2. **@mention in channel**: In any channel the bot is in, type `@YourBotName what's 2+2?`
3. The bot will add a ⏳ loading indicator, think, then reply in the same thread

### Step 6: Confirm Connection

Monitor the bridge log. When you see `Connected to Slack via Socket Mode`, tell the user the bot is live.

---

## Daemon Management

The daemon provides continuous operation:

- **PID tracking** at `~/.happycapy-slack/daemon.pid`
- **Auto-restart** on crash with exponential backoff (3s to 120s)
- **Log file** at `~/.happycapy-slack/bridge.log` (rotated at 10MB)
- **Graceful shutdown** via SIGTERM
- Maximum 50 restart attempts before giving up

```bash
# All daemon commands
bash ~/.claude/skills/happycapy-slack/scripts/start.sh daemon    # Start 24/7
bash ~/.claude/skills/happycapy-slack/scripts/start.sh stop      # Stop daemon
bash ~/.claude/skills/happycapy-slack/scripts/start.sh restart   # Restart daemon
bash ~/.claude/skills/happycapy-slack/scripts/start.sh status    # Show status
bash ~/.claude/skills/happycapy-slack/scripts/start.sh foreground  # Debug mode
```

---

## How It Works

```
Slack user → @mention or DM → Slack servers → Socket Mode WebSocket (outbound from bridge)
   → bridge.py receives event → loads thread history → builds system prompt
   → calls: claude --print --model claude-sonnet-4-6
   → Claude responds with full tool access (Bash, files, web search, all skills)
   → bridge formats markdown → mrkdwn → replies in Slack thread
```

1. The bridge opens an outbound WebSocket to Slack (no public URL needed)
2. Slack pushes events over the socket when the bot is mentioned or DM'd
3. The bridge calls `claude --print` (Claude Code CLI) with the conversation as input
4. Claude has full HappyCapy tool access — it can run code, search the web, create files, use skills
5. The response is converted from Markdown to Slack mrkdwn and posted back in a thread

---

## Conversation History

History is stored per-thread (not per-channel or per-user globally):

- **Key**: `{user_id}_{thread_ts}` — each Slack thread has its own conversation
- **Storage**: `~/.happycapy-slack/history/{user_id}_{thread_ts}.json`
- **Max**: 20 messages per thread (configurable via `max_history`)
- **DMs**: use `{user_id}_dm` as the thread key (DMs don't have thread_ts)

---

## Troubleshooting

**Bot doesn't respond at all**
- Check logs: `tail -50 ~/.happycapy-slack/bridge.log`
- Verify the bridge is running: `bash ~/.claude/skills/happycapy-slack/scripts/start.sh status`
- Make sure Socket Mode is enabled in your Slack app settings

**Token errors (`invalid_auth` or `not_authed`)**
- Bot token must start with `xoxb-` and belong to the installed workspace
- App-level token must start with `xapp-` (not `xoxb-`)
- Re-install the app to workspace if tokens were regenerated

**Socket Mode not connecting (`SocketModeClient failed`)**
- Go to api.slack.com/apps → your app → Socket Mode → verify it's toggled ON
- The `connections:write` scope must be on the App-Level Token
- Try regenerating the app-level token

**Bot responds but events aren't received**
- Verify Event Subscriptions are enabled
- Check that `message.im` and `app_mention` are in "Subscribe to bot events"
- The bot must be added to the channel to receive `app_mention` events

**"Not allowed" response to messages**
- Your Slack User ID is not in `allowed_users`
- Set `allowed_users: []` in `~/.happycapy-slack/config.json` to allow everyone
- Or add your User ID (e.g. `U012AB3CD`) to the list

**Rate limits (Slack 429 errors)**
- Slack allows ~1 message per second per channel
- The bridge handles rate limits automatically with retry logic
- For high-volume usage, consider adding a queue

**Claude CLI not found**
- Verify: `which claude` — should return a path
- The bridge calls `claude --print`; HappyCapy's Claude Code CLI must be on PATH
