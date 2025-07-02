# Image Builder MCP

This repo is in a DRAFT and playground state!

An MCP server to interact with [hosted image builder](https://osbuild.org/docs/hosted/architecture/)

## Authentication

Go to https://console.redhat.com to `'YOUR USER' ➡ My User Access ➡ Service Accounts` create a service account
and then set the environment variables `IMAGE_BUILDER_CLIENT_ID` and `IMAGE_BUILDER_CLIENT_SECRET` accordingly.

## Run

### Using Python directly
Just install the requirements

```
pip install -r requirements.txt
```

and run

```
python image-builder-mcp.py sse
```

This will start image-builder-mcp server at http://localhost:9000/sse

### Using Podman/Docker

You can also copy the command from the [Makefile]
For SSE mode:
```
make run-sse
```

You can also copy the command from the [Makefile]
For stdio mode:
```
make run-stdio
```

## Integrations

### VSCode
for the usage in your project, create a file `.vscode/mcp.json`

An example configuration here could look like this:

```
{
    "inputs": [
        {
            "id": "image_builder_client_id",
            "type": "promptString",
            "description": "Enter the Image Builder Client ID",
            "default": ""
        },
        {
            "id": "image_builder_client_secret",
            "type": "promptString",
            "description": "Enter the Image Builder Client Secret",
            "default": ""
        }
    ],
    "servers": {
        "image-builder-mcp-stdio": {
            "type": "stdio",
            "command": "podman",
            "args": [
                "run",
                "--env",
                "IMAGE_BUILDER_CLIENT_ID",
                "--env",
                "IMAGE_BUILDER_CLIENT_SECRET",
                "--interactive",
                "--rm",
                "ghcr.io/schuellerf/image-builder-mcp:latest"
            ],
            "env": {
                "IMAGE_BUILDER_CLIENT_ID": "${input:image_builder_client_id}",
                "IMAGE_BUILDER_CLIENT_SECRET": "${input:image_builder_client_secret}"
            }
        }
    }
}
```

### Cursor

To start the integration create a file `~/.cursor/mcp.json` with
```
{
  "mcpServers": {
    "image-builder-mcp-stdio": {
        "type": "stdio",
        "command": "podman",
        "args": [
            "run",
            "--env",
            "IMAGE_BUILDER_CLIENT_ID",
            "--env",
            "IMAGE_BUILDER_CLIENT_SECRET",
            "--interactive",
            "--rm",
            "ghcr.io/schuellerf/image-builder-mcp:latest"
        ],
        "env": {
            "IMAGE_BUILDER_CLIENT_ID": "YOUR_ID HERE",
            "IMAGE_BUILDER_CLIENT_SECRET": "YOUR_SECRET HERE"
        }
    }
  }
}
```