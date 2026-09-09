"""Lo semantico se lo pedimos a Claude: nombres legibles, tipo de entidad,
sinonimos, tipos semanticos dudosos y la lista de metricas. Claves y
relaciones NO: esas ya las decidieron los datos (heuristicas.py).

Flujo: `armar_pedido(modelo, perfiles, muestras)` -> prompt compacto;
`consultar_semantica(cliente, pedido)` -> RespuestaSemantica validada contra
el modelo (reintenta una vez con el error como feedback, §10);
`aplicar_semantica(modelo, respuesta)` -> modelo con lo de Claude marcado
`origen: llm`. Si algo falla, el modelo heuristico sigue valiendo.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.inferencia.llm import ClienteLLM, RespuestaLLM
from app.modelo.esquema import (
    TIPOS_NUMERICOS,
    Agregacion,
    ExpresionAgregacion,
    ExpresionCociente,
    Formato,
    Metrica,
    ModeloSemantico,
    TipoEntidad,
    TipoSemantico,
)
from app.nucleo.errores import ErrorApp
from app.perfilado import PerfilFuente

CONFIANZA_LLM = 0.8
MAX_TOKENS_SEMANTICA = 6000
UMBRAL_DUDOSO = 0.9  # tipos semanticos con menos confianza: Claude puede cambiarlos

SISTEMA = """Sos parte de UBoard, un BI para pymes argentinas. Recibís el modelo de datos que
armó un analizador automático (entidades, campos con tipo de dato y tipo semántico
tentativo, relaciones ya decididas, estadísticas por columna y unas filas de muestra)
y devolvés SOLO lo semántico, en castellano rioplatense, con nombres cortos y claros
como los usaría una persona de negocio ("Total ventas", "Ticket promedio", "Vendedor").
Reglas:
- No inventes campos, entidades ni relaciones: usá exactamente los ids que recibís.
- Mayúscula solo al inicio del nombre ("Medios de pago", no "Medios De Pago").
- Entidad de hechos = registra eventos o transacciones (ventas, pagos, movimientos);
  dimensión = catálogo o maestro (productos, vendedores, sucursales).
- Tipo semántico: cambialo solo si el tentativo está mal; los valores posibles son
  identificador, clave_foranea, fecha, monto, cantidad, porcentaje, categoria,
  texto_libre, booleano, geo. Nunca cambies identificador ni clave_foranea.
- Métricas: proponé entre 3 y 8, las que un gerente miraría primero. Agregaciones:
  suma, conteo, conteo_distinto, promedio, minimo, maximo; o un cociente entre dos
  ids de métricas de agregación que vos mismo definas (ej. ticket promedio =
  total_ventas / cantidad_ventas). Sumar precios unitarios o ids no tiene sentido.
  Formato: moneda para plata, entero para conteos y unidades, decimal, porcentaje.
- Sinónimos: 2 o 3 palabras con las que alguien buscaría esa entidad.
- Descripciones de una línea, sin adornos."""


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CampoSemantico(_Base):
    id: str
    nombre: str = Field(min_length=1, max_length=60)
    tipo_semantico: TipoSemantico
    descripcion: str | None = None


class EntidadSemantica(_Base):
    id: str
    nombre: str = Field(min_length=1, max_length=60)
    tipo: TipoEntidad
    sinonimos: list[str] = Field(default_factory=list, max_length=5)
    descripcion: str | None = None
    campos: list[CampoSemantico]


class MetricaSemantica(_Base):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")
    nombre: str = Field(min_length=1, max_length=60)
    tipo: Literal["agregacion", "cociente"]
    agregacion: Agregacion | None = None
    campo: str | None = Field(default=None, description="entidad.campo para agregaciones")
    numerador: str | None = None
    denominador: str | None = None
    formato: Formato
    descripcion: str | None = None


class RespuestaSemantica(_Base):
    entidades: list[EntidadSemantica]
    metricas: list[MetricaSemantica]


# ---------- Pedido ----------
def _perfil_compacto(perfil: PerfilFuente, campo_id: str, columna: str) -> dict[str, Any]:
    columna_perfil = perfil.columna(columna)
    if columna_perfil is None:
        return {}
    datos: dict[str, Any] = {"nulos": columna_perfil.nulos, "distintos": columna_perfil.distintos}
    if columna_perfil.minimo is not None:
        datos["min"] = columna_perfil.minimo
        datos["max"] = columna_perfil.maximo
    if columna_perfil.top_valores:
        datos["frecuentes"] = [top.valor for top in columna_perfil.top_valores[:5]]
    if columna_perfil.patron:
        datos["patron"] = columna_perfil.patron
    return datos


def armar_pedido(modelo: ModeloSemantico, perfiles: dict[str, PerfilFuente], muestras: dict[str, list[dict[str, Any]]]) -> str:
    """El texto del turno de usuario: JSON compacto con lo que Claude
    necesita, nada de columnas crudas fuera del modelo. `muestras` puede
    venir vacio (ENVIAR_MUESTRA_LLM=false)."""
    entidades = []
    for entidad in modelo.entidades:
        perfil = perfiles.get(entidad.fuente)
        campos = []
        for campo in entidad.campos:
            datos = {
                "id": campo.id,
                "tipo_dato": campo.tipo_dato,
                "tipo_semantico_tentativo": campo.tipo_semantico,
                "confianza": campo.confianza,
            }
            if perfil is not None:
                datos["perfil"] = _perfil_compacto(perfil, campo.id, campo.columna_origen)
            campos.append(datos)
        entidades.append(
            {
                "id": entidad.id,
                "fuente": entidad.fuente,
                "filas": perfil.filas if perfil else None,
                "tipo_tentativo": entidad.tipo,
                "clave_primaria": entidad.clave_primaria,
                "campos": campos,
                "muestra": muestras.get(entidad.fuente, []),
            }
        )
    relaciones = [
        {"desde": relacion.desde.referencia, "hacia": relacion.hacia.referencia, "confianza": relacion.confianza}
        for relacion in modelo.relaciones
    ]
    metricas = [
        {"id": metrica.id, "nombre_tentativo": metrica.nombre, "expresion": metrica.expresion.model_dump(mode="json"), "formato": metrica.formato}
        for metrica in modelo.metricas
    ]
    pedido = {"entidades": entidades, "relaciones_ya_decididas": relaciones, "metricas_tentativas": metricas}
    return json.dumps(pedido, ensure_ascii=False, separators=(",", ":"), default=str)


def huella_pedido(modelo_claude: str, sistema: str, pedido: str) -> str:
    return hashlib.sha256(f"{modelo_claude}|{sistema}|{pedido}".encode()).hexdigest()[:32]


# ---------- Validacion contra el modelo ----------
def validar_respuesta(modelo: ModeloSemantico, respuesta: RespuestaSemantica) -> list[str]:
    errores: list[str] = []
    ids_entidades = {entidad.id for entidad in modelo.entidades}
    vistas: set[str] = set()
    for entidad in respuesta.entidades:
        if entidad.id not in ids_entidades:
            errores.append(f"la entidad '{entidad.id}' no existe (ids válidos: {', '.join(sorted(ids_entidades))})")
            continue
        vistas.add(entidad.id)
        original = modelo.entidad(entidad.id)
        for campo in entidad.campos:
            campo_original = original.campo(campo.id)
            if campo_original is None:
                errores.append(f"el campo '{entidad.id}.{campo.id}' no existe")
            elif campo_original.tipo_semantico in ("identificador", "clave_foranea") and campo.tipo_semantico != campo_original.tipo_semantico:
                errores.append(f"'{entidad.id}.{campo.id}' es {campo_original.tipo_semantico} y no se cambia")
    faltantes = ids_entidades - vistas
    if faltantes:
        errores.append(f"faltan las entidades: {', '.join(sorted(faltantes))}")

    ids_metricas: dict[str, MetricaSemantica] = {}
    for metrica in respuesta.metricas:
        if metrica.id in ids_metricas:
            errores.append(f"la métrica '{metrica.id}' está repetida")
        ids_metricas[metrica.id] = metrica
    for metrica in respuesta.metricas:
        if metrica.tipo == "agregacion":
            if not metrica.agregacion or not metrica.campo:
                errores.append(f"la métrica '{metrica.id}' necesita agregacion y campo")
                continue
            resuelto = modelo.resolver_campo(metrica.campo)
            if resuelto is None:
                errores.append(f"la métrica '{metrica.id}' usa '{metrica.campo}', que no existe")
            elif metrica.agregacion in ("suma", "promedio") and resuelto[1].tipo_dato not in TIPOS_NUMERICOS:
                errores.append(f"la métrica '{metrica.id}' hace {metrica.agregacion} sobre '{metrica.campo}', que no es numérico")
        else:
            for lado in (metrica.numerador, metrica.denominador):
                if not lado or lado not in ids_metricas or ids_metricas[lado].tipo != "agregacion":
                    errores.append(f"el cociente '{metrica.id}' necesita numerador y denominador que sean métricas de agregación de esta misma lista")
    return errores


# ---------- Consulta con reintento ----------
def consultar_semantica(cliente: ClienteLLM, modelo: ModeloSemantico, pedido: str) -> tuple[RespuestaSemantica, RespuestaLLM]:
    """Pide, valida contra el modelo y reintenta UNA vez con los errores como
    feedback. Si la segunda tambien falla, E-INF-05."""
    usuario = pedido
    ultima: RespuestaLLM | None = None
    errores: list[str] = []
    for intento in range(2):
        if intento == 1:
            usuario = (
                pedido
                + "\n\nTu respuesta anterior tenía estos errores; corregilos y devolvé la respuesta completa de nuevo:\n- "
                + "\n- ".join(errores)
            )
        ultima = cliente.completar(sistema=SISTEMA, usuario=usuario, esquema=RespuestaSemantica, max_tokens=MAX_TOKENS_SEMANTICA)
        respuesta = RespuestaSemantica.model_validate(ultima.contenido)
        errores = validar_respuesta(modelo, respuesta)
        if not errores:
            return respuesta, ultima
    raise ErrorApp("E-INF-05", "; ".join(errores[:5]))


# ---------- Aplicar ----------
def aplicar_semantica(modelo: ModeloSemantico, respuesta: RespuestaSemantica) -> ModeloSemantico:
    """Nombres, tipo de entidad, sinonimos, descripciones y tipos semanticos
    dudosos desde Claude; la lista de metricas de Claude reemplaza a la
    tentativa (todas `propuesta`, origen llm). Claves y relaciones intactas."""
    modelo = modelo.model_copy(deep=True)
    por_id = {entidad.id: entidad for entidad in respuesta.entidades}
    for entidad in modelo.entidades:
        propuesta = por_id.get(entidad.id)
        if propuesta is None:
            continue
        entidad.nombre = propuesta.nombre
        entidad.tipo = propuesta.tipo
        entidad.sinonimos = propuesta.sinonimos
        entidad.descripcion = propuesta.descripcion
        entidad.origen = "llm"
        campos_propuestos = {campo.id: campo for campo in propuesta.campos}
        for campo in entidad.campos:
            campo_propuesto = campos_propuestos.get(campo.id)
            if campo_propuesto is None:
                continue
            campo.nombre = campo_propuesto.nombre
            campo.descripcion = campo_propuesto.descripcion
            if campo_propuesto.tipo_semantico != campo.tipo_semantico and campo.confianza < UMBRAL_DUDOSO:
                campo.evidencia = {**campo.evidencia, "tentativo": campo.tipo_semantico, "cambiado_por": "llm"}
                campo.tipo_semantico = campo_propuesto.tipo_semantico
                campo.confianza = CONFIANZA_LLM
            if campo.estado == "propuesta":
                campo.origen = "llm"

    metricas: list[Metrica] = []
    for metrica in respuesta.metricas:
        if metrica.tipo == "agregacion":
            expresion: ExpresionAgregacion | ExpresionCociente = ExpresionAgregacion(agregacion=metrica.agregacion, campo=metrica.campo)
        else:
            expresion = ExpresionCociente(numerador=metrica.numerador, denominador=metrica.denominador)
        metricas.append(
            Metrica(
                id=metrica.id,
                nombre=metrica.nombre,
                expresion=expresion,
                formato=metrica.formato,
                confianza=CONFIANZA_LLM,
                origen="llm",
                estado="propuesta",
                descripcion=metrica.descripcion,
            )
        )
    modelo.metricas = metricas
    return modelo
