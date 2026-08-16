"""Build a structured report by running the tool-calling agent loop.

Kept as a thin, separately-testable wrapper over agent_loop.run_agent so the job
queue depends on a stable build_report(company) -> dict contract.
"""

from finreport.agent.loop import run_agent


def build_report(company: str) -> dict:
    """Build the report dict for one company via the agent loop."""
    return run_agent(company)
