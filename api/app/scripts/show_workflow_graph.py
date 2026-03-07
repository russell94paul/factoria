from app.services.workflow_graph_service import WorkflowGraphService
from app.workflows.ticket_to_pr import WORKFLOW_GRAPH, STATE_AGENT_MAP

service = WorkflowGraphService(
    WORKFLOW_GRAPH,
    STATE_AGENT_MAP
)

print(service.generate_mermaid())