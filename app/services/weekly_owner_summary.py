import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlmodel import Session

from app.config.settings import settings
from app.models.business import Business
from app.models.notification import WeeklyOwnerSummarySettings
from app.services.communication import (
    GroqCommunicationService,
    communication_enabled,
)
from app.services.dashboard import DashboardService
from app.services.email import EmailService
from app.services.entitlements import EntitlementService
from app.services.intelligence import IntelligenceService
from app.services.report import ReportService


logger = logging.getLogger(__name__)

SECTION_KEYS = {
    "sales_performance",
    "inventory_health",
    "reorder_recommendations",
    "slow_moving_products",
    "inventory_anomalies",
    "supplier_issues",
}

RETRY_BASE_MINUTES = 5
RETRY_MAX_MINUTES = 360


@dataclass
class WeeklySummaryRunResult:
    due: int = 0
    sent: int = 0
    failed: int = 0
    skipped_not_entitled: int = 0
    would_send: int = 0


class WeeklyOwnerSummaryService:
    @staticmethod
    def _period(business: Business, period_end: date | None = None):
        zone = ZoneInfo(business.timezone)
        end = period_end or datetime.now(zone).date()
        start = end - timedelta(days=6)
        return start, end

    @staticmethod
    def get_or_create_settings(
        business: Business, owner_email: str, db: Session
    ) -> WeeklyOwnerSummarySettings:
        current = db.execute(
            select(WeeklyOwnerSummarySettings).where(
                WeeklyOwnerSummarySettings.business_id == business.id
            )
        ).scalar_one_or_none()
        if current:
            return current
        current = WeeklyOwnerSummarySettings(
            business_id=business.id,
            recipients=[owner_email.lower()],
            included_sections=[
                "sales_performance",
                "inventory_health",
                "reorder_recommendations",
                "slow_moving_products",
                "inventory_anomalies",
                "supplier_issues",
            ],
        )
        db.add(current)
        db.commit()
        db.refresh(current)
        return current

    @staticmethod
    def build_data(
        business: Business,
        db: Session,
        period_end: date | None = None,
    ) -> dict:
        period_start, period_end = WeeklyOwnerSummaryService._period(
            business, period_end
        )
        previous_end = period_start - timedelta(days=1)
        previous_start = previous_end - timedelta(days=6)
        sales = ReportService.get_sales_report(
            str(business.id), 7, db, period_start, period_end, business.timezone
        )
        previous_sales = ReportService.get_sales_report(
            str(business.id),
            7,
            db,
            previous_start,
            previous_end,
            business.timezone,
        )
        dashboard = DashboardService.get_dashboard(str(business.id), db)
        inventory = ReportService.get_inventory_report(str(business.id), db)
        change = None
        previous_revenue = previous_sales["summary"]["total_revenue"]
        if previous_revenue:
            change = round(
                (sales["summary"]["total_revenue"] - previous_revenue)
                / abs(previous_revenue)
                * 100,
                1,
            )
        top_seller = (
            sales["top_products"][0]["product_name"]
            if sales["top_products"]
            else None
        )
        attention = []
        attention.extend(dashboard["forecasts"][:10])
        attention.extend(dashboard["anomalies"][:10])
        attention.extend(dashboard["inventory_efficiency"]["actions"][:10])
        actions = [
            {
                "title": item.get("title") or item.get("product_name"),
                "action": item.get("recommended_action")
                or item.get("suggested_action")
                or item.get("detail"),
                "source": item.get("rule_id")
                or item.get("anomaly_type")
                or item.get("classification"),
            }
            for item in attention[:10]
        ]
        return {
            "period": f"{period_start.isoformat()} to {period_end.isoformat()}",
            "period_start": period_start,
            "period_end": period_end,
            "sales": sales["summary"]["total_revenue"],
            "sales_change_pct": change,
            "gross_profit": sales["summary"]["total_profit"],
            "top_seller": top_seller,
            "low_stock_count": inventory["summary"]["low_stock_count"],
            "stockout_risk_count": len(dashboard["forecasts"]),
            "dead_stock_value": dashboard["inventory_efficiency"][
                "dead_stock_value"
            ],
            "anomaly_count": len(dashboard["anomalies"]),
            "priority_actions": actions,
            "kpis": {
                "sales": sales["summary"]["total_revenue"],
                "gross_profit": sales["summary"]["total_profit"],
                "inventory_value": inventory["summary"]["total_stock_value"],
                "low_stock_count": inventory["summary"]["low_stock_count"],
                "stockout_risk_count": len(dashboard["forecasts"]),
                "dead_stock_value": dashboard["inventory_efficiency"][
                    "dead_stock_value"
                ],
                "anomaly_count": len(dashboard["anomalies"]),
            },
            "needs_attention": attention[:10],
            "recommended_actions": actions,
            "supplier_issues": [],
        }

    @staticmethod
    async def add_ai_summary(data: dict) -> dict:
        facts = {
            key: data[key]
            for key in (
                "period",
                "sales",
                "sales_change_pct",
                "gross_profit",
                "top_seller",
                "low_stock_count",
                "stockout_risk_count",
                "dead_stock_value",
                "anomaly_count",
                "priority_actions",
            )
        }
        facts["period"] = WeeklyOwnerSummaryService._format_period_for_ai(
            facts["period"]
        )
        if communication_enabled():
            try:
                communicator = GroqCommunicationService()
                summary = await communicator.create_weekly_owner_summary(facts)
            except Exception:
                logger.warning("Weekly owner AI summary failed", exc_info=True)
                summary = WeeklyOwnerSummaryService._fallback_summary(facts)
        else:
            summary = WeeklyOwnerSummaryService._fallback_summary(facts)
        return {**data, "ai_executive_summary": summary}

    @staticmethod
    def _fallback_summary(facts: dict) -> str:
        return (
            f"For {facts['period']}, recorded sales were {facts['sales']} "
            f"with gross profit of {facts['gross_profit']}. "
            f"The top seller was {facts['top_seller'] or 'not available'}, "
            f"with {facts['low_stock_count']} low-stock items and "
            f"{facts['stockout_risk_count']} stockout risks requiring review."
        )

    @staticmethod
    def _format_period_for_ai(period: str) -> str:
        try:
            start_value, end_value = period.split(" to ", maxsplit=1)
            start = date.fromisoformat(start_value)
            end = date.fromisoformat(end_value)
        except (TypeError, ValueError):
            return period
        return f"{start.strftime('%b %d, %Y')} to {end.strftime('%b %d, %Y')}"

    @staticmethod
    def render_email(
        business: Business,
        data: dict,
        settings_row,
    ) -> tuple[str, str]:
        currency = business.currency_code or "PHP"
        business_name = business.name
        period = data["period"]
        display_period = WeeklyOwnerSummaryService._format_period_for_ai(period)
        sections = settings_row.included_sections or []

        subject_title = f"Weekly Owner Summary | {business_name}"

        # ---------------------------------------------------------
        # Helpers
        # ---------------------------------------------------------

        def money(value) -> str:
            try:
                amount = float(value or 0)
                return f"{currency} {amount:,.2f}"
            except (TypeError, ValueError):
                return f"{currency} {value}"

        def humanize(value: str | None) -> str:
            if not value:
                return ""

            return str(value).replace("_", " ").strip().capitalize()

        def readable_action(action: str | None) -> str:
            if not action or str(action).lower() == "none":
                return "Review this item in KitaStock."

            action_map = {
                "count_variance": (
                    "Verify the physical count and review recent stock movements."
                ),
                "correction": (
                    "Review the inventory correction and confirm that the adjustment is valid."
                ),
                "verify_count": (
                    "Verify the physical count and check for missing or incorrect entries."
                ),
                "reorder_now": (
                    "Review the recommended reorder quantity and consider placing an order."
                ),
                "review_reorder": (
                    "Review the current stock forecast and reorder recommendation."
                ),
                "monitor_stock": (
                    "Monitor stock levels closely and review the forecast."
                ),
                "discount": (
                    "Consider a discount or promotion to move excess inventory."
                ),
            }

            normalized = str(action).strip().lower()

            if normalized in action_map:
                return action_map[normalized]

            # Preserve already-readable recommendations.
            if " " in str(action):
                return str(action)

            return humanize(str(action))

        def attention_label(item: dict) -> str:
            return str(
                item.get("title")
                or item.get("product_name")
                or item.get("anomaly_type")
                or "Inventory issue"
            )

        def attention_description(item: dict) -> str | None:
            description = (
                item.get("description")
                or item.get("reason")
                or item.get("message")
                or item.get("explanation")
            )
            if isinstance(description, (list, tuple)):
                description = " ".join(
                    str(part).strip()
                    for part in description
                    if str(part).strip()
                )
            return str(description).strip() if description else None

        # ---------------------------------------------------------
        # Plain-text email
        # ---------------------------------------------------------

        lines = [
            "WEEKLY OWNER SUMMARY",
            business_name,
            "",
            display_period,
            "",
            "AI EXECUTIVE SUMMARY",
            data["ai_executive_summary"],
        ]

        # ---------------------------------------------------------
        # HTML email
        # ---------------------------------------------------------

        html_sections = [
            f"""
            <div style="margin-bottom: 28px;">
                <h1 style="
                    margin: 0 0 6px 0;
                    font-size: 26px;
                    color: #111827;
                ">
                    Weekly Owner Summary
                </h1>

                <p style="
                    margin: 0;
                    color: #6b7280;
                    font-size: 14px;
                ">
                    {escape(business_name)} · {escape(display_period)}
                </p>
            </div>
            """,
            f"""
            <div style="
                background: #f8fafc;
                border: 1px solid #e5e7eb;
                border-radius: 10px;
                padding: 20px;
                margin-bottom: 28px;
            ">
                <h2 style="
                    margin: 0 0 10px 0;
                    font-size: 18px;
                    color: #111827;
                ">
                    This Week's Summary
                </h2>

                <p style="
                    margin: 0;
                    line-height: 1.6;
                    color: #374151;
                ">
                    {escape(data["ai_executive_summary"])}
                </p>
            </div>
            """,
        ]

        # ---------------------------------------------------------
        # KPI / Week at a Glance
        # ---------------------------------------------------------

        kpis = data.get("kpis", {})

        if "sales_performance" in sections or "inventory_health" in sections:
            lines += ["", "THIS WEEK AT A GLANCE"]

            table_rows = []

            if "sales_performance" in sections:
                sales = money(kpis.get("sales"))
                gross_profit = money(kpis.get("gross_profit"))

                lines += [
                    f"Sales: {sales}",
                    f"Gross Profit: {gross_profit}",
                ]

                table_rows += [
                    ("Sales", sales),
                    ("Gross Profit", gross_profit),
                ]

            if "inventory_health" in sections:
                inventory_value = money(kpis.get("inventory_value"))
                low_stock_count = kpis.get("low_stock_count", 0)

                lines += [
                    f"Inventory Value: {inventory_value}",
                    f"Low Stock Items: {low_stock_count}",
                ]

                table_rows += [
                    ("Inventory Value", inventory_value),
                    ("Low Stock Items", str(low_stock_count)),
                ]

            rows_html = "".join(
                f"""
                <tr>
                    <td style="
                        padding: 10px 12px;
                        border-bottom: 1px solid #e5e7eb;
                        color: #6b7280;
                    ">
                        {escape(label)}
                    </td>

                    <td style="
                        padding: 10px 12px;
                        border-bottom: 1px solid #e5e7eb;
                        text-align: right;
                        font-weight: 600;
                        color: #111827;
                    ">
                        {escape(value)}
                    </td>
                </tr>
                """
                for label, value in table_rows
            )

            html_sections.append(
                f"""
                <div style="margin-bottom: 28px;">
                    <h2 style="
                        font-size: 18px;
                        color: #111827;
                        margin-bottom: 12px;
                    ">
                        This Week at a Glance
                    </h2>

                    <table
                        width="100%"
                        cellpadding="0"
                        cellspacing="0"
                        style="
                            border-collapse: collapse;
                            border: 1px solid #e5e7eb;
                            border-radius: 8px;
                        "
                    >
                        {rows_html}
                    </table>
                </div>
                """
            )

        # ---------------------------------------------------------
        # Needs Your Attention
        # ---------------------------------------------------------

        include_attention = any(
            section in sections
            for section in [
                "reorder_recommendations",
                "slow_moving_products",
                "inventory_anomalies",
            ]
        )

        if include_attention:
            attention_items = data.get("needs_attention", [])

            lines += ["", "NEEDS YOUR ATTENTION"]

            html_items = []

            if attention_items:
                for item in attention_items:
                    label = attention_label(item)
                    description = attention_description(item)

                    if description:
                        lines.append(f"- {label}: {description}")
                    else:
                        lines.append(f"- {label}")

                    html_items.append(
                        f"""
                        <div style="
                            padding: 14px 0;
                            border-bottom: 1px solid #e5e7eb;
                        ">
                            <div style="
                                font-weight: 600;
                                color: #111827;
                                margin-bottom: 4px;
                            ">
                                {escape(label)}
                            </div>

                            {
                                f'''
                                <div style="
                                    color: #6b7280;
                                    font-size: 14px;
                                    line-height: 1.5;
                                ">
                                    {escape(str(description))}
                                </div>
                                '''
                                if description
                                else ""
                            }
                        </div>
                        """
                    )
            else:
                lines.append("- Nothing requires attention this period.")

                html_items.append(
                    """
                    <p style="color: #6b7280;">
                        Nothing requires attention this period.
                    </p>
                    """
                )

            html_sections.append(
                f"""
                <div style="margin-bottom: 28px;">
                    <h2 style="
                        font-size: 18px;
                        color: #111827;
                        margin-bottom: 8px;
                    ">
                        Needs Your Attention
                    </h2>

                    {''.join(html_items)}
                </div>
                """
            )

        # ---------------------------------------------------------
        # Recommended Priorities
        # ---------------------------------------------------------

        if "reorder_recommendations" in sections:
            recommended_actions = data.get("recommended_actions", [])

            lines += ["", "RECOMMENDED PRIORITIES"]

            html_actions = []

            if recommended_actions:
                for index, item in enumerate(recommended_actions, start=1):
                    title = str(item.get("title") or "Inventory item")
                    action = readable_action(item.get("action"))

                    lines.append(f"{index}. {title}: {action}")

                    html_actions.append(
                        f"""
                        <div style="
                            display: block;
                            margin-bottom: 16px;
                        ">
                            <div style="
                                font-weight: 600;
                                color: #111827;
                                margin-bottom: 3px;
                            ">
                                {index}. {escape(title)}
                            </div>

                            <div style="
                                color: #4b5563;
                                line-height: 1.5;
                                font-size: 14px;
                            ">
                                {escape(action)}
                            </div>
                        </div>
                        """
                    )
            else:
                lines.append("- No actions recommended this week.")

                html_actions.append(
                    """
                    <p style="color: #6b7280;">
                        No actions recommended this week.
                    </p>
                    """
                )

            html_sections.append(
                f"""
                <div style="margin-bottom: 30px;">
                    <h2 style="
                        font-size: 18px;
                        color: #111827;
                        margin-bottom: 14px;
                    ">
                        Recommended Priorities
                    </h2>

                    {''.join(html_actions)}
                </div>
                """
            )

        # ---------------------------------------------------------
        # CTA
        # ---------------------------------------------------------

        lines += [
            "",
            "OPEN KITASTOCK",
            settings.APP_URL,
        ]

        html_sections.append(
            f"""
            <div style="
                border-top: 1px solid #e5e7eb;
                padding-top: 24px;
                text-align: center;
            ">
                <p style="
                    margin: 0 0 16px 0;
                    color: #6b7280;
                ">
                    Review forecasts, inventory issues, and recommendations
                    in KitaStock.
                </p>

                <a
                    href="{escape(settings.APP_URL)}"
                    style="
                        display: inline-block;
                        background: #111827;
                        color: #ffffff;
                        text-decoration: none;
                        padding: 12px 22px;
                        border-radius: 8px;
                        font-weight: 600;
                    "
                >
                    Open KitaStock
                </a>
            </div>
            """
        )

        html = f"""
        <!DOCTYPE html>
        <html>
            <body style="
                margin: 0;
                padding: 0;
                background: #f3f4f6;
                font-family:
                    Arial,
                    Helvetica,
                    sans-serif;
            ">
                <div style="
                    max-width: 640px;
                    margin: 0 auto;
                    padding: 32px 16px;
                ">
                    <div style="
                        background: #ffffff;
                        border-radius: 12px;
                        padding: 32px;
                        border: 1px solid #e5e7eb;
                    ">
                        {''.join(html_sections)}
                    </div>

                    <p style="
                        text-align: center;
                        color: #9ca3af;
                        font-size: 12px;
                        margin-top: 20px;
                    ">
                        Generated by KitaStock
                    </p>
                </div>
            </body>
        </html>
        """

        return "\n".join(lines), html

    @staticmethod
    async def preview(
        business: Business,
        settings_row: WeeklyOwnerSummarySettings,
        db: Session,
    ) -> dict:
        data = WeeklyOwnerSummaryService.build_data(business, db)
        data = await WeeklyOwnerSummaryService.add_ai_summary(data)
        if settings_row.action_required_only and not data["needs_attention"]:
            data["recommended_actions"] = []
        return data

    @staticmethod
    async def send_now(
        business: Business,
        settings_row: WeeklyOwnerSummarySettings,
        db: Session,
    ) -> dict:
        data = await WeeklyOwnerSummaryService.preview(
            business, settings_row, db
        )
        text, html = WeeklyOwnerSummaryService.render_email(
            business, data, settings_row
        )
        WeeklyOwnerSummaryService.send_email(
            settings_row.recipients,
            f"Weekly Owner Summary | {business.name}",
            text,
            html,
        )
        WeeklyOwnerSummaryService._record_success(
            settings_row,
            data["period_end"],
            datetime.now(timezone.utc),
            db,
        )
        return data

    @staticmethod
    def due_businesses(
        now: datetime, db: Session
    ) -> list[tuple[Business, WeeklyOwnerSummarySettings, date]]:
        utc_now = WeeklyOwnerSummaryService._as_utc(now)
        rows = db.execute(
            select(Business, WeeklyOwnerSummarySettings)
            .join(
                WeeklyOwnerSummarySettings,
                WeeklyOwnerSummarySettings.business_id == Business.id,
            )
            .where(
                Business.is_active.is_(True),
                WeeklyOwnerSummarySettings.enabled.is_(True),
            )
        ).all()
        due = []
        for business, row in rows:
            try:
                period_end = WeeklyOwnerSummaryService._due_period_end(
                    business,
                    row,
                    utc_now,
                )
            except ZoneInfoNotFoundError:
                logger.error(
                    "Weekly summary skipped for business %s: invalid "
                    "timezone %s",
                    business.id,
                    business.timezone,
                )
                continue
            if period_end is not None:
                due.append((business, row, period_end))
        return due

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _due_period_end(
        business: Business,
        row: WeeklyOwnerSummarySettings,
        now: datetime,
    ) -> date | None:
        utc_now = WeeklyOwnerSummaryService._as_utc(now)
        local_now = utc_now.astimezone(ZoneInfo(business.timezone))
        if local_now.weekday() != row.send_weekday:
            return None
        scheduled = local_now.replace(
            hour=row.send_hour,
            minute=row.send_minute,
            second=0,
            microsecond=0,
        )
        if local_now < scheduled:
            return None
        period_end = local_now.date() - timedelta(days=1)
        if row.last_sent_period_end == period_end.isoformat():
            return None
        next_attempt = row.next_attempt_at
        if next_attempt is not None:
            if next_attempt.tzinfo is None:
                next_attempt = next_attempt.replace(tzinfo=timezone.utc)
            if next_attempt > utc_now:
                return None
        return period_end

    @staticmethod
    async def send_due(
        now: datetime,
        db: Session,
        *,
        dry_run: bool = False,
    ) -> WeeklySummaryRunResult:
        """Send every due summary while isolating failures by business."""
        utc_now = WeeklyOwnerSummaryService._as_utc(now)
        due = WeeklyOwnerSummaryService.due_businesses(utc_now, db)
        result = WeeklySummaryRunResult(due=len(due))
        for business, row, period_end in due:
            try:
                (
                    _,
                    entitlements,
                    _,
                ) = EntitlementService.entitlements_for_business(
                    str(business.id),
                    db,
                )
            except Exception:
                db.rollback()
                logger.exception(
                    "Weekly summary entitlement check failed for business %s",
                    business.id,
                )
                result.failed += 1
                continue
            if not entitlements.weekly_owner_summary:
                result.skipped_not_entitled += 1
                continue
            if dry_run:
                result.would_send += 1
                continue

            try:
                WeeklyOwnerSummaryService._record_attempt(
                    row,
                    period_end,
                    utc_now,
                    db,
                )
                data = WeeklyOwnerSummaryService.build_data(
                    business,
                    db,
                    period_end,
                )
                data = await WeeklyOwnerSummaryService.add_ai_summary(data)
                text, html = WeeklyOwnerSummaryService.render_email(
                    business,
                    data,
                    row,
                )
                WeeklyOwnerSummaryService.send_email(
                    row.recipients,
                    f"Weekly Owner Summary | {business.name}",
                    text,
                    html,
                )
                WeeklyOwnerSummaryService._record_success(
                    row,
                    period_end,
                    utc_now,
                    db,
                )
            except Exception as error:
                db.rollback()
                try:
                    WeeklyOwnerSummaryService._record_failure(
                        row,
                        period_end,
                        utc_now,
                        error,
                        db,
                    )
                except Exception:
                    db.rollback()
                    logger.exception(
                        "Could not record weekly summary failure for "
                        "business %s",
                        business.id,
                    )
                logger.exception(
                    "Weekly summary delivery failed for business %s",
                    business.id,
                )
                result.failed += 1
                continue

            logger.info(
                "Weekly summary sent for business %s, period ending %s",
                business.id,
                period_end.isoformat(),
            )
            result.sent += 1
        return result

    @staticmethod
    def _record_attempt(
        row: WeeklyOwnerSummarySettings,
        period_end: date,
        now: datetime,
        db: Session,
    ) -> None:
        period_key = period_end.isoformat()
        if row.last_attempt_period_end != period_key:
            row.consecutive_failures = 0
        row.last_attempt_period_end = period_key
        row.last_attempted_at = now
        row.last_delivery_status = "sending"
        row.last_delivery_error = None
        row.next_attempt_at = None
        db.add(row)
        db.commit()

    @staticmethod
    def _record_success(
        row: WeeklyOwnerSummarySettings,
        period_end: date,
        now: datetime,
        db: Session,
    ) -> None:
        tracked = db.get(WeeklyOwnerSummarySettings, row.id) or row
        tracked.last_sent_period_end = period_end.isoformat()
        tracked.last_sent_at = now
        tracked.last_delivery_status = "sent"
        tracked.last_delivery_error = None
        tracked.consecutive_failures = 0
        tracked.next_attempt_at = None
        db.add(tracked)
        db.commit()

    @staticmethod
    def _record_failure(
        row: WeeklyOwnerSummarySettings,
        period_end: date,
        now: datetime,
        error: Exception,
        db: Session,
    ) -> None:
        db.rollback()
        tracked = db.get(WeeklyOwnerSummarySettings, row.id) or row
        period_key = period_end.isoformat()
        previous_failures = (
            tracked.consecutive_failures or 0
            if tracked.last_attempt_period_end == period_key
            else 0
        )
        failures = previous_failures + 1
        delay = min(
            RETRY_BASE_MINUTES * (2 ** (failures - 1)),
            RETRY_MAX_MINUTES,
        )
        tracked.last_attempt_period_end = period_key
        tracked.last_attempted_at = now
        tracked.last_delivery_status = "failed"
        tracked.last_delivery_error = (f"{type(error).__name__}: {error}")[
            :1000
        ]
        tracked.consecutive_failures = failures
        tracked.next_attempt_at = now + timedelta(minutes=delay)
        db.add(tracked)
        db.commit()

    @staticmethod
    def send_email(
        recipients: list[str],
        subject: str,
        text: str,
        html: str,
    ) -> None:
        EmailService.send(recipients, subject, text, html)
