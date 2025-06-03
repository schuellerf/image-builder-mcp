import json
import uuid
import requests
from fastmcp import FastMCP, Event
from sseclient import SSEClient

# Constants for the API
TOKEN_URL = "https://sso.redhat.com/auth/realms/redhat-external/protocol/openid-connect/token"
API_URL = "https://console.redhat.com/api/image-builder/v1"
SCOPE = "api.console"

# A simple storage for the current token and its expiration time
token_cache = {"access_token": None, "expires_at": 0}

# Function to get a fresh token
def get_token(client_id, client_secret):
    global token_cache

    # If the current token is expired, request a new one
    if token_cache["access_token"] is None or token_cache["expires_at"] <= time.time():
        print("Fetching new access token...")

        response = requests.post(TOKEN_URL, data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
            "scope": SCOPE
        })

        if response.status_code == 200:
            data = response.json()
            token_cache["access_token"] = data["access_token"]
            # Set the expiration time (usually 900 seconds)
            token_cache["expires_at"] = time.time() + 900
            return token_cache["access_token"]
        else:
            raise Exception(f"Failed to fetch token: {response.text}")
    else:
        return token_cache["access_token"]

# Helper function to make API calls
def api_get(endpoint, client_id, client_secret):
    token = get_token(client_id, client_secret)
    response = requests.get(f"{API_URL}/{endpoint}", headers={"Authorization": f"Bearer {token}"})
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"API call failed: {response.text}")

# FastMCP server handler
class MyServer(FastMCP):
    def __init__(self, client_id, client_secret):
        super().__init__(port=9000)
        self.client_id = client_id
        self.client_secret = client_secret
        self.last_compose_id = None
        self.last_blueprint_id = None

    # Endpoint to get all blueprints
    async def on_blueprints(self, request):
        data = api_get("blueprints", self.client_id, self.client_secret)
        return {"blueprints": data}

    # Endpoint to get a specific blueprint
    async def on_blueprints_id(self, request, id):
        data = api_get(f"blueprints/{id}", self.client_id, self.client_secret)
        return {"blueprint": data}

    # Endpoint to get all composes
    async def on_composes(self, request):
        data = api_get("composes", self.client_id, self.client_secret)
        return {"composes": data}

    # Endpoint to get the status of a specific compose
    async def on_composes_composeId(self, request, composeId):
        data = api_get(f"composes/{composeId}", self.client_id, self.client_secret)
        return {"compose_status": data}

    # This function will handle the user's last compose or blueprint context
    async def on_latest_compose(self, request):
        if self.last_compose_id:
            return await self.on_composes_composeId(request, self.last_compose_id)
        else:
            return {"error": "No last compose available"}

    # Listen for events
    async def on_event(self, request):
        # Example of streaming data
        yield Event("message", json.dumps({"status": "Server is running"}))

    # Function to store last compose context (avoiding repeated UUIDs)
    async def on_store_compose_id(self, request, compose_id):
        self.last_compose_id = compose_id
        return {"status": f"Compose ID {compose_id} stored for future reference"}

    # Function to store last blueprint context
    async def on_store_blueprint_id(self, request, blueprint_id):
        self.last_blueprint_id = blueprint_id
        return {"status": f"Blueprint ID {blueprint_id} stored for future reference"}

    # Start the server
    def start(self):
        self.run()

# Main function to start the FastMCP server
def main():
    client_id = input("Enter your client_id: ")
    client_secret = input("Enter your client_secret: ")

    server = MyServer(client_id, client_secret)
    server.start()

if __name__ == "__main__":
    main()

