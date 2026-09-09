import csv
from io import StringIO
from typing import Any


REPORT_TITLES = {
    "sales": "Sales report",
    "purchases": "Purchase report",
    "inventory": "Inventory report",
    "profit": "Profit report",
    "low-stock": "Low stock report",
    "stock-movements": "Stock movement report",
}


class ReportExportService:
    @classmethod
    def build_csv(
        cls,
        report_name: str,
        report: dict,
        *,
        business_name: str,
        currency_code: str,
        period_label: str,
        generated_at: str,
    ) -> str:
        output = StringIO(newline="")
        writer = csv.writer(output, lineterminator="\r\n")
        writer.writerows(
            [
                ["Report", REPORT_TITLES[report_name]],
                ["Business", cls.safe_cell(business_name)],
                ["Currency", currency_code],
                ["Period", period_label],
                ["Generated at", generated_at],
            ]
        )

        if report_name == "sales":
            cls._write_sales(writer, report, currency_code)
        elif report_name == "purchases":
            cls._write_purchases(writer, report, currency_code)
        elif report_name == "inventory":
            cls._write_inventory(writer, report, currency_code)
        elif report_name == "profit":
            cls._write_profit(writer, report, currency_code)
        elif report_name == "low-stock":
            cls._write_low_stock(writer, report)
        elif report_name == "stock-movements":
            cls._write_movements(writer, report)
        else:
            raise ValueError(f"Unsupported report: {report_name}")

        return "\ufeff" + output.getvalue()

    @staticmethod
    def safe_cell(value: Any) -> Any:
        if value is None:
            return ""
        if isinstance(value, str) and value.startswith(
            ("=", "+", "-", "@", "\t", "\r")
        ):
            return "'" + value
        return value

    @classmethod
    def _write_summary(
        cls,
        writer: Any,
        rows: list[tuple[str, Any]],
    ) -> None:
        writer.writerow([])
        writer.writerow(["Summary"])
        writer.writerow(["Metric", "Value"])
        for label, value in rows:
            writer.writerow([label, cls.safe_cell(value)])

    @classmethod
    def _write_table(
        cls,
        writer: Any,
        title: str,
        columns: list[tuple[str, str]],
        rows: list[dict],
    ) -> None:
        writer.writerow([])
        writer.writerow([title])
        writer.writerow([label for label, _ in columns])
        for row in rows:
            writer.writerow([cls.safe_cell(row.get(key)) for _, key in columns])

    @classmethod
    def _write_sales(
        cls,
        writer: Any,
        report: dict,
        currency: str,
    ) -> None:
        summary = report["summary"]
        cls._write_summary(
            writer,
            [
                ("Completed sales", summary["total_sales"]),
                (f"Net revenue ({currency})", summary["total_revenue"]),
                (f"Gross profit ({currency})", summary["total_profit"]),
                ("Items sold", summary["total_items_sold"]),
                (
                    f"Average sale value ({currency})",
                    summary["average_sale_value"],
                ),
                ("Voided sales", summary["voided_count"]),
                ("Returns", summary["return_count"]),
                (f"Return amount ({currency})", summary["return_amount"]),
            ],
        )
        cls._write_table(
            writer,
            "Daily performance",
            [
                ("Date", "date"),
                (f"Revenue ({currency})", "revenue"),
                (f"Gross profit ({currency})", "profit"),
                ("Sales", "sales_count"),
            ],
            report.get("by_day", []),
        )
        cls._write_table(
            writer,
            "Top products",
            [
                ("Product ID", "product_id"),
                ("SKU", "sku"),
                ("Product", "product_name"),
                ("Quantity sold", "quantity_sold"),
                ("Units per day", "units_per_day"),
                ("Current stock", "current_stock"),
                ("Days of stock", "days_of_stock_remaining"),
                (f"Revenue ({currency})", "revenue"),
                (f"Gross profit ({currency})", "profit"),
            ],
            report.get("top_products", []),
        )
        cls._write_table(
            writer,
            "Slow-moving products",
            [
                ("Product ID", "product_id"),
                ("SKU", "sku"),
                ("Product", "product_name"),
                ("Current stock", "current_stock"),
                (f"Inventory value ({currency})", "inventory_value"),
                ("Last sale date", "last_sale_date"),
                ("Days without sale", "days_without_sale"),
                ("Classification", "classification"),
            ],
            report.get("slow_products", []),
        )

    @classmethod
    def _write_purchases(
        cls,
        writer: Any,
        report: dict,
        currency: str,
    ) -> None:
        summary = report["summary"]
        cls._write_summary(
            writer,
            [
                ("Received purchases", summary["total_purchases"]),
                (f"Total spent ({currency})", summary["total_spent"]),
                ("Items received", summary["total_items_received"]),
                (
                    f"Average purchase value ({currency})",
                    summary["average_purchase_value"],
                ),
                ("Pending purchases", summary["pending_count"]),
            ],
        )
        cls._write_table(
            writer,
            "Daily purchasing",
            [
                ("Date", "date"),
                (f"Spent ({currency})", "spent"),
                ("Purchases", "purchases_count"),
            ],
            report.get("by_day", []),
        )
        cls._write_table(
            writer,
            "Supplier breakdown",
            [
                ("Supplier ID", "supplier_id"),
                ("Supplier", "supplier_name"),
                (f"Total spent ({currency})", "total_spent"),
                ("Purchases", "purchases_count"),
            ],
            report.get("by_supplier", []),
        )

    @classmethod
    def _write_inventory(
        cls,
        writer: Any,
        report: dict,
        currency: str,
    ) -> None:
        summary = report["summary"]
        cls._write_summary(
            writer,
            [
                ("Active products", summary["total_products"]),
                (
                    f"Total stock value ({currency})",
                    summary["total_stock_value"],
                ),
                ("Total units", summary["total_units"]),
                ("Low-stock products", summary["low_stock_count"]),
                ("Out-of-stock products", summary["out_of_stock_count"]),
            ],
        )
        cls._write_table(
            writer,
            "Category breakdown",
            [
                ("Category", "category"),
                ("Products", "product_count"),
                ("Units", "total_units"),
                (f"Stock value ({currency})", "stock_value"),
            ],
            report.get("by_category", []),
        )

    @classmethod
    def _write_profit(
        cls,
        writer: Any,
        report: dict,
        currency: str,
    ) -> None:
        summary = report["summary"]
        cls._write_summary(
            writer,
            [
                (f"Revenue ({currency})", summary["total_revenue"]),
                (f"Cost of goods ({currency})", summary["total_cost"]),
                (f"Gross profit ({currency})", summary["total_profit"]),
                ("Gross margin (%)", summary["profit_margin_percent"]),
            ],
        )
        cls._write_table(
            writer,
            "Product profitability",
            [
                ("Product ID", "product_id"),
                ("Product", "product_name"),
                ("Quantity sold", "quantity_sold"),
                (f"Revenue ({currency})", "revenue"),
                (f"Cost ({currency})", "cost"),
                (f"Gross profit ({currency})", "profit"),
                ("Margin (%)", "margin_percent"),
            ],
            report.get("by_product", []),
        )

    @classmethod
    def _write_low_stock(cls, writer: Any, report: dict) -> None:
        cls._write_summary(
            writer,
            [("Products needing attention", report["total_items"])],
        )
        cls._write_table(
            writer,
            "Products requiring replenishment",
            [
                ("Product ID", "product_id"),
                ("SKU", "sku"),
                ("Product", "product_name"),
                ("Status", "status"),
                ("On hand", "quantity"),
                ("Reorder point", "reorder_point"),
                ("Safety stock", "safety_stock"),
                ("Supplier ID", "supplier_id"),
                ("Supplier", "supplier_name"),
                ("Lead time (days)", "lead_time_days"),
            ],
            report.get("items", []),
        )

    @classmethod
    def _write_movements(cls, writer: Any, report: dict) -> None:
        cls._write_summary(
            writer,
            [("Movement records", report["total_movements"])],
        )
        cls._write_table(
            writer,
            "Movement type breakdown",
            [
                ("Movement type", "movement_type"),
                ("Movements", "total_movements"),
                ("Net quantity change", "total_quantity_change"),
            ],
            report.get("by_type", []),
        )
