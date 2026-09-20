import argparse
import asyncio
import logging
from datetime import datetime, timezone

from app.config.database import SessionLocal
from app.config.settings import settings
from app.services.weekly_owner_summary import WeeklyOwnerSummaryService


logger = logging.getLogger(__name__)


async def run(*, dry_run: bool = False) -> int:
    now = datetime.now(timezone.utc)
    try:
        with SessionLocal() as db:
            result = await WeeklyOwnerSummaryService.send_due(
                now,
                db,
                dry_run=dry_run,
            )
    except Exception:
        logger.exception("Weekly owner summary job failed")
        return 1

    logger.info(
        "Weekly owner summary job complete: due=%s sent=%s failed=%s "
        "not_entitled=%s would_send=%s dry_run=%s",
        result.due,
        result.sent,
        result.failed,
        result.skipped_not_entitled,
        result.would_send,
        dry_run,
    )
    return 1 if result.failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send due KitaStock weekly owner summaries.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report due deliveries without sending email or updating state.",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    return asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    raise SystemExit(main())
