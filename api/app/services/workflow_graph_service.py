class WorkflowGraphService:

    def __init__(self, workflow_graph, state_agent_map):
        self.workflow_graph = workflow_graph
        self.state_agent_map = state_agent_map

    def generate_mermaid(self):

        lines = ["graph TD"]

        for state, next_state in self.workflow_graph.items():

            agent = self.state_agent_map.get(state, "None")

            label = f"{state}[{state}\\n({agent})]"

            if next_state:
                lines.append(f"{label} --> {next_state}")
            else:
                lines.append(label)

        return "\n".join(lines)