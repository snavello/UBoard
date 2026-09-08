"""Archivo completo -> Parquet tipado: CSV sucios y Excel de varias hojas.
Puro (sin Postgres), con directorios temporales."""
import io
from datetime import date, datetime, timedelta

import duckdb
import pytest
from openpyxl import Workbook

from app.ingesta.procesador import ResultadoTabla, ingestar_archivo, validar_extension
from app.nucleo.errores import ErrorApp


def _parquet(resultado: ResultadoTabla) -> list[tuple]:
    return duckdb.sql(f"SELECT * FROM read_parquet('{resultado.ruta_parquet_temporal.as_posix()}')").fetchall()


def _tipos(resultado: ResultadoTabla) -> dict[str, str]:
    return {columna.nombre: columna.tipo for columna in resultado.esquema}


def _ingestar_uno(datos: bytes, nombre: str, tmp_path) -> ResultadoTabla:
    directorio = tmp_path / nombre.replace(".", "_")
    directorio.mkdir()
    resultados = ingestar_archivo(datos, nombre, directorio)
    assert len(resultados) == 1
    return resultados[0]


def test_csv_latin1_punto_y_coma_y_coma_decimal(tmp_path):
    datos = "id;nombre;precio\n1;Dulce de Leche Ñandú;1.250,50\n2;Aceite Cañuelas;3.990,00\n".encode("latin-1")
    resultado = _ingestar_uno(datos, "Productos.csv", tmp_path)
    assert resultado.nombre_tabla == "productos"
    assert resultado.formato == "csv"
    assert resultado.filas == 2
    assert _tipos(resultado) == {"id": "entero", "nombre": "texto", "precio": "decimal"}
    assert resultado.opciones["delimitador"] == ";"
    assert resultado.opciones["codificacion"] == "cp1252"
    assert resultado.opciones["filas_saltadas"] == 0
    assert _parquet(resultado) == [(1, "Dulce de Leche Ñandú", 1250.5), (2, "Aceite Cañuelas", 3990.0)]
    assert [columna.nombre_origen for columna in resultado.esquema] == ["id", "nombre", "precio"]


def test_csv_con_bom_y_filas_de_titulo(tmp_path):
    datos = "﻿Listado de ventas\nExportado: hoy\nId Venta,Fecha\n1,05/03/2026\n2,2026-03-06\n".encode("utf-8")
    resultado = _ingestar_uno(datos, "ventas.csv", tmp_path)
    assert resultado.opciones["filas_saltadas"] == 2
    assert [columna.nombre for columna in resultado.esquema] == ["id_venta", "fecha"]
    assert _tipos(resultado)["fecha"] == "fecha"
    assert _parquet(resultado) == [(1, date(2026, 3, 5)), (2, date(2026, 3, 6))]


def test_csv_tabulado_con_comillas(tmp_path):
    datos = 'Id\tDetalle\n1\t"Aceite\t1,5L"\n2\tYerba\n'.encode("utf-8")
    resultado = _ingestar_uno(datos, "detalle.tsv", tmp_path)
    assert resultado.opciones["delimitador"] == "\t"
    assert _parquet(resultado) == [(1, "Aceite\t1,5L"), (2, "Yerba")]


def test_csv_filas_cortas_se_rellenan_con_nulos(tmp_path):
    resultado = _ingestar_uno(b"a,b,c\n1,2\n3,4,5\n", "corto.csv", tmp_path)
    assert resultado.filas == 2
    assert _parquet(resultado) == [(1, 2, None), (3, 4, 5)]
    nulos = {columna.nombre: columna.nulos for columna in resultado.esquema}
    assert nulos == {"a": 0, "b": 0, "c": 1}


def test_csv_sin_encabezado_genera_nombres(tmp_path):
    resultado = _ingestar_uno(b"1,2\n3,4\n", "numeros.csv", tmp_path)
    assert resultado.opciones["tiene_encabezado"] is False
    assert [columna.nombre for columna in resultado.esquema] == ["columna_1", "columna_2"]
    assert resultado.filas == 2


def test_csv_invalidos_se_cuentan_y_quedan_nulos(tmp_path):
    lineas = ["id,fecha"] + [f"{i},{date(2026, 1, 1) + timedelta(days=i)}" for i in range(1, 40)] + ["40,sin fecha"]
    resultado = _ingestar_uno("\n".join(lineas).encode(), "fechas.csv", tmp_path)
    columna_fecha = next(columna for columna in resultado.esquema if columna.nombre == "fecha")
    assert columna_fecha.tipo == "fecha"
    assert columna_fecha.invalidos == 1
    assert columna_fecha.nulos == 0
    assert _parquet(resultado)[-1] == (40, None)


def test_csv_vacio(tmp_path):
    with pytest.raises(ErrorApp) as error:
        ingestar_archivo(b"\n\n  \n", "vacio.csv", tmp_path)
    assert error.value.codigo == "E-ING-03"


def test_extension_no_soportada(tmp_path):
    with pytest.raises(ErrorApp) as error:
        ingestar_archivo(b"x", "programa.exe", tmp_path)
    assert error.value.codigo == "E-ING-05"
    assert validar_extension("Datos.XLSX") == ".xlsx"


def _excel(hojas: dict[str, list[list]]) -> bytes:
    libro = Workbook()
    libro.remove(libro.active)
    for nombre, filas in hojas.items():
        hoja = libro.create_sheet(nombre)
        for fila in filas:
            hoja.append(fila)
    buffer = io.BytesIO()
    libro.save(buffer)
    return buffer.getvalue()


def test_excel_una_tabla_por_hoja_con_datos(tmp_path):
    datos = _excel(
        {
            "Ventas": [
                ["Reporte de ventas"],
                [],
                ["Id", "Fecha", "Monto", "Pagado"],
                [1.0, datetime(2026, 3, 5), 1250.5, True],
                [2.0, datetime(2026, 3, 6), 300, False],
            ],
            "Vacia": [],
            "Clientes": [["Id Cliente", "Nombre"], [1, "Ana"], [2, "Bruno"]],
        }
    )
    resultados = ingestar_archivo(datos, "Cierre Marzo.xlsx", tmp_path)
    assert [resultado.nombre_tabla for resultado in resultados] == ["cierre_marzo_ventas", "cierre_marzo_clientes"]
    assert [resultado.hoja for resultado in resultados] == ["Ventas", "Clientes"]
    ventas = resultados[0]
    assert ventas.formato == "xlsx"
    assert ventas.opciones["filas_saltadas"] == 2
    assert _tipos(ventas) == {"id": "entero", "fecha": "fecha", "monto": "decimal", "pagado": "booleano"}
    assert _parquet(ventas) == [(1, date(2026, 3, 5), 1250.5, True), (2, date(2026, 3, 6), 300.0, False)]
    assert _parquet(resultados[1]) == [(1, "Ana"), (2, "Bruno")]


def test_excel_de_una_sola_hoja_usa_el_nombre_del_archivo(tmp_path):
    datos = _excel({"Hoja1": [["a", "b"], [1, 2]]})
    resultado = _ingestar_uno(datos, "Vendedores 2026.xlsx", tmp_path)
    assert resultado.nombre_tabla == "vendedores_2026"
    assert resultado.hoja == "Hoja1"


def test_excel_sin_datos(tmp_path):
    with pytest.raises(ErrorApp) as error:
        ingestar_archivo(_excel({"Hoja1": []}), "nada.xlsx", tmp_path)
    assert error.value.codigo == "E-ING-03"


def test_excel_roto(tmp_path):
    with pytest.raises(ErrorApp) as error:
        ingestar_archivo(b"esto no es un excel", "roto.xlsx", tmp_path)
    assert error.value.codigo == "E-ING-01"
