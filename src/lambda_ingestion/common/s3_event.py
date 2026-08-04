from __future__ import annotations

from urllib.parse import unquote_plus


def extract_s3_location(event: dict) -> tuple[str, str]:
    """Extrae (bucket, key) del evento, aceptando el envelope de la notificación
    S3 (`Records[0].s3`) y el de EventBridge (`detail`).

    Ambos formatos conviven durante la migración a EventBridge (SPEC-003
    "Eventos de S3"): la imagen se despliega antes que la infra, de modo que
    la Lambda funcione con el trigger viejo y el nuevo sin reconstruir la
    imagen.

    La notificación S3 entrega la key URL-encoded (espacios como `+`);
    EventBridge la entrega sin codificar.
    """
    if "Records" in event:
        record = event["Records"][0]["s3"]
        bucket = record["bucket"]["name"]
        key = unquote_plus(record["object"]["key"])
        return bucket, key

    if "detail" in event:
        detail = event["detail"]
        return detail["bucket"]["name"], detail["object"]["key"]

    raise ValueError(f"Unrecognized S3 event shape, expected keys 'Records' or 'detail': {event!r}")
