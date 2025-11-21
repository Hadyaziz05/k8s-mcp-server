# Kubernetes MCP Server

A Model Context Protocol (MCP) server that provides Kubernetes cluster management capabilities through a standardized interface. This server enables AI assistants to interact with Kubernetes clusters programmatically.

## Features

The server provides four main tools for Kubernetes operations:

- **kubectl_apply** - Apply Kubernetes manifests from YAML content
- **kubectl_get** - Retrieve Kubernetes resources (pods, deployments, services, nodes, namespaces)
- **kubectl_describe** - Get detailed information about specific resources
- **kubectl_delete** - Delete Kubernetes resources from YAML content

## Prerequisites

- Docker (for containerized deployment)
- Access to a Kubernetes cluster with a valid `~/.kube/config` file

## Installation

### Docker Deployment

1. Build the Docker image:
```bash
docker build -t k8s-mcp-server .
```

2. Run the container with your kubeconfig mounted:
```bash
docker run -it --rm \
  -v ~/.kube:/home/mcpuser/.kube:ro \
  k8s-mcp-server
```

Or use the published image:
```bash
docker run -it --rm \
  -v ~/.kube:/home/mcpuser/.kube:ro \
  <your-docker-username>/kubectl-mcp-server:latest
```

## Integration with GitHub Copilot in VS Code

You can integrate this MCP server with GitHub Copilot in Visual Studio Code to interact with your Kubernetes cluster through natural language.

### Setup Steps

1. **Create MCP Configuration File**

   Create a file at `.vscode/mcp.json` in your workspace with the following content:

   ```json
   {
     "inputs": [
       {
         "type": "promptString",
         "id": "kubeconfig_path",
         "description": "Path to your local .kube folder (e.g., /Users/username/.kube)"
       }
     ],
     "servers": {
       "k8s": {
         "command": "docker",
         "args": [
           "run",
           "--rm",
           "-i",
           "-v", "${input:kubeconfig_path}:/home/mcpuser/.kube:ro",
           "<your-docker-username>/kubectl-mcp-server:latest"
         ],
         "env": {
           "DEFAULT_CONFIG": "config"
         }
       }
     }
   }
   ```

   - Click **Add server** 
   - When asked for the kubeconfig path, enter the path to your `.kube` folder (e.g., `/Users/yourusername/.kube`).
   - Wait for the server to start successfully.

2. **Enable the Kubernetes Tools**

   - In the Copilot Chat box, select **Agent** from the popup menu.
   - Click the **Select tools** icon to see available actions.
   - In the Tools dropdown, under **MCP Server: k8s**, check the box to enable the Kubernetes tools.
   - You will see a list of available actions: `kubectl_apply`, `kubectl_get`, `kubectl_describe`, and `kubectl_delete`.

3. **Start Using Kubernetes Commands**

   In the Copilot Chat box, you can now ask questions or give commands related to your Kubernetes cluster:

   - "List all pods in the default namespace"
   - "Describe the frontend-deployment"
   - "Apply this deployment manifest: [paste YAML]"
   - "Show me all services in the production namespace"

   The Kubernetes MCP server will process your request and provide responses directly in the chat interface. You may be asked to provide additional permissions or information to complete certain actions.



## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
# k8s-mcp-server
