# app/api/routes/product_import.py

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
)
from sqlalchemy.orm import Session

from app.config.permissions import (
    RequestContext,
    require_permission,
)
from app.config.database import get_db
from app.schemas.product_import import (
    ProductImportCommitRequest,
)
from app.services.product_import_service import (
    commit_product_import,
    parse_product_import,
)

router = APIRouter(
    prefix="/imports/products",
    tags=["product import"],
)


@router.post("/preview")
async def preview_product_import(
    file: UploadFile = File(...),
    context: RequestContext = Depends(
        require_permission("products.create")
    ),
):
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty",
        )

    preview = parse_product_import(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=file.content_type,
    )

    return {
        "business_id": str(context.business_id),
        "filename": file.filename,
        "preview": preview.model_dump(mode="json"),
    }

@router.post("/commit")
def commit_product_import_route(
    payload: ProductImportCommitRequest,
    context: RequestContext = Depends(
        require_permission("products.create")
    ),
    session: Session = Depends(get_db),
):
    return commit_product_import(
        session=session,
        business_id=context.business_id,
        user_id=context.user.id,
        rows=payload.rows,
    )