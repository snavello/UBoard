"""Ingesta: archivo subido (CSV, Excel) -> Parquet tipado en el almacen +
fila `fuente` en el catalogo + vista DuckDB.

Etapas, cada una en su modulo y probada por separado:
1. codificacion: bytes -> texto UTF-8 (detecta latin-1, BOM, UTF-16).
2. encabezado: separador, fila de encabezado (saltando titulos), nombres de
   columna normalizados.
3. lector_csv / lector_excel: dejan una tabla con TODAS las columnas VARCHAR
   en una conexion DuckDB.
4. tipado: decide el tipo de cada columna con heuristicas deterministas
   (entero, decimal con coma o punto, fecha con formatos mezclados, booleano)
   y arma la expresion SQL que convierte; lo que no convierte queda NULL y se
   cuenta como invalido.
5. procesador: escribe el Parquet, arma el esquema y la huella, registra la
   fuente. `tarea.py` lo corre en segundo plano.
"""
