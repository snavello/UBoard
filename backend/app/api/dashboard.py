"""API del dashboard: el spec (cargar, leer, versiones) y los paneles con los
filtros activos (KPIs, graficos, explorador paginado, opciones de filtros).
Todo pasa por el compilador via ConsultaSemantica."""
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.almacen import obtener_almacen
from app.almacen.base import AlmacenArchivos
from app.api.tareas import TareaSalida, a_tarea_salida
from app.api.workspaces import workspace_del_usuario
from app.catalogo.sesion import obtener_sesion
from app.catalogo.tablas import RolUsuario, Usuario, VersionSpec, Workspace
from app.consultas import consultar
from app.consultas.compilador import compilar
from app.consultas.ejecutor import contar
from app.consultas.motor import fuentes_listas, obtener_motor
from app.dashboard import operaciones, paneles
from app.dashboard.esquema import SpecDashboard
from app.dashboard.filtros import a_filtros_de_consulta, parsear_filtros_activos
from app.dashboard.validacion import parsear_spec, validar_spec
from app.inferencia.tarea import TIPO_TAREA_PROPONER_SPEC
from app.modelo.esquema import ModeloSemantico
from app.nucleo.auth import exigir_rol
from app.nucleo.errores import ErrorApp
from app.tareas import ColaTareas, encolar_tarea, obtener_cola

router = APIRouter(prefix="/workspaces/{workspace_id}/dashboard", tags=["dashboard"])


# ---------- Esquemas de salida ----------
class VersionSpecResumen(BaseModel):
    numero: int
    modelo_version: int
    operacion: str
    resumen: str | None
    autor_id: int | None
    creada_en: datetime


class DashboardSalida(VersionSpecResumen):
    contenido: dict[str, Any]
    # Si el modelo cambio despues de guardar el spec, aca van los paneles que ya no cierran
    advertencias: list[dict[str, str]]


class ResultadoValidacion(BaseModel):
    valido: bool
    errores: list[dict[str, str]]
    resumen: str | None = None


class KpiSalida(BaseModel):
    id: str
    metrica: str
    titulo: str
    formato: str
    valor: Any


class ColumnaSalida(BaseModel):
    nombre: str
    tipo: str
    clase: str
    granularidad: str | None = None


class GraficoSalida(BaseModel):
    id: str
    tipo: str
    titulo: str
    metrica: dict[str, Any]
    dimension: ColumnaSalida
    filas: list[list[Any]]


class ColumnaExploradorSalida(BaseModel):
    alias: str
    titulo: str
    tipo: str
    clase: str
    oculta: bool
    formato: str | None = None


class ExploradorSalida(BaseModel):
    entidad: str
    titulo: str
    columnas: list[ColumnaExploradorSalida]
    filas: list[list[Any]]
    pagina: int
    tamanio: int
    total: int


class OpcionesSalida(BaseModel):
    filtro: str
    tipo: str
    valores: list[Any] | None = None
    minimo: Any = None
    maximo: Any = None


# ---------- Contexto comun ----------
class ContextoDashboard:
    def __init__(self, sesion: Session, workspace: Workspace, almacen: AlmacenArchivos, filtros_crudos: str | None):
        self.sesion = sesion
        self.workspace = workspace
        self.almacen = almacen
        self.version = operaciones.exigir_version_actual(sesion, workspace)
        self.spec = operaciones.spec_de(self.version)
        self.modelo, _ = operaciones.modelo_efectivo_actual(sesion, workspace)
        self.filtros = a_filtros_de_consulta(self.spec, parsear_filtros_activos(filtros_crudos))

    def consultar(self, consulta, modelo: ModeloSemantico | None = None):
        return consultar(self.sesion, self.workspace, self.almacen, modelo or self.modelo, consulta)


def contexto_dashboard(
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
    almacen: AlmacenArchivos = Depends(obtener_almacen),
    filtros: str | None = Query(None, description='JSON {id_filtro: valor}, ej. {"f_fecha": ["2026-01-01", null]}'),
) -> ContextoDashboard:
    return ContextoDashboard(sesion, workspace, almacen, filtros)


def _resumen(version: VersionSpec) -> VersionSpecResumen:
    return VersionSpecResumen(
        numero=version.numero,
        modelo_version=version.modelo_version,
        operacion=version.operacion,
        resumen=version.resumen,
        autor_id=version.autor_id,
        creada_en=version.creada_en,
    )


def _salida(sesion: Session, workspace: Workspace, version: VersionSpec) -> DashboardSalida:
    spec = operaciones.spec_de(version)
    advertencias: list[dict[str, str]] = []
    modelo, numero_modelo = operaciones.modelo_efectivo_actual(sesion, workspace)
    if numero_modelo != version.modelo_version:
        advertencias = [error.como_dict() for error in validar_spec(spec, modelo)]
    return DashboardSalida(**_resumen(version).model_dump(), contenido=version.contenido, advertencias=advertencias)


# ---------- Spec ----------
@router.get("", response_model=DashboardSalida)
def dashboard_actual(workspace: Workspace = Depends(workspace_del_usuario), sesion: Session = Depends(obtener_sesion)) -> DashboardSalida:
    return _salida(sesion, workspace, operaciones.exigir_version_actual(sesion, workspace))


@router.put("", response_model=DashboardSalida, status_code=status.HTTP_201_CREATED)
def cargar_spec(
    contenido: dict[str, Any] = Body(...),
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
) -> DashboardSalida:
    return _salida(sesion, workspace, operaciones.cargar_spec(sesion, workspace, contenido, usuario))


@router.post("/proponer", response_model=TareaSalida, status_code=status.HTTP_202_ACCEPTED)
def proponer_spec(
    workspace: Workspace = Depends(workspace_del_usuario),
    usuario: Usuario = Depends(exigir_rol(RolUsuario.CONSTRUCTOR)),
    sesion: Session = Depends(obtener_sesion),
    cola: ColaTareas = Depends(obtener_cola),
) -> TareaSalida:
    """Encola la propuesta del spec (fase 2, paso 14): genera un dashboard
    base desde el modelo efectivo actual y Claude lo cura (titulos, orden,
    que graficos vale la pena mostrar). 202 + tarea."""
    tarea = encolar_tarea(sesion, cola, tipo=TIPO_TAREA_PROPONER_SPEC, parametros={}, workspace=workspace, usuario=usuario)
    return a_tarea_salida(tarea)


@router.post("/validar", response_model=ResultadoValidacion, dependencies=[Depends(exigir_rol(RolUsuario.CONSTRUCTOR))])
def validar(
    contenido: dict[str, Any] = Body(...),
    workspace: Workspace = Depends(workspace_del_usuario),
    sesion: Session = Depends(obtener_sesion),
) -> ResultadoValidacion:
    try:
        spec = parsear_spec(contenido)
    except ErrorApp as error:
        return ResultadoValidacion(valido=False, errores=(error.extra or {}).get("errores", []))
    modelo, _ = operaciones.modelo_efectivo_actual(sesion, workspace)
    errores = validar_spec(spec, modelo)
    return ResultadoValidacion(valido=not errores, errores=[error.como_dict() for error in errores], resumen=spec.resumen())


@router.get("/versiones", response_model=list[VersionSpecResumen])
def listar_versiones(workspace: Workspace = Depends(workspace_del_usuario), sesion: Session = Depends(obtener_sesion)) -> list[VersionSpecResumen]:
    return [_resumen(version) for version in operaciones.listar_versiones(sesion, workspace)]


@router.get("/versiones/{numero}", response_model=DashboardSalida)
def obtener_version(numero: int, workspace: Workspace = Depends(workspace_del_usuario), sesion: Session = Depends(obtener_sesion)) -> DashboardSalida:
    return _salida(sesion, workspace, operaciones.obtener_version(sesion, workspace, numero))


# ---------- Paneles ----------
@router.get("/kpis", response_model=list[KpiSalida])
def kpis(contexto: ContextoDashboard = Depends(contexto_dashboard)) -> list[KpiSalida]:
    spec, modelo = contexto.spec, contexto.modelo
    if not spec.kpis:
        return []
    resultado = contexto.consultar(paneles.consulta_kpis(spec.kpis, contexto.filtros))
    valores = dict(zip([columna.nombre for columna in resultado.columnas], resultado.filas[0]))
    salida = []
    for kpi in spec.kpis:
        metrica = modelo.metrica(kpi.metrica)
        salida.append(
            KpiSalida(
                id=kpi.id,
                metrica=kpi.metrica,
                titulo=kpi.titulo or (metrica.nombre if metrica else kpi.metrica),
                formato=metrica.formato if metrica else "decimal",
                valor=valores.get(kpi.metrica),
            )
        )
    return salida


@router.get("/graficos/{grafico_id}", response_model=GraficoSalida)
def grafico(grafico_id: str, contexto: ContextoDashboard = Depends(contexto_dashboard)) -> GraficoSalida:
    grafico_spec = contexto.spec.grafico(grafico_id)
    if grafico_spec is None:
        raise ErrorApp("E-SPEC-04", f"grafico: {grafico_id!r}")
    resultado = contexto.consultar(paneles.consulta_grafico(grafico_spec, contexto.filtros))
    metrica = contexto.modelo.metrica(grafico_spec.metrica)
    dimension = resultado.columnas[0]
    return GraficoSalida(
        id=grafico_spec.id,
        tipo=grafico_spec.tipo,
        titulo=grafico_spec.titulo or f"{metrica.nombre} por {grafico_spec.dimension}",
        metrica={"id": metrica.id, "nombre": metrica.nombre, "formato": metrica.formato},
        dimension=ColumnaSalida(nombre=grafico_spec.dimension, tipo=dimension.tipo, clase="dimension", granularidad=dimension.granularidad),
        filas=resultado.filas,
    )


@router.get("/explorador/{entidad}", response_model=ExploradorSalida)
def explorador(
    entidad: str,
    contexto: ContextoDashboard = Depends(contexto_dashboard),
    pagina: int = Query(1, ge=1),
    tamanio: int | None = Query(None, ge=5, le=200),
    orden: str | None = Query(None, description="alias de columna o id de métrica"),
    direccion: Literal["asc", "desc"] = Query("asc"),
) -> ExploradorSalida:
    pestania = contexto.spec.pestania(entidad)
    if pestania is None:
        raise ErrorApp("E-SPEC-04", f"pestaña: {entidad!r}")
    modelo = contexto.modelo
    consulta, columnas = paneles.consulta_explorador(
        modelo, pestania, contexto.filtros, pagina=pagina, tamanio=tamanio, orden_por=orden, direccion=direccion
    )
    resultado = contexto.consultar(consulta)

    # Total sin paginar, para la barra de paginas
    consulta_total = consulta.model_copy(update={"limite": None, "desplazamiento": 0, "orden": []})
    conexion = obtener_motor().conexion(contexto.workspace.id, fuentes_listas(contexto.sesion, contexto.workspace), contexto.almacen)
    try:
        total = contar(conexion, compilar(modelo, consulta_total))
    finally:
        conexion.close()

    salida_columnas = []
    for columna_resultado in resultado.columnas:
        if columna_resultado.clase == "dimension":
            definicion = next(columna for columna in columnas if columna.alias == columna_resultado.nombre)
            _, campo = modelo.resolver_campo(definicion.campo)
            salida_columnas.append(
                ColumnaExploradorSalida(alias=definicion.alias, titulo=campo.nombre, tipo=columna_resultado.tipo, clase="dimension", oculta=definicion.oculta)
            )
        else:
            metrica = modelo.metrica(columna_resultado.nombre)
            salida_columnas.append(
                ColumnaExploradorSalida(alias=columna_resultado.nombre, titulo=metrica.nombre, tipo=columna_resultado.tipo, clase="metrica", oculta=False, formato=metrica.formato)
            )
    entidad_modelo = modelo.entidad(pestania.entidad)
    return ExploradorSalida(
        entidad=pestania.entidad,
        titulo=pestania.titulo or entidad_modelo.nombre,
        columnas=salida_columnas,
        filas=resultado.filas,
        pagina=pagina,
        tamanio=consulta.limite or pestania.tamanio_pagina,
        total=total,
    )


@router.get("/filtros/{filtro_id}/opciones", response_model=OpcionesSalida)
def opciones_de_filtro(filtro_id: str, contexto: ContextoDashboard = Depends(contexto_dashboard)) -> OpcionesSalida:
    """Valores posibles de un filtro. Sin filtrado asociativo (fase 4): son
    todos los valores del campo, sin mirar los demas filtros activos."""
    filtro = contexto.spec.filtro(filtro_id)
    if filtro is None:
        raise ErrorApp("E-SPEC-04", f"filtro: {filtro_id!r}")
    if filtro.tipo == "lista":
        resultado = contexto.consultar(paneles.consulta_opciones_lista(filtro.campo))
        return OpcionesSalida(filtro=filtro.id, tipo=filtro.tipo, valores=[fila[0] for fila in resultado.filas if fila[0] is not None])
    modelo_ampliado, consulta = paneles.modelo_con_rango(contexto.modelo, filtro.campo)
    resultado = contexto.consultar(consulta, modelo_ampliado)
    minimo, maximo = resultado.filas[0]
    return OpcionesSalida(filtro=filtro.id, tipo=filtro.tipo, minimo=minimo, maximo=maximo)
