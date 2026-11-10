#!/usr/bin/env bash
# Copia de seguridad de la BD del CRM publicado (T29).
#
# Solo lee la BD: pg_dump dentro del contenedor db, por el socket local, sin contraseñas ni .env
# a la vista. Guarda la copia comprimida (-Fc) y su huella sha256 en otro disco que el de la BD,
# y conserva solo las últimas copias diarias.
#
# Uso:
#   crm_backup.sh           copia diaria: entra en la rotación
#   crm_backup.sh manual    copia a mano (por ejemplo, antes de actualizar): nunca se borra sola
#
# Instalación: el script va junto a la carpeta app/ (el clon con compose.prod.yaml y .env), fuera
# del clon, y las copias se guardan en $HOME/crm-demo-backups. Conviene que $HOME esté en otro disco
# que la BD. Variables opcionales: CRM_APP_DIR, CRM_BACKUP_DIR, CRM_BACKUP_KEEP (diarias, 14).
set -euo pipefail
umask 077

APP_DIR=${CRM_APP_DIR:-$(dirname "$(readlink -f "$0")")/app}
BACKUP_DIR=${CRM_BACKUP_DIR:-$HOME/crm-demo-backups}
KEEP=${CRM_BACKUP_KEEP:-14}
MIN_FREE_MB=1024

log() { echo "$(date -u +%FT%TZ) $*"; }

KIND=diaria
case "${1:-}" in
  "") ;;
  manual) KIND=manual ;;
  *) echo "Uso: $0 [manual]" >&2; exit 2 ;;
esac
[[ $KEEP =~ ^[1-9][0-9]*$ ]] || { log "ERROR CRM_BACKUP_KEEP debe ser un entero mayor que 0"; exit 2; }
[[ -f $APP_DIR/compose.prod.yaml ]] || { log "ERROR no está $APP_DIR/compose.prod.yaml"; exit 1; }

DEST="$BACKUP_DIR/$KIND"
mkdir -p "$DEST"

# Una sola copia a la vez.
command -v flock > /dev/null || { log "ERROR falta flock"; exit 1; }
exec 9>"$BACKUP_DIR/.lock"
flock -n 9 || { log "ERROR otra copia en curso"; exit 1; }

free_mb=$(df -Pm "$BACKUP_DIR" | awk 'NR == 2 {print $4}')
(( free_mb >= MIN_FREE_MB )) || { log "ERROR poco espacio libre: ${free_mb} MB"; exit 1; }

cd "$APP_DIR"
dc() { docker compose -f compose.prod.yaml "$@"; }

# El nombre lleva el commit desplegado y la migración de la BD: al restaurar, dice con qué código encaja.
ts=$(date -u +%Y%m%dT%H%M%SZ)
code=$(git rev-parse --short HEAD)
rev=$(dc exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select version_num from alembic_version"')
[[ $rev =~ ^[0-9a-f]+$ ]] || { log "ERROR versión de migración no reconocida"; exit 1; }
name="crm_demo_${ts}_${code}_${rev}.dump"

# Se escribe como .part y solo se renombra si pg_dump termina bien y el archivo se puede leer.
trap 'rm -f "$DEST/$name.part"' EXIT
dc exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$DEST/$name.part" \
  || { log "ERROR pg_dump falló"; exit 1; }
found=$(dc exec -T db pg_restore --list < "$DEST/$name.part" | grep -c 'TABLE DATA public alembic_version ' || true)
[[ $found == 1 ]] || { log "ERROR la copia no se puede leer"; exit 1; }
mv "$DEST/$name.part" "$DEST/$name"
trap - EXIT
(cd "$DEST" && sha256sum "$name" > "$name.sha256")

# Retención: solo las diarias. El nombre empieza por la fecha UTC, así que ordenar por nombre es por fecha.
if [[ $KIND == diaria ]]; then
  ls -1 "$DEST" \
    | { grep -E '^crm_demo_[0-9]{8}T[0-9]{6}Z_[0-9a-f]+_[0-9a-f]+\.dump$' || true; } \
    | sort -r | tail -n +$((KEEP + 1)) \
    | while read -r old; do
        rm -f -- "$DEST/$old" "$DEST/$old.sha256"
        log "borrada $old"
      done
fi

log "OK $KIND/$name $(stat -c %s "$DEST/$name") bytes"
