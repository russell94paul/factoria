from sqlmodel import Session, select

from app.db import engine
from app.models.workflow_run import WorkflowRun


def list_runs():

    with Session(engine) as session:

        statement = select(WorkflowRun)

        results = session.exec(statement).all()

        print()
        print("Workflow Runs")
        print("-" * 80)

        for run in results:

            print(
                f"{run.workflow_run_id}   "
                f"{run.ticket_id}   "
                f"{run.current_state}   "
                f"{run.status}"
            )

        print()


if __name__ == "__main__":
    list_runs()