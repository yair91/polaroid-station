# Estación de fotos Polaroid

Backend para la estación de fotos que un fotógrafo coloca en bodas y eventos
sociales. Los invitados suben una foto con un mensaje para los festejados; el
backend guarda la foto reducida, compone una **polaroid** (marco blanco con el
mensaje escrito abajo) y al cerrar el evento entrega un `.zip` con el álbum
listo para imprimir. Las fotos originales se borran al terminar.

Un mismo despliegue atiende varios eventos a la vez: todo se organiza por
`event_id`.

---

## Arquitectura

```
                    ┌────────────────────────────┐
  Invitado / curl   │  EC2  t3.micro (AL2023)    │
  ───────────────►  │  systemd → uvicorn :8000   │
   HTTP             │  FastAPI + Pillow + boto3  │
                    │  instance profile:         │
                    │     LabInstanceProfile     │
                    └───┬───────────┬─────────┬──┘
                        │           │         │
        credenciales    │           │ fotos   │ metadata
        en runtime      ▼           ▼         ▼
             ┌──────────────┐ ┌──────────┐ ┌──────────────┐
             │   Secrets    │ │    S3    │ │ RDS MySQL    │
             │   Manager    │ │pictures/ │ │  events      │
             │ polaroid/rds │ │polaroids/│ │  photos      │
             └──────────────┘ └──────────┘ └──────────────┘
```

* **EC2** ejecuta el backend como servicio `systemd`. No tiene llaves de AWS:
  usa el **instance profile `LabInstanceProfile`**, y boto3 obtiene
  credenciales temporales desde el metadata service.
* **Secrets Manager** guarda usuario, contraseña, host y base de RDS. La app lo
  lee **en tiempo de ejecución** (`app/secrets.py`), con caché de 5 minutos.
  No hay contraseñas en el código ni en variables de ambiente.
* **S3** guarda la foto reducida de 128×128 en `pictures/<event_id>/<uuid>.jpg`
  y la polaroid en `polaroids/<event_id>/<uuid>.png`.
* **RDS MySQL** guarda las tablas `events` y `photos`, relacionadas por
  `event_id` con llave foránea (`ON DELETE CASCADE`).

### Modelo de datos

| `events`      |                                   | `photos`       |                                |
|---------------|-----------------------------------|----------------|--------------------------------|
| `event_id` PK | UUID                              | `photo_id` PK  | UUID                           |
| `client_name` | nombre del cliente                | `event_id` FK  | → `events.event_id`            |
| `event_type`  | boda, XV años, …                  | `message`      | mensaje del invitado           |
| `event_date`  | fecha del evento                  | `original_key` | ruta en `pictures/` (NULL al cerrar) |
| `created_at`  |                                   | `polaroid_key` | ruta en `polaroids/`           |
| `finished_at` | se llena con `/finish`            | `created_at`   |                                |

El esquema se crea solo al arrancar la app (`app/db.py`); también está en
[`infra/schema.sql`](infra/schema.sql).

---

## Endpoints

| Método | Ruta                 | Qué hace |
|--------|----------------------|----------|
| `POST` | `/events`            | Crea el evento en RDS y regresa el `event_id` generado. |
| `POST` | `/upload`            | Recibe `event_id`, foto y mensaje. Sube la foto 128×128 a `pictures/`, compone la polaroid, la sube a `polaroids/` y guarda el registro en RDS. |
| `GET`  | `/events/{event_id}` | Metadata del evento + número de fotos asociadas (consulta a RDS). |
| `POST` | `/finish`            | Empaqueta las polaroids del evento en un `.zip` descargable y borra las fotos originales. |
| `GET`  | `/health`            | Diagnóstico: conectividad con RDS, bucket y secret en uso. |
| `GET`  | `/docs`              | Documentación interactiva (Swagger). |

### Ejemplos

```bash
BASE=http://<IP-PUBLICA>:8000

# 1. Crear evento
curl -X POST $BASE/events -H 'Content-Type: application/json' \
  -d '{"client_name":"Ana y Luis","event_type":"Boda","event_date":"2026-09-26"}'
# {"event_id":"7c1f...","client_name":"Ana y Luis",...}

# 2. Subir una foto con mensaje
curl -X POST $BASE/upload \
  -F "event_id=7c1f..." \
  -F "message=Felicidades, que sean muy felices!" \
  -F "file=@foto.jpg"

# 3. Consultar el evento
curl $BASE/events/7c1f...
# {"event_id":"7c1f...","photo_count":3,...}

# 4. Cerrar el evento y descargar el álbum
curl -X POST $BASE/finish -H 'Content-Type: application/json' \
  -d '{"event_id":"7c1f..."}' -o album.zip
```

El script [`scripts/demo.sh`](scripts/demo.sh) ejecuta ese recorrido completo:

```bash
python3 scripts/make_sample_photos.py     # genera 3 fotos de prueba
./scripts/demo.sh http://<IP-PUBLICA>:8000
```

---

## Despliegue

### Opción A — automático (recomendado)

Con las credenciales del laboratorio ya cargadas (`~/.aws/credentials`):

```bash
git clone https://github.com/<tu-usuario>/<tu-repo>.git
cd <tu-repo>
nano infra/config.env      # BUCKET_NAME único y REPO_URL de tu repositorio
./setup.sh                 # ~10 min (RDS es lo que más tarda)
```

`setup.sh` crea: bucket S3, dos security groups, subnet group, instancia RDS
MySQL, el secret en Secrets Manager con una contraseña generada al momento, el
par de llaves SSH y la instancia EC2 con el instance profile
`LabInstanceProfile`. Al final imprime la URL del servicio.

La instancia tarda 2–4 minutos más en instalar dependencias. Para seguirlo:

```bash
ssh -i infra/polaroid-key.pem ec2-user@<IP-PUBLICA>
sudo tail -f /var/log/polaroid-bootstrap.log
sudo systemctl status polaroid
curl localhost:8000/health
```

### Opción B — manual desde la consola de AWS

1. **S3**: bucket nuevo, ajustes por defecto (bloqueo de acceso público activo).
2. **RDS**: MySQL, plantilla *Free tier*, `db.t3.micro`, base inicial
   `polaroids`, sin acceso público, security group que permita el puerto 3306
   desde el security group de la EC2.
3. **Secrets Manager**: secreto tipo *Other* llamado `polaroid/rds` con este
   JSON (los valores de tu RDS):
   ```json
   {"username":"admin","password":"...","host":"...rds.amazonaws.com","port":3306,"dbname":"polaroids","engine":"mysql"}
   ```
4. **EC2**: Amazon Linux 2023, `t3.micro`, security group con los puertos 22 y
   8000 abiertos, y en *Advanced details* → **IAM instance profile:
   `LabInstanceProfile`**.
5. Dentro de la instancia, pega el contenido de
   [`infra/user_data.sh`](infra/user_data.sh) sustituyendo los marcadores
   `__VAR__`, o ejecútalo como user data al crearla.

### Variables de ambiente de la app

Solo configuración, nunca credenciales (viven en `/etc/polaroid.env`):

| Variable | Descripción | Default |
|----------|-------------|---------|
| `AWS_REGION` | Región | `us-east-1` |
| `S3_BUCKET` | Bucket de fotos | *(obligatoria)* |
| `RDS_SECRET_NAME` | Nombre del secret | *(obligatoria)* |
| `DB_NAME` | Base de datos | `polaroids` |
| `THUMB_SIZE` | Lado de la foto reducida | `128` |
| `POLAROID_PHOTO_SIZE` | Lado de la foto dentro del marco | `600` |
| `DELETE_ORIGINALS_ON_FINISH` | Borrar originales al cerrar | `true` |

> La versión que se guarda en `pictures/` es la reducida de **128×128** que pide
> el enunciado. La polaroid se compone a partir de la imagen recibida a 600 px
> para que el marco y el mensaje se vean bien al imprimir.

---

## Correr en local (opcional, para desarrollo)

Necesitas credenciales de AWS válidas y acceso a la base:

```bash
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export AWS_REGION=us-east-1 S3_BUCKET=<bucket> RDS_SECRET_NAME=polaroid/rds
uvicorn app.main:app --reload
```

---

## Eliminar los recursos

```bash
./teardown.sh        # pide confirmación escribiendo BORRAR
```

El script termina la instancia EC2, elimina la instancia RDS (sin snapshot
final) y su subnet group, vacía y borra el bucket S3, elimina el secret con
`--force-delete-without-recovery`, borra los security groups y el par de llaves,
y al final vuelve a consultar cada servicio para **mostrar en consola que ya no
existe ninguno**.

### Pasos equivalentes desde la consola

1. **EC2** → seleccionar la instancia → *Instance state* → **Terminate**.
2. **RDS** → seleccionar la base → **Delete**, sin snapshot final.
   Después borrar el *subnet group* `polaroid-subnets`.
3. **S3** → bucket → **Empty**, luego **Delete**.
4. **Secrets Manager** → secreto → **Delete** (fuerza el borrado inmediato con
   `aws secretsmanager delete-secret --force-delete-without-recovery`).
5. **EC2 → Security Groups** → borrar `polaroid-app-sg` y `polaroid-db-sg`
   (primero el de la app).
6. **EC2 → Key Pairs** → borrar `polaroid-key`.

---

## Estructura del proyecto

```
.
├── app/
│   ├── main.py         FastAPI: los cuatro endpoints
│   ├── config.py       configuración no sensible
│   ├── secrets.py      credenciales de RDS desde Secrets Manager
│   ├── db.py           conexión MySQL + creación del esquema
│   ├── repository.py   consultas SQL sobre events y photos
│   ├── storage.py      subida/descarga/borrado en S3
│   ├── polaroid.py     miniatura 128x128 y composición de la polaroid
│   └── schemas.py      modelos de entrada y salida
├── infra/
│   ├── config.env      nombres de los recursos
│   ├── user_data.sh    bootstrap de la EC2
│   └── schema.sql      esquema de referencia
├── scripts/
│   ├── demo.sh         recorrido completo de la API
│   └── make_sample_photos.py
├── setup.sh            crea la infraestructura
├── teardown.sh         elimina la infraestructura
└── requirements.txt
```
