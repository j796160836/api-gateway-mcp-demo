"""Existing REST service. MCP unaware by design."""
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from config import MANAGER_KEY, REST_API_KEY
from database import connect, initialize


@asynccontextmanager
async def lifespan(app: FastAPI):
    initialize()
    yield


app = FastAPI(title="Existing Order REST API", version="1.0.0", lifespan=lifespan)


def auth(x_api_key: str | None):
    if x_api_key != REST_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid REST API key")


def order_response(order):
    result = dict(order)
    if result["cancellationReason"] is None:
        del result["cancellationReason"]
    return result


def find_order(db, order_id):
    order = db.execute("SELECT * FROM orders WHERE orderId = ?", (order_id,)).fetchone()
    if order is None:
        raise HTTPException(404, "Order not found")
    return order


def has_shipment(db, order_id):
    return db.execute("SELECT 1 FROM shipments WHERE orderId = ?", (order_id,)).fetchone() is not None


class ShipmentRequest(BaseModel):
    order_id: str = Field(description="Order ID, e.g. ORD-1001")


class OrderRequest(BaseModel):
    sku: str = Field(min_length=1, examples=["SKU-A01"])
    quantity: int = Field(strict=True, gt=0, le=2**63 - 1, examples=[2])


@app.get("/", include_in_schema=False)
async def service_info():
    return {"service": app.title, "docs": "/docs", "openapi": "/openapi.json"}


@app.get("/orders", operation_id="list_order", description="List orders and their current status.")
def list_order(x_api_key: str | None = Header(None)):
    auth(x_api_key)
    with connect() as db:
        return {"orders": [order_response(order) for order in db.execute("SELECT * FROM orders ORDER BY orderId")]}


@app.post(
    "/orders",
    operation_id="create_order",
    status_code=201,
    description="Create a paid demo order. Stock is deducted when the order ships.",
)
def create_order(data: OrderRequest, x_api_key: str | None = Header(None)):
    auth(x_api_key)
    with connect(write=True) as db:
        if db.execute("SELECT 1 FROM inventory WHERE sku = ?", (data.sku,)).fetchone() is None:
            raise HTTPException(404, "SKU not found")
        order_id = f"ORD-{uuid4().hex}"
        db.execute(
            "INSERT INTO orders (orderId, status, sku, quantity) VALUES (?, 'PAID', ?, ?)",
            (order_id, data.sku, data.quantity),
        )
        return order_response(find_order(db, order_id))


@app.get("/orders/{order_id}", operation_id="get_order", description="Look up an order by ID before checking its inventory.")
def get_order(order_id: str, x_api_key: str | None = Header(None)):
    auth(x_api_key)
    with connect() as db:
        return order_response(find_order(db, order_id))


@app.get("/inventory", operation_id="list_sku", description="List SKUs and their available inventory.")
def list_sku(x_api_key: str | None = Header(None)):
    auth(x_api_key)
    with connect() as db:
        return {"skus": [dict(row) for row in db.execute("SELECT * FROM inventory ORDER BY sku")]}


@app.get("/inventory/{sku}", operation_id="check_inventory", description="Check available inventory for an order SKU.")
def check_inventory(sku: str, x_api_key: str | None = Header(None)):
    auth(x_api_key)
    with connect() as db:
        inventory = db.execute("SELECT * FROM inventory WHERE sku = ?", (sku,)).fetchone()
        if inventory is None:
            raise HTTPException(404, "SKU not found")
        return dict(inventory)


@app.post("/shipments", operation_id="create_shipment", description="Create a shipment for a paid order if stock is available; requires human approval before calling.")
def create_shipment(data: ShipmentRequest, x_api_key: str | None = Header(None)):
    auth(x_api_key)
    with connect(write=True) as db:
        order = find_order(db, data.order_id)
        if order["status"] != "PAID":
            raise HTTPException(409, "Only paid orders can be shipped")
        if has_shipment(db, data.order_id):
            raise HTTPException(409, "Shipment already exists")
        updated = db.execute(
            "UPDATE inventory SET available = available - ? WHERE sku = ? AND available >= ?",
            (order["quantity"], order["sku"], order["quantity"]),
        )
        if updated.rowcount == 0:
            raise HTTPException(409, "Insufficient stock")
        shipment = db.execute(
            "INSERT INTO shipments (orderId, status) VALUES (?, 'CREATED')",
            (data.order_id,),
        )
        return {"shipmentId": f"SHP-{shipment.lastrowid:04d}", "orderId": data.order_id, "status": "CREATED"}


class CancellationRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@app.post("/orders/{order_id}/cancel", operation_id="cancel_order")
def cancel_order(
    order_id: str,
    data: CancellationRequest,
    x_api_key: str | None = Header(None),
    x_manager_key: str | None = Header(None),
):
    auth(x_api_key)
    if x_manager_key != MANAGER_KEY:
        raise HTTPException(403, "Manager approval required")
    with connect(write=True) as db:
        order = find_order(db, order_id)
        if order["status"] != "PAID":
            raise HTTPException(409, "Only paid orders can be cancelled")
        if has_shipment(db, order_id):
            raise HTTPException(409, "Shipment already exists")
        reason = data.reason.strip()
        if not reason:
            raise HTTPException(422, "Cancellation reason is required")
        db.execute(
            "UPDATE orders SET status = 'CANCELLED', cancellationReason = ? WHERE orderId = ?",
            (reason, order_id),
        )
        return order_response(find_order(db, order_id))
