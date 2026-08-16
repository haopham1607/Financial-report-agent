"""Entry point for the CLI — keeps `python agent.py "FPT"` working.

    python agent.py FPT              queue a job, exit immediately
    python agent.py FPT, Apple       queue several at once
    python agent.py status           build pending jobs; write their reports

The implementation lives in finreport/jobs/queue.py.
"""

from finreport.jobs.queue import main

if __name__ == "__main__":
    main()
