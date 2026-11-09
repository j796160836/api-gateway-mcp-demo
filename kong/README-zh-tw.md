# 用 Kong API Gateway 串接訂單範例

[English](README.md)

## 架構

```text
REST 客戶端 → Kong → FastAPI → SQLite
MCP 客戶端  → Kong → FastMCP → FastAPI → SQLite
```

這套 Compose 設定使用開源版 Kong，以 DB-less 模式讀取 [kong.yaml](kong.yaml) 的路由。FastMCP 根據 REST OpenAPI 文件產生五個 MCP 工具。訂單資料由 REST 服務寫入 Docker 命名磁碟區內的 SQLite。Kong 的 DB-less 設定與應用程式的 SQLite 資料各自獨立。 [Kong DB-less 模式](https://developer.konghq.com/gateway/db-less-mode/)、[Kong 官方映像檔](https://hub.docker.com/_/kong/)

| 傳給 Kong 的請求 | 上游服務 |
|---|---|
| `GET /` | FastMCP 服務資訊 |
| `/orders`、`/inventory`、`/shipments`、`/docs`、`/openapi.json` | FastAPI |
| `/mcp` | FastMCP Streamable HTTP |

Compose 只把 Kong 的代理埠開在本機迴環介面，並停用 Kong Admin API。這套本機範例的 MCP 端點沒有客戶端驗證。使用範例金鑰時，請維持預設的本機綁定。FastAPI 會驗證 REST 操作的 `x-api-key`，取消訂單還需要 `x-manager-key`。FastMCP 從自己的環境變數取得 REST 金鑰。

## 1. 啟動服務

需要已啟動的 Docker Engine 和 Docker Compose 外掛。以下指令都從專案根目錄執行。

```sh
docker compose version
docker compose -f kong/compose.yaml config --quiet
docker compose -f kong/compose.yaml up --build -d --wait
docker compose -f kong/compose.yaml ps
```

首次建置會下載 Kong 與 Python 映像檔，並安裝範例依賴。等待三個服務都顯示健康。預設入口為 `http://127.0.0.1:18000`。若該埠已被占用，先執行 `export KONG_DEMO_PORT=18001` 再啟動，並將以下範例改為該埠。若要更換範例金鑰，請在啟動前設定 `REST_API_KEY` 和 `MANAGER_KEY`。Compose 會將同一把 REST 金鑰傳給 FastAPI 與 FastMCP。

## 2. 透過 Kong 呼叫 REST API

```sh
export KONG_BASE=http://127.0.0.1:18000
export REST_API_KEY="${REST_API_KEY:-demo-rest-secret}"

curl -i "$KONG_BASE/"
curl -i "$KONG_BASE/orders"
curl -fsS "$KONG_BASE/orders" -H "x-api-key: $REST_API_KEY"
curl -fsS "$KONG_BASE/inventory" -H "x-api-key: $REST_API_KEY"
```

根路徑應回傳 HTTP 200 並顯示 MCP 路徑。查詢訂單時缺少金鑰會回傳 HTTP 401。使用正確金鑰查詢全新的資料庫，會看到 `ORD-1001`、`ORD-1002` 及 `SKU-A01` 的 8 件庫存。

從瀏覽器開啟 `$KONG_BASE/docs`，可經由 Kong 使用 Swagger UI。展開 **POST /orders**，點選 **Try it out**，填入 `x-api-key` 並送出下列內容。也可以直接用終端機操作。

```sh
curl -i -X POST "$KONG_BASE/orders" \
  -H "x-api-key: $REST_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"sku":"SKU-A01","quantity":2}'
```

從 HTTP 201 的回應複製 `orderId`。新訂單狀態為 `PAID`，庫存會在出貨時扣除。

## 3. 透過 Kong 探索 MCP 工具與核准出貨

啟用專案的 Python 虛擬環境，或先依照[主說明文件](../README-zh-tw.md)安裝依賴。保持 Compose 運行，將客戶端的 URL 指向 Kong。

```sh
export MCP_URL="$KONG_BASE/mcp"
python client.py
ORDER_ID='paste-order-id-here'
python approve_shipment.py "$ORDER_ID"
```

執行最後一行前，把 `ORDER_ID` 設為實際的 `orderId`。在提示中輸入 `YES`。預期會收到該訂單狀態為 `CREATED` 的出貨紀錄，再查詢 `/inventory` 時可看到庫存減少。

客戶端應能找到 `list_order`、`get_order`、`list_sku`、`check_inventory` 和 `create_shipment`。新增及取消訂單可透過 REST 操作。出貨確認由範例客戶端執行，能存取工具的呼叫端可直接呼叫它。多人共用環境需要另外設定授權和核准機制。

MCP 路由保留 `/mcp` 路徑，讓客戶端使用工作階段需要的 HTTP 方法，並停用請求和回應緩衝以支援串流。兩個上游服務皆停用代理層重試。 [Kong 路由](https://developer.konghq.com/gateway/entities/route/)、[Kong 服務](https://developer.konghq.com/gateway/entities/service/)

## 4. 排查問題與清理

| 現象 | 檢查方式 |
|---|---|
| 連接埠已被占用 | 改用其他 `KONG_DEMO_PORT`，並同步更新 `KONG_BASE` 與 `MCP_URL`。 |
| REST 回傳 401 或取消訂單回傳 403 | 檢查 `x-api-key`，取消訂單另需檢查 `x-manager-key`。 |
| Kong 回傳 502、503 或 504 | 檢查上游服務的健康狀態和日誌。 |
| MCP 交握或串流失敗 | 確認客戶端連到 `/mcp`，路由保留原路徑且關閉緩衝。用瀏覽器單獨開啟 `/mcp` 不會建立 MCP 工作階段。 |
| 出貨回傳 409 | 檢查訂單狀態、是否已有出貨紀錄，以及庫存是否足夠。 |

```sh
docker compose -f kong/compose.yaml logs --tail=100 kong rest mcp
docker compose -f kong/compose.yaml exec kong kong config parse /etc/kong/kong.yaml
```

編輯 `kong/kong.yaml` 後，重新建立 Kong 容器以讀取新的宣告式設定。

```sh
docker compose -f kong/compose.yaml up -d --force-recreate --wait kong
```

如需重置範例資料，在 REST 容器內執行既有腳本。它會清除這套服務的 SQLite 訂單、庫存及出貨紀錄，再還原範例資料。

```sh
docker compose -f kong/compose.yaml exec rest python reset_demo_db.py
```

用 `docker compose -f kong/compose.yaml down` 停止服務並保留 SQLite 磁碟區。若要同時刪除範例磁碟區，使用 `docker compose -f kong/compose.yaml down --volumes`。

## 選用 Kong 原生 REST 轉 MCP

原生 AI MCP Proxy 外掛需要 Kong AI Gateway Enterprise 授權，最低支援 Kong Gateway 3.12。在符合條件的環境，可先另建一條 MCP Route 驗證，於該 Route 掛上 `conversion-listener` 模式的外掛，並將其 Kong Service 指向 FastAPI。若使用 `/native-mcp` 等前綴路由，啟用 `strip_path` 並使用 `orders` 等相對工具路徑，讓 FastAPI 收到 `/orders`。依照外掛 schema 描述路徑參數及出貨請求本文。 [AI MCP Proxy](https://developer.konghq.com/plugins/ai-mcp-proxy/)、[外掛設定參考](https://developer.konghq.com/plugins/ai-mcp-proxy/reference/)

在原生 MCP Route 只設定這些工具。

| MCP 工具 | REST 操作 |
|---|---|
| `list_order` | `GET /orders` |
| `get_order` | `GET /orders/{order_id}` |
| `list_sku` | `GET /inventory` |
| `check_inventory` | `GET /inventory/{sku}` |
| `create_shipment` | `POST /shipments`，JSON 本文包含 `order_id` |

新增與取消訂單保留在 REST 路徑。在 MCP Route 驗證客戶端，透過部署環境的受保護設定供應上游 REST 金鑰，主管金鑰留在 REST 路徑，出貨仍保留人工核准。切換客戶端前先檢查原生 listener 回傳的工具 schema，因為外掛的參數結構可能與 FastMCP 不同。上面的 Compose 範例使用開源代理路徑。
