from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.sale import SaleReturnCreate


def test_return_requires_positive_quantity():
    with pytest.raises(ValidationError):
        SaleReturnCreate(
            reason="Customer return",
            items=[{"sale_item_id": "item-1", "quantity": "0"}],
        )


def test_return_rejects_duplicate_sale_items():
    with pytest.raises(ValidationError):
        SaleReturnCreate(
            reason="Customer return",
            items=[
                {"sale_item_id": "item-1", "quantity": "1"},
                {"sale_item_id": "item-1", "quantity": "2"},
            ],
        )


def test_return_accepts_partial_quantity():
    payload = SaleReturnCreate(
        reason="Wrong size",
        items=[{"sale_item_id": "item-1", "quantity": "1.5"}],
    )

    assert payload.items[0].quantity == Decimal("1.5")
