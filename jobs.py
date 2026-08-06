"""Job persistence: which research runs exist and where they stand.

Storage lives entirely behind JobStore — to move from the JSON file to
SQLite (or anything else) later, only this class changes.
"""

from __future__ import annotations

import dataclasses
import datetime
import json
import os
from dataclasses import dataclass

JOBS_FILE = os.path.join(os.path.dirname(__file__), "jobs.json")

_JOB_FIELDS = None  # populated after Job is defined


@dataclass
class Job:
    company: str
    interaction_id: str
    started_at: str
    state: str = "running"  # running | done | failed
    report_path: str | None = None

    @classmethod
    def new(cls, company: str, interaction_id: str) -> "Job":
        return cls(
            company=company,
            interaction_id=interaction_id,
            started_at=datetime.datetime.now().isoformat(timespec="seconds"),
        )


_JOB_FIELDS = {f.name for f in dataclasses.fields(Job)}


class JobStore:
    """JSON-file-backed job store with atomic writes."""

    def __init__(self, path: str = JOBS_FILE):
        self.path = path

    def load(self) -> list[Job]:
        if not os.path.exists(self.path):
            return []
        try:
            with open(self.path) as fh:
                items = json.load(fh)
        except (json.JSONDecodeError, OSError):
            # An empty or corrupted jobs file should never crash the app.
            return []
        jobs = []
        for item in items:
            if isinstance(item, dict) and {"company", "interaction_id"} <= item.keys():
                jobs.append(Job(**{k: v for k, v in item.items() if k in _JOB_FIELDS}))
        return jobs

    def save(self, jobs: list[Job]) -> None:
        # Write to a temp file then atomically replace, so a concurrent
        # reader never sees a half-written (or empty) jobs file.
        tmp_path = self.path + ".tmp"
        with open(tmp_path, "w") as fh:
            json.dump([dataclasses.asdict(job) for job in jobs], fh, indent=2)
        os.replace(tmp_path, self.path)
