"""An explicit human approval step for an operation that changes backend state."""
import argparse

from config import MCP_URL
from demo_mcp import Client, run_client


async def main(order_id):
    response = input(f"Create shipment for {order_id}? Type YES to approve: ")
    if response != "YES":
        print("Cancelled")
        return
    async with Client(MCP_URL, timeout=20, init_timeout=5) as client:
        print(await client.call_tool("create_shipment", {"order_id": order_id}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Approve a shipment for an order.")
    parser.add_argument("order_id", nargs="?", default="ORD-1001", help="Order ID (default: %(default)s)")
    args = parser.parse_args()
    run_client(lambda: main(args.order_id))
