#!/usr/bin/env python3
"""
HappyCapy Slack Bridge
======================
Connects HappyCapy's AI agent to Slack via Socket Mode WebSocket.
No public URL required — the bridge opens an outbound connection to Slack.

On each @mention or DM, it:
  1. Loads per-thread conversation history
  2. Builds a system prompt (user info, workspace, datetime)
  3. Calls `claude --print` (Claude Code CLI) for full tool access
  4. Converts markdown → Slack mrkdwn
  5. Replies in the original thread, splitting at 3000 chars

Architecture:
  Slack → Socket Mode WebSocket → bridge.py → claude --print → Slack reply
"""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CONFIG_PATH = Path.home() / ".happycapy-slack" / "config.json"
HISTORY_DIR = Path.home() / ".happycapy-slack" / "history"
LOG_PATH = Path.home() / ".happycapy-slack" / "bridge.log"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print(
            f"ERROR: Config not found at {CONFIG_PATH}.\n"
            "Run the happycapy-slack skill setup wizard first."
        )
        sys.exit(1)
    with open(CONFIG_PATH) as f:
        cfg = json.load(f)
    # Validate required fields
    for field in ("bot_token", "app_token"):
        if not cfg.get(field):
            print(f"ERROR: '{field}' is missing from config.")
            sys.exit(1)
    return cfg

CONFIG = load_config()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

LOG_LEVEL = getattr(logging, CONFIG.get("log_level", "INFO").upper(), logging.INFO)
logger = logging.getLogger("happycapy-slack")
logger.setLevel(LOG_LEVEL)

# Rotating file handler (10 MB, 1 backup)
fh = RotatingFileHandler(str(LOG_PATH), maxBytes=10 * 1024 * 1024, backupCount=1)
fh.setLevel(LOG_LEVEL)
fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(fh)

# Console handler
ch = logging.StreamHandler()
ch.setLevel(LOG_LEVEL)
ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
logger.addHandler(ch)

# ---------------------------------------------------------------------------
# Markdown → Slack mrkdwn conversion
# ---------------------------------------------------------------------------

def md_to_mrkdwn(text: str) -> str:
    """Convert standard Markdown to Slack mrkdwn format.

    Slack uses a non-standard subset:
      *bold*  (not **bold**)
      _italic_  (not *italic*)
      `inline code`  (same)
      ```code blocks```  (same, but no language tag)
      ~strikethrough~  (not ~~strikethrough~~)
      > blockquote  (same, but only single >)
      • bullet  (convert - / * list items)
      <URL|text>  (not [text](URL))
    """
    # Try slackify_markdown first (handles most cases)
    try:
        from slackify_markdown import convert
        return convert(text)
    except ImportError:
        pass

    # Fallback: manual conversion

    # Fenced code blocks — remove language tag, keep triple backticks
    text = re.sub(r"```[a-zA-Z0-9_+-]*\n", "```\n", text)

    # **bold** or __bold__ → *bold*
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"*\1*", text, flags=re.DOTALL)

    # *italic* or _italic_ → _italic_ (avoid touching already-converted *bold*)
    # Only convert single-asterisk italic if not already a *bold* span
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"_\1_", text)

    # ~~strikethrough~~ → ~strikethrough~
    text = re.sub(r"~~(.+?)~~", r"~\1~", text, flags=re.DOTALL)

    # [text](URL) → <URL|text>
    text = re.sub(r"\[([^\]]+)\]\((https?://[^\)]+)\)", r"<\2|\1>", text)

    # Markdown headers → bold text (Slack has no headers)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", text, flags=re.MULTILINE)

    # Unordered lists: "- item" or "* item" → "• item"
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)

    # Ordered lists: "1. item" → "1. item" (keep as-is, Slack renders them fine)

    return text


def split_message(text: str, max_len: int = 3000) -> list[str]:
    """Split a message at block boundaries to stay under Slack's block limit."""
    if len(text) <= max_len:
        return [text]

    chunks = []
    current = ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > max_len:
            if current:
                chunks.append(current.rstrip())
            current = line
        else:
            current += line
    if current:
        chunks.append(current.rstrip())
    return chunks or [text[:max_len]]


# ---------------------------------------------------------------------------
# Conversation history (per thread)
# ---------------------------------------------------------------------------

def history_key(user_id: str, thread_ts: str | None) -> str:
    """Unique key for a Slack thread. DMs without thread_ts use 'dm'."""
    ts = thread_ts.replace(".", "_") if thread_ts else "dm"
    return f"{user_id}_{ts}"


def history_path(key: str) -> Path:
    return HISTORY_DIR / f"{key}.json"


def load_history(key: str) -> list[dict]:
    p = history_path(key)
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text())
    except Exception:
        return []


def save_history(key: str, messages: list[dict]) -> None:
    max_hist = CONFIG.get("max_history", 20)
    messages = messages[-max_hist:]
    try:
        history_path(key).write_text(json.dumps(messages, indent=2))
    except Exception as e:
        logger.warning(f"Could not save history for {key}: {e}")


# ---------------------------------------------------------------------------
# Claude invocation
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """\
You are HappyCapy, an AI agent accessible via Slack. The user is communicating through Slack.
You have full access to all HappyCapy tools: run bash commands, read/write files, search the web, generate images/videos, use any installed skill.
Keep responses concise for Slack. Use Slack markdown: *bold*, `code`, ```code blocks```.
Do NOT use standard Markdown headers (#, ##) — Slack doesn't render them.
Current time: {datetime}
User: {slack_username}
Workspace: {workspace}
"""


def build_prompt(
    message_text: str,
    history: list[dict],
    user_id: str,
    username: str,
    workspace: str,
) -> str:
    """Build the full prompt string passed to `claude --print`."""
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        datetime=datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC"),
        slack_username=username or user_id,
        workspace=workspace or "Slack",
    )

    parts = [system_prompt.strip(), ""]

    if history:
        parts.append("--- Conversation so far ---")
        for msg in history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            parts.append(f"{role.upper()}: {content}")
        parts.append("--- End of history ---")
        parts.append("")

    parts.append(f"USER: {message_text}")
    return "\n".join(parts)


def call_claude(prompt: str) -> str:
    """Call `claude --print` with the prompt and return the response text."""
    model = CONFIG.get("model", "claude-sonnet-4-6")
    try:
        result = subprocess.run(
            ["claude", "--print", "--model", model],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes for complex tasks
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            logger.error(f"claude --print exited with code {result.returncode}: {stderr[:200]}")
            return "Sorry, I encountered an error while processing your request. Please try again."
        return result.stdout.strip() or "Done."
    except FileNotFoundError:
        logger.error("claude CLI not found. Is Claude Code installed and on PATH?")
        return "Error: Claude Code CLI (`claude`) is not installed or not on PATH."
    except subprocess.TimeoutExpired:
        logger.error("claude --print timed out after 300s")
        return "Sorry, that request took too long. Please try a simpler query."
    except Exception as e:
        logger.error(f"Unexpected error calling claude: {e}")
        return "Sorry, an unexpected error occurred."


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------

def is_allowed(user_id: str) -> bool:
    allowed = CONFIG.get("allowed_users", [])
    if not allowed:
        return True  # Empty list = everyone allowed
    return user_id in allowed


# ---------------------------------------------------------------------------
# Message processing (shared for mentions and DMs)
# ---------------------------------------------------------------------------

def process_message(
    client,
    user_id: str,
    text: str,
    channel: str,
    thread_ts: str | None,
    event_ts: str,
) -> None:
    """Core handler: load history, call Claude, post reply."""

    # Access check
    if not is_allowed(user_id):
        logger.info(f"Rejected message from unauthorized user {user_id}")
        client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts or event_ts,
            text="Sorry, you're not authorized to use this bot.",
        )
        return

    # Clean up @mention tags from the text (e.g. <@U012AB3CD>)
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    if not clean_text:
        return

    logger.info(f"Message from {user_id} ({len(clean_text)} chars)")

    # Show loading reaction
    try:
        client.reactions_add(channel=channel, name="hourglass_flowing_sand", timestamp=event_ts)
    except Exception:
        pass  # Non-fatal

    # Thread key for history
    key = history_key(user_id, thread_ts)
    history = load_history(key)

    # Resolve username
    username = user_id
    try:
        info = client.users_info(user=user_id)
        profile = info.get("user", {}).get("profile", {})
        username = profile.get("display_name") or profile.get("real_name") or user_id
    except Exception:
        pass

    workspace = CONFIG.get("workspace", "Slack")
    prompt = build_prompt(clean_text, history, user_id, username, workspace)

    # Call Claude
    response_text = call_claude(prompt)

    # Convert to Slack mrkdwn
    formatted = md_to_mrkdwn(response_text)
    chunks = split_message(formatted)

    # Determine reply thread_ts
    reply_thread = thread_ts or event_ts

    # Post reply (all chunks in the same thread)
    for i, chunk in enumerate(chunks):
        try:
            client.chat_postMessage(
                channel=channel,
                thread_ts=reply_thread,
                text=chunk,
                mrkdwn=True,
            )
        except Exception as e:
            logger.error(f"Failed to post chunk {i}: {e}")

    # Remove loading reaction
    try:
        client.reactions_remove(channel=channel, name="hourglass_flowing_sand", timestamp=event_ts)
    except Exception:
        pass

    # Update history
    history.append({"role": "user", "content": clean_text})
    history.append({"role": "assistant", "content": response_text})
    save_history(key, history)
    logger.info(f"Replied to {user_id} ({len(response_text)} chars, {len(chunks)} chunk(s))")


# ---------------------------------------------------------------------------
# Slack Bolt app
# ---------------------------------------------------------------------------

def main() -> None:
    try:
        from slack_bolt import App
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError:
        print("slack-bolt not installed. Run: pip install slack-bolt slackify-markdown")
        sys.exit(1)

    bot_token = CONFIG["bot_token"]
    app_token = CONFIG["app_token"]

    app = App(token=bot_token)

    # -----------------------------------------------------------------------
    # Event: app_mention — bot is @mentioned in a channel
    # -----------------------------------------------------------------------
    @app.event("app_mention")
    def handle_mention(event, client, logger):
        user_id = event.get("user", "")
        text = event.get("text", "")
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts")  # None if not already in a thread
        event_ts = event.get("ts", "")

        # Reply in thread — use event_ts as thread_ts if there's no thread yet
        process_message(
            client=client,
            user_id=user_id,
            text=text,
            channel=channel,
            thread_ts=thread_ts or event_ts,
            event_ts=event_ts,
        )

    # -----------------------------------------------------------------------
    # Event: message.im — direct message to the bot
    # -----------------------------------------------------------------------
    @app.event("message")
    def handle_dm(event, client, logger):
        # Only process DMs (channel_type = "im"), skip bots and subtypes
        if event.get("channel_type") != "im":
            return
        if event.get("bot_id") or event.get("subtype"):
            return

        user_id = event.get("user", "")
        text = event.get("text", "")
        channel = event.get("channel", "")
        event_ts = event.get("ts", "")
        thread_ts = event.get("thread_ts")  # DMs can have threads too

        process_message(
            client=client,
            user_id=user_id,
            text=text,
            channel=channel,
            thread_ts=thread_ts,
            event_ts=event_ts,
        )

    # -----------------------------------------------------------------------
    # Start Socket Mode handler
    # -----------------------------------------------------------------------
    logger.info("Starting HappyCapy Slack bridge (Socket Mode)...")
    logger.info(f"Config: model={CONFIG.get('model')}, workspace={CONFIG.get('workspace')}")
    allowed = CONFIG.get("allowed_users", [])
    logger.info(f"Access: {'everyone' if not allowed else str(allowed)}")

    handler = SocketModeHandler(app, app_token)
    logger.info("Connected to Slack via Socket Mode")
    handler.start()


if __name__ == "__main__":
    main()
