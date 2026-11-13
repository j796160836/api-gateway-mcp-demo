# Envoy Gateway for the order demo

Language: [繁體中文](README-zh-tw.md) | [English](README-en.md)

Both REST and MCP clients connect to Envoy, which calls FastAPI backed by SQLite. Envoy's MCP JSON REST Bridge handles the MCP handshake and translates tool calls according to five explicit mappings in [envoy.yaml](envoy.yaml). The stack has two containers, Envoy and the REST backend. Envoy marks the bridge as work in progress, so this demo binds both host ports to loopback. [Envoy MCP JSON REST Bridge](https://www.envoyproxy.io/docs/envoy/v1.40.2/api-v3/extensions/filters/http/mcp_json_rest_bridge/v3/mcp_json_rest_bridge.proto)

| MCP tool | REST operation |
|---|---|
| `list_order` | `GET /orders` |
| `get_order` | `GET /orders/{order_id}` |
| `list_sku` | `GET /inventory` |
| `check_inventory` | `GET /inventory/{sku}` |
| `create_shipment` | `POST /shipments` |

## 1. Start the stack

From the repository root, run the following with Docker Compose and `jq` installed.

```sh
docker compose -f envoy/compose.yaml up --build -d --wait
curl -fsS http://127.0.0.1:18301/ready
```

The default proxy port is `18300`, and the metrics port is `18301`. Set `ENVOY_DEMO_PORT` or `ENVOY_METRICS_PORT` before starting Compose to use other ports. Set `REST_API_KEY` before startup to override the demo backend key.

## 2. Verify REST and native MCP

```sh
BASE="http://127.0.0.1:${ENVOY_DEMO_PORT:-18300}"
KEY="${REST_API_KEY:-demo-rest-secret}"
curl -fsS "$BASE/orders" -H "x-api-key: $KEY" | jq .
```

Open `http://127.0.0.1:18300/docs` to use Swagger UI. Create orders through `POST /orders`. Cancel orders through the manager-protected REST endpoint. The bridge serves MCP initialization and discovery locally. Tool calls that reach FastAPI require the same `x-api-key` as direct REST requests.

```sh
envoy_mcp() {
  curl -fsS "$BASE/mcp" \
    -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
    -H 'MCP-Protocol-Version: 2025-11-25' -H "x-api-key: $KEY" -d "$1"
}

envoy_mcp '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"order-demo","version":"1"}}}' | jq .
envoy_mcp '{"jsonrpc":"2.0","method":"notifications/initialized"}'
envoy_mcp '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | jq -er '.result.tools[].name'
envoy_mcp '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_order","arguments":{"order_id":"ORD-1001"}}}' | jq -e '.result | select(.isError != true)'
```

In an MCP client such as `agy`, use `http://127.0.0.1:18300/mcp` as the server URL and send `x-api-key` as a custom header. A shipment takes `{"order_id":"ORD-1001"}` as its arguments. Only call it after explicit human approval. The tool description communicates that requirement to the client.

## 3. Inspect telemetry

```sh
curl -fsS "http://127.0.0.1:${ENVOY_METRICS_PORT:-18301}/stats/prometheus" \
  | grep -E '^envoy_(http_downstream_rq_|cluster_upstream_rq_)' | head -20
docker compose -f envoy/compose.yaml logs --tail=30 envoy
```

The metrics endpoint exposes Envoy's request counters and latency histograms in Prometheus format. JSON access logs distinguish `rest` and `mcp` routes and include HTTP status, duration, and request ID. HTTP status describes the transport, so inspect the JSON-RPC result for tool errors. The separate administration listener only allows `/ready` and `/stats/prometheus`. [Envoy administration interface](https://www.envoyproxy.io/docs/envoy/v1.40.2/operations/admin)

## 4. Reset or stop

```sh
docker compose -f envoy/compose.yaml exec rest python reset_demo_db.py
docker compose -f envoy/compose.yaml down
```

The reset command clears this stack's demo data and restores the sample orders and stock. The stop command preserves its SQLite volume. Use `down --volumes` to delete that volume as well.
