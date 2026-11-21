"""Daily jobs (APScheduler, in-process). Move to Celery/cron when there is more than one worker."""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import get_settings
from app.ingest import run_all

log = logging.getLogger(__name__)


def _job() -> None:
    try:
        report = run_all()
        log.info("Scheduled ingest finished: %s → %s", report["started_at"], report["finished_at"])
    except Exception:
        log.exception("Scheduled ingest failed")


def start_scheduler() -> BackgroundScheduler:
    tz = get_settings().scheduler_timezone
    sched = BackgroundScheduler(timezone=tz)
    # 07:15 Rome: overnight FRED releases and ECB/BoJ. 23:15 Rome: after the US close
    # (FRED rates and H.4.1 Thursday release, market prices).
    for hour in (7, 23):
        sched.add_job(_job, CronTrigger(hour=hour, minute=15, timezone=tz),
                      id=f"ingest_{hour}", max_instances=1, coalesce=True,
                      misfire_grace_time=3600)
    sched.start()
    log.info("Scheduler started (%s): ingest at 07:15 and 23:15", tz)
    return sched
