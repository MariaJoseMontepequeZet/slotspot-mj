# Diagrama entidad-relación

Esquema de PostgreSQL de SlotSpot MJ. El script que lo crea es `db/schema.sql`.

```mermaid
erDiagram
    ROLES ||--o{ USUARIOS : "tiene"
    USUARIOS ||--o{ SERVICIOS : "registra"
    USUARIOS ||--o{ PAGOS : "registra"
    USUARIOS ||--o{ AUDITORIA : "genera"
    TIPOS_VEHICULO ||--o{ SERVICIOS : "clasifica"
    SLOTS ||--o{ SERVICIOS : "aloja"
    SERVICIOS ||--o| PAGOS : "se cobra con"

    ROLES {
        smallint id PK
        text nombre UK "admin u operador"
    }

    USUARIOS {
        bigint id PK
        text nombre
        text email UK "unico sin distinguir mayusculas"
        text password_hash
        smallint rol_id FK
        boolean activo
        timestamptz creado_en
    }

    TIPOS_VEHICULO {
        smallint id PK
        text codigo UK "3 letras"
        text nombre UK
        text prefijo_placa UK "1 letra"
        numeric tarifa_hora "mayor o igual que 0"
        boolean activo
    }

    SLOTS {
        smallint numero PK
        boolean activo
    }

    SERVICIOS {
        bigint id PK
        text placa "X-000AAA"
        smallint tipo_id FK
        smallint slot_numero FK
        text estado "activo o finalizado"
        timestamptz entrada
        timestamptz salida
        bigint registrado_por FK
    }

    PAGOS {
        bigint id PK
        bigint servicio_id FK, UK
        integer horas "mayor o igual que 1"
        numeric tarifa_hora "tarifa aplicada"
        numeric total "horas por tarifa"
        timestamptz pagado_en
        bigint registrado_por FK
    }

    AUDITORIA {
        bigint id PK
        bigint usuario_id FK
        text accion
        text entidad
        bigint entidad_id
        jsonb detalle
        inet ip
        timestamptz creado_en
    }
```

## Normalización

El esquema está en tercera forma normal: cada dato depende de la clave de su tabla y de nada más. La tarifa vive en `tipos_vehiculo`, y el tipo, el slot y el usuario se referencian por clave foránea.

La única copia intencional es `pagos.tarifa_hora`. Guarda la tarifa vigente al momento del cobro, para que un cambio posterior de tarifa no altere el historial de ingresos.

## Reglas que vigila la base de datos

| Regla | Mecanismo |
|-------|-----------|
| Una placa solo puede tener un servicio activo | Índice único parcial `servicios_placa_activa_unica` |
| Un slot solo puede tener un servicio activo | Índice único parcial `servicios_slot_activo_unico` |
| La placa tiene el formato `X-000AAA` | `CHECK` sobre `servicios.placa` |
| El prefijo de la placa es el del tipo de vehículo | Trigger `servicios_prefijo_placa` |
| La tarifa no puede ser negativa | `CHECK` en `tipos_vehiculo` y `pagos` |
| Un servicio activo no tiene salida y uno finalizado sí, posterior a la entrada | `CHECK` `servicios_salida_coherente` |
| Un servicio finalizado no se edita, no se reabre y no se borra | Trigger `servicios_finalizado_inmutable` |
| Solo se cobra un servicio finalizado, y una sola vez | Trigger `pagos_servicio_finalizado` y `UNIQUE` en `servicio_id` |
| El total cobrado es horas por tarifa | `CHECK` `pagos_total_coherente` |
| La bitácora solo admite altas | Triggers `auditoria_solo_altas` y `auditoria_sin_truncate` |
| Un usuario con historial no se borra, se desactiva | Claves foráneas sin borrado en cascada |

La placa y el slot se reutilizan después de finalizar un servicio, porque los índices únicos solo miran los servicios activos.

## Relación con la aplicación actual

El frontend guarda hoy el `slot` en `null` al dar salida. En la base de datos el slot se conserva en el servicio finalizado como dato histórico, y la disponibilidad se calcula con los servicios activos.
