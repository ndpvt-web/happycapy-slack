# HappyCapy Slack — Configuration Schema

All configuration is stored at `~/.happycapy-slack/config.json`.

## Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `bot_token` | string | `""` | Slack Bot User OAuth Token. Starts with `xoxb-`. Required. Used for posting messages, reading events, and calling Slack API. |
| `app_token` | string | `""` | Slack App-Level Token. Starts with `xapp-`. Required. Used for Socket Mode WebSocket connection. Must have `connections:write` scope. |
| `workspace` | string | `"Slack"` | Display name of your Slack workspace. Injected into the system prompt so Claude knows which team it's helping. |
| `allowed_users` | string[] | `[]` | Slack User IDs (e.g. `["U012AB3CD", "U987ZY6WX"]`) that are allowed to use the bot. Empty array `[]` means everyone in the workspace can use it. |
| `model` | string | `"claude-sonnet-4-6"` | Claude model to use when calling `claude --print`. Must match a model available in Claude Code CLI. |
| `max_history` | integer | `20` | Maximum number of messages to keep per thread history. Older messages are dropped when the limit is reached (FIFO). |
| `reply_in_thread` | boolean | `true` | When true, all replies are posted in the original Slack thread, keeping channels clean. When false, replies go directly to the channel. (Currently always true in bridge.py for best UX.) |
| `log_level` | string | `"INFO"` | Logging verbosity. Options: `DEBUG`, `INFO`, `WARNING`, `ERROR`. DEBUG logs full prompt contents (sensitive — avoid in production). |

## Example config.json

```json
{
  "bot_token": "xoxb-YOUR-BOT-TOKEN-HERE",
  "app_token": "xapp-YOUR-APP-LEVEL-TOKEN-HERE",
  "workspace": "MyCompany",
  "allowed_users": [],
  "model": "claude-sonnet-4-6",
  "max_history": 20,
  "reply_in_thread": true,
  "log_level": "INFO"
}
```

## Data Files

| File | Location | Description |
|------|----------|-------------|
| `config.json` | `~/.happycapy-slack/config.json` | User configuration (permissions: 0o600) |
| `bridge.log` | `~/.happycapy-slack/bridge.log` | Bridge and daemon logs (rotated at 10MB) |
| `daemon.pid` | `~/.happycapy-slack/daemon.pid` | Daemon process ID (written by start.sh) |
| `history/` | `~/.happycapy-slack/history/` | Per-thread conversation history JSON files |

## History File Format

Each Slack thread gets its own history file at:
`~/.happycapy-slack/history/{user_id}_{thread_ts}.json`

For DMs with no thread: `~/.happycapy-slack/history/{user_id}_dm.json`

History file structure:
```json
[
  {"role": "user", "content": "What's the weather like?"},
  {"role": "assistant", "content": "I don't have real-time weather data, but I can run a web search..."}
]
```

## Slack App Requirements

The Slack app created at https://api.slack.com/apps must have:

### Bot Token Scopes (OAuth & Permissions)
| Scope | Purpose |
|-------|---------|
| `app_mentions:read` | Receive @mention events in channels |
| `chat:write` | Post messages in channels and DMs |
| `channels:history` | Read message history in channels the bot is in |
| `im:history` | Read DM message history |
| `im:read` | See DM conversations |
| `im:write` | Open DM conversations |
| `reactions:write` | Add loading indicator emoji (hourglass) |
| `users:read` | Resolve user IDs to display names (optional but improves system prompt) |

### App-Level Token Scopes
| Scope | Purpose |
|-------|---------|
| `connections:write` | Required for Socket Mode WebSocket connection |

### Event Subscriptions (Subscribe to bot events)
| Event | Trigger |
|-------|---------|
| `message.im` | Direct messages to the bot |
| `app_mention` | @mentions of the bot in any channel |

### Socket Mode
Must be enabled at Settings → Socket Mode (toggle ON).

## Daemon Configuration

The supervisor loop in `start.sh` uses these hardcoded settings:

| Setting | Value | Description |
|---------|-------|-------------|
| `MAX_RESTARTS` | 50 | Max restart attempts before giving up |
| `INITIAL_BACKOFF` | 3s | Initial wait before restart |
| `MAX_BACKOFF` | 120s | Maximum wait between restarts |
| `STABILITY_THRESHOLD` | 300s | Process must run this long to reset restart counter |
| `LOG_ROTATION_SIZE` | 10MB | Rotate log when it exceeds this size |

## Thread Reply Strategy

The bridge always replies in-thread (`thread_ts`) to keep Slack channels clean:

- **Channel @mention**: reply uses `thread_ts` if message is already in a thread, or `event_ts` to start a new thread
- **Direct message**: reply uses `thread_ts` if in a DM thread, or `event_ts` as the reply anchor
- **History key**: `{user_id}_{thread_ts}` — each thread has completely isolated conversation memory

This means:
1. Different threads in the same channel have separate conversations
2. Channels don't get cluttered — AI responses are always nested
3. Users can have multiple simultaneous independent conversations by using different threads
