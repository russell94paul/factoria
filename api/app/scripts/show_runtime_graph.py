from sqlmodel import Session, select
from app.db import engine
from app.models.workflow_run import WorkflowRun
from app.services.workflow_runtime_graph_service import WorkflowRuntimeGraphService


workflow_run_id = input("Workflow Run ID: ")

with Session(engine) as session:

    workflow_run = session.exec(
        select(WorkflowRun).where(WorkflowRun.workflow_run_id == workflow_run_id)
    ).first()

    if not workflow_run:
        print("Workflow run not found")
        exit()

    service = WorkflowRuntimeGraphService(session)

    graph = service.generate_mermaid(workflow_run_id)

    output_path = f"{workflow_run.workspace_root}/runtime_graph.md"

    with open(output_path, "w") as f:
        f.write("```mermaid\n")
        f.write(graph)
        f.write("\n```")

    print(f"\nGraph written to {output_path}\n")