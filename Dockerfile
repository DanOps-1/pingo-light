FROM python:3.13-alpine

LABEL org.opencontainers.image.source="https://github.com/DanOps-1/bingo-light"
LABEL org.opencontainers.image.description="AI-native fork maintenance"
LABEL org.opencontainers.image.licenses="MIT"

RUN apk add --no-cache git

COPY bingo-light mcp-server.py /usr/local/bin/
COPY bingo_core/ /usr/local/bin/bingo_core/

RUN chmod +x /usr/local/bin/bingo-light /usr/local/bin/mcp-server.py

# Default: CLI mode. Override with "mcp-server.py" for MCP stdio transport.
ENTRYPOINT ["bingo-light"]
