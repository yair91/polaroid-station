"""Configuracion NO sensible de la aplicacion.

Las credenciales de la base de datos NUNCA viven aqui: se leen en tiempo de
ejecucion desde AWS Secrets Manager (ver app/secrets.py).
"""
import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


# --- AWS ---
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET = os.getenv("S3_BUCKET", "")
RDS_SECRET_NAME = os.getenv("RDS_SECRET_NAME", "")

# Prefijos dentro del bucket (los pide el enunciado)
PICTURES_PREFIX = "pictures/"
POLAROIDS_PREFIX = "polaroids/"

# --- Base de datos ---
# Solo datos no sensibles; si el secret los trae, el secret gana.
DB_NAME_FALLBACK = os.getenv("DB_NAME", "polaroids")
DB_PORT_FALLBACK = _int_env("DB_PORT", 3306)
SECRET_CACHE_TTL = _int_env("SECRET_CACHE_TTL", 300)  # segundos

# --- Imagenes ---
THUMB_SIZE = _int_env("THUMB_SIZE", 128)        # foto reducida en pictures/
POLAROID_PHOTO_SIZE = _int_env("POLAROID_PHOTO_SIZE", 600)  # foto dentro del marco
MAX_UPLOAD_BYTES = _int_env("MAX_UPLOAD_BYTES", 15 * 1024 * 1024)
MAX_MESSAGE_CHARS = _int_env("MAX_MESSAGE_CHARS", 180)

# Al cerrar el evento se borran las fotos originales (lo pide la descripcion).
DELETE_ORIGINALS_ON_FINISH = os.getenv("DELETE_ORIGINALS_ON_FINISH", "true").lower() == "true"


def validate() -> None:
    """Falla rapido y claro si falta configuracion obligatoria."""
    missing = [n for n in ("S3_BUCKET", "RDS_SECRET_NAME") if not globals()[n]]
    if missing:
        raise RuntimeError(
            "Faltan variables de ambiente: " + ", ".join(missing) +
            ". Definelas en /etc/polaroid.env (no incluyen credenciales)."
        )
