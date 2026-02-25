from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import User
from app.schemas import ImportResponse
from app.services.ingest import ingest_csv

router = APIRouter()


@router.post("", response_model=ImportResponse)
async def import_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        content = await file.read()
        result = ingest_csv(db, user_id=current_user.id, file_bytes=content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ImportResponse(
        import_batch_id=result.import_batch.id,
        imported_rows=result.imported_rows,
        total_rows=result.total_rows,
        skipped_duplicates=result.skipped_duplicates,
    )
