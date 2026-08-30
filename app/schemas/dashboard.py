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
    forecasts: list[DemandForecastItem]
    anomalies: list[InventoryAnomaly]
