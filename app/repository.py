"""Consultas SQL sobre las tablas `events` y `photos`."""
from datetime import date
from typing import Any, Dict, List, Optional

from .db import cursor


def create_event(event_id: str, client_name: str, event_type: str, event_date: date) -> Dict[str, Any]:
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO events (event_id, client_name, event_type, event_date) "
            "VALUES (%s, %s, %s, %s)",
            (event_id, client_name, event_type, event_date),
        )
        cur.execute("SELECT * FROM events WHERE event_id = %s", (event_id,))
        return cur.fetchone()


def get_event(event_id: str) -> Optional[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute("SELECT * FROM events WHERE event_id = %s", (event_id,))
        return cur.fetchone()


def get_event_with_count(event_id: str) -> Optional[Dict[str, Any]]:
    """Metadata del evento + numero de fotos asociadas (una sola consulta)."""
    with cursor() as cur:
        cur.execute(
            """
            SELECT e.*, COUNT(p.photo_id) AS photo_count
            FROM events e
            LEFT JOIN photos p ON p.event_id = e.event_id
            WHERE e.event_id = %s
            GROUP BY e.event_id
            """,
            (event_id,),
        )
        return cur.fetchone()


def insert_photo(photo_id: str, event_id: str, message: str,
                 original_key: str, polaroid_key: str) -> Dict[str, Any]:
    with cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO photos (photo_id, event_id, message, original_key, polaroid_key) "
            "VALUES (%s, %s, %s, %s, %s)",
            (photo_id, event_id, message, original_key, polaroid_key),
        )
        cur.execute("SELECT * FROM photos WHERE photo_id = %s", (photo_id,))
        return cur.fetchone()


def list_photos(event_id: str) -> List[Dict[str, Any]]:
    with cursor() as cur:
        cur.execute(
            "SELECT photo_id, message, original_key, polaroid_key, created_at "
            "FROM photos WHERE event_id = %s ORDER BY created_at, photo_id",
            (event_id,),
        )
        return list(cur.fetchall())


def mark_finished(event_id: str, clear_originals: bool) -> None:
    """Marca el evento como cerrado y, si se borraron las fotos originales de
    S3, limpia su referencia en la base."""
    with cursor(commit=True) as cur:
        cur.execute(
            "UPDATE events SET finished_at = CURRENT_TIMESTAMP WHERE event_id = %s",
            (event_id,),
        )
        if clear_originals:
            cur.execute(
                "UPDATE photos SET original_key = NULL WHERE event_id = %s",
                (event_id,),
            )


def ping() -> None:
    with cursor() as cur:
        cur.execute("SELECT 1")
        cur.fetchone()
