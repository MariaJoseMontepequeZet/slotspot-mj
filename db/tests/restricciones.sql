\set ON_ERROR_STOP on

BEGIN;

CREATE PROCEDURE pg_temp.debe_fallar(sentencia text, esperado text, descripcion text)
LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        EXECUTE sentencia;
    EXCEPTION WHEN OTHERS THEN
        IF SQLSTATE = esperado THEN
            RAISE NOTICE 'OK    %', descripcion;
            RETURN;
        END IF;
        RAISE EXCEPTION 'FALLO % - se esperaba % y llego % (%)', descripcion, esperado, SQLSTATE, SQLERRM;
    END;
    RAISE EXCEPTION 'FALLO % - la sentencia no fallo', descripcion;
END;
$$;

CREATE PROCEDURE pg_temp.debe_funcionar(sentencia text, descripcion text)
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE sentencia;
    RAISE NOTICE 'OK    %', descripcion;
END;
$$;

CREATE PROCEDURE pg_temp.debe_ser(consulta text, esperado numeric, descripcion text)
LANGUAGE plpgsql AS $$
DECLARE
    obtenido numeric;
BEGIN
    EXECUTE consulta INTO obtenido;
    IF obtenido IS DISTINCT FROM esperado THEN
        RAISE EXCEPTION 'FALLO % - se esperaba % y se obtuvo %', descripcion, esperado, obtenido;
    END IF;
    RAISE NOTICE 'OK    %', descripcion;
END;
$$;

CREATE FUNCTION pg_temp.usuario() RETURNS bigint LANGUAGE sql AS $$ SELECT min(id) FROM usuarios $$;
CREATE FUNCTION pg_temp.tipo(cod text) RETURNS smallint LANGUAGE sql AS $$ SELECT id FROM tipos_vehiculo WHERE codigo = cod $$;
CREATE FUNCTION pg_temp.servicio(pl text) RETURNS bigint LANGUAGE sql AS $$ SELECT max(id) FROM servicios WHERE placa = pl $$;

CALL pg_temp.debe_ser($q$SELECT count(*) FROM roles$q$, 2, 'semilla: 2 roles');
CALL pg_temp.debe_ser($q$SELECT count(*) FROM tipos_vehiculo$q$, 5, 'semilla: 5 tipos de vehiculo');
CALL pg_temp.debe_ser($q$SELECT count(*) FROM slots$q$, 20, 'semilla: 20 slots');
CALL pg_temp.debe_ser($q$SELECT tarifa_hora FROM tipos_vehiculo WHERE codigo = 'AUT'$q$, 15.00, 'semilla: tarifa del automovil');

CALL pg_temp.debe_funcionar(
    $q$INSERT INTO usuarios (nombre, email, password_hash, rol_id)
       SELECT 'Prueba', 'prueba@slotspotmj.com', 'hash', id FROM roles WHERE nombre = 'admin'$q$,
    'usuario valido');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO usuarios (nombre, email, password_hash, rol_id) VALUES ('X', 'sin-arroba', 'h', 1)$q$,
    '23514', 'usuario: correo invalido');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO usuarios (nombre, email, password_hash, rol_id) VALUES ('X', 'PRUEBA@SLOTSPOTMJ.COM', 'h', 1)$q$,
    '23505', 'usuario: correo repetido sin distinguir mayusculas');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO usuarios (nombre, email, password_hash, rol_id) VALUES ('  ', 'otro@x.com', 'h', 1)$q$,
    '23514', 'usuario: nombre vacio');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO usuarios (nombre, email, password_hash, rol_id) VALUES ('X', 'otro@x.com', 'h', 999)$q$,
    '23503', 'usuario: rol inexistente');
CALL pg_temp.debe_fallar($q$INSERT INTO roles (nombre) VALUES ('invitado')$q$, '23514', 'rol: nombre no permitido');

CALL pg_temp.debe_fallar(
    $q$INSERT INTO tipos_vehiculo (codigo, nombre, prefijo_placa, tarifa_hora) VALUES ('XXX', 'Tanque', 'T', -1)$q$,
    '23514', 'tipo: tarifa negativa');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO tipos_vehiculo (codigo, nombre, prefijo_placa, tarifa_hora) VALUES ('xxx', 'Tanque', 'T', 1)$q$,
    '23514', 'tipo: codigo en minusculas');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO tipos_vehiculo (codigo, nombre, prefijo_placa, tarifa_hora) VALUES ('TAN', 'Tanque', 'P', 1)$q$,
    '23505', 'tipo: prefijo repetido');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO tipos_vehiculo (codigo, nombre, prefijo_placa, tarifa_hora) VALUES ('TAN', 'Moto', 'T', 1)$q$,
    '23505', 'tipo: nombre repetido');
CALL pg_temp.debe_funcionar(
    $q$INSERT INTO tipos_vehiculo (codigo, nombre, prefijo_placa, tarifa_hora) VALUES ('GRA', 'Gratis', 'G', 0)$q$,
    'tipo: tarifa 0 es valida');
CALL pg_temp.debe_fallar($q$INSERT INTO slots (numero) VALUES (0)$q$, '23514', 'slot: numero 0');

CALL pg_temp.debe_funcionar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, entrada, registrado_por)
       VALUES ('P-111AAA', pg_temp.tipo('AUT'), 1, now() - interval '150 minutes', pg_temp.usuario())$q$,
    'servicio valido: automovil en el slot 1');
CALL pg_temp.debe_funcionar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('M-222BBB', pg_temp.tipo('MOT'), 2, pg_temp.usuario())$q$,
    'servicio valido: moto en el slot 2');

CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-111AAA', pg_temp.tipo('AUT'), 3, pg_temp.usuario())$q$,
    '23505', 'servicio: placa activa repetida');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-333CCC', pg_temp.tipo('AUT'), 1, pg_temp.usuario())$q$,
    '23505', 'servicio: slot activo ocupado');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('M-444DDD', pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23514', 'servicio: prefijo de placa distinto al del tipo');

CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-12ABC', pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23514', 'placa: faltan digitos');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('p-123abc', pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23514', 'placa: minusculas');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-123AB1', pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23514', 'placa: un digito entre las letras');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P123ABC', pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23514', 'placa: sin guion');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-1234ABC', pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23514', 'placa: demasiados digitos');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES (NULL, pg_temp.tipo('AUT'), 5, pg_temp.usuario())$q$,
    '23502', 'placa: nula');

CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-555EEE', 999, 5, pg_temp.usuario())$q$,
    '23503', 'servicio: tipo inexistente');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-555EEE', pg_temp.tipo('AUT'), 99, pg_temp.usuario())$q$,
    '23503', 'servicio: slot inexistente');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-555EEE', pg_temp.tipo('AUT'), 5, 999999)$q$,
    '23503', 'servicio: usuario inexistente');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, estado, registrado_por)
       VALUES ('P-555EEE', pg_temp.tipo('AUT'), 5, 'cancelado', pg_temp.usuario())$q$,
    '23514', 'servicio: estado no permitido');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, salida, registrado_por)
       VALUES ('P-555EEE', pg_temp.tipo('AUT'), 5, now(), pg_temp.usuario())$q$,
    '23514', 'servicio: activo con hora de salida');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, estado, registrado_por)
       VALUES ('P-555EEE', pg_temp.tipo('AUT'), 5, 'finalizado', pg_temp.usuario())$q$,
    '23514', 'servicio: finalizado sin hora de salida');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, estado, entrada, salida, registrado_por)
       VALUES ('P-555EEE', pg_temp.tipo('AUT'), 5, 'finalizado', now(), now() - interval '1 hour', pg_temp.usuario())$q$,
    '23514', 'servicio: salida anterior a la entrada');

CALL pg_temp.debe_fallar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       VALUES (pg_temp.servicio('M-222BBB'), 1, 5.00, 5.00, pg_temp.usuario())$q$,
    '23514', 'pago: el servicio sigue activo');

CALL pg_temp.debe_funcionar(
    $q$UPDATE servicios SET estado = 'finalizado', salida = now() WHERE placa = 'P-111AAA'$q$,
    'cerrar el servicio del automovil');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       VALUES (pg_temp.servicio('P-111AAA'), 3, 15.00, 46.00, pg_temp.usuario())$q$,
    '23514', 'pago: total distinto de horas por tarifa');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       VALUES (pg_temp.servicio('P-111AAA'), 0, 15.00, 0.00, pg_temp.usuario())$q$,
    '23514', 'pago: cero horas');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       VALUES (pg_temp.servicio('P-111AAA'), 3, -15.00, -45.00, pg_temp.usuario())$q$,
    '23514', 'pago: tarifa negativa');
CALL pg_temp.debe_funcionar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       VALUES (pg_temp.servicio('P-111AAA'), 3, 15.00, 45.00, pg_temp.usuario())$q$,
    'pago valido: 3 horas a 15.00 son 45.00');
CALL pg_temp.debe_fallar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       VALUES (pg_temp.servicio('P-111AAA'), 3, 15.00, 45.00, pg_temp.usuario())$q$,
    '23505', 'pago: un servicio no se cobra dos veces');

CALL pg_temp.debe_fallar(
    $q$UPDATE servicios SET placa = 'P-999ZZZ' WHERE placa = 'P-111AAA'$q$,
    '23514', 'servicio finalizado: no se edita');
CALL pg_temp.debe_fallar(
    $q$UPDATE servicios SET estado = 'activo', salida = NULL WHERE placa = 'P-111AAA'$q$,
    '23514', 'servicio finalizado: no se reabre');
CALL pg_temp.debe_fallar(
    $q$DELETE FROM servicios WHERE placa = 'P-111AAA'$q$,
    '23514', 'servicio finalizado: no se borra');

CALL pg_temp.debe_funcionar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       VALUES ('P-111AAA', pg_temp.tipo('AUT'), 1, pg_temp.usuario())$q$,
    'la placa y el slot se reutilizan despues de finalizar');
CALL pg_temp.debe_fallar(
    $q$UPDATE servicios SET placa = 'M-111AAA' WHERE placa = 'P-111AAA' AND estado = 'activo'$q$,
    '23514', 'servicio activo: el nuevo prefijo debe seguir al tipo');
CALL pg_temp.debe_funcionar(
    $q$UPDATE servicios SET placa = 'P-999ZZZ' WHERE placa = 'P-111AAA' AND estado = 'activo'$q$,
    'servicio activo: se puede corregir la placa');

CALL pg_temp.debe_funcionar(
    $q$INSERT INTO auditoria (usuario_id, accion, entidad, entidad_id, detalle, ip)
       VALUES (pg_temp.usuario(), 'cobro', 'servicio', 1, '{"total": "45.00"}', '127.0.0.1')$q$,
    'auditoria: alta valida');
CALL pg_temp.debe_fallar($q$UPDATE auditoria SET accion = 'otra'$q$, '23001', 'auditoria: no se modifica');
CALL pg_temp.debe_fallar($q$DELETE FROM auditoria$q$, '23001', 'auditoria: no se borra');
CALL pg_temp.debe_fallar($q$TRUNCATE auditoria$q$, '23001', 'auditoria: no se vacia');
CALL pg_temp.debe_fallar(
    $q$DELETE FROM usuarios WHERE id = pg_temp.usuario()$q$,
    '23503', 'usuario con historial: no se borra');

CALL pg_temp.debe_ser($q$SELECT count(*) FROM servicios WHERE estado = 'activo'$q$, 2, 'resultado: 2 servicios activos');
CALL pg_temp.debe_ser($q$SELECT count(*) FROM servicios WHERE estado = 'finalizado'$q$, 1, 'resultado: 1 servicio finalizado');
CALL pg_temp.debe_ser($q$SELECT total FROM pagos$q$, 45.00, 'resultado: total cobrado');

ROLLBACK;

\echo 'TODAS LAS PRUEBAS DE RESTRICCIONES PASARON'
