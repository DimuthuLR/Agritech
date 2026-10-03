"""Quick sanity check for the task state machine."""
from app.db.models.task import TaskStatus
from app.services.task_service import _assert_transition, IllegalTransition


def run():
    # Valid transitions
    _assert_transition(TaskStatus.PENDING_APPROVAL, TaskStatus.APPROVED)
    print("pending->approved: OK")

    _assert_transition(TaskStatus.APPROVED, TaskStatus.DISPATCHED)
    print("approved->dispatched: OK")

    _assert_transition(TaskStatus.DISPATCHED, TaskStatus.ACKED)
    print("dispatched->acked: OK")

    # Illegal transition should raise
    try:
        _assert_transition(TaskStatus.DONE, TaskStatus.APPROVED)
        print("ERROR: should have raised")
    except IllegalTransition as e:
        print(f"done->approved correctly rejected: {e}")

    # Another illegal transition
    try:
        _assert_transition(TaskStatus.REJECTED, TaskStatus.DISPATCHED)
        print("ERROR: should have raised")
    except IllegalTransition as e:
        print(f"rejected->dispatched correctly rejected: {e}")

    print()
    print("State machine OK")


if __name__ == "__main__":
    run()