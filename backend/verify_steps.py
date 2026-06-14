"""
Verify the agent's logged steps for the most recent task.

Run from the backend/ folder with the venv active:
    cd c:\\Users\\mfaiz\\coworkx\\backend
    venv\\Scripts\\activate
    python verify_steps.py
"""

from sqlalchemy import text
from database import engine


def main():
    with engine.connect() as conn:
        # Most recent task
        task = conn.execute(text(
            "SELECT id, status, output_url, steps_count, duration_seconds "
            "FROM tasks ORDER BY created_at DESC LIMIT 1"
        )).fetchone()

        if not task:
            print("No tasks found.")
            return

        print("=" * 70)
        print("LATEST TASK")
        print(f"  id:        {task.id}")
        print(f"  status:    {task.status}")
        print(f"  output:    {task.output_url}")
        print(f"  steps:     {task.steps_count}")
        print(f"  duration:  {task.duration_seconds}s")
        print("=" * 70)

        rows = conn.execute(text(
            "SELECT step_number, action_type, action_params, reasoning, executed_at "
            "FROM task_steps WHERE task_id = :tid ORDER BY step_number"
        ), {"tid": str(task.id)}).fetchall()

        print(f"\nSTEPS ({len(rows)}):\n")
        for r in rows:
            print(f"  #{r.step_number}  {r.action_type}")
            print(f"     params:    {r.action_params}")
            print(f"     reasoning: {r.reasoning}")
            print(f"     at:        {r.executed_at}")
            print()


if __name__ == "__main__":
    main()
