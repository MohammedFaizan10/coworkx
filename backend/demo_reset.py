"""
demo_reset.py — Reset CoWorkX to a clean demo state.

Run from the backend/ folder with the venv active:
    cd c:\\Users\\mfaiz\\coworkx\\backend
    venv\\Scripts\\activate
    python demo_reset.py

What it does:
  - Clears all tasks, task_steps, and wallet_transactions
  - Resets the demo user's wallet to 100 CWX
  - Ensures a "busy" and an "offline" decorative machine exist (for map colors)
  - Leaves your REAL daemon-registered machine untouched (so live tasks still run)

NOTE: It does NOT delete your real online machine — deleting it would break the
running daemon. Your daemon's machine stays as the live "online" worker.
"""

import uuid
from datetime import datetime

import models
from database import SessionLocal, engine

# Same demo user UUID used by main.py
DEMO_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")

# Fixed UUIDs so re-running stays idempotent
BUSY_MACHINE_ID    = uuid.UUID("22222222-2222-2222-2222-222222222222")
OFFLINE_MACHINE_ID = uuid.UUID("33333333-3333-3333-3333-333333333333")


def main():
    # Make sure tables exist
    models.Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        # 1. Clear tasks, steps, ledger
        steps_deleted = db.query(models.TaskStep).delete()
        tasks_deleted = db.query(models.Task).delete()
        tx_deleted    = db.query(models.WalletTransaction).delete()

        # 2. Reset demo user wallet to 100
        wallet = db.query(models.Wallet).filter(
            models.Wallet.owner_id == DEMO_USER_ID
        ).first()
        if not wallet:
            wallet = models.Wallet(id=uuid.uuid4(), owner_id=DEMO_USER_ID, balance=100.0)
            db.add(wallet)
        else:
            wallet.balance = 100.0

        # 3. Ensure decorative busy + offline machines exist (for map colors)
        _ensure_machine(db, BUSY_MACHINE_ID, "Demo-Workstation-2",
                        models.MachineStatus.busy, 17.3850, 78.4867)   # Hyderabad
        _ensure_machine(db, OFFLINE_MACHINE_ID, "Demo-Workstation-3",
                        models.MachineStatus.offline, 19.0760, 72.8777)  # Mumbai

        db.commit()

        online = db.query(models.Machine).filter(
            models.Machine.status == models.MachineStatus.online
        ).count()

        print("Demo ready! ✅")
        print(f"  cleared {tasks_deleted} tasks, {steps_deleted} steps, {tx_deleted} transactions")
        print(f"  wallet reset to {float(wallet.balance):.2f} CWX")
        print(f"  online machines: {online} (your live daemon machine)")
        print("  decorative machines: 1 busy, 1 offline")
        if online == 0:
            print("  ⚠ No online machine — start your daemon (python daemon.py) so tasks can run.")
    finally:
        db.close()


def _ensure_machine(db, machine_id, name, status, lat, lon):
    m = db.query(models.Machine).filter(models.Machine.id == machine_id).first()
    if m:
        m.status = status
        return
    db.add(models.Machine(
        id                    = machine_id,
        owner_id              = uuid.uuid4(),
        display_name          = name,
        os                    = "windows",
        cpu_model             = "Intel Core i7",
        cpu_cores             = 8,
        ram_gb                = 16,
        gpu_model             = None,
        storage_gb            = 512,
        installed_software    = ["python", "node", "docker"],
        supported_tasks       = ["browsing", "coding"],
        price_per_hour        = 5.0,
        latitude              = lat,
        longitude             = lon,
        status                = status,
        cpu_usage_pct         = 0,
        ram_usage_pct         = 0,
        last_heartbeat        = datetime.utcnow(),
        total_tasks_completed = 0,
        daemon_version        = "0.0.3",
        registered_at         = datetime.utcnow(),
    ))


if __name__ == "__main__":
    main()
