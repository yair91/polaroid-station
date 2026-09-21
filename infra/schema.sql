-- Esquema de la base de datos (la aplicacion lo crea sola al arrancar).
-- Se incluye para consulta y para poder mostrarlo en la demostracion.

CREATE TABLE IF NOT EXISTS events (
    event_id    CHAR(36)     NOT NULL PRIMARY KEY,
    client_name VARCHAR(120) NOT NULL,
    event_type  VARCHAR(60)  NOT NULL,
    event_date  DATE         NOT NULL,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP    NULL DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS photos (
    photo_id     CHAR(36)     NOT NULL PRIMARY KEY,
    event_id     CHAR(36)     NOT NULL,
    message      VARCHAR(255) NOT NULL,
    original_key VARCHAR(512) NULL,          -- pictures/<event_id>/<uuid>.jpg
    polaroid_key VARCHAR(512) NOT NULL,      -- polaroids/<event_id>/<uuid>.png
    created_at   TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_photos_event
        FOREIGN KEY (event_id) REFERENCES events (event_id) ON DELETE CASCADE,
    INDEX idx_photos_event (event_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
