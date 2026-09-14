"""Reporte de calidad de datos (fase 4, "Profundidad" de la especificacion):
traduce lo que ya calculan el perfilado (paso 9, `fuente.perfil`) y la
ingesta (paso 3, `fuente.esquema[].invalidos`) en una lista de problemas
priorizados, en vez de numeros crudos sueltos — mas dos chequeos que
necesitan una consulta nueva contra la vista DuckDB de la fuente: filas
duplicadas exactas, y si hay un modelo semantico cargado, si su clave
primaria dejo de ser unica y si sus relaciones confirmadas tienen
huerfanos. Todo al vuelo (nada se persiste, a diferencia del perfil)."""
from typing import Any

import duckdb

from app.calidad.esquema import ProblemaCalidad, ReporteCalidad
from app.ingesta.tipado import columna_sql
from app.modelo.esquema import ModeloSemantico
from app.perfilado.perfil import PerfilFuente

# Por encima de esto se avisa "muchos vacios"; los invalidos son mas graves
# (un dato que existia y no se pudo interpretar, no un campo vacio) asi que
# su umbral es mas estricto.
UMBRAL_NULOS = 0.2
UMBRAL_NULOS_ALTA = 0.5
UMBRAL_INVALIDOS = 0.05

_ORDEN_SEVERIDAD = {"alta": 0, "media": 1, "baja": 2}


def _problemas_de_nulos(perfil: PerfilFuente) -> list[ProblemaCalidad]:
    if perfil.filas == 0:
        return []
    problemas = []
    for columna in perfil.columnas:
        proporcion = columna.nulos / perfil.filas
        if proporcion <= UMBRAL_NULOS:
            continue
        problemas.append(
            ProblemaCalidad(
                codigo="nulos_altos",
                severidad="alta" if proporcion >= UMBRAL_NULOS_ALTA else "media",
                campo=columna.nombre,
                mensaje=f"La columna '{columna.nombre}' tiene {proporcion:.0%} de valores vacíos ({columna.nulos} de {perfil.filas} filas).",
                detalle={"nulos": columna.nulos, "filas": perfil.filas, "proporcion": round(proporcion, 4)},
            )
        )
    return problemas


def _problemas_de_invalidos(esquema: list[dict[str, Any]], filas: int) -> list[ProblemaCalidad]:
    if filas == 0:
        return []
    problemas = []
    for columna in esquema:
        invalidos = columna.get("invalidos") or 0
        proporcion = invalidos / filas
        if proporcion <= UMBRAL_INVALIDOS:
            continue
        problemas.append(
            ProblemaCalidad(
                codigo="valores_invalidos",
                severidad="alta",
                campo=columna["nombre"],
                mensaje=f"La columna '{columna['nombre']}' tiene {invalidos} valor(es) que no se pudieron interpretar como {columna['tipo']} y quedaron vacíos.",
                detalle={"invalidos": invalidos, "filas": filas, "proporcion": round(proporcion, 4)},
            )
        )
    return problemas


def _contar_filas_duplicadas(conexion: duckdb.DuckDBPyConnection, nombre_tabla: str, columnas: list[str]) -> int:
    """Filas "de mas" respecto de si ninguna se repitiera: 3 filas identicas
    en `columnas` cuentan como 2 duplicadas, no 3."""
    if not columnas:
        return 0
    tabla = columna_sql(nombre_tabla)
    lista = ", ".join(columna_sql(nombre) for nombre in columnas)
    total, distintas = conexion.execute(
        f"SELECT count(*), count(DISTINCT ({lista})) FROM {tabla}"
    ).fetchone()
    return max(0, total - distintas)


def _contar_huerfanos(conexion: duckdb.DuckDBPyConnection, tabla_desde: str, columna_desde: str, tabla_hacia: str, columna_hacia: str) -> int:
    """Filas de `tabla_desde` cuyo valor de `columna_desde` no es nulo pero
    tampoco existe entre los valores no nulos de `columna_hacia` en
    `tabla_hacia` (mismo criterio que la inclusion de FK del paso 10)."""
    desde, hacia = columna_sql(tabla_desde), columna_sql(tabla_hacia)
    c_desde, c_hacia = columna_sql(columna_desde), columna_sql(columna_hacia)
    return conexion.execute(
        f"SELECT count(*) FROM {desde} a WHERE a.{c_desde} IS NOT NULL "
        f"AND a.{c_desde} NOT IN (SELECT b.{c_hacia} FROM {hacia} b WHERE b.{c_hacia} IS NOT NULL)"
    ).fetchone()[0]


def _problemas_de_modelo(
    conexion: duckdb.DuckDBPyConnection, nombre_tabla: str, modelo: ModeloSemantico
) -> list[ProblemaCalidad]:
    entidad = next((e for e in modelo.entidades if e.fuente == nombre_tabla), None)
    if entidad is None:
        return []
    problemas: list[ProblemaCalidad] = []

    columnas_clave = [campo.columna_origen for id_campo in entidad.clave_primaria if (campo := entidad.campo(id_campo)) is not None]
    duplicados_clave = _contar_filas_duplicadas(conexion, nombre_tabla, columnas_clave)
    if duplicados_clave > 0:
        etiqueta_clave = ", ".join(columnas_clave)
        problemas.append(
            ProblemaCalidad(
                codigo="clave_no_unica",
                severidad="alta",
                campo=f"{entidad.id}.{etiqueta_clave}",
                mensaje=f"La clave primaria de '{entidad.nombre}' ({etiqueta_clave}) ya no es única: hay {duplicados_clave} fila(s) repetida(s).",
                detalle={"duplicados": duplicados_clave},
            )
        )

    for relacion in modelo.relaciones:
        if relacion.estado != "confirmada" or relacion.desde.entidad != entidad.id:
            continue
        entidad_hacia = modelo.entidad(relacion.hacia.entidad)
        campo_desde = entidad.campo(relacion.desde.campo)
        campo_hacia = entidad_hacia.campo(relacion.hacia.campo) if entidad_hacia else None
        if entidad_hacia is None or campo_desde is None or campo_hacia is None:
            continue
        huerfanos = _contar_huerfanos(conexion, nombre_tabla, campo_desde.columna_origen, entidad_hacia.fuente, campo_hacia.columna_origen)
        if huerfanos > 0:
            problemas.append(
                ProblemaCalidad(
                    codigo="huerfanos",
                    severidad="alta",
                    campo=f"{entidad.id}.{campo_desde.columna_origen}",
                    mensaje=f"{huerfanos} fila(s) de '{entidad.nombre}' referencian un/a '{entidad_hacia.nombre}' que no existe.",
                    detalle={"huerfanos": huerfanos, "relacion": relacion.id, "hacia": entidad_hacia.id},
                )
            )
    return problemas


def calcular_reporte(
    conexion: duckdb.DuckDBPyConnection,
    *,
    nombre_tabla: str,
    esquema: list[dict[str, Any]],
    filas: int,
    perfil: dict[str, Any] | None,
    modelo: ModeloSemantico | None,
) -> ReporteCalidad:
    problemas: list[ProblemaCalidad] = []
    if perfil:
        problemas += _problemas_de_nulos(PerfilFuente.model_validate(perfil))
    problemas += _problemas_de_invalidos(esquema, filas)

    duplicados = _contar_filas_duplicadas(conexion, nombre_tabla, [columna["nombre"] for columna in esquema])
    if duplicados > 0:
        problemas.append(
            ProblemaCalidad(
                codigo="filas_duplicadas",
                severidad="media",
                campo=None,
                mensaje=f"Hay {duplicados} fila(s) repetida(s) exactamente (todas las columnas iguales).",
                detalle={"duplicados": duplicados, "filas": filas},
            )
        )

    if modelo is not None:
        problemas += _problemas_de_modelo(conexion, nombre_tabla, modelo)

    problemas.sort(key=lambda problema: _ORDEN_SEVERIDAD[problema.severidad])
    return ReporteCalidad(fuente=nombre_tabla, filas=filas, problemas=problemas)
