"""Versionado del modelo en el catalogo. En la fase 1 la unica operacion es
`cargar_json` (modelo entero); las operaciones granulares del wizard y el
chat (fases 2 y 3) crearan versiones con la misma tabla, dejando en
`operacion` y `diff` que cambio."""
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.catalogo.tablas import Usuario, VersionModelo, Workspace
from app.consultas.motor import fuentes_listas
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import exigir_valido, parsear_modelo, validar_contra_fuentes, validar_estructura
from app.nucleo.errores import ErrorApp

OPERACION_CARGAR_JSON = "cargar_json"


def esquemas_del_workspace(sesion: Session, workspace: Workspace) -> dict[str, list[dict[str, Any]]]:
    return {fuente.nombre_tabla: fuente.esquema for fuente in fuentes_listas(sesion, workspace)}


def validar_modelo(sesion: Session, workspace: Workspace, contenido: Any) -> ModeloSemantico:
    """Las tres capas de validacion. Devuelve el modelo parseado o E-MOD-01."""
    modelo = parsear_modelo(contenido)
    errores = validar_estructura(modelo)
    if not errores:
        errores = validar_contra_fuentes(modelo, esquemas_del_workspace(sesion, workspace))
    exigir_valido(errores)
    return modelo


def version_actual(sesion: Session, workspace: Workspace) -> VersionModelo | None:
    return sesion.scalar(
        select(VersionModelo).where(VersionModelo.workspace_id == workspace.id).order_by(VersionModelo.numero.desc()).limit(1)
    )


def exigir_version_actual(sesion: Session, workspace: Workspace) -> VersionModelo:
    version = version_actual(sesion, workspace)
    if version is None:
        raise ErrorApp("E-MOD-02", f"workspace: {workspace.id}")
    return version


def obtener_version(sesion: Session, workspace: Workspace, numero: int) -> VersionModelo:
    version = sesion.scalar(
        select(VersionModelo).where(VersionModelo.workspace_id == workspace.id, VersionModelo.numero == numero)
    )
    if version is None:
        raise ErrorApp("E-MOD-03", f"workspace: {workspace.id}, version: {numero}")
    return version


def listar_versiones(sesion: Session, workspace: Workspace) -> list[VersionModelo]:
    return list(
        sesion.scalars(
            select(VersionModelo).where(VersionModelo.workspace_id == workspace.id).order_by(VersionModelo.numero.desc())
        )
    )


def modelo_de(version: VersionModelo) -> ModeloSemantico:
    return ModeloSemantico.model_validate(version.contenido)


def cargar_modelo(sesion: Session, workspace: Workspace, contenido: Any, usuario: Usuario | None) -> VersionModelo:
    """Valida y guarda una nueva version con el modelo entero."""
    modelo = validar_modelo(sesion, workspace, contenido)
    anterior = version_actual(sesion, workspace)
    numero = (anterior.numero if anterior else 0) + 1
    modelo = modelo.model_copy(update={"version": numero})
    version = VersionModelo(
        workspace_id=workspace.id,
        numero=numero,
        contenido=modelo.model_dump(mode="json"),
        operacion=OPERACION_CARGAR_JSON,
        diff=calcular_diff(modelo_de(anterior), modelo) if anterior else None,
        resumen=modelo.resumen(),
        autor_id=usuario.id if usuario else None,
    )
    sesion.add(version)
    sesion.commit()
    sesion.refresh(version)
    return version


def calcular_diff(anterior: ModeloSemantico, nuevo: ModeloSemantico) -> dict[str, Any]:
    """Que ids aparecieron, desaparecieron o cambiaron en cada coleccion.
    Suficiente para el historial de la fase 1; el deshacer (fase 3) usa el
    contenido completo de la version anterior, no este diff."""
    diff: dict[str, Any] = {}
    colecciones = {
        "entidades": (anterior.entidades, nuevo.entidades),
        "relaciones": (anterior.relaciones, nuevo.relaciones),
        "metricas": (anterior.metricas, nuevo.metricas),
    }
    for nombre, (viejos, nuevos) in colecciones.items():
        mapa_viejo = {elemento.id: elemento for elemento in viejos}
        mapa_nuevo = {elemento.id: elemento for elemento in nuevos}
        diff[nombre] = {
            "agregados": sorted(set(mapa_nuevo) - set(mapa_viejo)),
            "quitados": sorted(set(mapa_viejo) - set(mapa_nuevo)),
            "cambiados": sorted(
                identificador for identificador in set(mapa_viejo) & set(mapa_nuevo) if mapa_viejo[identificador] != mapa_nuevo[identificador]
            ),
        }
    viejas = {dimension.campo for dimension in anterior.dimensiones_tiempo}
    nuevas = {dimension.campo for dimension in nuevo.dimensiones_tiempo}
    diff["dimensiones_tiempo"] = {"agregados": sorted(nuevas - viejas), "quitados": sorted(viejas - nuevas), "cambiados": []}
    return diff


def cantidad_versiones(sesion: Session, workspace: Workspace) -> int:
    return sesion.scalar(select(func.count()).select_from(VersionModelo).where(VersionModelo.workspace_id == workspace.id)) or 0
