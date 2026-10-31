#!/bin/sh
# MCP 入口(stdio),由 iphonectl mcp 注册到 Claude Code:
#   docker exec -i <容器名> /opt/ictl/mcp-server.sh
exec /opt/mcp/bin/iphone-mcp
