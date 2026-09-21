#!/usr/bin/env bash
# Elimina TODOS los recursos creados para la practica y muestra la evidencia
# de que ya no existen. Uso:  ./teardown.sh
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$ROOT/infra/config.env"
[[ -f "$ROOT/infra/.stack.env" ]] && source "$ROOT/infra/.stack.env"
export AWS_DEFAULT_REGION="$AWS_REGION"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()  { printf '    \033[0;32m%s\033[0m\n' "$*"; }
no()  { printf '    \033[0;33m%s\033[0m\n' "$*"; }

read -rp "Se eliminaran EC2, RDS, S3, el secret y los security groups. Escribe BORRAR: " CONFIRM
[[ "$CONFIRM" == "BORRAR" ]] || { echo "Cancelado."; exit 1; }

# ---------------------------------------------------------------- EC2
say "1/6 Terminando instancias EC2 del proyecto"
IDS=$(aws ec2 describe-instances \
  --filters "Name=tag:Name,Values=$EC2_NAME" "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text)
if [[ -n "$IDS" ]]; then
  aws ec2 terminate-instances --instance-ids $IDS \
    --query 'TerminatingInstances[].[InstanceId,CurrentState.Name]' --output table
  aws ec2 wait instance-terminated --instance-ids $IDS
  ok "instancias terminadas: $IDS"
else
  no "no habia instancias activas"
fi

# ---------------------------------------------------------------- RDS
say "2/6 Eliminando instancia RDS $DB_INSTANCE_ID"
if aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null 2>&1; then
  aws rds delete-db-instance --db-instance-identifier "$DB_INSTANCE_ID" \
    --skip-final-snapshot --delete-automated-backups >/dev/null
  echo "    esperando (puede tardar varios minutos)..."
  aws rds wait db-instance-deleted --db-instance-identifier "$DB_INSTANCE_ID"
  ok "base de datos eliminada"
else
  no "la instancia RDS ya no existe"
fi

aws rds delete-db-subnet-group --db-subnet-group-name "${SUBNET_GROUP:-${PROJECT}-subnets}" >/dev/null 2>&1 \
  && ok "subnet group eliminado" || no "sin subnet group que borrar"

# ---------------------------------------------------------------- S3
say "3/6 Vaciando y eliminando el bucket s3://$BUCKET_NAME"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
  aws s3 rm "s3://$BUCKET_NAME" --recursive
  aws s3api delete-bucket --bucket "$BUCKET_NAME"
  ok "bucket eliminado"
else
  no "el bucket ya no existe"
fi

# ---------------------------------------------------------------- Secret
say "4/6 Eliminando el secret $SECRET_NAME"
if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" >/dev/null 2>&1; then
  aws secretsmanager delete-secret --secret-id "$SECRET_NAME" \
    --force-delete-without-recovery --query 'Name' --output text >/dev/null
  ok "secret eliminado sin periodo de recuperacion"
else
  no "el secret ya no existe"
fi

# ------------------------------------------------- Security groups y llave
say "5/6 Security groups y par de llaves"
for SG in "${PROJECT}-app-sg" "${PROJECT}-db-sg"; do
  SG_ID=$(aws ec2 describe-security-groups --filters Name=group-name,Values="$SG" \
    --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null)
  if [[ -n "$SG_ID" && "$SG_ID" != "None" ]]; then
    for i in 1 2 3 4 5; do
      aws ec2 delete-security-group --group-id "$SG_ID" 2>/dev/null && { ok "$SG ($SG_ID) eliminado"; break; }
      sleep 15
    done
  else
    no "$SG ya no existe"
  fi
done
aws ec2 delete-key-pair --key-name "$KEY_NAME" >/dev/null 2>&1 && ok "key pair $KEY_NAME eliminado"
rm -f "$ROOT/infra/$KEY_NAME.pem" "$ROOT/infra/.stack.env"

# ---------------------------------------------------------------- Evidencia
say "6/6 Verificacion final"
echo "-- EC2 --";     aws ec2 describe-instances --filters "Name=tag:Name,Values=$EC2_NAME" \
  "Name=instance-state-name,Values=pending,running,stopping,stopped" \
  --query 'Reservations[].Instances[].InstanceId' --output text | grep -q . \
  && echo "    QUEDAN INSTANCIAS" || ok "sin instancias EC2"
echo "-- RDS --";     aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null 2>&1 \
  && echo "    QUEDA LA BASE" || ok "sin instancia RDS"
echo "-- S3 --";      aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null \
  && echo "    QUEDA EL BUCKET" || ok "sin bucket"
echo "-- Secret --";  aws secretsmanager describe-secret --secret-id "$SECRET_NAME" >/dev/null 2>&1 \
  && echo "    QUEDA EL SECRET" || ok "sin secret"

printf '\n\033[1;32mLimpieza completada.\033[0m\n'
