WORKFLOW_NAME = "tenant_provisioning"

WORKFLOW_GRAPH = {
    "PROVISIONING_REQUESTED": "DONE",
    "DONE": None,
}

STATE_AGENT_MAP = {
    "PROVISIONING_REQUESTED": "TenantProvisioningAgent",
}
