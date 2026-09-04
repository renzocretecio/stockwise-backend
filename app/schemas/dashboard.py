from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel


class DashboardKpis(BaseModel):
    sales_today: float
    sales_yesterday: float
    sales_change_percent: Optional[float] = None
    inventory_value: float
    low_stock_count: int
    out_of_stock_count: int


class InventoryRiskSummary(BaseModel):
    stock_days_threshold: int
    out_of_stock_skus: int
    low_stock_skus: int
    below_reorder_point: int
    below_days_of_stock: int
    pending_reorder_recommendations: int
    expected_deliveries_today: int
    late_purchase_orders: int
    estimated_sales_at_risk: float


class InventoryAgingBucket(BaseModel):
    key: Literal["active", "slowing", "at_risk", "dead_stock"]
    sku_count: int
    inventory_value: float


class InventoryEfficiencyAction(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    classification: Literal[
        "active", "slowing", "at_risk", "dead_stock"
    ]
    current_stock: float
    inventory_value: float
    last_sale_date: Optional[date] = None
    days_without_sale: int
    excess_units: float
    excess_value: float
    is_perishable: bool
    suggested_action: str


class InventoryEfficiencySummary(BaseModel):
    dead_stock_value: float
    dead_stock_percentage: float
    slow_moving_skus: int
    perishable_skus: int
    overstocked_products: int
    capital_tied_up: float
    aging_buckets: list[InventoryAgingBucket]
    actions: list[InventoryEfficiencyAction]


class DashboardTrendPoint(BaseModel):
    date: date
    revenue: float
    gross_profit: float
    items_sold: float
    order_count: int
    inventory_value: float
    stockout_count: int
    dead_stock_value: float
    inventory_turnover: float
    purchase_receipts: float
    adjustments: float
    discrepancies: float


class DashboardTrendsResponse(BaseModel):
    success: bool = True
    start_date: date
    end_date: date
    granularity: Literal["day", "week", "month"]
    inventory_valuation_method: str
    points: list[DashboardTrendPoint]


class ForecastPoint(BaseModel):
    date: date
    actual: Optional[float] = None
    forecast: Optional[float] = None


class DemandForecastItem(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    current_stock: float
    incoming_stock: float
    safety_stock: float
    estimated_unit_cost: float
    estimated_order_cost: float
    lead_time_days: int
    average_daily_sales_7d: float
    average_daily_sales_30d: float
    average_daily_sales_90d: float
    forecast_daily_demand: float
    lead_time_demand: float
    recommended_order_quantity: int
    estimated_stockout_date: Optional[date] = None
    order_by_date: date
    forecast_period_days: int
    history_days: int
    forecast_method: str
    confidence: Literal["high", "medium", "low"]
    recently_out_of_stock: Optional[bool] = None
    promotion_affected: Optional[bool] = None
    explanation: list[str]
    series: list[ForecastPoint]


class InventoryAnomaly(BaseModel):
    id: str
    product_id: str
    product_name: str
    anomaly_type: Literal[
        "negative_stock", "count_variance", "large_adjustment"
    ]
    severity: Literal["high", "medium"]
    quantity: float
    title: str
    detail: str
    occurred_at: Optional[str] = None
    historical_average_variance: Optional[float] = None
    anomaly_threshold: Optional[float] = None
    variance_percentage: Optional[float] = None
    historical_count: Optional[int] = None


class DashboardResponse(BaseModel):
    success: bool = True
    as_of: date
    kpis: DashboardKpis
    inventory_risk: InventoryRiskSummary
    inventory_efficiency: InventoryEfficiencySummary
    forecasts: list[DemandForecastItem]
    anomalies: list[InventoryAnomaly]
