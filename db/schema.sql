BEGIN;

CREATE TABLE roles (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre text NOT NULL UNIQUE CHECK (nombre IN ('admin', 'operador'))
);

CREATE TABLE usuarios (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    nombre text NOT NULL CHECK (length(btrim(nombre)) > 0),
    email text NOT NULL CHECK (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    password_hash text NOT NULL CHECK (length(password_hash) > 0),
    rol_id smallint NOT NULL REFERENCES roles (id),
    activo boolean NOT NULL DEFAULT true,
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX usuarios_email_unico ON usuarios (lower(email));

CREATE TABLE tipos_vehiculo (
    id smallint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    codigo text NOT NULL UNIQUE CHECK (codigo ~ '^[A-Z]{3}$'),
    nombre text NOT NULL UNIQUE CHECK (length(btrim(nombre)) > 0),
    prefijo_placa text NOT NULL UNIQUE CHECK (prefijo_placa ~ '^[A-Z]$'),
    tarifa_hora numeric(10, 2) NOT NULL CHECK (tarifa_hora >= 0),
    activo boolean NOT NULL DEFAULT true
);

CREATE TABLE slots (
    numero smallint PRIMARY KEY CHECK (numero > 0),
    activo boolean NOT NULL DEFAULT true
);

CREATE TABLE servicios (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    placa text NOT NULL CHECK (placa ~ '^[A-Z]-[0-9]{3}[A-Z]{3}$'),
    tipo_id smallint NOT NULL REFERENCES tipos_vehiculo (id),
    slot_numero smallint NOT NULL REFERENCES slots (numero),
    estado text NOT NULL DEFAULT 'activo' CHECK (estado IN ('activo', 'finalizado')),
    entrada timestamptz NOT NULL DEFAULT now(),
    salida timestamptz,
    registrado_por bigint NOT NULL REFERENCES usuarios (id),
    CONSTRAINT servicios_salida_coherente CHECK (
        (estado = 'activo' AND salida IS NULL)
        OR (estado = 'finalizado' AND salida IS NOT NULL AND salida >= entrada)
    )
);

-- Una placa y un slot solo pueden tener un servicio activo a la vez.
CREATE UNIQUE INDEX servicios_placa_activa_unica ON servicios (placa) WHERE estado = 'activo';
CREATE UNIQUE INDEX servicios_slot_activo_unico ON servicios (slot_numero) WHERE estado = 'activo';
CREATE INDEX servicios_tipo_idx ON servicios (tipo_id);
CREATE INDEX servicios_entrada_idx ON servicios (entrada);

CREATE TABLE pagos (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    servicio_id bigint NOT NULL UNIQUE REFERENCES servicios (id),
    horas integer NOT NULL CHECK (horas >= 1),
    tarifa_hora numeric(10, 2) NOT NULL CHECK (tarifa_hora >= 0),
    total numeric(12, 2) NOT NULL CHECK (total >= 0),
    pagado_en timestamptz NOT NULL DEFAULT now(),
    registrado_por bigint NOT NULL REFERENCES usuarios (id),
    CONSTRAINT pagos_total_coherente CHECK (total = round(horas * tarifa_hora, 2))
);

CREATE INDEX pagos_pagado_en_idx ON pagos (pagado_en);

CREATE TABLE auditoria (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    usuario_id bigint REFERENCES usuarios (id),
    accion text NOT NULL CHECK (length(btrim(accion)) > 0),
    entidad text NOT NULL CHECK (length(btrim(entidad)) > 0),
    entidad_id bigint,
    detalle jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip inet,
    creado_en timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX auditoria_creado_en_idx ON auditoria (creado_en);
CREATE INDEX auditoria_usuario_idx ON auditoria (usuario_id);

-- El prefijo de la placa debe ser el del tipo de vehiculo.
CREATE FUNCTION validar_prefijo_placa() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    prefijo text;
BEGIN
    SELECT prefijo_placa INTO prefijo FROM tipos_vehiculo WHERE id = NEW.tipo_id;
    IF prefijo IS NOT NULL AND NEW.placa IS NOT NULL AND left(NEW.placa, 1) <> prefijo THEN
        RAISE EXCEPTION 'La placa % no corresponde al prefijo % del tipo de vehiculo', NEW.placa, prefijo
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER servicios_prefijo_placa
    BEFORE INSERT OR UPDATE OF placa, tipo_id ON servicios
    FOR EACH ROW EXECUTE FUNCTION validar_prefijo_placa();

-- Un servicio finalizado queda cerrado: no se edita ni se borra.
CREATE FUNCTION proteger_servicio_finalizado() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.estado = 'finalizado' THEN
        RAISE EXCEPTION 'El servicio % ya esta finalizado y no se puede modificar', OLD.id
            USING ERRCODE = 'check_violation';
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER servicios_finalizado_inmutable
    BEFORE UPDATE OR DELETE ON servicios
    FOR EACH ROW EXECUTE FUNCTION proteger_servicio_finalizado();

-- Solo se cobra un servicio ya finalizado.
CREATE FUNCTION validar_pago_servicio() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM servicios WHERE id = NEW.servicio_id AND estado = 'finalizado'
    ) THEN
        RAISE EXCEPTION 'El servicio % no esta finalizado, no se puede registrar el pago', NEW.servicio_id
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER pagos_servicio_finalizado
    BEFORE INSERT ON pagos
    FOR EACH ROW EXECUTE FUNCTION validar_pago_servicio();

-- La bitacora solo admite altas.
CREATE FUNCTION proteger_auditoria() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'La bitacora de auditoria no admite %', TG_OP
        USING ERRCODE = 'restrict_violation';
END;
$$;

CREATE TRIGGER auditoria_solo_altas
    BEFORE UPDATE OR DELETE ON auditoria
    FOR EACH ROW EXECUTE FUNCTION proteger_auditoria();

CREATE TRIGGER auditoria_sin_truncate
    BEFORE TRUNCATE ON auditoria
    FOR EACH STATEMENT EXECUTE FUNCTION proteger_auditoria();

COMMIT;
