import os
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from fastmcp import FastMCP, Request, Response
from fastmcp.sse import SSEResponse

class ImageBuilderClient:
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = None
        self.base_url = "https://console.redhat.com/api/image-builder/v1"
        
    def get_token(self) -> str:
        """Get or refresh the authentication token."""
        if self.token and self.token_expiry and datetime.now() < self.token_expiry:
            return self.token
            
        token_url = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        
        token_data = response.json()
        self.token = token_data["access_token"]
        # Set token expiry to 5 minutes before actual expiry to ensure we refresh in time
        self.token_expiry = datetime.now() + timedelta(seconds=token_data["expires_in"] - 300)
        
        return self.token
    
    def make_request(self, endpoint: str, method: str = "GET", data: Optional[Dict] = None) -> Dict[str, Any]:
        """Make an authenticated request to the Image Builder API."""
        headers = {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json"
        }
        
        url = f"{self.base_url}/{endpoint}"
        response = requests.request(method, url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()

# Store active composes for easy reference
active_composes: Dict[str, str] = {}

def create_server(client_id: str, client_secret: str) -> FastMCP:
    client = ImageBuilderClient(client_id, client_secret)
    server = FastMCP()
    
    @server.route("/blueprints")
    def get_blueprints(request: Request) -> Response:
        """Get all blueprints."""
        try:
            blueprints = client.make_request("blueprints")
            return Response(json.dumps(blueprints))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)
    
    @server.route("/blueprints/{id}")
    def get_blueprint(request: Request) -> Response:
        """Get a specific blueprint by ID."""
        try:
            blueprint_id = request.path_params["id"]
            blueprint = client.make_request(f"blueprints/{blueprint_id}")
            return Response(json.dumps(blueprint))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)
    
    @server.route("/composes")
    def get_composes(request: Request) -> Response:
        """Get all composes."""
        try:
            composes = client.make_request("composes")
            return Response(json.dumps(composes))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)
    
    @server.route("/composes/{compose_id}")
    def get_compose(request: Request) -> Response:
        """Get a specific compose by ID."""
        try:
            compose_id = request.path_params["compose_id"]
            compose = client.make_request(f"composes/{compose_id}")
            return Response(json.dumps(compose))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)
    
    @server.route("/compose")
    def create_compose(request: Request) -> Response:
        """Create a new compose and store its ID for easy reference."""
        try:
            compose_data = request.json()
            result = client.make_request("compose", method="POST", data=compose_data)
            compose_id = result["id"]
            # Store compose ID with a friendly name
            friendly_name = f"compose_{len(active_composes) + 1}"
            active_composes[friendly_name] = compose_id
            return Response(json.dumps({
                "message": f"Compose created successfully. You can reference it as '{friendly_name}'",
                "compose_id": compose_id
            }))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)
    
    @server.route("/compose/{friendly_name}")
    def get_compose_by_friendly_name(request: Request) -> Response:
        """Get compose status using friendly name."""
        try:
            friendly_name = request.path_params["friendly_name"]
            if friendly_name not in active_composes:
                return Response(json.dumps({"error": "Compose not found"}), status=404)
            
            compose_id = active_composes[friendly_name]
            compose = client.make_request(f"composes/{compose_id}")
            return Response(json.dumps(compose))
        except Exception as e:
            return Response(json.dumps({"error": str(e)}), status=500)
    
    return server

def main():
    # Get credentials from environment variables or user input
    client_id = os.getenv("IMAGE_BUILDER_CLIENT_ID")
    client_secret = os.getenv("IMAGE_BUILDER_CLIENT_SECRET")
    
    if not client_id:
        client_id = input("Enter your Image Builder client ID: ")
    if not client_secret:
        client_secret = input("Enter your Image Builder client secret: ")
    
    server = create_server(client_id, client_secret)
    
    # Start the server with SSE support
    server.run(host="0.0.0.0", port=9000, sse=True)

if __name__ == "__main__":
    main()
