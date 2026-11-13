# API Gateway meets MCP — Order demo

Language: [繁體中文](README-zh-tw.md) | [English](README-en.md)

MCP Client → FastMCP Gateway → FastAPI REST API → SQLite

At startup, the gateway reads the REST API's OpenAPI schema and generates tools for the allowed operation IDs. The REST API checks credentials, manager approval, and order status.

## Gateway integrations

| Gateway | MCP architecture | Guides |
|---|---|---|
| Google Cloud API Gateway | Native MCP (Public Preview) converts tool calls to REST on Cloud Run | [English](docs/google-cloud.md) · [繁體中文](docs/google-cloud-zh-tw.md) |
| Kong Gateway | A local DB-less Kong deployment proxies REST and the existing FastMCP server | [English](kong/README.md) · [繁體中文](kong/README-zh-tw.md) |
| Envoy | Native MCP JSON REST Bridge translates tool calls to FastAPI | [English](envoy/README.md) · [繁體中文](envoy/README-zh-tw.md) |
| Apigee | Managed MCP Discovery Proxy maps OpenAPI operations to an Apigee REST proxy | [English](apigee/README.md) · [繁體中文](apigee/README-zh-tw.md) |

The standalone local demo is documented below.

| REST operation | MCP access |
|---|---|
| GET /orders | `list_order` |
| POST /orders | REST only (`create_order`) |
| GET /orders/{order_id} | `get_order` |
| GET /inventory | `list_sku` |
| GET /inventory/{sku} | `check_inventory` |
| POST /shipments | `create_shipment` |
| POST /orders/{order_id}/cancel | Manager-only REST operation (`cancel_order`) |

## Run locally

Use Python 3.11 or later. From the extracted project directory, install the dependencies.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Run each command from the project directory with the virtual environment active. In Windows PowerShell, activate it with `.venv\Scripts\Activate.ps1`.

**Terminal A — REST API**

```sh
python -m uvicorn api:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000/> for service information or <http://127.0.0.1:8000/docs> to explore the REST API.

The REST API uses Python’s built-in `sqlite3`. At startup it creates `db.sqlite3` beside the code and seeds two orders and one SKU when all three tables are empty. Orders, stock, and shipments persist across restarts. Set `SQLITE_PATH` to use a different database file. Environment defaults are in `config.py`.

**Terminal B — MCP gateway**

```sh
python gateway.py
```

The Streamable HTTP endpoint is `http://127.0.0.1:9000/mcp`.

**Terminal C — MCP client**

```sh
python client.py
python approve_shipment.py ORD-1001
```

The first script lists the available tools, lists orders and SKUs, and checks an individual order and its stock. Pass an order ID to the second script, then enter `YES` to approve its shipment. The script defaults to `ORD-1001` if you omit the ID.

## Create a demo order

In Swagger UI at `http://127.0.0.1:8000/docs`, expand **POST /orders**, click **Try it out**, and set `x-api-key` to `demo-rest-secret` (or your configured key). Use a body like this:

```json
{"sku": "SKU-A01", "quantity": 2}
```

The API returns HTTP 201 with a generated `orderId` and status `PAID`. Copy the ID and pass it to `python approve_shipment.py ORDER_ID` to try shipping the new order. Stock is deducted on shipment.

## Demonstrate order cancellation

Use `ORD-1002` so it stays separate from the shipment demo.

```sh
curl -i http://127.0.0.1:8000/orders/ORD-1002/cancel \
  -H 'x-api-key: demo-rest-secret' \
  -H 'Content-Type: application/json' \
  -d '{"reason":"Customer requested cancellation"}'
```

The REST API returns HTTP 403 with the service key alone. Repeat the request with `-H 'x-manager-key: demo-manager-secret'` to receive HTTP 200. The order stays available with status `CANCELLED` and its cancellation reason.

```sh
curl -s http://127.0.0.1:8000/orders/ORD-1002 \
  -H 'x-api-key: demo-rest-secret'
```

The API returns HTTP 409 if you try to ship a cancelled order, cancel an order twice, or cancel an order that already has a shipment.

## Reset the demo database

Run this command with the same `SQLITE_PATH` setting as the REST service. It clears the demo orders, inventory, and shipments, then restores the sample data in a single transaction.

```sh
python reset_demo_db.py
```

## End-to-end tests

Start both services with the default keys. To isolate the test data, set `SQLITE_PATH` to a dedicated file, such as `test-demo.sqlite3`, when starting the REST service and running the reset script. Reset that database before each test run.

```sh
python -m unittest -v test_demo
```

The standalone demo uses local services and sample keys. The Google Cloud guide uses `google-cloud-openapi-example.yaml` as its deployment template.

---

## LICENSE

MIT