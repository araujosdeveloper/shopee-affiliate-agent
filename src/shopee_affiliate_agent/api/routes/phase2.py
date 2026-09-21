import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

import kombu.exceptions  # type: ignore[import-untyped]
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import asc, desc, select
from sqlalchemy.orm import Session

from shopee_affiliate_agent.api.dependencies import require_idempotency_key, require_operator_id
from shopee_affiliate_agent.api.schemas import (
    AlertOut,
    AssessmentCreate,
    AssessmentOut,
    BatchOut,
    DismissAction,
    ManualImportCreate,
    OpportunityOut,
    ProductCreate,
    ProductOut,
    ProductUpdate,
    RowOut,
    ScoreOut,
    SnapshotCreate,
    SnapshotOut,
    VersionAction,
)
from shopee_affiliate_agent.db.models import (
    ImportBatch,
    ImportOutbox,
    ImportRow,
    OperationalAlert,
    Product,
    ProductAssessment,
    ProductOpportunity,
    ProductScore,
    ProductSnapshot,
)
from shopee_affiliate_agent.db.session import get_db_session
from shopee_affiliate_agent.domain.enums import (
    AlertStatus,
    ImportBatchStatus,
    OpportunityStatus,
    OutboxStatus,
    ProductSource,
)
from shopee_affiliate_agent.services.commerce import audit, calculate_score, generate_opportunity
from shopee_affiliate_agent.services.idempotency import record, replay
from shopee_affiliate_agent.services.imports import ImportFileError, ParsedRow, parse_official_csv
from shopee_affiliate_agent.services.ingestion import (
    add_rows,
    create_batch,
    enqueue_import,
    find_snapshot_duplicate,
    process_batch,
)
from shopee_affiliate_agent.services.normalization import (
    canonical_data,
    canonical_sha256,
    normalize_product,
    payload_sha256,
)
from shopee_affiliate_agent.worker import process_import_task

router = APIRouter(prefix="/api/v1", tags=["phase-2"])
Db = Annotated[Session, Depends(get_db_session)]
Operator = Annotated[UUID, Depends(require_operator_id)]
Key = Annotated[str, Depends(require_idempotency_key)]


def found[T](value: T | None, name: str = "resource") -> T:
    if value is None:
        raise HTTPException(status_code=404, detail=f"{name} not found")
    return value


def page(limit: int, offset: int, items: list[Any]) -> dict[str, Any]:
    return {"items": items, "limit": limit, "offset": offset}


@router.post("/products", response_model=ProductOut, status_code=201)
def create_product(body: ProductCreate, session: Db, operator: Operator, key: Key) -> Product:
    payload = body.model_dump(mode="json")
    prior = replay(
        session,
        key=key,
        operation="product.create",
        entity_type="product",
        entity_id=None,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(Product, prior.entity_id), "product")
    existing = session.scalar(
        select(Product).where(
            Product.source == ProductSource.MANUAL, Product.external_id == body.external_id.strip()
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="product already exists")
    normalized = normalize_product(
        {
            **body.model_dump(),
            "price": "0.00",
            "currency": "BRL",
            "available": True,
            "collected_at": datetime.now(UTC),
        },
        ProductSource.MANUAL,
    )
    product = Product(
        source=ProductSource.MANUAL,
        external_id=normalized.external_id,
        title=normalized.title,
        canonical_url=normalized.canonical_url,
        category=normalized.category,
        is_active=True,
    )
    session.add(product)
    session.flush()
    record(
        session,
        key=key,
        operation="product.create",
        entity_type="product",
        entity_id=product.id,
        actor_id=operator,
        payload=payload,
    )
    audit(session, "product.created", "product", product.id, f"audit:{key}", operator)
    session.commit()
    session.refresh(product)
    return product


@router.get("/products")
def list_products(
    session: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return page(
        limit,
        offset,
        list(
            session.scalars(select(Product).order_by(Product.id).limit(limit).offset(offset)).all()
        ),
    )


@router.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: UUID, session: Db) -> Product:
    return found(session.get(Product, product_id), "product")


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(
    product_id: UUID, body: ProductUpdate, session: Db, operator: Operator, key: Key
) -> Product:
    payload = body.model_dump(mode="json", exclude_unset=True)
    prior = replay(
        session,
        key=key,
        operation="product.update",
        entity_type="product",
        entity_id=product_id,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(Product, prior.entity_id), "product")
    product: Product = found(session.get(Product, product_id), "product")
    if product.version != body.version:
        raise HTTPException(status_code=409, detail="stale_version")
    values = body.model_dump(exclude_unset=True, exclude={"version", "is_active"})
    if values:
        normalized = normalize_product(
            {
                "external_id": product.external_id,
                "title": values.get("title", product.title),
                "canonical_url": values.get("canonical_url", product.canonical_url),
                "category": values.get("category", product.category),
                "price": "0.00",
                "currency": "BRL",
                "available": True,
                "collected_at": datetime.now(UTC),
            },
            product.source,
        )
        product.title = normalized.title
        product.canonical_url = normalized.canonical_url
        product.category = normalized.category
    if body.is_active is not None:
        product.is_active = body.is_active
    record(
        session,
        key=key,
        operation="product.update",
        entity_type="product",
        entity_id=product.id,
        actor_id=operator,
        payload=payload,
    )
    audit(session, "product.updated", "product", product.id, f"audit:{key}", operator)
    session.commit()
    session.refresh(product)
    return product


@router.post("/products/{product_id}/snapshots", response_model=SnapshotOut, status_code=201)
def create_snapshot(
    product_id: UUID, body: SnapshotCreate, session: Db, operator: Operator, key: Key
) -> ProductSnapshot:
    payload = {"product_id": str(product_id), "body": body.model_dump(mode="json")}
    prior = replay(
        session,
        key=key,
        operation="snapshot.create",
        entity_type="product_snapshot",
        entity_id=None,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(ProductSnapshot, prior.entity_id), "snapshot")
    product: Product = found(session.get(Product, product_id), "product")
    if product.source != ProductSource.MANUAL:
        raise HTTPException(status_code=409, detail="unsupported_source")
    normalized = normalize_product(
        {
            "external_id": product.external_id,
            "title": product.title,
            **body.model_dump(),
            "canonical_url": product.canonical_url,
            "category": product.category,
        },
        product.source,
    )
    digest = canonical_sha256(normalized)
    snapshot_key = f"canonical:{digest}"
    duplicate = find_snapshot_duplicate(
        session,
        product_id=product.id,
        source=product.source,
        canonical_digest=digest,
        source_payload_hash=normalized.source_payload_hash,
    )
    if duplicate:
        record(
            session,
            key=key,
            operation="snapshot.create",
            entity_type="product_snapshot",
            entity_id=duplicate.id,
            actor_id=operator,
            payload=payload,
        )
        session.commit()
        return duplicate
    snapshot = ProductSnapshot(
        product_id=product.id,
        source=product.source,
        price=normalized.price,
        currency=normalized.currency,
        available=normalized.available,
        collected_at=normalized.collected_at,
        source_payload_hash=normalized.source_payload_hash,
        idempotency_key=snapshot_key,
    )
    session.add(snapshot)
    session.flush()
    record(
        session,
        key=key,
        operation="snapshot.create",
        entity_type="product_snapshot",
        entity_id=snapshot.id,
        actor_id=operator,
        payload=payload,
    )
    audit(session, "snapshot.created", "product_snapshot", snapshot.id, f"audit:{key}", operator)
    session.commit()
    session.refresh(snapshot)
    return snapshot


@router.get("/products/{product_id}/snapshots")
def list_snapshots(
    product_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    found(session.get(Product, product_id), "product")
    items = session.scalars(
        select(ProductSnapshot)
        .where(ProductSnapshot.product_id == product_id)
        .order_by(ProductSnapshot.collected_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return page(limit, offset, list(items))


@router.post("/imports/manual", response_model=BatchOut, status_code=201)
def manual_import(
    body: ManualImportCreate, session: Db, operator: Operator, key: Key
) -> ImportBatch:
    payload_model = body.model_dump(mode="json")
    prior = replay(
        session,
        key=key,
        operation="import.manual",
        entity_type="import_batch",
        entity_id=None,
        actor_id=operator,
        payload=payload_model,
    )
    if prior:
        return found(session.get(ImportBatch, prior.entity_id), "import batch")
    normalized = normalize_product(body.model_dump(), ProductSource.MANUAL)
    canonical = canonical_data(normalized)
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    batch = create_batch(
        session,
        source=ProductSource.MANUAL,
        filename=None,
        content_type="application/json",
        payload_hash=payload_sha256(payload),
        operator_id=operator,
        key=key,
    )
    add_rows(
        session,
        batch,
        [ParsedRow(1, {name: str(value) for name, value in body.model_dump().items()}, canonical)],
    )
    record(
        session,
        key=key,
        operation="import.manual",
        entity_type="import_batch",
        entity_id=batch.id,
        actor_id=operator,
        payload=payload_model,
    )
    process_batch(session, batch.id)
    session.commit()
    session.refresh(batch)
    return batch


@router.post("/imports/official", response_model=BatchOut, status_code=202)
def official_import(
    session: Db, operator: Operator, key: Key, file: Annotated[UploadFile, File()]
) -> ImportBatch:
    if file.content_type not in {"text/csv", "application/csv", "application/vnd.ms-excel"}:
        raise HTTPException(status_code=415, detail="CSV content type is required")
    payload = file.file.read(5 * 1024 * 1024 + 1)
    try:
        rows = parse_official_csv(payload)
    except ImportFileError as exc:
        raise HTTPException(status_code=422, detail=exc.code) from exc
    digest = payload_sha256(payload)
    prior = replay(
        session,
        key=key,
        operation="import.official",
        entity_type="import_batch",
        entity_id=None,
        actor_id=operator,
        payload={"sha256": digest},
    )
    if prior:
        return found(session.get(ImportBatch, prior.entity_id), "import batch")
    batch = create_batch(
        session,
        source=ProductSource.OFFICIAL_IMPORT,
        filename=(file.filename or "")[:255] or None,
        content_type="text/csv",
        payload_hash=digest,
        operator_id=operator,
        key=key,
    )
    add_rows(session, batch, rows)
    enqueue_import(session, batch)
    record(
        session,
        key=key,
        operation="import.official",
        entity_type="import_batch",
        entity_id=batch.id,
        actor_id=operator,
        payload={"sha256": digest},
    )
    session.commit()
    try:
        process_import_task.delay(str(batch.id))
    except (ConnectionError, OSError, kombu.exceptions.OperationalError):
        pass
    session.refresh(batch)
    return batch


@router.get("/imports")
def list_imports(
    session: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return page(
        limit,
        offset,
        list(
            session.scalars(
                select(ImportBatch)
                .order_by(ImportBatch.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        ),
    )


@router.get("/imports/{batch_id}", response_model=BatchOut)
def get_import(batch_id: UUID, session: Db) -> ImportBatch:
    return found(session.get(ImportBatch, batch_id), "import batch")


@router.get("/imports/{batch_id}/rows")
def list_import_rows(
    batch_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    found(session.get(ImportBatch, batch_id), "import batch")
    rows = session.scalars(
        select(ImportRow)
        .where(ImportRow.import_batch_id == batch_id)
        .order_by(ImportRow.row_number)
        .limit(limit)
        .offset(offset)
    ).all()
    return page(limit, offset, [RowOut.model_validate(row) for row in rows])


@router.post("/imports/{batch_id}/cancel", response_model=BatchOut)
def cancel_import(
    batch_id: UUID, action: VersionAction, session: Db, operator: Operator, key: Key
) -> ImportBatch:
    payload = action.model_dump(mode="json")
    prior = replay(
        session,
        key=key,
        operation="import.cancel",
        entity_type="import_batch",
        entity_id=batch_id,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(ImportBatch, prior.entity_id), "import batch")
    batch: ImportBatch = found(session.get(ImportBatch, batch_id), "import batch")
    if batch.version != action.version:
        raise HTTPException(status_code=409, detail="stale_version")
    if batch.status not in {ImportBatchStatus.RECEIVED, ImportBatchStatus.VALIDATING}:
        raise HTTPException(status_code=409, detail="invalid_state_transition")
    batch.status = ImportBatchStatus.CANCELLED
    batch.completed_at = datetime.now(UTC)
    outbox = session.scalar(select(ImportOutbox).where(ImportOutbox.import_batch_id == batch.id))
    if outbox:
        outbox.status = OutboxStatus.COMPLETED
        outbox.completed_at = datetime.now(UTC)
    record(
        session,
        key=key,
        operation="import.cancel",
        entity_type="import_batch",
        entity_id=batch.id,
        actor_id=operator,
        payload=payload,
    )
    audit(session, "import.cancelled", "import_batch", batch.id, f"audit:{key}", operator)
    session.commit()
    session.refresh(batch)
    return batch


@router.post("/products/{product_id}/assessments", response_model=AssessmentOut, status_code=201)
def create_assessment(
    product_id: UUID, body: AssessmentCreate, session: Db, operator: Operator, key: Key
) -> ProductAssessment:
    payload = {"product_id": str(product_id), "body": body.model_dump(mode="json")}
    prior = replay(
        session,
        key=key,
        operation="assessment.create",
        entity_type="product_assessment",
        entity_id=None,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(ProductAssessment, prior.entity_id), "assessment")
    found(session.get(Product, product_id), "product")
    snapshot: ProductSnapshot = found(
        session.get(ProductSnapshot, body.product_snapshot_id), "snapshot"
    )
    if snapshot.product_id != product_id:
        raise HTTPException(status_code=409, detail="product_snapshot_mismatch")
    values = body.model_dump()
    if any(
        values[name] < 0 or values[name] > 100
        for name in (
            "conversion_potential",
            "net_commission",
            "product_quality",
            "price_stock_stability",
            "niche_fit",
            "video_demonstration_potential",
            "cancellation_quality",
        )
    ):
        raise HTTPException(
            status_code=422, detail="assessment dimensions must be between 0 and 100"
        )
    assessment = ProductAssessment(
        product_id=product_id, assessed_by_id=operator, idempotency_key=key, **values
    )
    session.add(assessment)
    session.flush()
    record(
        session,
        key=key,
        operation="assessment.create",
        entity_type="product_assessment",
        entity_id=assessment.id,
        actor_id=operator,
        payload=payload,
    )
    audit(
        session, "assessment.created", "product_assessment", assessment.id, f"audit:{key}", operator
    )
    session.commit()
    session.refresh(assessment)
    return assessment


@router.get("/products/{product_id}/assessments")
def list_assessments(
    product_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return page(
        limit,
        offset,
        list(
            session.scalars(
                select(ProductAssessment)
                .where(ProductAssessment.product_id == product_id)
                .order_by(ProductAssessment.created_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        ),
    )


@router.post("/assessments/{assessment_id}/score", response_model=ScoreOut, status_code=201)
def score_assessment(assessment_id: UUID, session: Db, key: Key) -> ProductScore:
    payload = {"assessment_id": str(assessment_id)}
    prior = replay(
        session,
        key=key,
        operation="score.calculate",
        entity_type="product_score",
        entity_id=None,
        actor_id=None,
        payload=payload,
    )
    if prior:
        return found(session.get(ProductScore, prior.entity_id), "score")
    assessment: ProductAssessment = found(
        session.get(ProductAssessment, assessment_id), "assessment"
    )
    score = calculate_score(session, assessment, key)
    record(
        session,
        key=key,
        operation="score.calculate",
        entity_type="product_score",
        entity_id=score.id,
        actor_id=None,
        payload=payload,
    )
    session.commit()
    session.refresh(score)
    return score


@router.get("/products/{product_id}/scores")
def list_scores(
    product_id: UUID,
    session: Db,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    return page(
        limit,
        offset,
        list(
            session.scalars(
                select(ProductScore)
                .where(ProductScore.product_id == product_id)
                .order_by(ProductScore.calculated_at.desc())
                .limit(limit)
                .offset(offset)
            ).all()
        ),
    )


@router.post("/scores/{score_id}/opportunities", response_model=OpportunityOut, status_code=201)
def create_opportunity(score_id: UUID, session: Db, key: Key) -> ProductOpportunity:
    payload = {"score_id": str(score_id)}
    prior = replay(
        session,
        key=key,
        operation="opportunity.generate",
        entity_type="product_opportunity",
        entity_id=None,
        actor_id=None,
        payload=payload,
    )
    if prior:
        return found(session.get(ProductOpportunity, prior.entity_id), "opportunity")
    score: ProductScore = found(session.get(ProductScore, score_id), "score")
    item = generate_opportunity(session, score, key)
    record(
        session,
        key=key,
        operation="opportunity.generate",
        entity_type="product_opportunity",
        entity_id=item.id,
        actor_id=None,
        payload=payload,
    )
    session.commit()
    session.refresh(item)
    return item


@router.get("/opportunities")
def list_opportunities(
    session: Db,
    category: str | None = None,
    source: ProductSource | None = None,
    available: bool | None = None,
    score_min: Decimal | None = None,
    score_max: Decimal | None = None,
    collected_after: datetime | None = None,
    collected_before: datetime | None = None,
    opportunity_status: OpportunityStatus | None = None,
    shortlisted: bool | None = None,
    title: str | None = None,
    order_by: str = "default",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    stmt = (
        select(ProductOpportunity)
        .join(Product)
        .join(ProductSnapshot, ProductSnapshot.id == ProductOpportunity.product_snapshot_id)
    )
    for condition in (
        Product.category == category if category else None,
        Product.source == source if source else None,
        ProductSnapshot.available == available if available is not None else None,
        ProductOpportunity.score >= score_min if score_min is not None else None,
        ProductOpportunity.score <= score_max if score_max is not None else None,
        ProductSnapshot.collected_at >= collected_after if collected_after else None,
        ProductSnapshot.collected_at <= collected_before if collected_before else None,
        ProductOpportunity.status == opportunity_status if opportunity_status else None,
        ProductOpportunity.status == OpportunityStatus.SHORTLISTED if shortlisted else None,
        Product.title.ilike(f"%{title}%") if title else None,
    ):
        if condition is not None:
            stmt = stmt.where(condition)
    orders = {
        "default": (
            desc(ProductOpportunity.score),
            desc(ProductSnapshot.collected_at),
            asc(ProductOpportunity.product_id),
        ),
        "score_asc": (
            asc(ProductOpportunity.score),
            desc(ProductSnapshot.collected_at),
            asc(ProductOpportunity.product_id),
        ),
        "collected_at_desc": (
            desc(ProductSnapshot.collected_at),
            asc(ProductOpportunity.product_id),
        ),
    }
    if order_by not in orders:
        raise HTTPException(status_code=422, detail="unsupported ordering")
    items = session.scalars(stmt.order_by(*orders[order_by]).limit(limit).offset(offset)).all()
    return page(limit, offset, list(items))


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityOut)
def get_opportunity(opportunity_id: UUID, session: Db) -> ProductOpportunity:
    return found(session.get(ProductOpportunity, opportunity_id), "opportunity")


def transition_opportunity(
    item: ProductOpportunity,
    expected_version: int,
    target: OpportunityStatus,
    reason: str | None = None,
) -> None:
    if item.version != expected_version:
        raise HTTPException(status_code=409, detail="stale_version")
    if item.status != OpportunityStatus.CANDIDATE:
        raise HTTPException(status_code=409, detail="invalid_state_transition")
    item.status = target
    if target == OpportunityStatus.SHORTLISTED:
        item.shortlisted_at = datetime.now(UTC)
    else:
        item.dismissed_at = datetime.now(UTC)
        item.dismissed_reason = reason


@router.post("/opportunities/{opportunity_id}/shortlist", response_model=OpportunityOut)
def shortlist(
    opportunity_id: UUID, action: VersionAction, session: Db, operator: Operator, key: Key
) -> ProductOpportunity:
    payload = action.model_dump(mode="json")
    prior = replay(
        session,
        key=key,
        operation="opportunity.shortlist",
        entity_type="product_opportunity",
        entity_id=opportunity_id,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(ProductOpportunity, prior.entity_id), "opportunity")
    item: ProductOpportunity = found(session.get(ProductOpportunity, opportunity_id), "opportunity")
    product = found(session.get(Product, item.product_id), "product")
    snapshot = found(session.get(ProductSnapshot, item.product_snapshot_id), "snapshot")
    if not product.is_active or not snapshot.available:
        raise HTTPException(status_code=409, detail="invalid_state_transition")
    if snapshot.collected_at + timedelta(minutes=60) <= datetime.now(UTC):
        raise HTTPException(status_code=409, detail="stale_snapshot")
    transition_opportunity(item, action.version, OpportunityStatus.SHORTLISTED)
    record(
        session,
        key=key,
        operation="opportunity.shortlist",
        entity_type="product_opportunity",
        entity_id=item.id,
        actor_id=operator,
        payload=payload,
    )
    audit(
        session, "opportunity.shortlisted", "product_opportunity", item.id, f"audit:{key}", operator
    )
    session.commit()
    session.refresh(item)
    return item


@router.post("/opportunities/{opportunity_id}/dismiss", response_model=OpportunityOut)
def dismiss(
    opportunity_id: UUID, action: DismissAction, session: Db, operator: Operator, key: Key
) -> ProductOpportunity:
    payload = action.model_dump(mode="json")
    prior = replay(
        session,
        key=key,
        operation="opportunity.dismiss",
        entity_type="product_opportunity",
        entity_id=opportunity_id,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(ProductOpportunity, prior.entity_id), "opportunity")
    item: ProductOpportunity = found(session.get(ProductOpportunity, opportunity_id), "opportunity")
    transition_opportunity(item, action.version, OpportunityStatus.DISMISSED, action.reason)
    record(
        session,
        key=key,
        operation="opportunity.dismiss",
        entity_type="product_opportunity",
        entity_id=item.id,
        actor_id=operator,
        payload=payload,
    )
    audit(
        session, "opportunity.dismissed", "product_opportunity", item.id, f"audit:{key}", operator
    )
    session.commit()
    session.refresh(item)
    return item


@router.get("/alerts")
def list_alerts(
    session: Db,
    alert_status: AlertStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict[str, Any]:
    stmt = select(OperationalAlert)
    if alert_status:
        stmt = stmt.where(OperationalAlert.status == alert_status)
    return page(
        limit,
        offset,
        list(
            session.scalars(
                stmt.order_by(OperationalAlert.detected_at.desc()).limit(limit).offset(offset)
            ).all()
        ),
    )


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: UUID, session: Db) -> OperationalAlert:
    return found(session.get(OperationalAlert, alert_id), "alert")


def transition_alert(
    alert: OperationalAlert,
    expected_version: int,
    target: AlertStatus,
    operator: UUID,
    session: Session,
    key: str,
) -> OperationalAlert:
    operation = f"alert.{target.value}"
    payload = {"version": expected_version}
    prior = replay(
        session,
        key=key,
        operation=operation,
        entity_type="operational_alert",
        entity_id=alert.id,
        actor_id=operator,
        payload=payload,
    )
    if prior:
        return found(session.get(OperationalAlert, prior.entity_id), "alert")
    if alert.version != expected_version:
        raise HTTPException(status_code=409, detail="stale_version")
    allowed = alert.status == AlertStatus.OPEN or (
        alert.status == AlertStatus.ACKNOWLEDGED and target == AlertStatus.RESOLVED
    )
    if not allowed:
        raise HTTPException(status_code=409, detail="invalid_state_transition")
    now = datetime.now(UTC)
    alert.status = target
    alert.acknowledged_at = alert.acknowledged_at or now
    alert.acknowledged_by_id = alert.acknowledged_by_id or operator
    if target == AlertStatus.RESOLVED:
        alert.resolved_at = now
    record(
        session,
        key=key,
        operation=operation,
        entity_type="operational_alert",
        entity_id=alert.id,
        actor_id=operator,
        payload=payload,
    )
    audit(session, f"alert.{target.value}", "operational_alert", alert.id, f"audit:{key}", operator)
    session.commit()
    session.refresh(alert)
    return alert


@router.post("/alerts/{alert_id}/acknowledge", response_model=AlertOut)
def acknowledge_alert(
    alert_id: UUID, action: VersionAction, session: Db, operator: Operator, key: Key
) -> OperationalAlert:
    return transition_alert(
        found(session.get(OperationalAlert, alert_id), "alert"),
        action.version,
        AlertStatus.ACKNOWLEDGED,
        operator,
        session,
        key,
    )


@router.post("/alerts/{alert_id}/resolve", response_model=AlertOut)
def resolve_alert(
    alert_id: UUID, action: VersionAction, session: Db, operator: Operator, key: Key
) -> OperationalAlert:
    return transition_alert(
        found(session.get(OperationalAlert, alert_id), "alert"),
        action.version,
        AlertStatus.RESOLVED,
        operator,
        session,
        key,
    )
