from sqlmodel import Session, select
from collections import defaultdict

from app.db import engine
from app.models.artifact import Artifact


def list_artifacts():

    with Session(engine) as session:

        artifacts = session.exec(select(Artifact)).all()

        grouped = defaultdict(list)

        for a in artifacts:
            grouped[a.workflow_run_id].append(a)

        print()
        print("Artifacts by Workflow Run")
        print("=" * 90)

        for run_id, items in grouped.items():

            print(f"\nRun: {run_id}")
            print("-" * 90)

            for a in items:
                file_name = a.file_path.split("/")[-1]

                print(
                    f"  {file_name:<25} "
                    f"{a.artifact_type:<10} "
                    f"{a.artifact_role}"
                )

        print()


if __name__ == "__main__":
    list_artifacts()