WORKFLOW_NAME = "ticket_to_pr"

WORKFLOW_GRAPH = {
    "DATA_INGESTION": "TICKET_INTAKE",
    "TICKET_INTAKE": "DESIGN_REVIEW",
    "DESIGN_REVIEW": "PROFILING",
    "PROFILING": "BUILD",
    "BUILD": "QA",
    "QA": "READY_FOR_REVIEW",
    "READY_FOR_REVIEW": "PR_CREATION",
    "PR_CREATION": "DONE",
    "DONE": None,
}

STATE_AGENT_MAP = {
    "DATA_INGESTION": "DataIngestionAgent",
    "TICKET_INTAKE": "IntakeAgent",
    "DESIGN_REVIEW": "DesignAgent",
    "PROFILING": "ProfilerAgent",
    "BUILD": "BuilderAgent",
    "QA": "QAAgent",
    "PR_CREATION": "PRAgent",
}
