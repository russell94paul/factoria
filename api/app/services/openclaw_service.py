import requests


class OpenClawClient:

    def __init__(self):
        self.gateway_url = "http://openclaw:18789"

    def start_agent(self, agent_name, workflow_run_id):

        url = f"{self.gateway_url}/agent/run"

        payload = {
            "agent": agent_name,
            "workflow_run_id": workflow_run_id
        }

        response = requests.post(url, json=payload)

        print("OpenClaw response status:", response.status_code)
        print("OpenClaw response:", response.text)

        return response.text