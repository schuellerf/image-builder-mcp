"""Image Builder MCP client for interacting with the Image Builder API."""

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union

import requests


class ImageBuilderClient:  # pylint: disable=too-many-instance-attributes
    """Client for interacting with the Red Hat Image Builder API.

    This client handles authentication, token management, and API requests
    to the Image Builder service.
    """

    def __init__(  # pylint: disable=too-many-arguments
            self,
            client_id: Optional[str],
            client_secret: Optional[str],
            stage: Optional[bool] = False,
            proxy_url: Optional[str] = None,
            image_builder_mcp_client_id: str = "mcp"
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token: Optional[str] = None
        self.token_expiry: Optional[datetime] = None
        self.stage = stage
        self.proxy_url = proxy_url
        self.image_builder_mcp_client_id = image_builder_mcp_client_id
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
            self.logger.debug(
                "Using cached token valid until %s", self.token_expiry)
            # mypy doesn't understand that self.token is not None after the check above
            assert self.token is not None
            return self.token
        self.logger.debug("Fetching new token")
        token_url = f"https://{self.sso_domain}/auth/realms/redhat-external/protocol/openid-connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret
        }

        response = requests.post(token_url, data=data, timeout=60)
        response.raise_for_status()

        token_data = response.json()
        self.token = token_data["access_token"]
        # Set token expiry to 5 minutes before actual expiry to ensure we refresh in time
        self.token_expiry = datetime.now(
        ) + timedelta(seconds=token_data["expires_in"] - 300)

        # Ensure we return a string (self.token was just assigned above)
        assert self.token is not None
        return self.token

    def make_request(
        self,
        endpoint: str,
        method: str = "GET",
        data: Optional[Dict] = None
    ) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
        """Make an authenticated request to the Image Builder API."""
        headers = {
            "Content-Type": "application/json",
            "X-ImageBuilder-ui": self.image_builder_mcp_client_id
        }
        if self.client_id and self.client_secret:
            headers["Authorization"] = f"Bearer {self.get_token()}"
        # else no authentication, use public API

        url = f"{self.base_url}/{endpoint}"
        self.logger.debug("Making %s request to %s with data %s", method, url, data)

        proxies = None
        if self.stage and self.proxy_url:
            proxy = self.proxy_url
            proxies = {
                "http": proxy,
                "https": proxy
            }

        response = requests.request(method, url, headers=headers, json=data, proxies=proxies, timeout=60)
        response.raise_for_status()
        ret = response.json()
        self.logger.debug("Response from %s: %s", url, json.dumps(ret, indent=2))

        return ret
