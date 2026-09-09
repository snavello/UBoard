"""Heuristicas deterministas: de los perfiles de las fuentes (y una conexion
DuckDB para medir inclusion de valores entre columnas) a un ModeloSemantico
PROPUESTO. Claude no interviene aca: las claves y las relaciones las deciden
los datos.

Umbrales (aprobados por Sd, ajustables por config):
- Clave primaria: 100 % unicos y sin nulos (`perfil.unica`). Si hay varias
  candidatas gana la que parece clave por nombre (id, codigo, nombre de la
  tabla); si no, la primera. Confianza 0.98 con una sola candidata, 0.85 si
  hubo que elegir. Sin candidata: la primera columna con 0.3, para que la
  entidad exista y el wizard lo corrija.
- Clave foranea: >= 95 % de las FILAS no nulas de la columna tienen un
  valor que existe en la clave primaria destino (por filas y no por valores
  distintos: un solo id huerfano repetido no tiene que tirar abajo la
  relacion), mismo tipo de dato, destino unica (n:1). Confianza 0.7 por
  inclusion, +0.2 si el nombre es similar, +0.05 si la inclusion es total,
  -0.25 si el nombre no parece clave ni es similar. Un `cantidad` de 1 a 6
  tambien "incluye" en los ids de vendedores, asi que sin nombre a favor se
  exige ademas que no parezca una medida por nombre y que cubra al menos la
  mitad de las claves destino. Se descarta por debajo de 0.5, y si una
  columna tiene una relacion >= 0.9 se descartan sus otras candidatas sin
  nombre similar. Solo >= 0.9 entra sin confirmar, y entre las que superan
  0.9 no puede haber dos por la misma columna, dos entre el mismo par de
  entidades ni un ciclo: las sobrantes bajan a 0.89.
- Con varias candidatas a clave primaria: 0.95 si exactamente una parece
  clave por nombre, 0.85 si hubo que elegir sin ese apoyo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import duckdb

from app.ingesta.tipado import columna_sql
from app.modelo.esquema import (
    Campo,
    DimensionTiempo,
    Entidad,
    ExpresionAgregacion,
    ExtremoRelacion,
    Metrica,
    ModeloSemantico,
    Relacion,
)
from app.perfilado import PerfilColumna, PerfilFuente

UMBRAL_EFECTIVO = 0.9
CONFIANZA_MAXIMA_NO_EFECTIVA = 0.89
CONFIANZA_MINIMA_RELACION = 0.5

TOKENS_CLAVE = ("id", "cod", "codigo", "clave", "nro", "num", "key", "fk", "pk")
NOMBRES_MONTO = re.compile(r"(monto|importe|precio|total|neto|bruto|costo|valor|tarifa|saldo|pago|venta|ingreso|gasto|facturado|subtotal)")
NOMBRES_PORCENTAJE = re.compile(r"(porc|pct|porcentaje|tasa|ratio|percent)")
NOMBRES_CANTIDAD = re.compile(r"(cantidad|cant|unidades|cuotas|qty|stock|piezas|items|nro_|numero_de|dias|horas|edad|anios)")
NOMBRES_GEO = re.compile(r"(provincia|ciudad|pais|localidad|region|departamento|partido|municipio|barrio|domicilio|direccion)")
MAXIMO_DISTINTOS_CATEGORIA = 50
FRACCION_DISTINTOS_CATEGORIA = 0.05


@dataclass
class FuentePerfilada:
    nombre_tabla: str
    esquema: list[dict[str, Any]]  # [{nombre, tipo, ...}] como lo guarda la ingesta
    perfil: PerfilFuente


@dataclass
class _Candidata:
    desde_entidad: str
    desde_campo: str
    hacia_entidad: str
    hacia_campo: str
    confianza: float
    evidencia: dict[str, Any]


# ---------- Nombres ----------
def id_valido(nombre: str) -> str:
    """nombre_tabla ya viene normalizado por la ingesta; esto solo garantiza
    el patron de IdCorto por si acaso."""
    texto = re.sub(r"[^a-z0-9_]+", "_", nombre.lower()).strip("_")
    if not texto or not texto[0].isalpha():
        texto = f"t_{texto}" if texto else "tabla"
    return texto[:60]


def nombre_legible(identificador: str) -> str:
    """'medios_pago' -> 'Medios pago'. Claude lo mejora en el paso 11."""
    texto = identificador.replace("_", " ").strip()
    return texto[:1].upper() + texto[1:]


def _raices(nombre: str) -> set[str]:
    """Variantes del nombre sin prefijos/sufijos de clave ni plural, para
    comparar: 'id_vendedor' -> {'vendedor'}, 'vendedores' -> {'vendedores',
    'vendedore', 'vendedor'}, 'clientes' -> {'clientes', 'cliente', 'client'}.
    Se comparan todas contra todas y gana la mejor."""
    texto = nombre.lower()
    texto = re.sub(r"^(id|cod|codigo|clave|nro|num|fk|pk)_", "", texto)
    texto = re.sub(r"_(id|cod|codigo|clave|nro|num|fk|pk)$", "", texto)
    variantes = {texto}
    if texto.endswith("s") and len(texto) > 3:
        variantes.add(texto[:-1])
    if texto.endswith("es") and len(texto) > 4:
        variantes.add(texto[:-2])
    return variantes


def _misma_raiz(a: str, b: str) -> bool:
    return bool(_raices(a) & _raices(b))


def similitud_nombre(columna: str, tabla_destino: str, clave_destino: str) -> float:
    """Que tanto se parece el nombre de la columna al de la tabla destino o
    al de su clave. Ratio de difflib entre 0 y 1."""
    candidatos = [SequenceMatcher(None, columna.lower(), clave_destino.lower()).ratio()]
    for raiz_columna in _raices(columna):
        for otra in _raices(tabla_destino) | _raices(clave_destino):
            candidatos.append(SequenceMatcher(None, raiz_columna, otra).ratio())
            if len(raiz_columna) >= 4 and (raiz_columna in otra or otra in raiz_columna):
                candidatos.append(0.95)
    return max(candidatos)


def parece_clave(nombre: str) -> bool:
    partes = set(nombre.lower().split("_"))
    return any(token in partes for token in TOKENS_CLAVE) or nombre.lower().startswith("id")


def parece_medida(nombre: str) -> bool:
    nombre_bajo = nombre.lower()
    return bool(NOMBRES_CANTIDAD.search(nombre_bajo) or NOMBRES_MONTO.search(nombre_bajo) or NOMBRES_PORCENTAJE.search(nombre_bajo))


# ---------- Claves primarias ----------
def elegir_clave_primaria(fuente: FuentePerfilada) -> tuple[str, float, dict[str, Any]]:
    candidatas = fuente.perfil.candidatas_clave
    if not candidatas:
        primera = fuente.esquema[0]["nombre"]
        return primera, 0.3, {"motivo": "sin_candidata", "detalle": "ninguna columna es única y sin nulos"}
    if len(candidatas) == 1:
        return candidatas[0], 0.98, {"motivo": "unica_candidata"}
    con_nombre = [nombre for nombre in candidatas if parece_clave(nombre) or _misma_raiz(nombre, fuente.nombre_tabla)]
    if len(con_nombre) == 1:
        return con_nombre[0], 0.95, {"motivo": "varias_candidatas_una_con_nombre_de_clave", "candidatas": list(candidatas)}
    elegida = con_nombre[0] if con_nombre else candidatas[0]
    return elegida, 0.85, {"motivo": "varias_candidatas", "candidatas": list(candidatas)}


# ---------- Relaciones ----------
def _medir_inclusion(
    conexion: duckdb.DuckDBPyConnection, tabla_desde: str, columna_desde: str, tabla_hacia: str, columna_hacia: str
) -> tuple[int, int]:
    """(valores distintos de desde que existen en hacia, filas de desde cuyo
    valor no existe en hacia = huerfanos)."""
    desde, hacia = columna_sql(tabla_desde), columna_sql(tabla_hacia)
    c_desde, c_hacia = columna_sql(columna_desde), columna_sql(columna_hacia)
    incluidos = conexion.execute(
        f"SELECT count(DISTINCT a.{c_desde}) FROM {desde} a WHERE a.{c_desde} IN (SELECT b.{c_hacia} FROM {hacia} b WHERE b.{c_hacia} IS NOT NULL)"
    ).fetchone()[0]
    huerfanos = conexion.execute(
        f"SELECT count(*) FROM {desde} a WHERE a.{c_desde} IS NOT NULL AND a.{c_desde} NOT IN (SELECT b.{c_hacia} FROM {hacia} b WHERE b.{c_hacia} IS NOT NULL)"
    ).fetchone()[0]
    return incluidos, huerfanos


def _candidatas_relacion(
    conexion: duckdb.DuckDBPyConnection,
    fuentes: list[FuentePerfilada],
    claves: dict[str, str],
    umbral_inclusion: float,
    umbral_nombre: float,
) -> list[_Candidata]:
    tipos = {fuente.nombre_tabla: {columna["nombre"]: columna["tipo"] for columna in fuente.esquema} for fuente in fuentes}
    perfiles = {fuente.nombre_tabla: fuente.perfil for fuente in fuentes}
    candidatas: list[_Candidata] = []
    for origen in fuentes:
        for columna in origen.esquema:
            nombre, tipo = columna["nombre"], columna["tipo"]
            if tipo not in ("entero", "texto") or nombre == claves[origen.nombre_tabla]:
                continue
            perfil_columna = perfiles[origen.nombre_tabla].columna(nombre)
            if perfil_columna is None or perfil_columna.distintos == 0:
                continue
            for destino in fuentes:
                if destino.nombre_tabla == origen.nombre_tabla:
                    continue
                clave = claves[destino.nombre_tabla]
                perfil_clave = perfiles[destino.nombre_tabla].columna(clave)
                if tipos[destino.nombre_tabla][clave] != tipo or perfil_clave is None or not perfil_clave.unica:
                    continue
                incluidos, huerfanos = _medir_inclusion(conexion, origen.nombre_tabla, nombre, destino.nombre_tabla, clave)
                filas_no_nulas = perfiles[origen.nombre_tabla].filas - perfil_columna.nulos
                if filas_no_nulas <= 0:
                    continue
                inclusion = (filas_no_nulas - huerfanos) / filas_no_nulas
                if inclusion < umbral_inclusion:
                    continue
                cobertura = incluidos / max(perfil_clave.distintos, 1)
                similitud = similitud_nombre(nombre, destino.nombre_tabla, clave)
                similar = similitud >= umbral_nombre
                if not similar and not parece_clave(nombre) and (parece_medida(nombre) or cobertura < 0.5):
                    continue
                confianza = 0.7
                if similar:
                    confianza += 0.2
                if inclusion >= 1.0:
                    confianza += 0.05
                if not similar and not parece_clave(nombre):
                    confianza -= 0.25
                confianza = round(confianza, 2)
                if confianza < CONFIANZA_MINIMA_RELACION:
                    continue
                candidatas.append(
                    _Candidata(
                        origen.nombre_tabla,
                        nombre,
                        destino.nombre_tabla,
                        clave,
                        confianza,
                        {
                            "inclusion": round(inclusion, 4),
                            "inclusion_distintos": round(incluidos / perfil_columna.distintos, 4),
                            "cobertura": round(cobertura, 4),
                            "huerfanos": huerfanos,
                            "nombre_similar": similar,
                            "similitud": round(similitud, 2),
                            "distintos": perfil_columna.distintos,
                            "nulos": perfil_columna.nulos,
                        },
                    )
                )
    return candidatas


def _resolver_conflictos(candidatas: list[_Candidata]) -> list[_Candidata]:
    """Entre las que entrarian solas al modelo (>= 0.9): una por columna
    origen, una por par de entidades y sin ciclos. Las que pierden bajan a
    0.89: siguen propuestas, pero las decide el wizard."""
    ordenadas = sorted(candidatas, key=lambda c: (-c.confianza, c.desde_entidad, c.desde_campo, c.hacia_entidad))
    # Una columna con una relacion clara (>= 0.9) no necesita que le
    # propongan ademas las tablas donde "cabe" por casualidad
    claras = {(c.desde_entidad, c.desde_campo) for c in ordenadas if c.confianza >= UMBRAL_EFECTIVO}
    ordenadas = [
        c for c in ordenadas if c.confianza >= UMBRAL_EFECTIVO or c.evidencia["nombre_similar"] or (c.desde_entidad, c.desde_campo) not in claras
    ]
    padre: dict[str, str] = {}

    def raiz(entidad: str) -> str:
        padre.setdefault(entidad, entidad)
        while padre[entidad] != entidad:
            padre[entidad] = padre[padre[entidad]]
            entidad = padre[entidad]
        return entidad

    columnas_usadas: set[tuple[str, str]] = set()
    pares_usados: set[frozenset[str]] = set()
    for candidata in ordenadas:
        if candidata.confianza < UMBRAL_EFECTIVO:
            continue
        columna = (candidata.desde_entidad, candidata.desde_campo)
        par = frozenset({candidata.desde_entidad, candidata.hacia_entidad})
        motivo = None
        if columna in columnas_usadas:
            motivo = "otra_relacion_mas_confiable_para_la_columna"
        elif par in pares_usados:
            motivo = "ya_hay_relacion_entre_las_entidades"
        elif raiz(candidata.desde_entidad) == raiz(candidata.hacia_entidad):
            motivo = "cerraria_un_ciclo"
        if motivo:
            candidata.confianza = CONFIANZA_MAXIMA_NO_EFECTIVA
            candidata.evidencia["bajada_por"] = motivo
            continue
        columnas_usadas.add(columna)
        pares_usados.add(par)
        padre[raiz(candidata.desde_entidad)] = raiz(candidata.hacia_entidad)
    return ordenadas


# ---------- Tipos semanticos ----------
def tipo_semantico_de(
    nombre: str, tipo: str, perfil: PerfilColumna, filas: int, *, es_pk: bool, confianza_fk: float | None
) -> tuple[str, float, dict[str, Any]]:
    """(tipo_semantico, confianza, evidencia). Lo dudoso queda en 0.6 para
    que Claude opine en el paso 11."""
    if es_pk:
        return "identificador", 0.98, {"motivo": "clave_primaria"}
    if confianza_fk is not None:
        return "clave_foranea", confianza_fk, {"motivo": "relacion_propuesta"}
    if tipo in ("fecha", "fecha_hora"):
        return "fecha", 0.99, {"motivo": "tipo_de_dato"}
    if tipo == "booleano":
        return "booleano", 0.99, {"motivo": "tipo_de_dato"}
    nombre_bajo = nombre.lower()
    if tipo == "decimal":
        if NOMBRES_PORCENTAJE.search(nombre_bajo):
            return "porcentaje", 0.85, {"motivo": "nombre"}
        if NOMBRES_MONTO.search(nombre_bajo):
            return "monto", 0.9, {"motivo": "nombre"}
        if perfil.minimo is not None and perfil.maximo is not None and 0 <= perfil.minimo and perfil.maximo <= 1:
            return "porcentaje", 0.6, {"motivo": "rango_0_1"}
        return "monto", 0.6, {"motivo": "decimal_sin_nombre_conocido"}
    if tipo == "entero":
        if NOMBRES_CANTIDAD.search(nombre_bajo):
            return "cantidad", 0.9, {"motivo": "nombre"}
        if NOMBRES_MONTO.search(nombre_bajo):
            return "monto", 0.8, {"motivo": "nombre"}
        if perfil.distintos <= MAXIMO_DISTINTOS_CATEGORIA and not parece_clave(nombre) and perfil.distintos < max(filas, 1) * FRACCION_DISTINTOS_CATEGORIA:
            return "categoria", 0.6, {"motivo": "entero_con_pocos_valores"}
        return "cantidad", 0.6, {"motivo": "entero_sin_nombre_conocido"}
    # texto
    if perfil.patron in ("email", "url"):
        return "texto_libre", 0.9, {"motivo": f"patron_{perfil.patron}"}
    if NOMBRES_GEO.search(nombre_bajo):
        return "geo", 0.85, {"motivo": "nombre"}
    if perfil.patron in ("codigo", "numerico") and not perfil.unica:
        return "categoria", 0.7, {"motivo": f"patron_{perfil.patron}"}
    if perfil.distintos <= MAXIMO_DISTINTOS_CATEGORIA or perfil.distintos <= max(filas, 1) * FRACCION_DISTINTOS_CATEGORIA:
        return "categoria", 0.9, {"motivo": "pocos_valores_distintos", "distintos": perfil.distintos}
    if perfil.unica:
        return "categoria", 0.6, {"motivo": "texto_unico"}
    return "texto_libre", 0.7, {"motivo": "muchos_valores_distintos", "distintos": perfil.distintos}


# ---------- Modelo ----------
def proponer_modelo(
    conexion: duckdb.DuckDBPyConnection,
    fuentes: list[FuentePerfilada],
    *,
    umbral_inclusion: float = 0.95,
    umbral_nombre: float = 0.8,
) -> ModeloSemantico:
    """Un modelo semantico propuesto entero desde los perfiles. Todo con
    origen `heuristica` y estado `propuesta`, salvo la clave primaria de cada
    entidad, que va confirmada (una entidad no existe sin clave)."""
    if not fuentes:
        raise ValueError("proponer_modelo necesita al menos una fuente")
    fuentes = sorted(fuentes, key=lambda fuente: fuente.nombre_tabla)
    ids = {fuente.nombre_tabla: id_valido(fuente.nombre_tabla) for fuente in fuentes}

    claves: dict[str, str] = {}
    evidencia_clave: dict[str, tuple[float, dict[str, Any]]] = {}
    for fuente in fuentes:
        clave, confianza, evidencia = elegir_clave_primaria(fuente)
        claves[fuente.nombre_tabla] = clave
        evidencia_clave[fuente.nombre_tabla] = (confianza, evidencia)

    candidatas = _resolver_conflictos(_candidatas_relacion(conexion, fuentes, claves, umbral_inclusion, umbral_nombre))
    fk_por_columna: dict[tuple[str, str], float] = {}
    for candidata in candidatas:
        columna = (candidata.desde_entidad, candidata.desde_campo)
        fk_por_columna[columna] = max(fk_por_columna.get(columna, 0.0), candidata.confianza)
    con_fk_efectiva = {c.desde_entidad for c in candidatas if c.confianza >= UMBRAL_EFECTIVO}

    entidades: list[Entidad] = []
    for fuente in fuentes:
        clave = claves[fuente.nombre_tabla]
        confianza_clave, evidencia = evidencia_clave[fuente.nombre_tabla]
        campos: list[Campo] = []
        for columna in fuente.esquema:
            nombre, tipo = columna["nombre"], columna["tipo"]
            perfil_columna = fuente.perfil.columna(nombre) or PerfilColumna(nombre=nombre, tipo=tipo, nulos=0, distintos=0, unica=False)
            es_pk = nombre == clave
            tipo_semantico, confianza, evidencia_campo = tipo_semantico_de(
                nombre, tipo, perfil_columna, fuente.perfil.filas, es_pk=es_pk, confianza_fk=fk_por_columna.get((fuente.nombre_tabla, nombre))
            )
            if es_pk:
                confianza, evidencia_campo = confianza_clave, {**evidencia_campo, **evidencia}
            evidencia_campo.update({"nulos": perfil_columna.nulos, "distintos": perfil_columna.distintos})
            campos.append(
                Campo(
                    id=id_valido(nombre),
                    columna_origen=nombre,
                    nombre=nombre_legible(nombre),
                    tipo_dato=tipo,
                    tipo_semantico=tipo_semantico,
                    confianza=confianza,
                    origen="heuristica",
                    estado="confirmada" if es_pk else "propuesta",
                    evidencia=evidencia_campo,
                )
            )
        entidades.append(
            Entidad(
                id=ids[fuente.nombre_tabla],
                nombre=nombre_legible(fuente.nombre_tabla),
                fuente=fuente.nombre_tabla,
                tipo="hechos" if fuente.nombre_tabla in con_fk_efectiva else "dimension",
                clave_primaria=[id_valido(clave)],
                campos=campos,
            )
        )

    relaciones: list[Relacion] = []
    ids_relacion: set[str] = set()
    for candidata in candidatas:
        base = id_valido(f"{ids[candidata.desde_entidad]}_{candidata.desde_campo}")
        identificador = base
        if identificador in ids_relacion:
            identificador = id_valido(f"{base}_{ids[candidata.hacia_entidad]}")
        ids_relacion.add(identificador)
        relaciones.append(
            Relacion(
                id=identificador,
                desde=ExtremoRelacion(entidad=ids[candidata.desde_entidad], campo=id_valido(candidata.desde_campo)),
                hacia=ExtremoRelacion(entidad=ids[candidata.hacia_entidad], campo=id_valido(candidata.hacia_campo)),
                cardinalidad="n:1",
                confianza=candidata.confianza,
                evidencia=candidata.evidencia,
                estado="propuesta",
            )
        )

    metricas: list[Metrica] = []
    dimensiones: list[DimensionTiempo] = []
    for entidad in entidades:
        if entidad.tipo != "hechos":
            continue
        clave = entidad.clave_primaria[0]
        metricas.append(
            Metrica(
                id=id_valido(f"cantidad_{entidad.id}"),
                nombre=f"Cantidad de {entidad.nombre.lower()}",
                expresion=ExpresionAgregacion(agregacion="conteo", campo=f"{entidad.id}.{clave}"),
                formato="entero",
                confianza=0.9,
                origen="heuristica",
                estado="propuesta",
            )
        )
        for campo in entidad.campos:
            if campo.tipo_semantico == "monto" and not re.search(r"(precio|unitario|tarifa|lista)", campo.id):
                metricas.append(
                    Metrica(
                        id=id_valido(f"total_{campo.id}"),
                        nombre=f"Total {campo.nombre.lower()}",
                        expresion=ExpresionAgregacion(agregacion="suma", campo=f"{entidad.id}.{campo.id}"),
                        formato="moneda",
                        confianza=min(0.85, campo.confianza),
                        origen="heuristica",
                        estado="propuesta",
                    )
                )
            elif campo.tipo_semantico == "cantidad" and campo.confianza >= 0.9:
                metricas.append(
                    Metrica(
                        id=id_valido(f"total_{campo.id}"),
                        nombre=f"Total {campo.nombre.lower()}",
                        expresion=ExpresionAgregacion(agregacion="suma", campo=f"{entidad.id}.{campo.id}"),
                        formato="entero",
                        confianza=0.7,
                        origen="heuristica",
                        estado="propuesta",
                    )
                )
            if campo.tipo_dato in ("fecha", "fecha_hora"):
                dimensiones.append(DimensionTiempo(campo=f"{entidad.id}.{campo.id}"))
    # ids de metrica repetidos (dos entidades con "importe"): sufijo con la entidad
    vistos: set[str] = set()
    for metrica in metricas:
        if metrica.id in vistos:
            entidad_id = metrica.expresion.campo.split(".")[0]  # type: ignore[union-attr]
            metrica.id = id_valido(f"{metrica.id}_{entidad_id}")
        vistos.add(metrica.id)

    return ModeloSemantico(entidades=entidades, relaciones=relaciones, metricas=metricas, dimensiones_tiempo=dimensiones)
