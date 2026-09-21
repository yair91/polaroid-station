"""Lectura de las credenciales de RDS desde AWS Secrets Manager.

La instancia EC2 tiene asignado el instance profile `LabInstanceProfile`, por lo
que boto3 obtiene credenciales temporales desde el metadata service (IMDS).
No hay llaves de acceso en el codigo ni en variables de ambiente.
"""
import json
import logging
import time
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from . import config

log = logging.getLogger(__name__)

_cache: Dict[str, Any] = {"value": None, "fetched_at": 0.0}


def _client():
    return boto3.client("secretsmanager", region_name=config.AWS_REGION)


def get_db_secret(force_refresh: bool = False) -> Dict[str, Any]:
    """Devuelve el secret como dict. Se cachea unos minutos para no pegarle
    a Secrets Manager en cada request, pero se refresca solo (rotacion)."""
    age = time.time() - _cache["fetched_at"]
    if not force_refresh and _cache["value"] and age < config.SECRET_CACHE_TTL:
        return _cache["value"]

    try:
        resp = _client().get_secret_value(SecretId=config.RDS_SECRET_NAME)
    except ClientError as exc:
        raise RuntimeError(
            f"No se pudo leer el secret '{config.RDS_SECRET_NAME}': {exc}. "
            "Verifica que la EC2 tenga el instance profile LabInstanceProfile."
        ) from exc

    raw = resp.get("SecretString") or resp["SecretBinary"].decode("utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("El secret debe ser un JSON con host/username/password.") from exc

    for field in ("username", "password", "host"):
        if not data.get(field):
            raise RuntimeError(f"El secret no contiene el campo '{field}'.")

    _cache.update(value=data, fetched_at=time.time())
    log.info("Credenciales de RDS obtenidas desde Secrets Manager.")
    return data
