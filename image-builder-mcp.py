import os
import json
from datetime import datetime, timedelta
from typing import Annotated, Optional, Dict, Any
from pydantic import Field
import requests
from fastmcp import FastMCP, Context

# this text describes the context used for all tool-fuctions here
GENERAL_INTRO = "function for Redhat console.redhat.com image-builder. aka osbuild.org"

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

class ImageBuilderMCP(FastMCP):
    def __init__(self, client_id: str, client_secret: str, default_response_size: int = 10):
        super().__init__("Image Builder MCP Server")
        self.client = ImageBuilderClient(client_id, client_secret)
        self.blueprints = None
        self.composes = None
        self.blueprint_current_index = 0

        self.default_response_size = default_response_size
        
        # Register all tools
        self.tool()(self.get_blueprints)
        self.tool()(self.get_more_blueprints)
        self.tool()(self.get_blueprint_details)
        self.tool()(self.get_composes)
        self.tool()(self.get_compose)

    def get_blueprints(self, response_size: int|None = None) -> str:
        f"""
        {GENERAL_INTRO}
        Get all blueprints without details.
        For "all" set "response_size" to None
        This starts a fresh search.

        Args:
            response_size: number of items returned (optional)

        Returns:
            List of blueprints

        Raises:
            Exception: If the image-builder connection fails.
        """
        response_size = response_size or self.default_response_size
        if response_size <= 0:
            response_size = self.default_response_size
        try:
            response = self.client.make_request("blueprints")
            ret = []
            i = 1
            self.blueprints = []
            for blueprint in response["data"]:
                data = {"reply_id": i,
                        "blueprint_uuid": blueprint["id"],
                        "name": blueprint["name"]}

                self.blueprints.append(data)
                
                if i <= response_size:
                    ret.append(data)

                i += 1
            self.blueprint_current_index = min(i, response_size)
            intro = ""
            if len(self.blueprints) > len(ret):
                intro = f"Only {len(ret)} out of {len(self.blueprints)} returned. Ask for more if needed:"
            else:
                intro = f"All {len(ret)} entries. There are no more."
            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_more_blueprints(self, response_size: int|None = None) -> str:
        f"""
        {GENERAL_INTRO}
        Get more blueprints without details. To be called after get_blueprints if the user wants more.

        Args:
            response_size: number of items returned (optional)

        Returns:
            List of blueprints

        Raises:
            Exception: If the image-builder connection fails.
        """
        response_size = response_size or self.default_response_size
        try:
            if not self.blueprints:
                self.get_blueprints()

            if self.blueprint_current_index >= len(self.blueprints):
                return "There are no more blueprints. Should I start a fresh search?"

            i = 1
            ret = []
            for blueprint in self.blueprints:
                i += 1
                if i > self.blueprint_current_index and i <= (self.blueprint_current_index + response_size):
                    ret.append(blueprint)

            self.blueprint_current_index = min(self.blueprint_current_index + len(ret), len(self.blueprints))

            intro = ""
            if len(self.blueprints) > len(ret):
                intro = f"Only {len(ret)} out of {len(self.blueprints)} returned. Ask for more if needed:"
            else:
                intro = f"All {len(ret)} entries. There are no more."
            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_blueprint_details(self, blueprint_uuid: str) -> str:
        f"""
        {GENERAL_INTRO}
        Get details of a specific blueprint by UUID. Always provide a blueprint_uuid here. Not the name of the blueprint.
        
        Args:
            blueprint_uuid: the UUID to query

        Returns:
            Blueprint details

        Raises:
            Exception: If the image-builder connection fails.
        """
        if not blueprint_uuid:
            return "Error: Blueprint UUID is required"
        try:
            if not self.blueprints:
                self.get_blueprints("")
            uuids = []
            for b in self.blueprints:
                if b["name"] == blueprint_uuid:
                    uuids.append(b["blueprint_uuid"])
                elif b["blueprint_uuid"] == blueprint_uuid:
                    uuids.append(b["blueprint_uuid"])
                elif b["reply_id"] == blueprint_uuid:
                    uuids.append(b["blueprint_uuid"])
            ret = []
            for uuid in uuids:
                response = self.client.make_request(f"blueprints/{blueprint_uuid}")
                # TBD filter irrelevant attributes
                ret.append(response)

            intro = ""
            if len(uuids) == 0:
                intro = f"No blueprint found for '{blueprint_uuid}'.\n"
            elif len(uuids) > 1:
                intro = f"Found {len(ret)} blueprints for '{blueprint_uuid}'.\n"

            return f"{intro}{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_composes(self, username: str|None) -> str:
        f"""
        {GENERAL_INTRO}
        Get all composes.

        Args:
            username: dummy parameter to avoid typing problems with Langflow

        Returns:
            List of composes

        Raises:
            Exception: If the image-builder connection fails.
        """
        try:
            response = self.client.make_request("composes")

            ret = []
            x = 1
            for compose in response["data"]:
                ret.append({"reply_id": x,
                            "compose_uuid": compose["id"],
                            "image_name": compose["image_name"]})
                x += 1
                # TBD: think about paging?
                if x > 10:
                    break
            self.composes = ret
            return json.dumps(ret)
        except Exception as e:
            return f"Error: {str(e)}"

    def get_compose(self, compose_uuid: str = None) -> str:
        f"""
        {GENERAL_INTRO}
        Get a specific compose by UUID.
        
        Args:
            compose_uuid: the UUID to query

        Returns:
            Compose details

        Raises:
            Exception: If the image-builder connection fails.
        """
        if not compose_uuid:
            return "Error: Compose UUID is required"
        try:
            if not self.composes:
                self.get_composes("")
            for c in self.composes:
                if c["image_name"].lower() == compose_uuid.lower():
                    compose_uuid = c["compose_uuid"]
                    break
            return json.dumps(self.client.make_request(f"composes/{compose_uuid}"), indent=2)
        except Exception as e:
            return f"Error: {str(e)}"

if __name__ == "__main__":
    # Get credentials from environment variables or user input
    client_id = os.getenv("IMAGE_BUILDER_CLIENT_ID")
    client_secret = os.getenv("IMAGE_BUILDER_CLIENT_SECRET")

    if not client_id:
        client_id = input("Enter your Image Builder client ID: ")
    if not client_secret:
        client_secret = input("Enter your Image Builder client secret: ")

    # Create and run the MCP server
    mcp_server = ImageBuilderMCP(client_id, client_secret)
    mcp_server.run(transport="sse", host="127.0.0.1", port=9000)
