import os
from typing import Any, Dict, List

import requests


class RunnerClient:

    def __init__(self):
        self.base_url = os.getenv("RUNNER_URL", "http://runner:9000")

    def write_files(self, workspace: str, files: List[Dict[str, Any]]):
        payload = {
        "job": "workspace_write_files",
        "workspace": workspace,
        "args": {"files": files},
        }

        response = requests.post(f"{self.base_url}/run", json=payload, timeout=30)

        if response.status_code != 200:
            raise RuntimeError(f"runner error: {response.text}")

        data = response.json()

        if data.get("status") != "succeeded":
            raise RuntimeError("runner job failed")

        return data.get("result", {})