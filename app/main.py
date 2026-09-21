"""Estacion de fotos Polaroid - backend.

Flujo: el fotografo crea un evento, los invitados suben fotos con un mensaje,
y al terminar se descarga un ZIP con todas las polaroids listas para imprimir.
"""
import io
import logging
import re
import uuid
import zipfile
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile

from . import config, polaroid, repository, storage
from .schemas import (EventCreate, EventCreated, EventDetail, FinishRequest,
                      HealthResponse, PhotoUploaded)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("polaroid")


@asynccontextmanager
async def lifespan(_: FastAPI):
    config.validate()
    from .db import init_schema
    init_schema()
    log.info("Backend listo. Bucket=%s Secret=%s", config.S3_BUCKET, config.RDS_SECRET_NAME)
    yield


app = FastAPI(
    title="Estacion de fotos Polaroid",
    description="Backend para eventos sociales: fotos + mensajes -> album Polaroid.",
    version="1.0.0",
    lifespan=lifespan,
)


def _slug(text: str, fallback: str = "evento") -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return slug or fallback


def _require_event(event_id: str):
    event = repository.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail=f"El evento '{event_id}' no existe.")
    return event


# --------------------------------------------------------------------------
# Endpoints
# --------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["operacion"])
def health():
    """Verifica que la app alcance RDS con las credenciales del secret."""
    try:
        repository.ping()
        db_status = "ok"
    except Exception as exc:  # pragma: no cover
        log.exception("Fallo el health check de la base")
        db_status = f"error: {exc}"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        database=db_status,
        bucket=config.S3_BUCKET,
        secret=config.RDS_SECRET_NAME,
    )


@app.post("/events", response_model=EventCreated, status_code=201, tags=["eventos"])
def create_event(payload: EventCreate):
    """Crea un evento nuevo en RDS y regresa el `event_id` generado."""
    event_id = str(uuid.uuid4())
    row = repository.create_event(
        event_id, payload.client_name.strip(), payload.event_type.strip(), payload.event_date
    )
    log.info("Evento creado %s (%s)", event_id, payload.client_name)
    return EventCreated(**row)


@app.get("/events/{event_id}", response_model=EventDetail, tags=["eventos"])
def get_event(event_id: str):
    """Metadata del evento y numero de fotos asociadas, consultando RDS."""
    row = repository.get_event_with_count(event_id)
    if not row:
        raise HTTPException(status_code=404, detail=f"El evento '{event_id}' no existe.")
    return EventDetail(**row)


@app.post("/upload", response_model=PhotoUploaded, status_code=201, tags=["fotos"])
async def upload_photo(
    event_id: str = Form(..., description="Evento al que pertenece la foto"),
    message: str = Form(..., description="Mensaje para los festejados"),
    file: UploadFile = File(..., description="Foto del invitado"),
):
    """Sube la foto reducida a `pictures/`, compone la polaroid, la sube a
    `polaroids/` y guarda el registro en RDS. Todo en la misma llamada."""
    _require_event(event_id)

    message = message.strip()
    if not message:
        raise HTTPException(status_code=422, detail="El mensaje no puede estar vacio.")
    if len(message) > config.MAX_MESSAGE_CHARS:
        raise HTTPException(
            status_code=422,
            detail=f"El mensaje excede {config.MAX_MESSAGE_CHARS} caracteres.",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=422, detail="El archivo esta vacio.")
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"La foto excede {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    try:
        image = polaroid.open_image(raw)
    except ValueError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc

    photo_id = str(uuid.uuid4())
    original_key = f"{config.PICTURES_PREFIX}{event_id}/{photo_id}.jpg"
    polaroid_key = f"{config.POLAROIDS_PREFIX}{event_id}/{photo_id}.png"

    storage.upload_bytes(original_key, polaroid.thumbnail(image), "image/jpeg")
    storage.upload_bytes(polaroid_key, polaroid.compose(image, message), "image/png")

    try:
        row = repository.insert_photo(photo_id, event_id, message, original_key, polaroid_key)
    except Exception:
        # Si falla la base, no dejamos objetos huerfanos en S3.
        storage.delete_keys([original_key, polaroid_key])
        raise

    log.info("Foto %s registrada en evento %s", photo_id, event_id)
    return PhotoUploaded(**row)


@app.post("/finish", tags=["eventos"],
          responses={200: {"content": {"application/zip": {}},
                           "description": "ZIP con las polaroids del evento"}})
def finish_event(payload: FinishRequest):
    """Consulta las polaroids del evento en RDS, las empaqueta en un `.zip`
    descargable y borra de S3 las fotos originales."""
    event = _require_event(payload.event_id)
    photos = repository.list_photos(payload.event_id)
    if not photos:
        raise HTTPException(status_code=409, detail="El evento no tiene fotos que empaquetar.")

    buffer = io.BytesIO()
    index_lines = [f"Album Polaroid - {event['client_name']} ({event['event_type']})",
                   f"Fecha del evento: {event['event_date']}",
                   f"Evento: {event['event_id']}", ""]

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        for index, photo in enumerate(photos, start=1):
            data = storage.download_bytes(photo["polaroid_key"])
            name = f"polaroid-{index:02d}.png"
            bundle.writestr(name, data)
            index_lines.append(f"{name}: {photo['message']}")
        bundle.writestr("mensajes.txt", "\n".join(index_lines) + "\n")

    originals = [p["original_key"] for p in photos if p.get("original_key")]
    cleared = False
    if config.DELETE_ORIGINALS_ON_FINISH and originals:
        storage.delete_keys(originals)
        cleared = True
        log.info("Borradas %d fotos originales del evento %s", len(originals), payload.event_id)

    repository.mark_finished(payload.event_id, clear_originals=cleared)

    filename = f"album-{_slug(event['client_name'])}-{payload.event_id[:8]}.zip"
    return Response(
        content=buffer.getvalue(),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Polaroid-Count": str(len(photos)),
        },
    )
