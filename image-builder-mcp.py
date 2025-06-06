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

GENERAL_INTRO = "Function for Redhat console.redhat.com image-builder osbuild.org. Interacting with the production API."

class ImageBuilderMCP(FastMCP):
    def __init__(self, client_id: str, client_secret: str, default_response_size: int = 10):
        super().__init__("Image Builder MCP Server")
        self.client = ImageBuilderClient(client_id, client_secret)
        self.blueprints = None
        self.composes = None
        self.blueprint_current_index = 0
        self.compose_current_index = 0

        self.default_response_size = default_response_size
        # prepend generic keywords for use of many other tools
        # and register with "self.tool()"
        tool_functions = [self.get_blueprints,
                          self.get_more_blueprints,
                          self.get_blueprint_details,
                          self.get_composes,
                          self.get_more_composes,
                          self.get_compose_details]
        for f in tool_functions:
            self.tool(
                description=f.__doc__.format(GENERAL_INTRO=GENERAL_INTRO),
                annotations={
                    "readOnlyHint": True,
                    "openWorldHint": True
                }
                )(f)

    def get_blueprints(self, response_size: int, search_string: str|None = None) -> str:
        """{GENERAL_INTRO}
        Get all blueprints without details.
        For "all" set "response_size" to None
        This starts a fresh search.

        Args:
            response_size: number of items returned (use 7 as default)
            search_string: substring to search for in the name (optional)

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

            # Sort data by created_at
            sorted_data = sorted(response["data"],
                               key=lambda x: x.get("last_modified_at", ""),
                               reverse=True)

            ret = []
            i = 1
            self.blueprints = []
            for blueprint in sorted_data:
                data = {"reply_id": i,
                        "blueprint_uuid": blueprint["id"],
                        "UI_URL": f"https://console.redhat.com/insights/image-builder/imagewizard/{blueprint["id"]}",
                        "name": blueprint["name"]}

                self.blueprints.append(data)

                if len(ret) < response_size:
                    if search_string:
                        if search_string.lower() in data["name"].lower():
                            ret.append(data)
                    else:
                        ret.append(data)

                i += 1
            self.blueprint_current_index = min(i, response_size)
            intro = "[INSTRUCTION] Use the UI_URL to link to the blueprint\n"
            if len(self.blueprints) > len(ret):
                intro += f"Only {len(ret)} out of {len(self.blueprints)} returned. Ask for more if needed:"
            else:
                intro += f"All {len(ret)} entries. There are no more."
            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"


    def get_more_blueprints(self, response_size: int, search_string: str|None = None) -> str:
        """{GENERAL_INTRO}
        Get more blueprints without details. To be called after get_blueprints if the user wants more.

        Args:
            response_size: number of items returned (use 7 as default)
            search_string: substring to search for in the name (optional)

        Returns:
            List of blueprints

        Raises:
            Exception: If the image-builder connection fails.
        """
        response_size = response_size or self.default_response_size
        if response_size <= 0:
            response_size = self.default_response_size
        try:
            if not self.blueprints:
                self.get_blueprints()

            if self.blueprint_current_index >= len(self.blueprints):
                return "There are no more blueprints. Should I start a fresh search?"

            i = 1
            ret = []
            for blueprint in self.blueprints:
                i += 1
                if i > self.blueprint_current_index and len(ret) < response_size:
                    if search_string:
                        if search_string.lower() in blueprint["name"].lower():
                            ret.append(blueprint)
                    else:
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

    def get_blueprint_details(self, blueprint_identifier: str) -> str:
        """{GENERAL_INTRO}
        Get blueprint details.

        Args:
            blueprint_identifier: the UUID, name or reply_id to query

        Returns:
            Blueprint details

        Raises:
            Exception: If the image-builder connection fails.
        """
        if not blueprint_identifier:
            return "Error: a blueprint identifier is required"
        try:
            if not self.blueprints:
                self.get_blueprints("")

            # Find matching blueprints using filter
            matching_blueprints = list(filter(
                lambda b: (b["name"] == blueprint_identifier or
                          b["blueprint_uuid"] == blueprint_identifier or
                          str(b["reply_id"]) == blueprint_identifier),
                self.blueprints
            ))

            # Get details for each matching blueprint
            ret = []
            for blueprint in matching_blueprints:
                response = self.client.make_request(f"blueprints/{blueprint['blueprint_uuid']}")
                # TBD filter irrelevant attributes
                ret.append(response)

            # Prepare response message
            intro = ""
            if len(matching_blueprints) == 0:
                intro = f"No blueprint found for '{blueprint_identifier}'.\n"
            elif len(matching_blueprints) > 1:
                intro = f"Found {len(ret)} blueprints for '{blueprint_identifier}'.\n"

            return f"{intro}{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"


    def get_composes(self, response_size: int, search_string: str|None = None) -> str:
        """{GENERAL_INTRO}
        Get all composes without details.
        For "all" set "response_size" to None
        This starts a fresh search.

        Args:
            response_size: number of items returned (use 7 as default)
            search_string: substring to search for in the name (optional)

        Returns:
            List of composes

        Raises:
            Exception: If the image-builder connection fails.
        """
        response_size = response_size or self.default_response_size
        if response_size <= 0:
            response_size = self.default_response_size
        try:
            response = self.client.make_request("composes")

            # Sort data by created_at
            sorted_data = sorted(response["data"],
                               key=lambda x: x.get("created_at", ""),
                               reverse=True)

            ret = []
            i = 1
            self.composes = []
            for compose in sorted_data:
                data = {"reply_id": i,
                        "compose_uuid": compose["id"],
                        "image_name": compose["image_name"]}

                self.composes.append(data)

                if len(ret) < response_size:
                    if search_string:
                        if search_string.lower() in data["image_name"].lower():
                            ret.append(data)
                    else:
                        ret.append(data)

                i += 1
            self.compose_current_index = min(i, response_size)
            intro = ""
            if len(self.composes) > len(ret):
                intro = f"Only {len(ret)} out of {len(self.composes)} returned. Ask for more if needed:"
            else:
                intro = f"All {len(ret)} entries. There are no more."
            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_more_composes(self, response_size: int, search_string: str|None = None) -> str:
        """{GENERAL_INTRO}
        Get more composes without details. To be called after get_composes if the user wants more.

        Args:
            response_size: number of items returned (use 7 as default)
            search_string: substring to search for in the name (optional)

        Returns:
            List of composes

        Raises:
            Exception: If the image-builder connection fails.
        """
        response_size = response_size or self.default_response_size
        if response_size <= 0:
            response_size = self.default_response_size
        try:
            if not self.composes:
                self.get_composes()

            if self.compose_current_index >= len(self.composes):
                return "There are no more composes. Should I start a fresh search?"

            # Filter composes if search_string is provided
            filtered_composes = self.composes
            if search_string:
                search_lower = search_string.lower()
                filtered_composes = list(filter(
                    lambda c: search_lower in c["image_name"].lower(),
                    self.composes
                ))

            # Get the next batch of items
            ret = filtered_composes[self.compose_current_index:self.compose_current_index + response_size]
            self.compose_current_index = min(self.compose_current_index + len(ret), len(self.composes))

            # Prepare response message
            intro = ""
            if len(filtered_composes) > self.compose_current_index:
                intro = f"Only {len(ret)} out of {len(filtered_composes)} returned. Ask for more if needed:"
            else:
                intro = f"All {len(ret)} entries. There are no more."

            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_compose_details(self, compose_identifier: str) -> str:
        """{GENERAL_INTRO}
        Get compose details.

        Args:
            compose_identifier: the UUID, name or reply_id to query

        Returns:
            Compose details

        Raises:
            Exception: If the image-builder connection fails.
        """
        if not compose_identifier:
            return "Error: Compose UUID is required"
        try:
            if not self.composes:
                self.get_composes()

            # Find matching composes using filter
            matching_composes = list(filter(
                lambda c: (c["image_name"] == compose_identifier or
                          c["compose_uuid"] == compose_identifier or
                          str(c["reply_id"]) == compose_identifier),
                self.composes
            ))

            # Get details for each matching compose
            ret = []
            for compose in matching_composes:
                response = self.client.make_request(f"composes/{compose['compose_uuid']}")
                # TBD filter irrelevant attributes
                ret.append(response)

            # Prepare response message
            intro = ""
            if len(matching_composes) == 0:
                intro = f"No compose found for '{compose_identifier}'.\n"
            elif len(matching_composes) > 1:
                intro = f"Found {len(ret)} composes for '{compose_identifier}'.\n"

            return f"{intro}{json.dumps(ret)}"
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
