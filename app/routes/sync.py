from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select
from sqlmodel import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, get_request_context, require_permission
from app.models.sync_event import SyncEvent
from app.schemas.sale import SaleCreate
from app.schemas.stock import StockAdjustmentCreate
from app.schemas.sync import SyncMutation, SyncMutationResponse
from app.schemas.purchase import PurchaseCreate
from app.schemas.inventory_count import (
    InventoryCountCreate,
    RecordCountItems,
)
from app.services.sale import SaleService
from app.services.stock import StockService
from app.services.purchase import PurchaseService
from app.services.inventory_count import InventoryCountService
from app.services.entitlements import EntitlementService


router = APIRouter(prefix="/sync", tags=["sync"])

PERMISSIONS_BY_TYPE = {
    "sale": "sales.create",
    "stock_adjustment": "inventory.adjust",
    "physical_count": "inventory.count",
    "purchase": "purchases.create",
}


@router.post(
    "/mutations",
    response_model=SyncMutationResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_mutation(
    mutation: SyncMutation,
    context: RequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    permission = PERMISSIONS_BY_TYPE.get(mutation.type)
    if permission is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported sync mutation type: {mutation.type}",
        )

    EntitlementService.require_feature(
        str(context.business_id),
        "offline_sync",
        db,
    )

    # Reuse the same role/permission rules as the online endpoints.
    require_permission(permission)(context=context, session=db)

    existing = db.execute(
        select(SyncEvent).where(
            SyncEvent.business_id == context.business_id,
            SyncEvent.client_event_id == mutation.client_event_id,
        )
    ).scalar_one_or_none()
    if existing:
        if existing.event_type != mutation.type or existing.payload != mutation.payload:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="client_event_id was already used for a different mutation",
            )
        return {
            "success": True,
            "duplicate": True,
            "client_event_id": mutation.client_event_id,
            "type": existing.event_type,
        }

    event = SyncEvent(
        business_id=context.business_id,
        user_id=context.user.id,
        client_event_id=mutation.client_event_id,
        event_type=mutation.type,
        payload=mutation.payload,
        occurred_at=mutation.occurred_at,
    )
    db.add(event)
    try:
        # Reserve the event before applying the business mutation. The service
        # commits this same session, so the reservation and mutation commit
        # together.
        db.flush()
    except IntegrityError:
        db.rollback()
        duplicate = db.execute(
            select(SyncEvent).where(
                SyncEvent.business_id == context.business_id,
                SyncEvent.client_event_id == mutation.client_event_id,
            )
        ).scalar_one_or_none()
        if duplicate and (
            duplicate.event_type != mutation.type
            or duplicate.payload != mutation.payload
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="client_event_id was already used for a different mutation",
            )
        if duplicate:
            return {
                "success": True,
                "duplicate": True,
                "client_event_id": mutation.client_event_id,
                "type": duplicate.event_type,
            }
        raise

    if mutation.type == "sale":
        payload = SaleCreate.model_validate(mutation.payload)
        result = SaleService.create_sale(
            business_id=str(context.business_id),
            payload=payload,
            user_id=str(context.user.id),
            db=db,
        )
    elif mutation.type == "stock_adjustment":
        payload = StockAdjustmentCreate.model_validate(mutation.payload)
        result = StockService.adjust_stock(
            business_id=str(context.business_id),
            payload=payload,
            user_id=str(context.user.id),
            db=db,
        )
    elif mutation.type == "purchase":
        payload = PurchaseCreate.model_validate(mutation.payload)
        result = PurchaseService.create_purchase(
            business_id=str(context.business_id),
            payload=payload,
            user_id=str(context.user.id),
            db=db,
        )
    elif mutation.type == "physical_count":
        action = mutation.payload.get("action")
        if action == "start":
            payload = InventoryCountCreate.model_validate(mutation.payload)
            result = InventoryCountService.create_count(
                business_id=str(context.business_id),
                payload=payload,
                user_id=str(context.user.id),
                count_id=mutation.payload.get("client_count_id"),
                db=db,
            )
        elif action == "record":
            payload = RecordCountItems.model_validate(mutation.payload)
            result = InventoryCountService.record_count_items(
                business_id=str(context.business_id),
                count_id=str(mutation.payload.get("count_id")),
                items=payload.items,
                user_id=str(context.user.id),
                db=db,
            )
        elif action == "finalize":
            result = InventoryCountService.finalize_count(
                business_id=str(context.business_id),
                count_id=str(mutation.payload.get("count_id")),
                user_id=str(context.user.id),
                db=db,
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Physical count sync action must be start, record, or finalize",
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Sync mutation type '{mutation.type}' is recognized but not "
                "implemented yet"
            ),
        )

    return {
        "success": True,
        "duplicate": False,
        "client_event_id": mutation.client_event_id,
        "type": mutation.type,
        "result": result,
    }
