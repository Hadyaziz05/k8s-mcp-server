import asyncio
import os
import json
import yaml
from kubernetes import client, config, utils
from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
import mcp.types as types

# -----------------------------
# Kubernetes initialization
# -----------------------------
def load_kube_config_once():
    """
    Load Kubernetes configuration from ~/.kube/config
    """
    try:
        config.load_kube_config()
        print("Loaded kubeconfig from ~/.kube/config", flush=True)
    except Exception as e:
        raise Exception(f"Failed to load kubernetes config from ~/.kube/config. Error: {e}")

# Load config and create clients once at module level
load_kube_config_once()
v1 = client.CoreV1Api() # Core V1 API client to deal with (pods, services, nodes, namespaces, etc.)
apps_v1 = client.AppsV1Api() # Apps V1 API client to deal with (deployments, statefulsets, etc.)
api_client = client.ApiClient() # Generic API client (create_from_yaml, etc.)

# -----------------------------
# MCP SERVER SETUP
# -----------------------------
server = Server("k8s-mcp-server")

# -----------------------------
# List tools
# -----------------------------
@server.list_tools()
async def list_tools():
    return [
        types.Tool(
            name="kubectl_apply",
            description="Apply a Kubernetes manifest from YAML content (kubectl apply -f)",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_content": {
                        "type": "string",
                        "description": "YAML manifest content to apply"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to apply the resource in (optional)"
                    }
                },
                "required": ["yaml_content"]
            }
        ),
        types.Tool(
            name="kubectl_get",
            description="Get Kubernetes resources (kubectl get)",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {
                        "type": "string",
                        "description": "Type of resource to get (e.g., pods, deployments, services, nodes, namespaces)"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to get resources from (not applicable for cluster-scoped resources like nodes)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Specific resource name (optional)"
                    }
                },
                "required": ["resource_type"]
            }
        ),
        types.Tool(
            name="kubectl_describe",
            description="Describe a Kubernetes resource (kubectl describe)",
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_type": {
                        "type": "string",
                        "description": "Type of resource to describe (e.g., pod, deployment, service, node)"
                    },
                    "name": {
                        "type": "string",
                        "description": "Name of the resource to describe"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace of the resource (not applicable for cluster-scoped resources)"
                    }
                },
                "required": ["resource_type", "name"]
            }
        ),
        types.Tool(
            name="kubectl_delete",
            description="Delete a Kubernetes resource from YAML content (kubectl delete -f)",
            inputSchema={
                "type": "object",
                "properties": {
                    "yaml_content": {
                        "type": "string",
                        "description": "YAML manifest content to delete"
                    },
                    "namespace": {
                        "type": "string",
                        "description": "Namespace to delete the resource from (optional)"
                    }
                },
                "required": ["yaml_content"]
            }
        )
    ]

# -----------------------------
# TOOL IMPLEMENTATIONS
# -----------------------------
@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "kubectl_apply":
        yaml_content = arguments.get("yaml_content")
        if not yaml_content:
            return [types.TextContent(type="text", text="Error: yaml_content is required")]
        
        namespace = arguments.get("namespace")
        
        try:
            docs = list(yaml.safe_load_all(yaml_content))

            utils.create_from_yaml(
                api_client,
                yaml_objects=docs,
                namespace=namespace
            )
            
            resource_name = docs[0].get("metadata", {}).get("name", "unknown")
            resource_kind = docs[0].get("kind", "unknown")
            
            return [types.TextContent(
                type="text",
                text=f"Successfully applied {resource_kind}/{resource_name}"
            )]
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error applying manifest: {str(e)}")]
    
    if name == "kubectl_get":
        resource_type = arguments.get("resource_type")
        if not resource_type:
            return [types.TextContent(type="text", text="Error: resource_type is required")]
        
        resource_type = resource_type.lower()
        namespace = arguments.get("namespace", "default")
        name = arguments.get("name")
        
        try:
            result = []
            
            if resource_type in ["pod", "pods"]:
                if name:
                    pod = v1.read_namespaced_pod(name=name, namespace=namespace)
                    result.append({
                        "name": pod.metadata.name,
                        "namespace": namespace,
                        "status": pod.status.phase,
                        "ready": f"{sum(1 for c in (pod.status.container_statuses or []) if c.ready)}/{len(pod.status.container_statuses or [])}",
                        "restarts": sum(c.restart_count for c in (pod.status.container_statuses or [])),
                        "node": pod.spec.node_name
                    })
                else:
                    pods = v1.list_namespaced_pod(namespace=namespace)
                    for p in pods.items:
                        result.append({
                            "name": p.metadata.name,
                            "namespace": namespace,
                            "status": p.status.phase,
                            "ready": f"{sum(1 for c in (p.status.container_statuses or []) if c.ready)}/{len(p.status.container_statuses or [])}",
                            "restarts": sum(c.restart_count for c in (p.status.container_statuses or [])),
                            "node": p.spec.node_name
                        })
            
            elif resource_type in ["deployment", "deployments"]:
                if name:
                    dep = apps_v1.read_namespaced_deployment(name=name, namespace=namespace)
                    result.append({
                        "name": dep.metadata.name,
                        "namespace": namespace,
                        "ready": f"{dep.status.ready_replicas or 0}/{dep.spec.replicas}",
                        "up_to_date": dep.status.updated_replicas or 0,
                        "available": dep.status.available_replicas or 0
                    })
                else:
                    deployments = apps_v1.list_namespaced_deployment(namespace=namespace)
                    for dep in deployments.items:
                        result.append({
                            "name": dep.metadata.name,
                            "namespace": namespace,
                            "ready": f"{dep.status.ready_replicas or 0}/{dep.spec.replicas}",
                            "up_to_date": dep.status.updated_replicas or 0,
                            "available": dep.status.available_replicas or 0
                        })
            
            elif resource_type in ["service", "services", "svc"]:
                if name:
                    svc = v1.read_namespaced_service(name=name, namespace=namespace)
                    result.append({
                        "name": svc.metadata.name,
                        "namespace": namespace,
                        "type": svc.spec.type,
                        "cluster_ip": svc.spec.cluster_ip,
                        "external_ip": svc.spec.external_i_ps or "none",
                        "ports": [f"{p.port}/{p.protocol}" for p in (svc.spec.ports or [])]
                    })
                else:
                    services = v1.list_namespaced_service(namespace=namespace)
                    for svc in services.items:
                        result.append({
                            "name": svc.metadata.name,
                            "namespace": namespace,
                            "type": svc.spec.type,
                            "cluster_ip": svc.spec.cluster_ip,
                            "external_ip": svc.spec.external_i_ps or "none",
                            "ports": [f"{p.port}/{p.protocol}" for p in (svc.spec.ports or [])]
                        })
            
            elif resource_type in ["node", "nodes"]:
                if name:
                    node = v1.read_node(name=name)
                    conditions = {c.type: c.status for c in node.status.conditions}
                    result.append({
                        "name": node.metadata.name,
                        "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
                        "roles": [label.split("/")[1] for label in node.metadata.labels.keys() if "node-role.kubernetes.io" in label] or ["<none>"],
                        "version": node.status.node_info.kubelet_version,
                        "internal_ip": next((addr.address for addr in node.status.addresses if addr.type == "InternalIP"), "")
                    })
                else:
                    nodes = v1.list_node()
                    for node in nodes.items:
                        conditions = {c.type: c.status for c in node.status.conditions}
                        result.append({
                            "name": node.metadata.name,
                            "status": "Ready" if conditions.get("Ready") == "True" else "NotReady",
                            "roles": [label.split("/")[1] for label in node.metadata.labels.keys() if "node-role.kubernetes.io" in label] or ["<none>"],
                            "version": node.status.node_info.kubelet_version,
                            "internal_ip": next((addr.address for addr in node.status.addresses if addr.type == "InternalIP"), "")
                        })
            
            elif resource_type in ["namespace", "namespaces", "ns"]:
                if name:
                    ns = v1.read_namespace(name=name)
                    result.append({
                        "name": ns.metadata.name,
                        "status": ns.status.phase,
                        "age": str(ns.metadata.creation_timestamp)
                    })
                else:
                    namespaces = v1.list_namespace()
                    for ns in namespaces.items:
                        result.append({
                            "name": ns.metadata.name,
                            "status": ns.status.phase,
                            "age": str(ns.metadata.creation_timestamp)
                        })
            
            else:
                return [types.TextContent(type="text", text=f"Unsupported resource type: {resource_type}")]
            
            return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
        
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error getting resource: {str(e)}")]
    
    if name == "kubectl_describe":
        resource_type = arguments.get("resource_type")
        if not resource_type:
            return [types.TextContent(type="text", text="Error: resource_type is required")]
        
        name_arg = arguments.get("name")
        if not name_arg:
            return [types.TextContent(type="text", text="Error: name is required")]
        
        resource_type = resource_type.lower()
        namespace = arguments.get("namespace", "default")
        
        try:
            description = {}
            
            if resource_type in ["pod", "pods"]:
                pod = v1.read_namespaced_pod(name=name_arg, namespace=namespace)
                description = {
                    "name": pod.metadata.name,
                    "namespace": pod.metadata.namespace,
                    "labels": pod.metadata.labels,
                    "annotations": pod.metadata.annotations,
                    "status": pod.status.phase,
                    "ip": pod.status.pod_ip,
                    "node": pod.spec.node_name,
                    "containers": [
                        {
                            "name": c.name,
                            "image": c.image,
                            "ready": cs.ready if cs else False,
                            "restart_count": cs.restart_count if cs else 0,
                            "state": str(cs.state) if cs else "unknown"
                        }
                        for c, cs in zip(
                            pod.spec.containers,
                            pod.status.container_statuses or [None] * len(pod.spec.containers)
                        )
                    ],
                    "conditions": [{"type": c.type, "status": c.status, "reason": c.reason} for c in (pod.status.conditions or [])],
                    "events": "Use kubectl get events for pod events"
                }
            
            elif resource_type in ["deployment", "deployments"]:
                dep = apps_v1.read_namespaced_deployment(name=name_arg, namespace=namespace)
                description = {
                    "name": dep.metadata.name,
                    "namespace": dep.metadata.namespace,
                    "labels": dep.metadata.labels,
                    "annotations": dep.metadata.annotations,
                    "replicas": dep.spec.replicas,
                    "ready_replicas": dep.status.ready_replicas or 0,
                    "available_replicas": dep.status.available_replicas or 0,
                    "updated_replicas": dep.status.updated_replicas or 0,
                    "selector": dep.spec.selector.match_labels,
                    "strategy": dep.spec.strategy.type,
                    "conditions": [{"type": c.type, "status": c.status, "reason": c.reason} for c in (dep.status.conditions or [])]
                }
            
            elif resource_type in ["service", "services", "svc"]:
                svc = v1.read_namespaced_service(name=name_arg, namespace=namespace)
                description = {
                    "name": svc.metadata.name,
                    "namespace": svc.metadata.namespace,
                    "labels": svc.metadata.labels,
                    "annotations": svc.metadata.annotations,
                    "type": svc.spec.type,
                    "cluster_ip": svc.spec.cluster_ip,
                    "external_ips": svc.spec.external_i_ps,
                    "ports": [{"port": p.port, "protocol": p.protocol, "target_port": str(p.target_port)} for p in (svc.spec.ports or [])],
                    "selector": svc.spec.selector
                }
            
            elif resource_type in ["node", "nodes"]:
                node = v1.read_node(name=name_arg)
                description = {
                    "name": node.metadata.name,
                    "labels": node.metadata.labels,
                    "annotations": node.metadata.annotations,
                    "capacity": node.status.capacity,
                    "allocatable": node.status.allocatable,
                    "conditions": [{"type": c.type, "status": c.status, "reason": c.reason} for c in (node.status.conditions or [])],
                    "addresses": [{"type": a.type, "address": a.address} for a in (node.status.addresses or [])],
                    "node_info": {
                        "kubelet_version": node.status.node_info.kubelet_version,
                        "os_image": node.status.node_info.os_image,
                        "container_runtime": node.status.node_info.container_runtime_version
                    }
                }
            
            else:
                return [types.TextContent(type="text", text=f"Unsupported resource type: {resource_type}")]
            
            return [types.TextContent(type="text", text=json.dumps(description, indent=2, default=str))]
        
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error describing resource: {str(e)}")]
    
    if name == "kubectl_delete":
        yaml_content = arguments.get("yaml_content")
        if not yaml_content:
            return [types.TextContent(type="text", text="Error: yaml_content is required")]
        
        namespace = arguments.get("namespace")
        
        try:
            
            manifest = yaml.safe_load(yaml_content)
            
            if not manifest:
                return [types.TextContent(type="text", text="Error: Invalid YAML content")]
            
            resource_name = manifest.get("metadata", {}).get("name")
            if not resource_name:
                return [types.TextContent(type="text", text="Error: Resource name not found in YAML")]
            
            resource_kind = manifest.get("kind", "").lower()
            if not resource_kind:
                return [types.TextContent(type="text", text="Error: Resource kind not found in YAML")]
            
            resource_namespace = namespace or manifest.get("metadata", {}).get("namespace", "default")
            
            if resource_kind == "pod":
                v1.delete_namespaced_pod(name=resource_name, namespace=resource_namespace)
            elif resource_kind == "deployment":
                apps_v1.delete_namespaced_deployment(name=resource_name, namespace=resource_namespace)
            elif resource_kind == "service":
                v1.delete_namespaced_service(name=resource_name, namespace=resource_namespace)
            else:
                return [types.TextContent(type="text", text=f"Generic deletion not fully implemented for {resource_kind}")]
            
            return [types.TextContent(
                type="text",
                text=f"Successfully deleted {resource_kind}/{resource_name} from namespace {resource_namespace}"
            )]
        
        except Exception as e:
            return [types.TextContent(type="text", text=f"Error deleting resource: {str(e)}")]
    
    raise ValueError(f"Unknown tool: {name}")

# -----------------------------
# STDIO SERVER RUNNER
# -----------------------------
async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream=read_stream,
            write_stream=write_stream,
            initialization_options=InitializationOptions(
                server_name="k8s-mcp-server",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={}
                )
            )
        )

if __name__ == "__main__":
    asyncio.run(main())