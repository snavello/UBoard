"""Compilador: ConsultaSemantica + ModeloSemantico -> SQL de DuckDB parametrizado.

Es el UNICO lugar donde el modelo se convierte en SQL. Reglas:

- Cada entidad es una vista DuckDB (`Entidad.fuente`) con alias = id de la
  entidad. Los campos se leen por `columna_origen`.
- El camino entre dos entidades es unico porque el grafo de relaciones del
  modelo efectivo es un arbol (lo garantiza la validacion). Un paso es
  "seguro" si va del lado "muchos" al lado "uno" (n:1 desde->hacia): no
  multiplica filas.
- Cada metrica se agrega en una subconsulta que parte de SU entidad y solo
  hace LEFT JOIN por pasos seguros hacia las entidades de las dimensiones;
  si una dimension exige un paso inseguro, la combinacion multiplicaria filas
  y se rechaza (E-CONS-04). LEFT JOIN y no INNER: las filas huerfanas no
  desaparecen, quedan en el grupo NULL, y los totales cierran con los KPIs.
- Un filtro sobre una entidad alcanzable solo por un paso inseguro se aplica
  como semi-join (EXISTS): "ventas que tienen algun pago en efectivo" es una
  pregunta bien definida aunque "ventas por medio de pago" no lo sea.
- Con metricas de varias entidades, cada subconsulta va en un CTE y se pegan
  por las dimensiones (IS NOT DISTINCT FROM, para que NULL case con NULL). Con
  `entidad_base` (explorador) la lista de filas sale de esa entidad y las
  metricas se le pegan con LEFT JOIN: aparecen todas, con metricas NULL.
- Los cocientes se calculan afuera: numerador / NULLIF(denominador, 0). Las
  formulas (suma, resta, multiplicacion, division entre metricas y
  constantes) se arman igual, recorriendo el arbol; cada division anidada
  lleva su propio NULLIF.
- Los valores de los filtros van SIEMPRE como parametros (?), con CAST al tipo
  del campo.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app.consultas.esquema import ConsultaSemantica, DimensionConsulta, FiltroConsulta
from app.modelo.esquema import (
    TIPOS_TEMPORALES,
    Campo,
    Entidad,
    ExpresionAgregacion,
    ExpresionCociente,
    ExpresionFormula,
    Metrica,
    ModeloSemantico,
    Operando,
    Relacion,
)
from app.nucleo.errores import ErrorApp

OPERADOR_FORMULA_SQL = {"suma": "+", "resta": "-", "multiplicacion": "*", "division": "/"}
AGREGACION_SQL = {
    "suma": "SUM({})",
    "conteo": "COUNT({})",
    "conteo_distinto": "COUNT(DISTINCT {})",
    "promedio": "AVG({})",
    "minimo": "MIN({})",
    "maximo": "MAX({})",
}
GRANULARIDAD_SQL = {
    "dia": "CAST({} AS DATE)",
    "semana": "CAST(date_trunc('week', {}) AS DATE)",
    "mes": "CAST(date_trunc('month', {}) AS DATE)",
    "trimestre": "CAST(date_trunc('quarter', {}) AS DATE)",
    "anio": "CAST(date_trunc('year', {}) AS DATE)",
}
CAST_PARAMETRO = {"fecha": "DATE", "fecha_hora": "TIMESTAMP", "entero": "BIGINT", "decimal": "DOUBLE", "booleano": "BOOLEAN"}
OPERADORES_ESCALARES = {"igual": "=", "distinto": "<>", "mayor": ">", "mayor_igual": ">=", "menor": "<", "menor_igual": "<="}


def identificador(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


@dataclass
class ColumnaResultado:
    nombre: str
    tipo: str
    clase: str  # "dimension" | "metrica"
    granularidad: str | None = None


@dataclass
class SQLCompilado:
    sql: str
    parametros: list[Any]
    columnas: list[ColumnaResultado]


@dataclass
class _Paso:
    """Un salto entre dos entidades por una relacion."""

    desde: str
    hasta: str
    relacion: Relacion
    seguro: bool


@dataclass
class _Dimension:
    entidad: Entidad
    campo: Campo
    granularidad: str | None
    alias: str

    @property
    def tipo(self) -> str:
        return "fecha" if self.granularidad else self.campo.tipo_dato


@dataclass
class _Agregacion:
    metrica: Metrica
    entidad: Entidad
    campo: Campo
    expresion: ExpresionAgregacion


@dataclass
class _Fragmento:
    sql: str
    parametros: list[Any] = field(default_factory=list)


class Compilador:
    def __init__(self, modelo: ModeloSemantico):
        """`modelo` tiene que ser el modelo EFECTIVO (ver modelo.validacion)."""
        self.modelo = modelo
        self.grafo: dict[str, list[_Paso]] = {entidad.id: [] for entidad in modelo.entidades}
        for relacion in modelo.relaciones:
            ida_segura = relacion.cardinalidad in ("n:1", "1:1")
            vuelta_segura = relacion.cardinalidad in ("1:n", "1:1")
            self.grafo[relacion.desde.entidad].append(_Paso(relacion.desde.entidad, relacion.hacia.entidad, relacion, ida_segura))
            self.grafo[relacion.hacia.entidad].append(_Paso(relacion.hacia.entidad, relacion.desde.entidad, relacion, vuelta_segura))

    # ---------- Resolucion ----------
    def _entidad(self, entidad_id: str) -> Entidad:
        entidad = self.modelo.entidad(entidad_id)
        if entidad is None:
            raise ErrorApp("E-CONS-01", f"entidad: {entidad_id!r}")
        return entidad

    def _campo(self, referencia: str) -> tuple[Entidad, Campo]:
        resuelto = self.modelo.resolver_campo(referencia)
        if resuelto is None:
            raise ErrorApp("E-CONS-01", f"campo: {referencia!r}")
        return resuelto

    def _metrica(self, metrica_id: str) -> Metrica:
        metrica = self.modelo.metrica(metrica_id)
        if metrica is None:
            raise ErrorApp("E-CONS-01", f"metrica: {metrica_id!r}")
        return metrica

    def _agregacion(self, metrica: Metrica) -> _Agregacion:
        if not isinstance(metrica.expresion, ExpresionAgregacion):
            raise ErrorApp("E-CONS-01", f"la metrica {metrica.id!r} no es una agregacion")
        entidad, campo = self._campo(metrica.expresion.campo)
        return _Agregacion(metrica, entidad, campo, metrica.expresion)

    def _recolectar_agregaciones(self, operando: Operando, agregaciones: dict[str, _Agregacion]) -> None:
        """Baja un arbol de formula hasta sus metricas de agregacion (las que
        de verdad hay que calcular en una subconsulta): una formula puede
        referenciar otra formula por id, y esa a su vez otra, sin limite."""
        if isinstance(operando, ExpresionFormula):
            self._recolectar_agregaciones(operando.izquierda, agregaciones)
            self._recolectar_agregaciones(operando.derecha, agregaciones)
            return
        if isinstance(operando, (int, float)):
            return
        metrica = self._metrica(operando)
        if isinstance(metrica.expresion, ExpresionAgregacion):
            agregaciones.setdefault(metrica.id, self._agregacion(metrica))
        elif isinstance(metrica.expresion, ExpresionFormula):
            self._recolectar_agregaciones(metrica.expresion.izquierda, agregaciones)
            self._recolectar_agregaciones(metrica.expresion.derecha, agregaciones)
        else:
            raise ErrorApp("E-CONS-01", f"la metrica {metrica.id!r} no se puede usar en una formula")

    def _dimension(self, pedida: DimensionConsulta) -> _Dimension:
        entidad, campo = self._campo(pedida.campo)
        if pedida.granularidad is not None:
            if campo.tipo_dato not in TIPOS_TEMPORALES:
                raise ErrorApp("E-CONS-05", f"{pedida.campo} es {campo.tipo_dato}")
            declarada = next((d for d in self.modelo.dimensiones_tiempo if d.campo == pedida.campo), None)
            if declarada is None or pedida.granularidad not in declarada.granularidades:
                raise ErrorApp("E-CONS-05", f"{pedida.campo} no declara la granularidad {pedida.granularidad!r}")
        return _Dimension(entidad, campo, pedida.granularidad, pedida.alias or pedida.campo)

    def _camino(self, origen: str, destino: str) -> list[_Paso] | None:
        """BFS en el arbol de relaciones. None si no hay camino."""
        if origen == destino:
            return []
        anteriores: dict[str, _Paso | None] = {origen: None}
        cola = deque([origen])
        while cola:
            actual = cola.popleft()
            for paso in self.grafo.get(actual, []):
                if paso.hasta in anteriores:
                    continue
                anteriores[paso.hasta] = paso
                if paso.hasta == destino:
                    camino = []
                    nodo = destino
                    while anteriores[nodo] is not None:
                        paso_previo = anteriores[nodo]
                        camino.append(paso_previo)
                        nodo = paso_previo.desde
                    return list(reversed(camino))
                cola.append(paso.hasta)
        return None

    # ---------- Compilacion ----------
    def compilar(self, consulta: ConsultaSemantica) -> SQLCompilado:
        if consulta.entidad_base is not None:
            self._entidad(consulta.entidad_base)  # que exista, aunque sin dimensiones no se use
        dimensiones = [self._dimension(pedida) for pedida in consulta.dimensiones]
        alias_vistos = [dimension.alias for dimension in dimensiones]
        if len(set(alias_vistos)) != len(alias_vistos):
            raise ErrorApp("E-CONS-06", "dos dimensiones con el mismo alias")

        metricas = [self._metrica(metrica_id) for metrica_id in consulta.metricas]
        # Agregaciones necesarias: las pedidas mas las que componen cocientes y formulas
        agregaciones: dict[str, _Agregacion] = {}
        for metrica in metricas:
            if isinstance(metrica.expresion, ExpresionCociente):
                for parte in (metrica.expresion.numerador, metrica.expresion.denominador):
                    agregaciones.setdefault(parte, self._agregacion(self._metrica(parte)))
            elif isinstance(metrica.expresion, ExpresionFormula):
                self._recolectar_agregaciones(metrica.expresion, agregaciones)
            else:
                agregaciones.setdefault(metrica.id, self._agregacion(metrica))

        # Una subconsulta por entidad de metrica, en orden de aparicion
        grupos: dict[str, list[_Agregacion]] = {}
        for agregacion in agregaciones.values():
            grupos.setdefault(agregacion.entidad.id, []).append(agregacion)

        filtros = [(self._campo(filtro.campo), filtro) for filtro in consulta.filtros]

        base_filas: str | None = None
        if dimensiones:
            if consulta.entidad_base is not None:
                base_filas = self._entidad(consulta.entidad_base).id
            elif not grupos:
                base_filas = dimensiones[0].entidad.id
        elif not grupos:
            raise ErrorApp("E-CONS-07", "sin metricas ni dimensiones")

        ctes: list[tuple[str, _Fragmento]] = []
        alias_de_agregacion: dict[str, str] = {}
        for indice, (entidad_id, grupo) in enumerate(grupos.items()):
            alias_cte = f"m{indice}"
            ctes.append((alias_cte, self._subconsulta(self._entidad(entidad_id), dimensiones, filtros, grupo)))
            for agregacion in grupo:
                alias_de_agregacion[agregacion.metrica.id] = alias_cte
        if base_filas is not None:
            ctes.append(("d", self._subconsulta(self._entidad(base_filas), dimensiones, filtros, [])))

        return self._ensamblar(consulta, dimensiones, metricas, ctes, alias_de_agregacion, base_filas is not None)

    def _subconsulta(
        self,
        base: Entidad,
        dimensiones: list[_Dimension],
        filtros: list[tuple[tuple[Entidad, Campo], FiltroConsulta]],
        agregaciones: list[_Agregacion],
    ) -> _Fragmento:
        """SELECT dims, agregaciones FROM base LEFT JOIN ... WHERE ... GROUP BY dims."""
        joins: list[_Paso] = []
        unidas = {base.id}

        def unir_camino(pasos: list[_Paso]) -> None:
            for paso in pasos:
                if paso.hasta not in unidas:
                    joins.append(paso)
                    unidas.add(paso.hasta)

        for dimension in dimensiones:
            camino = self._camino(base.id, dimension.entidad.id)
            if camino is None:
                raise ErrorApp("E-CONS-02", f"{base.id} y {dimension.entidad.id}")
            inseguro = next((paso for paso in camino if not paso.seguro), None)
            if inseguro is not None:
                que = ", ".join(a.metrica.id for a in agregaciones) or f"las filas de {base.id}"
                raise ErrorApp(
                    "E-CONS-04",
                    f"{que} ({base.id}) por {dimension.alias}: el paso {inseguro.desde} -> {inseguro.hasta} multiplica filas",
                )
            unir_camino(camino)

        condiciones: list[_Fragmento] = []
        for (entidad_filtro, campo_filtro), filtro in filtros:
            camino = self._camino(base.id, entidad_filtro.id)
            if camino is None:
                raise ErrorApp("E-CONS-02", f"{base.id} y {entidad_filtro.id}")
            posicion_insegura = next((i for i, paso in enumerate(camino) if not paso.seguro), None)
            if posicion_insegura is None:
                unir_camino(camino)
                condiciones.append(self._predicado(entidad_filtro.id, campo_filtro, filtro))
            else:
                unir_camino(camino[:posicion_insegura])
                condiciones.append(self._existe(camino[posicion_insegura:], entidad_filtro, campo_filtro, filtro))

        seleccion = [f"{self._expresion_dimension(dimension)} AS {identificador(dimension.alias)}" for dimension in dimensiones]
        for agregacion in agregaciones:
            columna = f"{identificador(agregacion.entidad.id)}.{identificador(agregacion.campo.columna_origen)}"
            seleccion.append(f"{AGREGACION_SQL[agregacion.expresion.agregacion].format(columna)} AS {identificador(agregacion.metrica.id)}")

        sql = f"SELECT {', '.join(seleccion)} FROM {identificador(base.fuente)} AS {identificador(base.id)}"
        for paso in joins:
            hasta = self._entidad(paso.hasta)
            sql += f" LEFT JOIN {identificador(hasta.fuente)} AS {identificador(hasta.id)} ON {self._condicion(paso.relacion, {})}"
        parametros: list[Any] = []
        if condiciones:
            sql += " WHERE " + " AND ".join(condicion.sql for condicion in condiciones)
            for condicion in condiciones:
                parametros.extend(condicion.parametros)
        if dimensiones:
            sql += " GROUP BY " + ", ".join(str(i + 1) for i in range(len(dimensiones)))
        return _Fragmento(sql, parametros)

    def _existe(
        self, pasos: list[_Paso], entidad_filtro: Entidad, campo_filtro: Campo, filtro: FiltroConsulta
    ) -> _Fragmento:
        """Semi-join desde la primera entidad del lado 'muchos' hasta la del
        filtro. Adentro los alias llevan sufijo __f para no pisar los de afuera."""
        primero = pasos[0]
        alias_interno = {paso.hasta: f"{paso.hasta}__f" for paso in pasos}
        entidad_primera = self._entidad(primero.hasta)
        sql = f"EXISTS (SELECT 1 FROM {identificador(entidad_primera.fuente)} AS {identificador(alias_interno[primero.hasta])}"
        for paso in pasos[1:]:
            hasta = self._entidad(paso.hasta)
            sql += f" JOIN {identificador(hasta.fuente)} AS {identificador(alias_interno[paso.hasta])} ON {self._condicion(paso.relacion, alias_interno)}"
        predicado = self._predicado(alias_interno[entidad_filtro.id], campo_filtro, filtro)
        sql += f" WHERE {self._condicion(primero.relacion, alias_interno)} AND {predicado.sql})"
        return _Fragmento(sql, predicado.parametros)

    def _condicion(self, relacion: Relacion, alias_de: dict[str, str]) -> str:
        """desde.campo = hacia.campo, con los alias externos salvo los que se indiquen."""
        entidad_desde, campo_desde = self._campo(relacion.desde.referencia)
        entidad_hacia, campo_hacia = self._campo(relacion.hacia.referencia)
        alias_desde = alias_de.get(entidad_desde.id, entidad_desde.id)
        alias_hacia = alias_de.get(entidad_hacia.id, entidad_hacia.id)
        return (
            f"{identificador(alias_desde)}.{identificador(campo_desde.columna_origen)} = "
            f"{identificador(alias_hacia)}.{identificador(campo_hacia.columna_origen)}"
        )

    def _expresion_dimension(self, dimension: _Dimension) -> str:
        columna = f"{identificador(dimension.entidad.id)}.{identificador(dimension.campo.columna_origen)}"
        if dimension.granularidad:
            return GRANULARIDAD_SQL[dimension.granularidad].format(columna)
        return columna

    def _predicado(self, alias: str, campo: Campo, filtro: FiltroConsulta) -> _Fragmento:
        columna = f"{identificador(alias)}.{identificador(campo.columna_origen)}"
        tipo_cast = CAST_PARAMETRO.get(campo.tipo_dato)
        marcador = f"CAST(? AS {tipo_cast})" if tipo_cast else "?"
        valor = filtro.valor
        operador = filtro.operador

        if operador in ("es_nulo", "no_es_nulo"):
            return _Fragmento(f"{columna} IS {'NOT ' if operador == 'no_es_nulo' else ''}NULL")
        if operador in OPERADORES_ESCALARES:
            if valor is None or isinstance(valor, (list, dict)):
                raise ErrorApp("E-CONS-06", f"{filtro.campo} {operador} necesita un valor simple")
            return _Fragmento(f"{columna} {OPERADORES_ESCALARES[operador]} {marcador}", [valor])
        if operador == "en":
            if not isinstance(valor, list) or not valor:
                raise ErrorApp("E-CONS-06", f"{filtro.campo} en: necesita una lista con al menos un valor")
            return _Fragmento(f"{columna} IN ({', '.join([marcador] * len(valor))})", list(valor))
        if operador == "entre":
            if not isinstance(valor, list) or len(valor) != 2 or all(extremo is None for extremo in valor):
                raise ErrorApp("E-CONS-06", f"{filtro.campo} entre: necesita [desde, hasta]")
            desde, hasta = valor
            if desde is None:
                return _Fragmento(f"{columna} <= {marcador}", [hasta])
            if hasta is None:
                return _Fragmento(f"{columna} >= {marcador}", [desde])
            return _Fragmento(f"{columna} BETWEEN {marcador} AND {marcador}", [desde, hasta])
        if operador == "contiene":
            if not isinstance(valor, str) or not valor:
                raise ErrorApp("E-CONS-06", f"{filtro.campo} contiene: necesita un texto")
            return _Fragmento(f"CAST({columna} AS VARCHAR) ILIKE ?", [f"%{valor}%"])
        raise ErrorApp("E-CONS-06", f"operador desconocido {operador!r}")

    def _ensamblar(
        self,
        consulta: ConsultaSemantica,
        dimensiones: list[_Dimension],
        metricas: list[Metrica],
        ctes: list[tuple[str, _Fragmento]],
        alias_de_agregacion: dict[str, str],
        con_base_de_filas: bool,
    ) -> SQLCompilado:
        parametros: list[Any] = []
        sql = "WITH " + ", ".join(f"{alias} AS ({fragmento.sql})" for alias, fragmento in ctes)
        for _, fragmento in ctes:
            parametros.extend(fragmento.parametros)
        alias_metricas = [alias for alias, _ in ctes if alias != "d"]

        # De donde salen las dimensiones y como se pegan las subconsultas
        if not dimensiones:
            origen_dims = None
            desde = " CROSS JOIN ".join(alias_metricas)
        elif con_base_de_filas or len(alias_metricas) == 1:
            origen_dims = "d" if con_base_de_filas else alias_metricas[0]
            desde = origen_dims
            for alias in alias_metricas:
                if alias != origen_dims:
                    desde += f" LEFT JOIN {alias} ON " + " AND ".join(
                        f"{origen_dims}.{identificador(d.alias)} IS NOT DISTINCT FROM {alias}.{identificador(d.alias)}" for d in dimensiones
                    )
        else:
            columnas_dims = ", ".join(identificador(d.alias) for d in dimensiones)
            union = " UNION ".join(f"SELECT {columnas_dims} FROM {alias}" for alias in alias_metricas)
            sql += f", d AS ({union})"
            origen_dims = "d"
            desde = "d"
            for alias in alias_metricas:
                desde += f" LEFT JOIN {alias} ON " + " AND ".join(
                    f"d.{identificador(d.alias)} IS NOT DISTINCT FROM {alias}.{identificador(d.alias)}" for d in dimensiones
                )

        seleccion = [f"{origen_dims}.{identificador(d.alias)} AS {identificador(d.alias)}" for d in dimensiones]
        columnas = [ColumnaResultado(d.alias, d.tipo, "dimension", d.granularidad) for d in dimensiones]
        for metrica in metricas:
            if isinstance(metrica.expresion, ExpresionCociente):
                numerador = f"{alias_de_agregacion[metrica.expresion.numerador]}.{identificador(metrica.expresion.numerador)}"
                denominador = f"{alias_de_agregacion[metrica.expresion.denominador]}.{identificador(metrica.expresion.denominador)}"
                seleccion.append(f"CAST({numerador} AS DOUBLE) / NULLIF({denominador}, 0) AS {identificador(metrica.id)}")
            elif isinstance(metrica.expresion, ExpresionFormula):
                seleccion.append(f"{self._renderizar_formula(metrica.expresion, alias_de_agregacion)} AS {identificador(metrica.id)}")
            else:
                seleccion.append(f"{alias_de_agregacion[metrica.id]}.{identificador(metrica.id)} AS {identificador(metrica.id)}")
            columnas.append(ColumnaResultado(metrica.id, self._tipo_metrica(metrica), "metrica"))

        sql += f" SELECT {', '.join(seleccion)} FROM {desde}"

        nombres_salida = {columna.nombre for columna in columnas}
        orden = []
        for pedido in consulta.orden:
            if pedido.por not in nombres_salida:
                raise ErrorApp("E-CONS-08", f"orden por {pedido.por!r}")
            orden.append(f"{identificador(pedido.por)} {pedido.direccion.upper()} NULLS LAST")
        if not orden and dimensiones:
            orden = [f"{identificador(d.alias)} ASC NULLS LAST" for d in dimensiones]
        if orden:
            sql += " ORDER BY " + ", ".join(orden)
        if consulta.limite is not None:
            sql += f" LIMIT {consulta.limite}"
        if consulta.desplazamiento:
            sql += f" OFFSET {consulta.desplazamiento}"
        return SQLCompilado(sql, parametros, columnas)

    def _renderizar_formula(self, expresion: ExpresionFormula, alias_de_agregacion: dict[str, str]) -> str:
        izquierda = self._renderizar_operando(expresion.izquierda, alias_de_agregacion)
        derecha = self._renderizar_operando(expresion.derecha, alias_de_agregacion)
        if expresion.operacion == "division":
            return f"({izquierda} / NULLIF({derecha}, 0))"
        return f"({izquierda} {OPERADOR_FORMULA_SQL[expresion.operacion]} {derecha})"

    def _renderizar_operando(self, operando: Operando, alias_de_agregacion: dict[str, str]) -> str:
        if isinstance(operando, ExpresionFormula):
            return self._renderizar_formula(operando, alias_de_agregacion)
        if isinstance(operando, (int, float)):
            return repr(float(operando))
        metrica = self._metrica(operando)
        if isinstance(metrica.expresion, ExpresionAgregacion):
            alias_cte = alias_de_agregacion[metrica.id]
            return f"CAST({alias_cte}.{identificador(metrica.id)} AS DOUBLE)"
        if isinstance(metrica.expresion, ExpresionFormula):
            return self._renderizar_formula(metrica.expresion, alias_de_agregacion)
        raise ErrorApp("E-CONS-01", f"la metrica {metrica.id!r} no se puede usar en una formula")

    def _tipo_metrica(self, metrica: Metrica) -> str:
        expresion = metrica.expresion
        if isinstance(expresion, (ExpresionCociente, ExpresionFormula)):
            return "decimal"
        _, campo = self._campo(expresion.campo)
        if expresion.agregacion in ("conteo", "conteo_distinto"):
            return "entero"
        if expresion.agregacion == "promedio":
            return "decimal"
        return campo.tipo_dato


def compilar(modelo: ModeloSemantico, consulta: ConsultaSemantica) -> SQLCompilado:
    return Compilador(modelo).compilar(consulta)
