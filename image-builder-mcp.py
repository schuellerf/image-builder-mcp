from contextlib import asynccontextmanager
import logging
import os
import json
from datetime import datetime, timedelta
import sys
from typing import Annotated, Optional, Dict, Any
import mcp
from pydantic import Field
import requests
from fastmcp import FastMCP, Context
import argparse
from fastmcp.server.dependencies import get_http_headers

class ImageBuilderClient:
    def __init__(
            self,
            client_id: str,
            client_secret: str,
            stage: bool = False,
            proxy_url: Optional[str] = None
            ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token = None
        self.token_expiry = None
        self.stage = stage
        self.proxy_url = proxy_url
        self.logger = logging.getLogger("ImageBuilderClient")

        if self.stage:
            self.domain = "console.stage.redhat.com"
            self.sso_domain = "sso.stage.redhat.com"
        else:
            self.domain = "console.redhat.com"
            self.sso_domain = "sso.redhat.com"
        self.base_url = f"https://{self.domain}/api/image-builder/v1"


    def get_token(self) -> str:
        """Get or refresh the authentication token."""
        if self.token and self.token_expiry and datetime.now() < self.token_expiry:
            self.logger.debug(f"Using cached token valid until {self.token_expiry}")
            return self.token
        self.logger.debug("Fetching new token")
        token_url = f"https://{self.sso_domain}/auth/realms/redhat-external/protocol/openid-connect/token"
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
            "Content-Type": "application/json"
        }
        if self.client_id and self.client_secret:
            headers["Authorization"] = f"Bearer {self.get_token()}"
        # else no authentication, use public API

        url = f"{self.base_url}/{endpoint}"
        self.logger.debug(f"Making {method} request to {url} with data {data}")

        proxies = None
        if self.stage and self.proxy_url:
            proxy = self.proxy_url
            proxies = {
                "http": proxy,
                "https": proxy
            }

        response = requests.request(method, url, headers=headers, json=data, proxies=proxies)
        response.raise_for_status()
        ret = response.json()
        self.logger.debug(f"Response from {url}: {ret}")

        return ret

# Store active composes for easy reference
active_composes: Dict[str, str] = {}


class ImageBuilderMCP(FastMCP):
    def __init__(
            self,
            client_id: str,
            client_secret: str,
            default_response_size: int = 10,
            stage: bool = False,
            proxy_url: Optional[str] = None):
        self.stage = stage
        self.proxy_url = proxy_url
        if stage:
            api_type = "stage"
        else:
            api_type = "production"

        self.logger = logging.getLogger("ImageBuilderMCP")

        general_intro = f"""Function for Redhat console.redhat.com image-builder osbuild.org.
        Interacting with the {api_type} API.
        Use this to create custom Redhat enterprise, Centos or Fedora Linux disk images."""

        super().__init__(
            name = "Image Builder MCP Server",
            instructions= general_intro
        )
        # could be used once we have e.g. "/distributions" available without authentication
        self.client_noauth = ImageBuilderClient(None, None, stage, proxy_url=proxy_url)

        # cache the client for all users
        # TBD: purge cache after some time
        self.clients = {}
        self.client_id = None
        self.client_secret = None
        if client_id and client_secret:
            self.clients[client_id] = ImageBuilderClient(client_id, client_secret, stage, proxy_url=proxy_url)
            self.client_id = client_id
            self.client_secret = client_secret

        self.blueprints = None
        self.composes = None
        self.blueprint_current_index = 0
        self.compose_current_index = 0

        self.register_tools()

    def register_tools(self):
        # prepend generic keywords for use of many other tools
        # and register with "self.tool()"
        tool_functions = [#self.get_openapi,
                          #self.create_blueprint,
                          self.get_blueprints,
                          self.get_more_blueprints,
                          self.get_blueprint_details,
                          self.get_composes,
                          self.get_more_composes,
                          self.get_compose_details,
                          self.compose]
        
        # use dynamic attributes to get the distributions, architectures and image types
        # once the API is changed to un-authenticated access
        # self.distributions = self.client_noauth.make_request("distributions")
        self.distributions = [
            {'description': 'CentOS Stream 9', 'name': 'centos-9'},
            {'description': 'Fedora Linux 37', 'name': 'fedora-37'},
            {'description': 'Fedora Linux 38', 'name': 'fedora-38'},
            {'description': 'Fedora Linux 39', 'name': 'fedora-39'},
            {'description': 'Fedora Linux 40', 'name': 'fedora-40'},
            {'description': 'Fedora Linux 41', 'name': 'fedora-41'},
            {'description': 'Fedora Linux 42', 'name': 'fedora-42'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 10 Beta', 'name': 'rhel-10-beta'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 10', 'name': 'rhel-10.0'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 10', 'name': 'rhel-10'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-8.10'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-8'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-84'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-85'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-86'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-87'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-88'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 8', 'name': 'rhel-89'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9 beta', 'name': 'rhel-9-beta'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-9.6'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-9'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-90'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-91'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-92'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-93'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-94'},
            {'description': 'Red Hat Enterprise Linux (RHEL) 9', 'name': 'rhel-95'}
        ]

        # TBD: get from openapi
        self.architectures = ["x86_64", "aarch64"]

        # TBD: get from openapi
        self.image_types = ["aws",
                            "azure",
                            "edge-commit",
                            "edge-installer",
                            "gcp",
                            "guest-image",
                            "image-installer",
                            "oci"
                            "vsphere",
                            "vsphere-ova",
                            "wsl",
                            "ami",
                            "rhel-edge-commit",
                            "rhel-edge-installer",
                            "vhd"]

        for f in tool_functions:
            self.add_tool(
                fn=f,
                description=f.__doc__.format(
                    distributions=", ".join([d['name'] for d in self.distributions]),
                    architectures=", ".join(self.architectures),
                    image_types=", ".join(self.image_types)
                ),
                annotations={
                    "readOnlyHint": True,
                    "openWorldHint": True
                }
                )

    def get_client(self, headers: Dict[str, str]) -> ImageBuilderClient:
        """Get the ImageBuilderClient instance for the current user."""
        if self.client_id and self.client_secret:
            # we have a global client_id and client_secret
            client_id = self.client_id
            client_secret = self.client_secret
        else:
            client_id = headers.get("x-client-id")
            client_secret = headers.get("x-client-secret")
        self.logger.debug(f"{headers}")
        if not client_id or not client_secret:
            raise ValueError("Client ID and secret are required to access the Image Builder API")
        client = self.clients.get(client_id)
        if not client:
            client = ImageBuilderClient(client_id, client_secret, stage=self.stage, proxy_url=self.proxy_url)
            self.clients[client_id] = client
        return client

    def no_auth_error(self, e: Exception) -> str:
        return f"[INSTRUCTION] Tell the user that the MCP server setup is not valid!" \
                    "The user should to go to https://console.redhat.com to `'YOUR USER' ➡ My User Access ➡ Service Accounts` "\
                    "create a service account and then set the " \
                    "header variables `x-client-ID` and `x-client-secret` in your request.\n" \
                    "Here is the direct link for the user's convenience: https://console.redhat.com/iam/service-accounts " \
                    "Come up with a detailed description of this for the user. " \
                    "Only describe this, don't expose details about the tool function itself." \
                    "Don't proceed with the request before this is fixed." \
                    "Error: {str(e)}."

    def compose(self,
                distribution: str,
                architecture: str = "x86_64",
                image_type: str = "guest-image",
                image_name: Optional[str] = None,
                image_description: Optional[str] = None) -> str:
        """Create a new operating system image. Assure that the data is according to ComposeRequest descriped in openapi.
        Ask user for more details to be able to fill "data" properly before calling this.

        Args:
            distribution: the distribution to use (ask for one of {distributions})
            architecture: the architecture to use (ask for one of {architectures})
            image_type: the type of image to create (ask for one of {image_types})
            image_name: optional name for the image (ask if the user wants to set this)
            image_description: optional description for the image (ask if the user wants to set this)
        """
        try:
            client = self.get_client(get_http_headers())
        except ValueError as e:
            return self.no_auth_error(e)

        data = {
            "distribution": distribution,
            "image_requests": [
                {
                    "architecture": architecture,
                    "image_type": image_type,
                    "upload_request": {
                        "type": "aws.s3",
                        "options": {}
                    }
                }
            ]
            #"customizations": {…}
        }
        if image_name:
            data["image_name"] = image_name
        else:
            # Generate a default image name based on distribution and architecture
            data["image_name"] = f"{distribution}-{architecture}-{image_type}-{datetime.now().strftime('%Y%m%d%H%M%S')}-mcp"
        if image_description:
            data["image_description"] = image_description
        else:
            # Generate a default image description
            data["image_description"] = f"Image created via image-builder-mcp on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        try:
            # TBD: programmatically check against openapi
            response = client.make_request("compose", method="POST", data=data)
            return f"Compose created successfully: {json.dumps(response)}"
        except Exception as e:
            return f"Error: {str(e)} for compose {json.dumps(data)}"

    def get_openapi(self, response_size: int) -> str:
        """Get OpenAPI spec. Use this to get details e.g for a new blueprint

        Args:
            response_size: number of items returned (use 7 as default)

        Returns:
            List of blueprints

        Raises:
            Exception: If the image-builder connection fails.
        """
        # response_size is just a dummy parameter for langflow
        try:
            response = self.client_noauth.make_request("openapi.json")
            return json.dumps(response)
        except Exception as e:
            return f"Error: {str(e)}"

    def create_blueprint(self, data: dict) -> str:
        """Create a new blueprint. Assure that the data is according to CreateBlueprintRequest descriped in openapi.
        Ask user for more details to be able to fill "data" properly before calling this.
        """
        try:
            client = self.get_client(get_http_headers())
        except ValueError as e:
            return self.no_auth_error(e)
        try:
            # TBD: programmatically check against openapi
            response = client.make_request("blueprints", method="POST", data=data)
        except Exception as e:
            return f"Error: {str(e)}"

    def get_blueprints(self, response_size: int, search_string: str|None = None) -> str:
        """Get all blueprints without details.
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

        try:
            client = self.get_client(get_http_headers())
        except ValueError as e:
            return self.no_auth_error(e)

        response_size = response_size or self.default_response_size
        if response_size <= 0:
            response_size = self.default_response_size
        try:
            response = client.make_request("blueprints")

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
                        "UI_URL": f"https://{client.domain}/insights/image-builder/imagewizard/{blueprint["id"]}",
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
            intro += f"[ANSWER]\n"
            if len(self.blueprints) > len(ret):
                intro += f"Only {len(ret)} out of {len(self.blueprints)} returned. Ask for more if needed:"
            else:
                intro += f"All {len(ret)} entries. There are no more."
            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"


    def get_more_blueprints(self, response_size: int, search_string: str|None = None) -> str:
        """Get more blueprints without details. To be called after get_blueprints if the user wants more.

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
        """Get blueprint details.

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

            try:
                client = self.get_client(get_http_headers())
            except ValueError as e:
                return self.no_auth_error(e)

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
                response = client.make_request(f"blueprints/{blueprint['blueprint_uuid']}")
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
        """Get all composes without details.
        Use this to get the latest image builds.
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
            try:
                client = self.get_client(get_http_headers())
            except ValueError as e:
                return self.no_auth_error(e)

            response = client.make_request("composes")

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
                        "blueprint_id": compose.get("blueprint_id", "N/A"),
                        "image_name": compose.get("image_name","")}

                if compose.get("blueprint_id"):
                    data["blueprint_url"] = f"https://{client.domain}/insights/image-builder/imagewizard/{compose['blueprint_id']}"
                else:
                    data["blueprint_url"] = "N/A"
                self.composes.append(data)

                if len(ret) < response_size:
                    if search_string:
                        if search_string.lower() in data["image_name"].lower():
                            ret.append(data)
                    else:
                        ret.append(data)

                i += 1
            self.compose_current_index = min(i, response_size)
            intro = "[INSTRUCTION] Present a bulleted list and use the blueprint_url to link to the blueprint which created this compose\n"
            if len(self.composes) > len(ret):
                intro += f"Only {len(ret)} out of {len(self.composes)} returned. Ask for more if needed:"
            else:
                intro += f"All {len(ret)} entries. There are no more."
            return f"{intro}\n{json.dumps(ret)}"
        except Exception as e:
            return f"Error: {str(e)}"

    def get_more_composes(self, response_size: int, search_string: str|None = None) -> str:
        """Get more composes without details. To be called after get_composes if the user wants more.

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
                    lambda c: search_lower in c.get("image_name","").lower(),
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
        """Get compose details especially for the status of an image build.

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
            try:
                client = self.get_client(get_http_headers())
            except ValueError as e:
                return self.no_auth_error(e)

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
                response = client.make_request(f"composes/{compose['compose_uuid']}")
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
    parser = argparse.ArgumentParser(description="Run Image Builder MCP server.")
    parser.add_argument("--sse", action="store_true", help="Use SSE transport instead of stdio")
    parser.add_argument("--host", default="127.0.0.1", help="Host for SSE transport (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9000, help="Port for SSE transport (default: 9000)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--stage", action="store_true", help="Use stage API instead of production API")
    args = parser.parse_args()

    # Get credentials from environment variables or user input
    client_id = os.getenv("IMAGE_BUILDER_CLIENT_ID")
    client_secret = os.getenv("IMAGE_BUILDER_CLIENT_SECRET")

    proxy_url = None
    if args.stage:
        proxy_url = os.getenv("IMAGE_BUILDER_STAGE_PROXY_URL")
        if not proxy_url:
            print("Please set IMAGE_BUILDER_STAGE_PROXY_URL to access the stage API")
            print("hint: IMAGE_BUILDER_STAGE_PROXY_URL=http://yoursquidproxy…:3128")
            sys.exit(1)

    if args.debug:
        log_file = "image-builder-mcp.log"
        file_handler = logging.FileHandler(log_file)
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        formatter = logging.Formatter(format)
        file_handler.setFormatter(formatter)
        loggers = [
            logging.getLogger("ImageBuilderMCP"),
            logging.getLogger("ImageBuilderClient")
            ]
        for logger in loggers:
            logger.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)
            logger.propagate = False

    # Create and run the MCP server
    mcp_server = ImageBuilderMCP(client_id, client_secret, stage=args.stage, proxy_url=proxy_url)

    if args.sse:
        mcp_server.run(transport="sse", host=args.host, port=args.port)
    else:
        if args.host != "127.0.0.1" or args.port != 9000:
            print("Warning: --host and --port are ignored when not using --sse")
        mcp_server.run()
