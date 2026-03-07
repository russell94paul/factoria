WORKFLOW_NAME = "ticket_to_pr"

WORKFLOW_GRAPH = {
    "TICKET_INTAKE": "DESIGN_REVIEW",
    "DESIGN_REVIEW": "PROFILING",
    "PROFILING": "BUILD",
    "BUILD": "QA",
    "QA": "PR_CREATION",
    "PR_CREATION": None,
}

STATE_AGENT_MAP = {
    "TICKET_INTAKE": "IntakeAgent",
    "DESIGN_REVIEW": "DesignAgent",
    "PROFILING": "ProfilerAgent",
    "BUILD": "BuilderAgent",
    "QA": "QAAgent",
    "PR_CREATION": "PRAgent",
}