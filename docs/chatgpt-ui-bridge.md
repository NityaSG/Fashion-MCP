# Fashion Trends MCP Apps Bridge

The `chatgpt/` directory contains the Node.js bridge that exposes your existing fashion FastMCP tools as UI-enabled MCP tools for ChatGPT-style clients.

The bridge does not call custom REST endpoints. It proxies tool calls to the Python FastMCP server over MCP Streamable HTTP, transforms those results into widget-friendly `structuredContent`, and serves the widget HTML used by the client.

## Architecture

```text
ChatGPT / Claude / MCP client
        |
        v
chatgpt/server.js
  - serves /mcp
  - serves /widget/app.html
  - proxies remote media through /media
  - transforms FastMCP tool output into UI payloads
        |
        v
fashion_trends_mcp_server.py
  - runs FastMCP tools
  - must be started in HTTP mode for this bridge
```

## Prerequisites

- Node.js 18 or newer
- Python environment for `fashion_trends_mcp_server.py`
- Database credentials already configured for the Python FastMCP server

## Quick Start

### 1. Install bridge dependencies

```bash
cd chatgpt
npm install
```

### 2. Configure the bridge

Copy `.env.example` to `.env` if you want to override defaults.

```bash
PORT=8787
BACKEND_MCP_URL=http://127.0.0.1:8000/mcp
PUBLIC_BASE_URL=http://localhost:8787
MEDIA_CDN_BASE_URL=https://d99zyv0ifyenn.cloudfront.net
```

Notes:

- `BACKEND_MCP_URL` is the preferred setting.
- `MEDIA_CDN_BASE_URL` is used to rewrite legacy S3 image links onto your CloudFront distribution.
- `API_URL` is still accepted as a legacy fallback and will be normalized to `/mcp`.

### 3. Start the Python FastMCP server in HTTP mode

From the repo root:

```bash
# PowerShell
$env:MCP_TRANSPORT = "http"
python .\fashion_trends_mcp_server.py
```

```bash
# bash
MCP_TRANSPORT=http python ./fashion_trends_mcp_server.py
```

By default this serves the backend MCP endpoint on `http://127.0.0.1:8000/mcp`.

Optional backend overrides:

```bash
MCP_HOST=0.0.0.0
MCP_PORT=8000
```

### 4. Start the UI bridge

```bash
cd chatgpt
npm start
```

Useful local routes:

- `http://localhost:8787/health`
- `http://localhost:8787/mcp`
- `http://localhost:8787/preview`
- `http://localhost:8787/widget/app.html`

### 5. Verify locally before connecting ChatGPT

```bash
npm run verify
```

Then open:

```text
http://localhost:8787/preview
```

`/preview` loads the widget inside a local host harness that speaks the same JSON-RPC bridge methods used by ChatGPT:

- `ui/initialize`
- `ui/notifications/initialized`
- `ui/notifications/tool-result`
- `tools/call`
- `ui/message`
- `ui/open-link`

## MCP Client Configuration

For a local desktop MCP client that launches the bridge as a stdio process:

```json
{
  "mcpServers": {
    "fashion-trends-ui": {
      "command": "node",
      "args": [
        "C:\\Users\\KIIT\\Desktop\\Kreeda\\ICh\\MCP2.0\\chatgpt\\server.js"
      ],
      "env": {
        "PORT": "8787",
        "BACKEND_MCP_URL": "http://127.0.0.1:8000/mcp"
      }
    }
  }
}
```

Use the absolute path to `server.js`.

## Exposed UI Tools

The bridge currently wraps these backend tools:

- `get_color_trends`
- `get_trending_posts`
- `get_top_brands_or_influencers`
- `get_apparel_trends`
- `get_print_pattern_trends`
- `get_fabric_trends`
- `get_database_statistics`
- `search_posts_by_keywords`
- `compare_time_periods`
- `execute_custom_sql`

## Widget Payload Types

The widget renders these `structuredContent.type` values:

- `color_trends`
- `post_grid`
- `entity_rankings`
- `trend_breakdown`
- `time_comparison`
- `database_overview`
- `query_result`
- `error`

## Local Preview Notes

- The preview harness is demo-driven. It helps validate the widget contract and in-widget follow-up actions without depending on ChatGPT.
- The bridge itself still talks to the real Python backend during actual MCP tool calls.
- External images are proxied through `/media` so the widget only needs the bridge origin in CSP.

## Troubleshooting

### Bridge starts but tool calls fail

Check that the Python server is running in HTTP mode:

```bash
curl http://127.0.0.1:8000/mcp
```

If you get a method error or a 4xx response, the endpoint is at least reachable. If the connection is refused, the backend is not running.

### Preview loads but nothing renders

- Open browser devtools and inspect console errors.
- Confirm `/widget/app.html` loads.
- Confirm the harness log shows `ui/initialize` followed by `ui/notifications/initialized`.

### Remote post images do not load

- Known fashion media URLs are rewritten directly onto `MEDIA_CDN_BASE_URL`.
- Other remote assets still fall back to `/media?url=...`.
- Check the bridge logs for upstream fetch errors.

### The MCP client cannot connect

- Verify the bridge is listening on the configured port.
- Verify `BACKEND_MCP_URL` points to the Python FastMCP endpoint, not just the host root.
- Ensure Node 18+ is being used.

## Development Notes

If you add another backend tool:

1. Register it in `server.js` with `registerAppTool(...)`.
2. Convert backend output into a widget-specific payload.
3. Add a renderer in `widget/app.html`.
4. Add a demo state or tool-call stub in `test-harness.html`.

## Files

```text
chatgpt/
├── server.js
├── test-harness.html
├── verify.js
├── package.json
├── .env.example
├── widget/
│   └── app.html
└── static/
    └── image/
```
