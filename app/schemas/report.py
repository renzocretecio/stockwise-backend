from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime


# ============================================================================
# SALES REPORT
# ============================================================================

class SalesReportSummary(BaseModel):
    total_sales: int
    total_revenue: float
    total_profit: float
    total_items_sold: float
    average_sale_value: float
    voided_count: int


class SalesReportByDay(BaseModel):
    date: str
    revenue: float
    profit: float
    sales_count: int


class SalesReportTopProduct(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    quantity_sold: float
    units_per_day: float
    current_stock: float
    days_of_stock_remaining: Optional[float] = None
    revenue: float
    profit: float


class SalesReportSlowProduct(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    current_stock: float
    inventory_value: float
    last_sale_date: Optional[str] = None
    days_without_sale: int
    classification: str


class SalesReportResponse(BaseModel):
    success: bool = True
    period_days: int
    summary: SalesReportSummary
    by_day: list[SalesReportByDay]
    top_products: list[SalesReportTopProduct]
    slow_products: list[SalesReportSlowProduct]


class OperationalMetricsResponse(BaseModel):
    success: bool = True
    period_days: int
    stock_accuracy_rate: Optional[float] = None
    counted_items: int
    accurate_items: int
    inventory_days: Optional[float] = None
    inventory_value: float
    period_cogs: float
    shrinkage_rate: Optional[float] = None
    shrinkage_units: float
    shrinkage_value: float
    receipt_completion_rate: Optional[float] = None
    ordered_purchases: int
    received_purchases: int


# ============================================================================
# PURCHASE REPORT
# ============================================================================

class PurchaseReportSummary(BaseModel):
    total_purchases: int
    total_spent: float
    total_items_received: float
    average_purchase_value: float
    pending_count: int


class PurchaseReportByDay(BaseModel):
    date: str
    spent: float
    purchases_count: int


class PurchaseReportBySupplier(BaseModel):
    supplier_id: str
    supplier_name: str
    total_spent: float
    purchases_count: int


class PurchaseReportResponse(BaseModel):
    success: bool = True
    period_days: int
    summary: PurchaseReportSummary
    by_day: list[PurchaseReportByDay]
    by_supplier: list[PurchaseReportBySupplier]


# ============================================================================
# INVENTORY REPORT
# ============================================================================

class InventoryReportSummary(BaseModel):
    total_products: int
    total_stock_value: float
    total_units: float
    low_stock_count: int
    out_of_stock_count: int


class InventoryReportByCategory(BaseModel):
    category: str
    product_count: int
    stock_value: float
    total_units: float


class InventoryReportResponse(BaseModel):
    success: bool = True
    summary: InventoryReportSummary
    by_category: list[InventoryReportByCategory]


# ============================================================================
# PROFIT REPORT
# ============================================================================

class ProfitReportSummary(BaseModel):
    total_revenue: float
    total_cost: float
    total_profit: float
    profit_margin_percent: float


class ProfitReportByProduct(BaseModel):
    product_id: str
    product_name: str
    quantity_sold: float
    revenue: float
    cost: float
    profit: float
    margin_percent: float


class ProfitReportResponse(BaseModel):
    success: bool = True
    period_days: int
    summary: ProfitReportSummary
    by_product: list[ProfitReportByProduct]


# ============================================================================
# LOW STOCK REPORT
# ============================================================================

class LowStockItem(BaseModel):
    product_id: str
    product_name: str
    sku: Optional[str] = None
    quantity: float
    reorder_point: float
    safety_stock: float
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    lead_time_days: int
    status: str  # "low_stock" | "out_of_stock"


class LowStockReportResponse(BaseModel):
    success: bool = True
    total_items: int
    items: list[LowStockItem]


# ============================================================================
# STOCK MOVEMENT REPORT
# ============================================================================

class StockMovementSummaryByType(BaseModel):
    movement_type: str
    total_movements: int
    total_quantity_change: float


class StockMovementReportResponse(BaseModel):
    success: bool = True
    period_days: int
    by_type: list[StockMovementSummaryByType]
    total_movements: int
