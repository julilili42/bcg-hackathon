"""Azure Functions entry point: the FastAPI app served through the ASGI adapter.

Locally you can run the same app with ``uvicorn reach.app:create_app --factory`` and never need
Azure Functions Core Tools. ``host.json`` sets an empty route prefix so paths match in both.
"""

import azure.functions as func

from reach.app import create_app

app = func.AsgiFunctionApp(app=create_app(), http_auth_level=func.AuthLevel.ANONYMOUS)
