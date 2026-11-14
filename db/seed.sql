BEGIN;

INSERT INTO roles (nombre)
VALUES ('admin'), ('operador')
ON CONFLICT (nombre) DO NOTHING;

INSERT INTO tipos_vehiculo (codigo, nombre, prefijo_placa, tarifa_hora)
VALUES
    ('AUT', 'Automóvil', 'P', 15.00),
    ('MOT', 'Moto', 'M', 5.00),
    ('CAM', 'Camioneta', 'C', 20.00),
    ('BIC', 'Bicicleta', 'B', 2.00),
    ('SCO', 'Scooter', 'S', 3.00)
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO slots (numero)
SELECT generate_series(1, 20)
ON CONFLICT (numero) DO NOTHING;

COMMIT;
