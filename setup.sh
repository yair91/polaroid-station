#!/usr/bin/env bash
# Crea toda la infraestructura: S3, security groups, RDS MySQL, el secret en
# Secrets Manager y la instancia EC2 con el instance profile LabInstanceProfile.
# Uso:  ./setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HERE="$ROOT/infra"
source "$HERE/config.env"
STACK_FILE="$HERE/.stack.env"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
ok()  { printf '    \033[0;32mOK\033[0m %s\n' "$*"; }

command -v aws >/dev/null || { echo "Falta AWS CLI"; exit 1; }
command -v jq  >/dev/null || { echo "Falta jq (sudo dnf install -y jq)"; exit 1; }
[[ "$REPO_URL" == *"TU-USUARIO"* ]] && { echo "Edita REPO_URL en config.env"; exit 1; }
[[ "$BUCKET_NAME" == *"cambia-esto"* ]] && { echo "Edita BUCKET_NAME en config.env"; exit 1; }

export AWS_DEFAULT_REGION="$AWS_REGION"
: > "$STACK_FILE"
record() { echo "export $1=\"$2\"" >> "$STACK_FILE"; }

say "Identidad y red"
aws sts get-caller-identity --output table
VPC_ID=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true \
  --query 'Vpcs[0].VpcId' --output text)
[[ "$VPC_ID" == "None" ]] && { echo "No hay VPC default"; exit 1; }
mapfile -t SUBNETS < <(aws ec2 describe-subnets --filters Name=vpc-id,Values="$VPC_ID" \
  --query 'Subnets[].SubnetId' --output text | tr '\t' '\n')
ok "VPC $VPC_ID con ${#SUBNETS[@]} subnets"
record VPC_ID "$VPC_ID"

say "Bucket S3: $BUCKET_NAME"
if aws s3api head-bucket --bucket "$BUCKET_NAME" 2>/dev/null; then
  ok "ya existia"
else
  if [[ "$AWS_REGION" == "us-east-1" ]]; then
    aws s3api create-bucket --bucket "$BUCKET_NAME" >/dev/null
  else
    aws s3api create-bucket --bucket "$BUCKET_NAME" \
      --create-bucket-configuration LocationConstraint="$AWS_REGION" >/dev/null
  fi
  ok "creado"
fi
record BUCKET_NAME "$BUCKET_NAME"

say "Security groups"
create_sg() { # nombre descripcion -> id
  local id
  id=$(aws ec2 describe-security-groups --filters Name=vpc-id,Values="$VPC_ID" \
        Name=group-name,Values="$1" --query 'SecurityGroups[0].GroupId' --output text 2>/dev/null || echo None)
  if [[ "$id" == "None" || -z "$id" ]]; then
    id=$(aws ec2 create-security-group --group-name "$1" --description "$2" \
          --vpc-id "$VPC_ID" --query GroupId --output text)
  fi
  echo "$id"
}
SG_APP=$(create_sg "${PROJECT}-app-sg" "Backend Polaroid (HTTP + SSH)")
SG_DB=$(create_sg  "${PROJECT}-db-sg"  "RDS MySQL Polaroid (solo desde la app)")
aws ec2 authorize-security-group-ingress --group-id "$SG_APP" --protocol tcp \
  --port 22 --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
aws ec2 authorize-security-group-ingress --group-id "$SG_APP" --protocol tcp \
  --port "$APP_PORT" --cidr 0.0.0.0/0 >/dev/null 2>&1 || true
aws ec2 authorize-security-group-ingress --group-id "$SG_DB" --protocol tcp \
  --port 3306 --source-group "$SG_APP" >/dev/null 2>&1 || true
ok "app=$SG_APP  db=$SG_DB"
record SG_APP "$SG_APP"; record SG_DB "$SG_DB"

say "Subnet group de RDS"
SUBNET_GROUP="${PROJECT}-subnets"
aws rds create-db-subnet-group --db-subnet-group-name "$SUBNET_GROUP" \
  --db-subnet-group-description "Subnets default para $PROJECT" \
  --subnet-ids "${SUBNETS[@]}" >/dev/null 2>&1 || ok "ya existia"
record SUBNET_GROUP "$SUBNET_GROUP"

say "Instancia RDS MySQL: $DB_INSTANCE_ID (tarda ~7 minutos)"
DB_PASSWORD=$(openssl rand -base64 30 | tr -dc 'A-Za-z0-9' | head -c 24)
if aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" >/dev/null 2>&1; then
  echo "La instancia ya existe. Si no recuerdas la contrasena, corre teardown.sh primero."
  DB_PASSWORD=""
else
  aws rds create-db-instance \
    --db-instance-identifier "$DB_INSTANCE_ID" \
    --db-instance-class "$DB_INSTANCE_CLASS" \
    --engine mysql \
    --master-username "$DB_USER" \
    --master-user-password "$DB_PASSWORD" \
    --allocated-storage 20 \
    --db-name "$DB_NAME" \
    --db-subnet-group-name "$SUBNET_GROUP" \
    --vpc-security-group-ids "$SG_DB" \
    --no-publicly-accessible \
    --backup-retention-period 0 \
    --no-multi-az >/dev/null
fi
aws rds wait db-instance-available --db-instance-identifier "$DB_INSTANCE_ID"
DB_HOST=$(aws rds describe-db-instances --db-instance-identifier "$DB_INSTANCE_ID" \
  --query 'DBInstances[0].Endpoint.Address' --output text)
ok "endpoint $DB_HOST"
record DB_INSTANCE_ID "$DB_INSTANCE_ID"

say "Secret en Secrets Manager: $SECRET_NAME"
if [[ -z "$DB_PASSWORD" ]]; then
  echo "Se reutiliza el secret existente."
else
  SECRET_JSON=$(jq -n --arg u "$DB_USER" --arg p "$DB_PASSWORD" --arg h "$DB_HOST" \
    --arg d "$DB_NAME" '{username:$u, password:$p, host:$h, port:3306, dbname:$d, engine:"mysql"}')
  if aws secretsmanager describe-secret --secret-id "$SECRET_NAME" >/dev/null 2>&1; then
    aws secretsmanager put-secret-value --secret-id "$SECRET_NAME" \
      --secret-string "$SECRET_JSON" >/dev/null
  else
    aws secretsmanager create-secret --name "$SECRET_NAME" \
      --description "Credenciales de RDS para la estacion Polaroid" \
      --secret-string "$SECRET_JSON" >/dev/null
  fi
  unset SECRET_JSON DB_PASSWORD
  ok "guardado (la contrasena solo vive aqui)"
fi
record SECRET_NAME "$SECRET_NAME"

say "Par de llaves SSH: $KEY_NAME"
if [[ -f "$HERE/$KEY_NAME.pem" ]]; then
  ok "ya tienes $KEY_NAME.pem"
else
  aws ec2 delete-key-pair --key-name "$KEY_NAME" >/dev/null 2>&1 || true
  aws ec2 create-key-pair --key-name "$KEY_NAME" --query KeyMaterial \
    --output text > "$HERE/$KEY_NAME.pem"
  chmod 400 "$HERE/$KEY_NAME.pem"
  ok "guardada en infra/$KEY_NAME.pem"
fi
record KEY_NAME "$KEY_NAME"

say "Instancia EC2 con instance profile $INSTANCE_PROFILE"
AMI_ID=$(aws ssm get-parameters \
  --names /aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64 \
  --query 'Parameters[0].Value' --output text)
USER_DATA=$(mktemp)
sed -e "s|__REPO_URL__|$REPO_URL|g" \
    -e "s|__REPO_BRANCH__|$REPO_BRANCH|g" \
    -e "s|__AWS_REGION__|$AWS_REGION|g" \
    -e "s|__BUCKET_NAME__|$BUCKET_NAME|g" \
    -e "s|__SECRET_NAME__|$SECRET_NAME|g" \
    -e "s|__DB_NAME__|$DB_NAME|g" \
    -e "s|__APP_PORT__|$APP_PORT|g" \
    "$HERE/user_data.sh" > "$USER_DATA"

INSTANCE_ID=$(aws ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --security-group-ids "$SG_APP" \
  --subnet-id "${SUBNETS[0]}" \
  --associate-public-ip-address \
  --iam-instance-profile "Name=$INSTANCE_PROFILE" \
  --user-data "file://$USER_DATA" \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=$EC2_NAME},{Key=Project,Value=$PROJECT}]" \
  --query 'Instances[0].InstanceId' --output text)
rm -f "$USER_DATA"
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID"
PUBLIC_IP=$(aws ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)
record INSTANCE_ID "$INSTANCE_ID"
record PUBLIC_IP "$PUBLIC_IP"
record APP_PORT "$APP_PORT"
record AWS_REGION "$AWS_REGION"
record DB_HOST "$DB_HOST"
record DB_USER "$DB_USER"
record DB_NAME "$DB_NAME"

cat <<EOF

--------------------------------------------------------------------
  Listo. La instancia todavia esta instalando dependencias (2-4 min).

  API:     http://$PUBLIC_IP:$APP_PORT
  Swagger: http://$PUBLIC_IP:$APP_PORT/docs
  Salud:   curl http://$PUBLIC_IP:$APP_PORT/health

  SSH:     ssh -i infra/$KEY_NAME.pem ec2-user@$PUBLIC_IP
  Log:     sudo tail -f /var/log/polaroid-bootstrap.log
  Estado:  sudo systemctl status polaroid

  Datos guardados en infra/.stack.env (no subir a git).
--------------------------------------------------------------------
EOF
