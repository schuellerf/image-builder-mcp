import os
import json
from datetime import datetime, timedelta
from typing import Annotated, Optional, Dict, Any
from pydantic import Field
import requests
from fastmcp import FastMCP, Context

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
        ret = response.json()
        return ret

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

blueprints = None

@mcp.tool()
def get_blueprints(dummy: str|None = "") -> str:
    """
    Get all blueprints without details. Always use blueprint_uuid for followup calls.

    Args:
        dummy: Avoid typing problems with Langflow

    Returns:
        List of blueprints

    Raises:
        Exception: If the image-builder connection fails.
    """
    global blueprints
    try:
        response = client.make_request("blueprints")
        ret = []
        x = 1
        for blueprint in response["data"]:
            ret.append({"reply_id": x,
                        "blueprint_uuid": blueprint["id"],
                        "name": blueprint["name"]})
            x += 1
            # TBD: think about paging?
            if x > 10:
                break
        blueprints = ret
        return json.dumps(ret)
    except Exception as e:
        return f"Error: {str(e)}"

# not sure what is the best way so the LLM knows to do
# get_blueprints() first, then get_blueprint_details
#@mcp.tool()
def get_blueprint_uuid(dummy: str|None, reply_id: int) -> str:
    """Get a UUID for a response of get_blueprints to be used with get_blueprint"""
    global blueprints
    if not blueprints:
        get_blueprints("")
    if len(blueprints) >= reply_id:
        return json.dumps(blueprints[reply_id])
    else:
        return f"I couldn't find the blueprint #{reply_id}"

@mcp.tool()
def get_blueprint_details(blueprint_uuid: str) -> str:
    """Get details of a specific blueprint by UUID. Always provide a blueprint_uuid here. Not the name of the blueprint."""
    if not blueprint_uuid:
        return "Error: Blueprint UUID is required"
    try:
        return json.dumps(client.make_request(f"blueprints/{blueprint_uuid}"), indent=2)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_composes(dummy: str|None = "") -> str:
    """Get all composes."""
    try:
        return json.dumps(client.make_request("composes"), indent=2)
    except Exception as e:
        return f"Error: {str(e)}"

@mcp.tool()
def get_compose(compose_uuid: str) -> str:
    """Get a specific compose by UUID."""
    if not compose_uuid:
        return "Error: Compose UUID is required"
    try:
        return json.dumps(client.make_request(f"composes/{compose_uuid}"), indent=2)
    except Exception as e:
        return f"Error: {str(e)}"

if __name__ == "__main__":
    mcp.run(transport="sse", host="127.0.0.1", port=9000)
