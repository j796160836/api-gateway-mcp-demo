"""REST entry point for the private, IAM-authenticated Cloud Run service."""
from api import app as order_api
from config import REST_API_KEY


async def app(scope, receive, send):
    if scope["type"] == "http":
        # Cloud Run IAM authenticates the caller before invoking this application.
        # Replace the public gateway credential with the existing REST service key.
        headers = [(name, value) for name, value in scope["headers"] if name.lower() != b"x-api-key"]
        scope = {**scope, "headers": [*headers, (b"x-api-key", REST_API_KEY.encode())]}
    await order_api(scope, receive, send)
