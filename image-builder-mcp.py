from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel
from typing import Optional, Dict
import time
import requests
import threading

from langflow.interface.custom_components.base import CustomComponent

app = FastAPI()

# In-memory cache for the access token and compose state
class TokenCache:
    def __init__(self):
        self.access_token = None
        self.expires_at = 0
        self.lock = threading.Lock()

    def get_token(self, client_id: str, client_secret: str) -> str:
        with self.lock:
            if self.access_token and time.time() < self.expires_at:
                return self.access_token

            token_url = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
            data = {
                "client_id": client_id,
                "client_secret": client_secret,
                "grant_type": "client_credentials",
                "scope": "api.console"
            }
            response = requests.post(token_url, data=data)
            if not response.ok:
                raise HTTPException(status_code=401, detail="Unable to authenticate with Red Hat SSO")

            token_info = response.json()
            self.access_token = token_info["access_token"]
            self.expires_at = time.time() + token_info.get("expires_in", 900) - 30  # expire a bit early
            return self.access_token


token_cache = TokenCache()
compose_cache: Dict[str, str] = {}  # maps user -> last composeId (could use sessions, here just in-memory)


class Credentials(BaseModel):
    client_id: str
    client_secret: str


BASE_URL = "https://console.redhat.com/api/image-builder/v1"


def auth_headers(client_id: str, client_secret: str):
    token = token_cache.get_token(client_id, client_secret)
    return {"Authorization": f"Bearer {token}"}


@app.post("/blueprints")
def get_blueprints(creds: Credentials):
    """
    Retrieves all available blueprints.

    Parameters:
        creds (BaseModel): Contains `client_id` and `client_secret`

    Returns:
        JSON object containing blueprint metadata
    """
    resp = requests.get(f"{BASE_URL}/blueprints", headers=auth_headers(creds.client_id, creds.client_secret))
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/blueprints/{blueprint_id}")
def get_blueprint_by_id(blueprint_id: str, creds: Credentials):
    """
    Fetches a specific blueprint by its ID.

    Parameters:
        blueprint_id (str): The ID of the blueprint to retrieve
        creds (BaseModel): Contains `client_id` and `client_secret`

    Returns:
        JSON object of the blueprint
    """
    resp = requests.get(f"{BASE_URL}/blueprints/{blueprint_id}", headers=auth_headers(creds.client_id, creds.client_secret))
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


@app.post("/composes")
def get_composes(creds: Credentials):
    """
    Retrieves a list of image composes. Also caches the most recent compose ID.

    Parameters:
        creds (BaseModel): Contains `client_id` and `client_secret`

    Returns:
        JSON object containing compose metadata
    """
    resp = requests.get(f"{BASE_URL}/composes", headers=auth_headers(creds.client_id, creds.client_secret))
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)

    data = resp.json()
    if data.get("meta", {}).get("count"):
        latest_compose_id = data["data"][0]["id"]
        compose_cache[creds.client_id] = latest_compose_id
    return data


@app.post("/composes/{compose_id}")
def get_compose_by_id(compose_id: str, creds: Credentials):
    """
    Fetches details of a specific compose by its UUID.

    Parameters:
        compose_id (str): UUID of the compose
        creds (BaseModel): Contains `client_id` and `client_secret`

    Returns:
        JSON object of the compose status
    """
    compose_cache[creds.client_id] = compose_id  # Update latest used composeId for this user
    resp = requests.get(f"{BASE_URL}/composes/{compose_id}", headers=auth_headers(creds.client_id, creds.client_secret))
    if not resp.ok:
        raise HTTPException(status_code=resp.status_code, detail=resp.text)
    return resp.json()


# Langflow integration

class ImageBuilderComponent(CustomComponent):
    display_name = "Image Builder"
    description = (
        "Use this component to interact with Red Hat's Image Builder API. "
        "It retrieves compose status or lists all composes depending on whether a Compose ID is provided. "
        "The component authenticates using client credentials."
    )

    def build_config(self):
        return {
            "client_id": {"multiline": False, "description": "OAuth client ID from Red Hat SSO."},
            "client_secret": {"multiline": False, "description": "OAuth client secret."},
            "compose_id": {
                "multiline": False,
                "required": False,
                "description": "Optional UUID of a specific compose to fetch. If omitted, returns the latest list of composes."
            },
        }

    def run(self, client_id: str, client_secret: str, compose_id: Optional[str] = None) -> dict:
        headers = auth_headers(client_id, client_secret)
        if compose_id:
            url = f"{BASE_URL}/composes/{compose_id}"
        else:
            url = f"{BASE_URL}/composes"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

