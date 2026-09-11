"""Versionado del spec en el catalogo, espejo del versionado del modelo."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.tablas import Usuario, VersionSpec, Workspace
from app.dashboard.edicion import aplicar_operacion, parsear_operacion
from app.dashboard.esquema import SpecDashboard
from app.dashboard.validacion import exigir_valido, parsear_spec, validar_spec
from app.modelo import operaciones as operaciones_modelo
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo
from app.nucleo.errores import ErrorApp

OPERACION_CARGAR_JSON = "cargar_json"
OPERACION_RESTAURAR = "restaurar"


def modelo_efectivo_actual(sesion: Session, workspace: Workspace) -> tuple[ModeloSemantico, int]:
    """El modelo efectivo de la version actual y su numero. E-MOD-02 si no hay."""
    version = operaciones_modelo.exigir_version_actual(sesion, workspace)
    return modelo_efectivo(operaciones_modelo.modelo_de(version)), version.numero


def validar_contenido(sesion: Session, workspace: Workspace, contenido: Any) -> tuple[SpecDashboard, int]:
    spec = parsear_spec(contenido)
    modelo, numero_modelo = modelo_efectivo_actual(sesion, workspace)
    exigir_valido(validar_spec(spec, modelo))
    return spec, numero_modelo


def version_actual(sesion: Session, workspace: Workspace) -> VersionSpec | None:
    return sesion.scalar(
        select(VersionSpec).where(VersionSpec.workspace_id == workspace.id).order_by(VersionSpec.numero.desc()).limit(1)
    )


def exigir_version_actual(sesion: Session, workspace: Workspace) -> VersionSpec:
    version = version_actual(sesion, workspace)
    if version is None:
        raise ErrorApp("E-SPEC-02", f"workspace: {workspace.id}")
    return version


def obtener_version(sesion: Session, workspace: Workspace, numero: int) -> VersionSpec:
    version = sesion.scalar(select(VersionSpec).where(VersionSpec.workspace_id == workspace.id, VersionSpec.numero == numero))
    if version is None:
        raise ErrorApp("E-SPEC-03", f"workspace: {workspace.id}, version: {numero}")
    return version


def listar_versiones(sesion: Session, workspace: Workspace) -> list[VersionSpec]:
    return list(
        sesion.scalars(select(VersionSpec).where(VersionSpec.workspace_id == workspace.id).order_by(VersionSpec.numero.desc()))
    )


def spec_de(version: VersionSpec) -> SpecDashboard:
    return SpecDashboard.model_validate(version.contenido)


def cargar_spec(sesion: Session, workspace: Workspace, contenido: Any, usuario: Usuario | None) -> VersionSpec:
    spec, numero_modelo = validar_contenido(sesion, workspace, contenido)
    return guardar_version(sesion, workspace, spec, numero_modelo, operacion=OPERACION_CARGAR_JSON, autor_id=usuario.id if usuario else None)


def aplicar_y_guardar(sesion: Session, workspace: Workspace, contenido_operacion: Any, usuario: Usuario | None) -> VersionSpec:
    """Una operacion granular del chat constructor (paso 20; el wizard de
    modelo ya usa el equivalente para modelo desde el paso 12): se aplica
    sobre la version actual del spec, se valida contra el modelo efectivo
    (`validar_spec`, compila cada panel) y queda una version nueva. Sin spec
    cargado, E-SPEC-02."""
    operacion = parsear_operacion(contenido_operacion)
    actual = exigir_version_actual(sesion, workspace)
    spec, resumen = aplicar_operacion(spec_de(actual), operacion)
    modelo, numero_modelo = modelo_efectivo_actual(sesion, workspace)
    exigir_valido(validar_spec(spec, modelo))
    return guardar_version(
        sesion, workspace, spec, numero_modelo, operacion=operacion.operacion, autor_id=usuario.id if usuario else None, resumen=resumen
    )


def restaurar(sesion: Session, workspace: Workspace, numero: int, usuario: Usuario | None) -> VersionSpec:
    """Deshacer (fase 3, paso 17): mismo mecanismo que en el modelo. Se
    revalida contra el modelo efectivo actual, por si cambió desde
    entonces (un panel que dependía de una métrica ya rechazada no vuelve
    a colarse en silencio)."""
    vieja = obtener_version(sesion, workspace, numero)
    spec, numero_modelo = validar_contenido(sesion, workspace, vieja.contenido)
    return guardar_version(
        sesion,
        workspace,
        spec,
        numero_modelo,
        operacion=OPERACION_RESTAURAR,
        autor_id=usuario.id if usuario else None,
        resumen=f"Se restauró la versión {numero}",
    )


def guardar_version(
    sesion: Session,
    workspace: Workspace,
    spec: SpecDashboard,
    numero_modelo: int,
    *,
    operacion: str,
    autor_id: int | None,
    resumen: str | None = None,
) -> VersionSpec:
    """Nueva fila en version_spec con el spec YA validado, el numero
    siguiente y el diff contra la version anterior. La comparten la carga de
    JSON, la propuesta inicial (paso 14), las operaciones (paso 16) y
    restaurar (paso 17)."""
    anterior = version_actual(sesion, workspace)
    numero = (anterior.numero if anterior else 0) + 1
    spec = spec.model_copy(update={"version": numero, "modelo_version": numero_modelo})
    version = VersionSpec(
        workspace_id=workspace.id,
        numero=numero,
        modelo_version=numero_modelo,
        contenido=spec.model_dump(mode="json"),
        operacion=operacion,
        diff=calcular_diff(spec_de(anterior), spec) if anterior else None,
        resumen=(resumen or spec.resumen())[:300],
        autor_id=autor_id,
    )
    sesion.add(version)
    sesion.commit()
    sesion.refresh(version)
    return version


def calcular_diff(anterior: SpecDashboard, nuevo: SpecDashboard) -> dict[str, Any]:
    """Que ids aparecieron, desaparecieron o cambiaron en cada coleccion del
    spec; mismo formato que `modelo/operaciones.calcular_diff`."""
    diff: dict[str, Any] = {}
    colecciones = {
        "filtros": ({f.id: f for f in anterior.filtros}, {f.id: f for f in nuevo.filtros}),
        "kpis": ({k.id: k for k in anterior.kpis}, {k.id: k for k in nuevo.kpis}),
        "graficos": ({g.id: g for g in anterior.graficos}, {g.id: g for g in nuevo.graficos}),
        "pestanias": (
            {p.entidad: p for p in anterior.explorador.pestanias},
            {p.entidad: p for p in nuevo.explorador.pestanias},
        ),
    }
    for nombre, (mapa_viejo, mapa_nuevo) in colecciones.items():
        diff[nombre] = {
            "agregados": sorted(set(mapa_nuevo) - set(mapa_viejo)),
            "quitados": sorted(set(mapa_viejo) - set(mapa_nuevo)),
            "cambiados": sorted(
                identificador for identificador in set(mapa_viejo) & set(mapa_nuevo) if mapa_viejo[identificador] != mapa_nuevo[identificador]
            ),
        }
    if anterior.titulo != nuevo.titulo:
        diff["titulo"] = {"anterior": anterior.titulo, "nuevo": nuevo.titulo}
    return diff
