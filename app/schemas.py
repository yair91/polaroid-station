"""Modelos de entrada y salida de la API."""
from datetime import date, datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class EventCreate(BaseModel):
    client_name: str = Field(..., min_length=1, max_length=120,
                             description="Nombre del cliente o de los festejados")
    event_type: str = Field(..., min_length=1, max_length=60,
                            description="Boda, XV anos, cumpleanos, etc.")
    event_date: date = Field(..., description="Fecha del evento (YYYY-MM-DD)")


class EventCreated(BaseModel):
    event_id: str
    client_name: str
    event_type: str
    event_date: date
    created_at: datetime


class EventDetail(EventCreated):
    finished_at: Optional[datetime] = None
    photo_count: int


class PhotoUploaded(BaseModel):
    photo_id: str
    event_id: str
    message: str
    original_key: str
    polaroid_key: str
    created_at: datetime


class FinishRequest(BaseModel):
    event_id: str = Field(..., description="Evento a cerrar y empaquetar")


class HealthResponse(BaseModel):
    status: str
    database: str
    bucket: str
    secret: str
