import os
import sys
import django
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'marmot.settings')
django.setup()

from apps.backtest.models import BacktestTask
from apps.backtest.services import send_backtest_control_command, execute_python_rl_backtest, BacktestControlRegistry

def run_integration_test():
    task = BacktestTask.objects.order_by('-id').first()
    if not task:
        print("No task found to test.")
        return

    print(f"=== Starting Control Lifecycle Test on Task #{task.id} ===")
    
    # 1. Test Pause & Resume registration state
    BacktestControlRegistry.register(task.id)
    ctrl = BacktestControlRegistry.get(task.id)
    assert ctrl is not None, "Registry should contain task"
    assert ctrl["pause_event"].is_set() is True, "Initial pause event should be set (unpaused)"
    assert ctrl["cancel_event"].is_set() is False, "Initial cancel event should not be set"

    BacktestControlRegistry.pause(task.id)
    assert ctrl["pause_event"].is_set() is False, "Pause event should be cleared"

    BacktestControlRegistry.resume(task.id)
    assert ctrl["pause_event"].is_set() is True, "Pause event should be set again after resume"

    BacktestControlRegistry.cancel(task.id)
    assert ctrl["cancel_event"].is_set() is True, "Cancel event should be set"
    assert ctrl["pause_event"].is_set() is True, "Cancel should unblock pause wait"
    print("✅ BacktestControlRegistry unit assertions passed.")

    # 2. Test Live Thread Simulation
    print("\n--- Testing Live Background Thread Pause/Resume/Cancel ---")
    task.status = BacktestTask.StatusChoices.RUNNING
    task.progress = 5
    task.save(update_fields=['status', 'progress'])

    # Start background execution in a separate daemon thread
    exec_thread = threading.Thread(target=execute_python_rl_backtest, args=(task.id,), daemon=True)
    exec_thread.start()

    # Give it 0.5s to start running
    time.sleep(0.5)
    task.refresh_from_db()
    print(f"Task status after start: {task.status}, progress: {task.progress}%")

    # Now send PAUSE
    print("\nTriggering PAUSE...")
    send_backtest_control_command(task.id, 'PAUSE')
    time.sleep(0.3)
    task.refresh_from_db()
    paused_status = task.status
    paused_prog = task.progress
    print(f"Task status after PAUSE: {paused_status}, progress: {paused_prog}%")
    assert paused_status == BacktestTask.StatusChoices.PAUSED, f"Expected PAUSED, got {paused_status}"

    # Wait 1 second to confirm it remains frozen and doesn't advance
    time.sleep(1.0)
    task.refresh_from_db()
    print(f"Task progress after waiting 1s while PAUSED: {task.progress}% (was {paused_prog}%)")
    assert task.status == BacktestTask.StatusChoices.PAUSED
    assert task.progress == paused_prog, "Progress should NOT advance while paused!"
    print("✅ Execution is strictly frozen during PAUSE!")

    # Now send RESUME
    print("\nTriggering RESUME...")
    send_backtest_control_command(task.id, 'RESUME')
    time.sleep(0.5)
    task.refresh_from_db()
    print(f"Task status after RESUME: {task.status}, progress: {task.progress}%")
    assert task.status == BacktestTask.StatusChoices.RUNNING, f"Expected RUNNING, got {task.status}"
    print("✅ Execution resumed successfully!")

    # Now send CANCEL
    print("\nTriggering CANCEL...")
    send_backtest_control_command(task.id, 'CANCEL')
    time.sleep(0.8)
    task.refresh_from_db()
    print(f"Task status after CANCEL: {task.status}, progress: {task.progress}%")
    assert task.status == BacktestTask.StatusChoices.CANCELLED, f"Expected CANCELLED, got {task.status}"

    # Wait an additional 1.5 seconds to ensure the thread terminated and did NOT overwrite status to COMPLETED
    time.sleep(1.5)
    task.refresh_from_db()
    print(f"Task status after 1.5s post-cancel: {task.status}")
    assert task.status == BacktestTask.StatusChoices.CANCELLED, f"Status must remain CANCELLED, got {task.status}"
    print("✅ Status remained CANCELLED and was NOT overwritten to COMPLETED!")
    print(f"Preserved partial trades count: {len(task.results.get('trades', []))}")

    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! Control mechanism is 100% efficient.")

if __name__ == "__main__":
    run_integration_test()
