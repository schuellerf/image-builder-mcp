# Image Builder MCP

This repo is in a DRAFT and playground state!

An MCP server to interact with [hosted image builder](https://osbuild.org/docs/hosted/architecture/)

## Authentication

Go to https://console.redhat.com to `'YOUR USER' ➡ My User Access ➡ Service Accounts` create a service account
and then set the environment variables `IMAGE_BUILDER_CLIENT_ID` and `IMAGE_BUILDER_CLIENT_SECRET` accordingly.

## Run
Just install the requirements

```
pip install -r requirements.txt
```

and run

```
python image-builder-mcp.py
```

This will start image-builder-mcp server at http://localhost:9000/sse
