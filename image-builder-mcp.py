from fastapi import FastAPI, HTTPException, Path
from pydantic import BaseModel
from typing import Optional, Dict
import time
import requests
import threading

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


@app.post("/watch")
async def sse_watch(creds: Credentials):
    headers = auth_headers(creds.client_id, creds.client_secret)
    compose_id = creds.compose_id or compose_cache.get(creds.client_id)

    if not compose_id:
        raise HTTPException(status_code=404, detail="No compose ID provided or cached")

    compose_cache[creds.client_id] = compose_id

    async def event_generator():
        last_status = None
        while True:
            try:
                resp = requests.get(f"{BASE_URL}/composes/{compose_id}", headers=headers)
                if not resp.ok:
                    yield f"event: error\ndata: Failed to fetch compose: {resp.text}\n\n"
                    await asyncio.sleep(10)
                    continue

                data = resp.json()
                status = data.get("image_status", {}).get("status")
                if status != last_status:
                    yield f"data: {data}\n\n"
                    last_status = status

                if status in {"success", "failure"}:
                    break

                await asyncio.sleep(5)
            except Exception as e:
                yield f"event: error\ndata: Exception occurred: {str(e)}\n\n"
                await asyncio.sleep(10)

    return EventSourceResponse(event_generator())

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


