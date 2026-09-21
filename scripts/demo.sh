#!/usr/bin/env bash
# Recorrido completo de la API, pensado para grabar el video.
# Uso:  ./scripts/demo.sh http://<IP-PUBLICA>:8000
set -euo pipefail

BASE="${1:-}"
[[ -z "$BASE" ]] && { echo "Uso: $0 http://<IP-PUBLICA>:8000"; exit 1; }
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PHOTOS_DIR="${PHOTOS_DIR:-$ROOT/scripts/sample_photos}"
OUT_DIR="${OUT_DIR:-$ROOT/salida}"
mkdir -p "$OUT_DIR"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }

say "0. Salud del servicio"
curl -sS "$BASE/health" | jq

say "1. POST /events  - se crea el evento"
EVENT_JSON=$(curl -sS -X POST "$BASE/events" \
  -H 'Content-Type: application/json' \
  -d '{"client_name":"Ana y Luis","event_type":"Boda","event_date":"2026-09-26"}')
echo "$EVENT_JSON" | jq
EVENT_ID=$(echo "$EVENT_JSON" | jq -r .event_id)
echo "event_id = $EVENT_ID"

MESSAGES=(
  "Felicidades Ana y Luis, que sean muy felices!"
  "Gracias por dejarnos ser parte de este dia tan bonito."
  "Por muchos anos mas juntos. Los queremos!"
)

say "2. POST /upload  - tres fotos con mensaje"
i=0
for PHOTO in "$PHOTOS_DIR"/*; do
  [[ -f "$PHOTO" ]] || continue
  [[ $i -ge 3 ]] && break
  echo "--- $(basename "$PHOTO")"
  curl -sS -X POST "$BASE/upload" \
    -F "event_id=$EVENT_ID" \
    -F "message=${MESSAGES[$i]}" \
    -F "file=@$PHOTO" | jq
  i=$((i + 1))
done

say "3. GET /events/$EVENT_ID  - metadata y numero de fotos"
curl -sS "$BASE/events/$EVENT_ID" | jq

say "4. POST /finish  - descarga del album en ZIP"
curl -sS -X POST "$BASE/finish" \
  -H 'Content-Type: application/json' \
  -d "{\"event_id\":\"$EVENT_ID\"}" \
  -o "$OUT_DIR/album.zip" -D "$OUT_DIR/finish-headers.txt"
cat "$OUT_DIR/finish-headers.txt"
unzip -o "$OUT_DIR/album.zip" -d "$OUT_DIR/album"
ls -lh "$OUT_DIR/album"
cat "$OUT_DIR/album/mensajes.txt"

printf '\n\033[1;32mListo. Las polaroids estan en %s/album\033[0m\n' "$OUT_DIR"
