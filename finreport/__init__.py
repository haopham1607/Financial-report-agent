"""Financial Report Agent — an LLM agent that builds company health reports.

ROOT is the project root (the directory holding app.py / agent.py / .env). Every
runtime path — .env, jobs.json, reports/ — resolves through it, so moving a module
inside the package never changes where those files live.
"""

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
