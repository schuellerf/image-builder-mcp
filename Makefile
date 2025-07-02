build:
	podman build --tag image-builder-mcp .

run-sse: build
	# add firewall rules for fedora
	podman run --rm --network=host --name image-builder-mcp-sse localhost/image-builder-mcp:latest sse

# just an example command
# doesn't really make sense
# rather integrate this with an MCP client directly
run-stdio: build
	podman run --interactive --tty --rm --name image-builder-mcp-stdio localhost/image-builder-mcp:latest
