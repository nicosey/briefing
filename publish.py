import sys

from config import log
from db     import init_db, get_pending_outbox, mark_outbox_published, cleanup_outbox
from delivery import make_delivery


def main():
    args    = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry_run = "--dry-run" in sys.argv[1:]
    dest    = args[0] if args else None

    init_db()

    pending = get_pending_outbox(dest)
    if not pending:
        log(f"📭 No pending outbox entries{f' for {dest}' if dest else ''}.")
        return

    log(f"📬 {len(pending)} pending entr{'y' if len(pending) == 1 else 'ies'}"
        f"{f' for {dest}' if dest else ''}{'  [DRY RUN]' if dry_run else ''}")
    log("")

    for outbox_id, entry_dest, message in pending:
        log(f"📨 [{entry_dest}] {message[:60].strip()}...")
        delivery = make_delivery(entry_dest, dry_run)
        ok = delivery.send_long(message)
        if ok and not dry_run:
            mark_outbox_published(outbox_id)
        log("")

    cleanup_outbox(max_age_hours=24)
    log("Done!")


if __name__ == "__main__":
    main()
