from sqlmodel import Session, select
from app.db import engine, create_db_and_tables
from app.models.agent_task import AgentTask
from app.models.workflow_run import WorkflowRun
from app.services.agent_runner import AgentRunner
import time


def worker_loop():

    print("Agent worker started")

    # Ensure DB schema exists
    create_db_and_tables()

    while True:

        with Session(engine) as session:

            tasks = session.exec(
                select(AgentTask).where(AgentTask.status == "pending")
            ).all()

            for task in tasks:

                print(f"Running agent: {task.agent_name}")

                runner = AgentRunner(session)

                workflow = session.get(WorkflowRun, task.workflow_run_id)

                if workflow:
                    runner.run_for_state(workflow)

                task.status = "completed"
                session.add(task)
                session.commit()

        time.sleep(1)


if __name__ == "__main__":
    worker_loop()