"""Acceso a MySQL (Amazon RDS).

La conexion se arma con las credenciales que vienen de Secrets Manager.
Se usa pymysql directo (sin ORM) para que el SQL y el modelo de datos sean
faciles de leer y de mostrar en la demostracion.
"""
import logging
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from . import config
from .secrets import get_db_secret

log = logging.getLogger(__name__)

SCHEMA_SQL = (
    """
    CREATE TABLE IF NOT EXISTS events (
        event_id    CHAR(36)     NOT NULL PRIMARY KEY,
        client_name VARCHAR(120) NOT NULL,
        event_type  VARCHAR(60)  NOT NULL,
        event_date  DATE         NOT NULL,
        created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TIMESTAMP    NULL DEFAULT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
    """
    CREATE TABLE IF NOT EXISTS photos (
        photo_id     CHAR(36)     NOT NULL PRIMARY KEY,
        event_id     CHAR(36)     NOT NULL,
        message      VARCHAR(255) NOT NULL,
        original_key VARCHAR(512) NULL,
        polaroid_key VARCHAR(512) NOT NULL,
        created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT fk_photos_event
            FOREIGN KEY (event_id) REFERENCES events (event_id)
            ON DELETE CASCADE,
        INDEX idx_photos_event (event_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """,
)


def connect() -> pymysql.connections.Connection:
    secret = get_db_secret()
    return pymysql.connect(
        host=secret["host"],
        port=int(secret.get("port") or config.DB_PORT_FALLBACK),
        user=secret["username"],
        password=secret["password"],
        database=secret.get("dbname") or config.DB_NAME_FALLBACK,
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10,
        charset="utf8mb4",
    )


@contextmanager
def cursor(commit: bool = False):
    """Abre conexion + cursor y los cierra siempre."""
    conn = connect()
    try:
        with conn.cursor() as cur:
            yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    """Crea las tablas si no existen (idempotente)."""
    with cursor(commit=True) as cur:
        for statement in SCHEMA_SQL:
            cur.execute(statement)
    log.info("Esquema verificado: tablas 'events' y 'photos' listas.")
