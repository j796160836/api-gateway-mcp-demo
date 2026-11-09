"""Demonstrate MCP discovery and invocation, without an LLM or cloud account."""
from config import MCP_URL
from demo_mcp import Client, run_client

async def main():
    async with Client(MCP_URL, timeout=20, init_timeout=5) as client:
        tools = await client.list_tools()
        print("Available MCP tools:", [t.name for t in tools])
        print("list_order:", await client.call_tool("list_order", {}))
        print("list_sku:", await client.call_tool("list_sku", {}))
        print("get_order:", await client.call_tool("get_order", {"order_id": "ORD-1001"}))
        print("check_inventory:", await client.call_tool("check_inventory", {"sku": "SKU-A01"}))
        print("\nCancel order tool exposed?", any(t.name == "cancel_order" for t in tools))
        print("\nMutation deliberately NOT called automatically.")
        print("To approve a shipment, run: python approve_shipment.py ORD-1001")

if __name__ == "__main__":
    run_client(main)
