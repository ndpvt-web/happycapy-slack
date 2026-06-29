#!/bin/bash
# HappyCapy Slack Skill - Stop Script
# Convenience wrapper: just calls start.sh stop

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
exec bash "$SKILL_DIR/scripts/start.sh" stop
