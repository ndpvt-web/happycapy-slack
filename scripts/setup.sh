#!/bin/bash
# HappyCapy Slack Skill - Dependency Setup
# Run this once before starting the bridge.

set -e

echo "Installing HappyCapy Slack dependencies..."

pip install slack-bolt slackify-markdown --quiet

mkdir -p ~/.happycapy-slack/history

echo "Setup complete. Dependencies installed."
echo "Next: run the setup wizard via the happycapy-slack skill, then start with:"
echo "  bash ~/.claude/skills/happycapy-slack/scripts/start.sh daemon"
