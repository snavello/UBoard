"""Versionado del spec en el catalogo, espejo del versionado del modelo."""
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalogo.tablas import Usuario, VersionSpec, Workspace
from app.dashboard.esquema import SpecDashboard
from app.dashboard.validacion import exigir_valido, parsear_spec, validar_spec
from app.modelo import operaciones as operaciones_modelo
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo
from app.nucleo.errores import ErrorApp

OPERACION_CARGAR_JSON = "cargar_json"


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
    anterior = version_actual(sesion, workspace)
    numero = (anterior.numero if anterior else 0) + 1
    spec = spec.model_copy(update={"version": numero, "modelo_version": numero_modelo})
    version = VersionSpec(
        workspace_id=workspace.id,
        numero=numero,
        modelo_version=numero_modelo,
        contenido=spec.model_dump(mode="json"),
        operacion=OPERACION_CARGAR_JSON,
        resumen=spec.resumen(),
        autor_id=usuario.id if usuario else None,
    )
    sesion.add(version)
    sesion.commit()
    sesion.refresh(version)
    return version
