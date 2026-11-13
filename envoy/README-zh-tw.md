# 用 Envoy 串接訂單範例

語言：[繁體中文](README-zh-tw.md) | [English](README-en.md)

REST 與 MCP 客戶端都連到 Envoy，再由 Envoy 呼叫以 SQLite 儲存資料的 FastAPI。Envoy 的 MCP JSON REST Bridge 處理 MCP 握手，並依 [envoy.yaml](envoy.yaml) 內的五個對應規則轉譯工具呼叫。Compose 只執行 Envoy 和 REST 後端兩個容器。Envoy 將這個 Bridge 標為開發中，因此範例只在本機迴環介面開放連接埠。 [Envoy MCP JSON REST Bridge](https://www.envoyproxy.io/docs/envoy/v1.40.2/api-v3/extensions/filters/http/mcp_json_rest_bridge/v3/mcp_json_rest_bridge.proto)

| MCP 工具 | REST 操作 |
|---|---|
| `list_order` | `GET /orders` |
| `get_order` | `GET /orders/{order_id}` |
| `list_sku` | `GET /inventory` |
| `check_inventory` | `GET /inventory/{sku}` |
| `create_shipment` | `POST /shipments` |

## 1. 啟動服務

安裝 Docker Compose 和 `jq` 後，從專案根目錄執行。

```sh
docker compose -f envoy/compose.yaml up --build -d --wait
curl -fsS http://127.0.0.1:18301/ready
```

代理預設使用 `18300`，指標預設使用 `18301`。若要改埠，可在啟動 Compose 前設定 `ENVOY_DEMO_PORT` 或 `ENVOY_METRICS_PORT`。要更換後端的示範金鑰，可在啟動前設定 `REST_API_KEY`。

## 2. 驗證 REST 與原生 MCP

```sh
BASE="http://127.0.0.1:${ENVOY_DEMO_PORT:-18300}"
KEY="${REST_API_KEY:-demo-rest-secret}"
curl -fsS "$BASE/orders" -H "x-api-key: $KEY" | jq .
```

開啟 `http://127.0.0.1:18300/docs` 可使用 Swagger UI。新增訂單用 `POST /orders`，取消訂單走需要主管金鑰的 REST 端點。MCP 握手與工具探索由 Bridge 直接回應。工具呼叫轉到 FastAPI 時，需帶上與 REST 相同的 `x-api-key`。

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

在 `agy` 等 MCP 客戶端，把伺服器網址設為 `http://127.0.0.1:18300/mcp`，並加上 `x-api-key` 標頭。出貨工具接受 `{"order_id":"ORD-1001"}` 作為參數。請取得人工核准後才呼叫，工具描述會把這項要求告知客戶端。

## 3. 查看 telemetry

```sh
curl -fsS "http://127.0.0.1:${ENVOY_METRICS_PORT:-18301}/stats/prometheus" \
  | grep -E '^envoy_(http_downstream_rq_|cluster_upstream_rq_)' | head -20
docker compose -f envoy/compose.yaml logs --tail=30 envoy
```

指標端點以 Prometheus 格式提供請求計數與延遲直方圖。JSON 存取日誌會區分 `rest` 與 `mcp` 路由，並列出 HTTP 狀態、耗時和請求 ID。判斷工具是否成功時，還要檢查 JSON-RPC 回應。獨立的管理埠只允許 `/ready` 和 `/stats/prometheus`。 [Envoy 管理介面](https://www.envoyproxy.io/docs/envoy/v1.40.2/operations/admin)

## 4. 重置或停止服務

```sh
docker compose -f envoy/compose.yaml exec rest python reset_demo_db.py
docker compose -f envoy/compose.yaml down
```

重置指令會清除這套範例的資料，並還原範例訂單和庫存。停止服務時會保留 SQLite 磁碟區。如需刪除該磁碟區，可使用 `down --volumes`。
