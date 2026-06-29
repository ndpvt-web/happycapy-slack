# HappyCapy Slack Skill

Connect your HappyCapy AI agent to Slack via Socket Mode. Once set up, @mentions and DMs in your Slack workspace are answered by Claude with full HappyCapy tool access — Bash, file ops, web search, image generation, 300,000+ Skills.

## What This Does

Every message sent to the bot (DM or @mention in a channel) gets answered by a full HappyCapy agent. The bridge uses Slack's Socket Mode WebSocket — no public URL required. Replies are always posted in-thread to keep channels clean. Each Slack thread has its own isolated conversation history.

## Requirements

- HappyCapy sandbox (happycapy.ai)
- Slack app with Bot Token (`xoxb-`) and App-Level Token (`xapp-`)
- Python 3.11+ (pre-installed on HappyCapy)

## Install as HappyCapy Skill

```bash
git clone https://github.com/ndpvt-web/happycapy-slack ~/.claude/skills/happycapy-slack
```

Then in HappyCapy, say: "connect Slack" or "/slack"

## File Structure

```
SKILL.md              — Setup wizard and usage instructions
scripts/
  setup.sh            — One-time dependency install (slack-bolt, slackify-markdown)
  bridge.py           — Main bridge process (Socket Mode → claude --print)
  start.sh            — Start/stop/status/restart daemon manager (with auto-restart)
  stop.sh             — Stop convenience wrapper
references/
  config-schema.md    — All config fields documented
```

## Architecture

```
Slack user → @mention or DM → Slack servers → Socket Mode WebSocket (outbound from bridge)
   → bridge.py receives event → loads thread history → builds system prompt
   → calls: claude --print --model claude-sonnet-4-6
   → Claude responds with full tool access (Bash, files, web search, all skills)
   → bridge formats markdown → mrkdwn → replies in Slack thread
```

The bridge opens an outbound WebSocket to Slack (no firewall rules needed), processes events, and calls the Claude Code CLI for each message. Logs rotate at 10MB and the daemon auto-restarts on crash with exponential backoff.

## License

MIT
