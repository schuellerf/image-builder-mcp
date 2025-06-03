import os
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import requests
from fastmcp import FastMCP

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

# Initialize FastMCP
mcp = FastMCP("Image Builder MCP Server")

# Get credentials from environment variables or user input
client_id = os.getenv("IMAGE_BUILDER_CLIENT_ID")
client_secret = os.getenv("IMAGE_BUILDER_CLIENT_SECRET")

if not client_id:
    client_id = input("Enter your Image Builder client ID: ")
if not client_secret:
    client_secret = input("Enter your Image Builder client secret: ")

client = ImageBuilderClient(client_id, client_secret)

@mcp.tool()
async def get_blueprints():
    """Get all blueprints."""
    try:
        blueprints = client.make_request("blueprints")
        return {"data": blueprints}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_blueprint(blueprint_id: str):
    """Get a specific blueprint by ID."""
    try:
        blueprint = client.make_request(f"blueprints/{blueprint_id}")
        return {"data": blueprint}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_composes():
    """Get all composes."""
    try:
        composes = client.make_request("composes")
        return {"data": composes}
    except Exception as e:
        return {"error": str(e)}

@mcp.tool()
async def get_compose(compose_id: str):
    """Get a specific compose by ID."""
    try:
        compose = client.make_request(f"composes/{compose_id}")
        return {"data": compose}
    except Exception as e:
        return {"error": str(e)}

if __name__ == "__main__":
    mcp.run(transport="sse", host="127.0.0.1", port=9000)
