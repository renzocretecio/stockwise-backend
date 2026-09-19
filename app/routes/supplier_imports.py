from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config.database import get_db
from app.config.permissions import RequestContext, require_permission
from app.models.product import Supplier
from app.schemas.supplier_import import (
    SupplierImportCommitRequest,
    SupplierImportCommitResponse,
)
from app.services.supplier_import_service import (
    commit_supplier_import,
    parse_supplier_import,
)


router = APIRouter(
    prefix="/imports/suppliers",
    tags=["supplier import"],
)

MAX_IMPORT_BYTES = 5 * 1024 * 1024


@router.post("/preview")
async def preview_supplier_import(
    file: UploadFile = File(...),
    context: RequestContext = Depends(require_permission("suppliers.create")),
    session: Session = Depends(get_db),
):
    file_bytes = await file.read(MAX_IMPORT_BYTES + 1)

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file is empty",
        )

    if len(file_bytes) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Supplier import files must be 5 MB or smaller",
        )

    existing_names = set(
        session.scalars(
            select(Supplier.name).where(
                Supplier.business_id == context.business_id,
                Supplier.is_active.is_(True),
            )
        ).all()
    )
    preview = parse_supplier_import(
        file_bytes=file_bytes,
        filename=file.filename,
        content_type=file.content_type,
        existing_names=existing_names,
    )

    return {
        "business_id": str(context.business_id),
        "filename": file.filename,
        "preview": preview.model_dump(mode="json"),
    }


@router.post(
    "/commit",
    response_model=SupplierImportCommitResponse,
)
def commit_supplier_import_route(
    payload: SupplierImportCommitRequest,
    context: RequestContext = Depends(require_permission("suppliers.create")),
    session: Session = Depends(get_db),
):
    return commit_supplier_import(
        session=session,
        business_id=context.business_id,
        rows=payload.rows,
    )
