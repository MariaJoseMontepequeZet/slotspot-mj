\set ON_ERROR_STOP on

BEGIN;

CREATE PROCEDURE public.debe_fallar(sentencia text, esperado text, descripcion text)
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

CREATE PROCEDURE public.debe_funcionar(sentencia text, descripcion text)
LANGUAGE plpgsql AS $$
BEGIN
    EXECUTE sentencia;
    RAISE NOTICE 'OK    %', descripcion;
END;
$$;

CREATE PROCEDURE public.debe_ser(consulta text, esperado text, descripcion text)
LANGUAGE plpgsql AS $$
DECLARE
    obtenido text;
BEGIN
    EXECUTE consulta INTO obtenido;
    IF obtenido IS DISTINCT FROM esperado THEN
        RAISE EXCEPTION 'FALLO % - se esperaba % y se obtuvo %', descripcion, esperado, obtenido;
    END IF;
    RAISE NOTICE 'OK    %', descripcion;
END;
$$;

INSERT INTO usuarios (nombre, email, password_hash, rol_id)
SELECT 'Base', 'base@slotspotmj.com', 'hash', id FROM roles WHERE nombre = 'admin';

INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
SELECT 'P-100AAA', t.id, 1, u.id FROM tipos_vehiculo t, usuarios u WHERE t.codigo = 'AUT';

CALL public.debe_ser(
    format($q$SELECT bool_or(rolsuper OR rolcreaterole OR rolcreatedb OR rolreplication OR rolbypassrls)::text
              FROM pg_roles WHERE rolname = %L$q$, :'rol'),
    'false', 'el rol no es superusuario ni puede crear roles, bases o replicar');
CALL public.debe_ser(
    format($q$SELECT count(*)::text FROM pg_auth_members WHERE member = %L::regrole$q$, :'rol'),
    '0', 'el rol no pertenece a ningun otro rol');
CALL public.debe_ser(
    format($q$SELECT has_schema_privilege(%L, 'public', 'CREATE')::text$q$, :'rol'),
    'false', 'el rol no puede crear objetos en el esquema public');
CALL public.debe_ser(
    format($q$SELECT has_database_privilege(%L, current_database(), 'CONNECT')::text$q$, :'rol'),
    'true', 'el rol puede conectarse a la base');
CALL public.debe_ser(
    format($q$SELECT has_database_privilege(%L, current_database(), 'TEMPORARY')::text$q$, :'rol'),
    'false', 'el rol no puede crear tablas temporales');

SELECT format('SET LOCAL ROLE %I', :'rol') \gexec

CALL public.debe_ser('SELECT current_user::text', :'rol', 'las pruebas siguientes corren con el rol de la aplicacion');

CALL public.debe_funcionar('SELECT count(*) FROM roles', 'puede leer roles');
CALL public.debe_funcionar('SELECT count(*) FROM tipos_vehiculo', 'puede leer tipos');
CALL public.debe_funcionar('SELECT count(*) FROM slots', 'puede leer slots');
CALL public.debe_funcionar(
    $q$INSERT INTO usuarios (nombre, email, password_hash, rol_id)
       VALUES ('Op', 'op@slotspotmj.com', 'hash', (SELECT id FROM roles WHERE nombre = 'operador'))$q$,
    'puede crear usuarios');
CALL public.debe_funcionar($q$UPDATE usuarios SET activo = false WHERE email = 'op@slotspotmj.com'$q$, 'puede desactivar usuarios');
CALL public.debe_funcionar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       SELECT 'M-200BBB', t.id, 2, u.id FROM tipos_vehiculo t, usuarios u
       WHERE t.codigo = 'MOT' AND u.email = 'base@slotspotmj.com'$q$,
    'puede registrar un ingreso');
CALL public.debe_funcionar(
    $q$UPDATE servicios SET estado = 'finalizado', salida = now() WHERE placa = 'P-100AAA'$q$,
    'puede dar salida a un servicio');
CALL public.debe_funcionar(
    $q$INSERT INTO pagos (servicio_id, horas, tarifa_hora, total, registrado_por)
       SELECT s.id, 1, 15.00, 15.00, s.registrado_por FROM servicios s WHERE s.placa = 'P-100AAA'$q$,
    'puede registrar un pago');
CALL public.debe_funcionar(
    $q$INSERT INTO auditoria (usuario_id, accion, entidad) SELECT id, 'cobro', 'servicio' FROM usuarios LIMIT 1$q$,
    'puede escribir en la bitacora');
CALL public.debe_funcionar('SELECT count(*) FROM auditoria', 'puede leer la bitacora');
CALL public.debe_funcionar($q$UPDATE tipos_vehiculo SET tarifa_hora = 16.00 WHERE codigo = 'AUT'$q$, 'puede cambiar una tarifa');
CALL public.debe_funcionar('UPDATE slots SET activo = true WHERE numero = 3', 'puede actualizar un slot');

CALL public.debe_fallar('UPDATE auditoria SET accion = ''otra''', '42501', 'no puede modificar la bitacora');
CALL public.debe_fallar('DELETE FROM auditoria', '42501', 'no puede borrar de la bitacora');
CALL public.debe_fallar('TRUNCATE auditoria', '42501', 'no puede vaciar la bitacora');
CALL public.debe_fallar('DELETE FROM usuarios', '42501', 'no puede borrar usuarios');
CALL public.debe_fallar('DELETE FROM servicios', '42501', 'no puede borrar servicios');
CALL public.debe_fallar('DELETE FROM pagos', '42501', 'no puede borrar pagos');
CALL public.debe_fallar('UPDATE pagos SET total = 0', '42501', 'no puede modificar pagos');
CALL public.debe_fallar('DELETE FROM tipos_vehiculo', '42501', 'no puede borrar tipos de vehiculo');
CALL public.debe_fallar('INSERT INTO slots (numero) VALUES (99)', '42501', 'no puede crear slots');
CALL public.debe_fallar('DELETE FROM slots', '42501', 'no puede borrar slots');
CALL public.debe_fallar('UPDATE roles SET nombre = ''admin''', '42501', 'no puede modificar roles');
CALL public.debe_fallar('TRUNCATE usuarios', '42501', 'no puede vaciar usuarios');

CALL public.debe_fallar('DROP TABLE usuarios', '42501', 'no puede borrar tablas');
CALL public.debe_fallar('ALTER TABLE usuarios ADD COLUMN x integer', '42501', 'no puede alterar tablas');
CALL public.debe_fallar('ALTER TABLE auditoria DISABLE TRIGGER ALL', '42501', 'no puede desactivar los triggers de la bitacora');
CALL public.debe_fallar('DROP TRIGGER auditoria_solo_altas ON auditoria', '42501', 'no puede borrar los triggers');
CALL public.debe_fallar('CREATE TABLE public.intruso (id integer)', '42501', 'no puede crear tablas');
CALL public.debe_fallar('CREATE FUNCTION public.intruso() RETURNS integer LANGUAGE sql AS ''SELECT 1''', '42501', 'no puede crear funciones');
CALL public.debe_fallar('CREATE TEMPORARY TABLE temporal (id integer)', '42501', 'no puede crear tablas temporales');
CALL public.debe_fallar('CREATE ROLE intruso', '42501', 'no puede crear roles');
CALL public.debe_fallar('SELECT pg_read_file(''/etc/passwd'')', '42501', 'no puede leer archivos del servidor');
CALL public.debe_fallar('COPY usuarios TO PROGRAM ''true''', '42501', 'no puede ejecutar programas del servidor');

CALL public.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       SELECT 'M-300CCC', t.id, 4, u.id FROM tipos_vehiculo t, usuarios u
       WHERE t.codigo = 'AUT' AND u.email = 'base@slotspotmj.com'$q$,
    '23514', 'las reglas del negocio siguen valiendo para el rol: prefijo de placa');
CALL public.debe_fallar(
    $q$UPDATE servicios SET placa = 'P-999ZZZ' WHERE placa = 'P-100AAA'$q$,
    '23514', 'las reglas del negocio siguen valiendo para el rol: servicio finalizado');
CALL public.debe_fallar(
    $q$INSERT INTO servicios (placa, tipo_id, slot_numero, registrado_por)
       SELECT 'P-400DDD', t.id, 2, u.id FROM tipos_vehiculo t, usuarios u
       WHERE t.codigo = 'AUT' AND u.email = 'base@slotspotmj.com'$q$,
    '23505', 'las reglas del negocio siguen valiendo para el rol: slot ocupado');

ROLLBACK;

\echo 'TODAS LAS PRUEBAS DE PERMISOS PASARON'
