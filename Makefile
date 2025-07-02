build:
	podman build --tag image-builder-mcp .

# `IMAGE_BUILDER_CLIENT_ID` and `IMAGE_BUILDER_CLIENT_SECRET` are optional
# if you hand those over via http headers from the client.
run-sse: build
	# add firewall rules for fedora
	podman run --rm --network=host --env IMAGE_BUILDER_CLIENT_ID --env IMAGE_BUILDER_CLIENT_SECRET --name image-builder-mcp-sse localhost/image-builder-mcp:latest sse

# just an example command
# doesn't really make sense
# rather integrate this with an MCP client directly
run-stdio: build
	podman run --interactive --tty --rm --env IMAGE_BUILDER_CLIENT_ID --env IMAGE_BUILDER_CLIENT_SECRET --name image-builder-mcp-stdio localhost/image-builder-mcp:latest
