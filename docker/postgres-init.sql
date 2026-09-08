-- Corre una sola vez, al crear el volumen del Postgres de desarrollo.
-- La base uboard_dev la crea la imagen por POSTGRES_DB; aca se suma la base
-- de tests, separada para que los tests de API nunca toquen datos de trabajo.
CREATE DATABASE uboard_test OWNER uboard;
