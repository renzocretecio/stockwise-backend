from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.config.settings import settings
from app.routes import internal
from app.services.weekly_owner_summary import WeeklySummaryRunResult


def test_scheduled_jobs_require_the_configured_bearer_secret(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", "cron-secret")

    internal.require_cron_secret("Bearer cron-secret")

    with pytest.raises(HTTPException) as error:
        internal.require_cron_secret("Bearer wrong-secret")

    assert error.value.status_code == 401


def test_scheduled_jobs_are_unavailable_without_a_secret(monkeypatch):
    monkeypatch.setattr(settings, "CRON_SECRET", None)

    with pytest.raises(HTTPException) as error:
        internal.require_cron_secret("Bearer any-value")

    assert error.value.status_code == 503


@pytest.mark.asyncio
async def test_weekly_summary_job_returns_delivery_counts(monkeypatch):
    async def fake_send_due(now, db, *, dry_run=False):
        assert dry_run is False
        return WeeklySummaryRunResult(
            due=3,
            sent=2,
            skipped_not_entitled=1,
        )

    monkeypatch.setattr(
        internal.WeeklyOwnerSummaryService,
        "send_due",
        fake_send_due,
    )

    result = await internal.run_weekly_owner_summaries(
        False,
        None,
        SimpleNamespace(),
    )

    assert result.due == 3
    assert result.sent == 2
    assert result.skipped_not_entitled == 1


@pytest.mark.asyncio
async def test_weekly_summary_job_returns_error_for_partial_failure(
    monkeypatch,
):
    async def fake_send_due(now, db, *, dry_run=False):
        return WeeklySummaryRunResult(due=1, failed=1)

    monkeypatch.setattr(
        internal.WeeklyOwnerSummaryService,
        "send_due",
        fake_send_due,
    )

    with pytest.raises(HTTPException) as error:
        await internal.run_weekly_owner_summaries(
            False,
            None,
            SimpleNamespace(),
        )

    assert error.value.status_code == 502
    assert error.value.detail["failed"] == 1


@pytest.mark.asyncio
async def test_scheduled_job_supports_dry_run(monkeypatch):
    async def fake_send_due(now, db, *, dry_run=False):
        assert dry_run is True
        return WeeklySummaryRunResult(due=1, would_send=1)

    monkeypatch.setattr(
        internal.WeeklyOwnerSummaryService,
        "send_due",
        fake_send_due,
    )

    result = await internal.run_weekly_owner_summaries(
        True,
        None,
        SimpleNamespace(),
    )

    assert result.due == 1
    assert result.would_send == 1
