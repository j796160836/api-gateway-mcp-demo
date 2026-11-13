# Kong API Gateway for the order demo

Language: [繁體中文](README-zh-tw.md) | [English](README-en.md)

## Architecture

```text
REST client → Kong → FastAPI → SQLite
MCP client  → Kong → FastMCP → FastAPI → SQLite
```

The included Compose stack uses the Kong open-source image in DB-less mode. Kong loads its routes from [kong.yaml](kong.yaml), and FastMCP builds the five MCP tools from the REST OpenAPI document. The REST service stores orders in SQLite on a named Docker volume. Kong's DB-less configuration and the application's SQLite storage are independent. [Kong DB-less mode](https://developer.konghq.com/gateway/db-less-mode/), [Kong image](https://hub.docker.com/_/kong/)

| Request to Kong | Upstream |
|---|---|
| `GET /` | FastMCP service information |
| `/orders`, `/inventory`, `/shipments`, `/docs`, `/openapi.json` | FastAPI |
| `/mcp` | FastMCP Streamable HTTP |

Only the Kong proxy is published, on loopback. Kong's Admin API is disabled. The MCP endpoint has no client authentication in this local lab. Keep the default loopback binding when using demo credentials. FastAPI validates `x-api-key` on REST operations and additionally requires `x-manager-key` for cancellations. FastMCP supplies the REST credential from its own environment.

## 1. Start the stack

Use Docker Engine with the Docker Compose plugin. Run the commands from the repository root.

```sh
docker compose version
docker compose -f kong/compose.yaml config --quiet
docker compose -f kong/compose.yaml up --build -d --wait
docker compose -f kong/compose.yaml ps
```

The first build downloads the Kong and Python images and installs the demo's Python dependencies. Wait for all three services to become healthy. The default address is `http://127.0.0.1:18000`. If that port is in use, run `export KONG_DEMO_PORT=18001` before starting Compose and use that port in the examples below. To use different lab credentials, export `REST_API_KEY` and `MANAGER_KEY` before starting the stack. Compose passes the same REST credential to FastAPI and FastMCP.

## 2. Exercise the REST API through Kong

```sh
export KONG_BASE=http://127.0.0.1:18000
export REST_API_KEY="${REST_API_KEY:-demo-rest-secret}"

curl -i "$KONG_BASE/"
curl -i "$KONG_BASE/orders"
curl -fsS "$KONG_BASE/orders" -H "x-api-key: $REST_API_KEY"
curl -fsS "$KONG_BASE/inventory" -H "x-api-key: $REST_API_KEY"
```

The root responds with HTTP 200 and shows the MCP path. Listing orders without the key returns HTTP 401. With the key, a fresh database returns `ORD-1001` and `ORD-1002` and shows eight available units of `SKU-A01`.

Open `$KONG_BASE/docs` in a browser to use Swagger UI through Kong. Expand **POST /orders**, click **Try it out**, fill in `x-api-key`, and submit the following body. The same request can be made from the terminal.

```sh
curl -i -X POST "$KONG_BASE/orders" \
  -H "x-api-key: $REST_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-A01","quantity":2}'
```

Copy the `orderId` from the HTTP 201 response. The order starts as `PAID`. Stock is deducted when it ships.

## 3. Discover MCP tools and approve a shipment through Kong

Activate the project's Python environment or follow the dependency steps in the [main README](../README.md). Keep the Compose stack running and set the client's URL to the Kong endpoint.

```sh
export MCP_URL="$KONG_BASE/mcp"
python client.py
ORDER_ID='paste-order-id-here'
python approve_shipment.py "$ORDER_ID"
```

Set `ORDER_ID` to the actual `orderId` before running the last command. Enter `YES` at the prompt. Expect a `CREATED` shipment for that order and a decrease in the available quantity when you query `/inventory` again.

The client should discover `list_order`, `get_order`, `list_sku`, `check_inventory`, and `create_shipment`. Creating or cancelling orders is available on the REST route. The shipping prompt is implemented by the demo client. Any caller with access to the tool can invoke it directly, so a shared deployment needs its own authorization and approval controls.

The MCP route preserves `/mcp`, leaves methods unrestricted so the client can use its session lifecycle, and disables request and response buffering for streaming. Both upstream services have proxy retries disabled. [Kong routes](https://developer.konghq.com/gateway/entities/route/), [Kong services](https://developer.konghq.com/gateway/entities/service/)

## 4. Observe requests with Prometheus and access logs

The bundled Prometheus plugin records request counts by service, route, and HTTP status, along with request, Kong, and upstream latency. Compose publishes the Status API on loopback port `18100`. Use `KONG_METRICS_PORT` to change it. Kong's Admin API remains disabled. [Kong Prometheus plugin](https://developer.konghq.com/plugins/prometheus/)

```sh
curl -fsS "$KONG_BASE/orders" -H "x-api-key: $REST_API_KEY"
MCP_URL="$KONG_BASE/mcp" python client.py
curl -fsS "http://127.0.0.1:${KONG_METRICS_PORT:-18100}/metrics" \
  | grep -E '^kong_(http_requests_total|request_latency_ms_count)'
docker compose -f kong/compose.yaml logs --tail=30 kong
```

Look for `order-rest-routes` and `order-mcp-stream`. A Prometheus process on the host can scrape `127.0.0.1:18100` at `/metrics`. A Prometheus container on the Compose network can scrape `kong:8100`. After upgrading an existing stack, run `docker compose -f kong/compose.yaml up -d --wait` to apply the port and plugin configuration.

## 5. Troubleshoot and clean up

| Symptom | Check |
|---|---|
| Port already in use | Set `KONG_DEMO_PORT` to a free port and update `KONG_BASE` and `MCP_URL`. |
| REST 401 or cancellation 403 | Check `x-api-key` and, for cancellation, `x-manager-key`. |
| Proxy 502/503/504 | Inspect the upstream service health and logs. |
| MCP handshake or streaming fails | Confirm the client uses `/mcp` and the route preserves the path and disables buffering. A browser GET to `/mcp` alone does not establish an MCP session. |
| Shipment returns 409 | Check the order state, existing shipment, and available stock. |

```sh
docker compose -f kong/compose.yaml logs --tail=100 kong rest mcp
docker compose -f kong/compose.yaml exec kong kong config parse /etc/kong/kong.yaml
```

After editing `kong/kong.yaml`, recreate the Kong container to load the declarative configuration.

```sh
docker compose -f kong/compose.yaml up -d --force-recreate --wait kong
```

To reset the demo data, run the existing reset script in the REST container. It clears orders, inventory, and shipments in this stack's SQLite database and restores the sample rows.

```sh
docker compose -f kong/compose.yaml exec rest python reset_demo_db.py
```

Stop the stack while preserving the SQLite volume with `docker compose -f kong/compose.yaml down`. To stop it and delete the demo volume, use `docker compose -f kong/compose.yaml down --volumes`.

## Optional native REST-to-MCP conversion

Kong's native AI MCP Proxy plugin requires a Kong AI Gateway Enterprise license. The plugin's minimum Kong Gateway version is 3.12. On an eligible deployment, create a separate MCP Route for validation, attach the plugin to that Route in `conversion-listener` mode, and point its Kong Service directly at FastAPI. For a prefix Route such as `/native-mcp`, enable `strip_path` and use relative tool paths such as `orders` so FastAPI receives `/orders`. Use the plugin schema to describe path parameters and the shipment request body. [AI MCP Proxy](https://developer.konghq.com/plugins/ai-mcp-proxy/), [Plugin configuration reference](https://developer.konghq.com/plugins/ai-mcp-proxy/reference/)

Configure only these tools on the native MCP Route.

| MCP tool | REST operation |
|---|---|
| `list_order` | `GET /orders` |
| `get_order` | `GET /orders/{order_id}` |
| `list_sku` | `GET /inventory` |
| `check_inventory` | `GET /inventory/{sku}` |
| `create_shipment` | `POST /shipments` with JSON body containing `order_id` |

Keep order creation and cancellation outside that tool list. Authenticate clients on the MCP Route and supply the upstream REST credential through your deployment's protected configuration. Keep the manager key out of the MCP path and preserve a human approval step for shipment. Inspect the tool schemas returned by the native listener before switching clients, since the plugin may expose a different argument shape than FastMCP. The Compose example uses the open-source proxy path above.
