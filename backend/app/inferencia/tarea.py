"""Proponer el modelo como tarea en segundo plano (a pedido, desde el boton
"Proponer modelo" de Fuentes)."""
from app.catalogo.tablas import Workspace
from app.consultas.motor import fuentes_listas, obtener_motor
from app.inferencia.fusion import fusionar
from app.inferencia.heuristicas import FuentePerfilada, proponer_modelo
from app.modelo import operaciones
from app.modelo.validacion import validar_contra_fuentes, validar_estructura
from app.nucleo.config import obtener_configuracion
from app.nucleo.errores import ErrorApp
from app.perfilado import PerfilFuente
from app.tareas import ContextoTarea, registrar_tarea

TIPO_TAREA_PROPONER_MODELO = "inferencia.proponer_modelo"
OPERACION_PROPONER = "proponer_modelo"


@registrar_tarea(TIPO_TAREA_PROPONER_MODELO)
def tarea_proponer_modelo(contexto: ContextoTarea, parametros: dict) -> dict:
    workspace = contexto.sesion.get(Workspace, contexto.workspace_id)
    if workspace is None:
        raise ErrorApp("E-WS-01", f"id: {contexto.workspace_id}")
    fuentes = fuentes_listas(contexto.sesion, workspace)
    if not fuentes:
        raise ErrorApp("E-INF-02", f"workspace: {workspace.id}")
    sin_perfil = [fuente.nombre_tabla for fuente in fuentes if not fuente.perfil]
    if sin_perfil:
        raise ErrorApp("E-INF-03", "fuentes: " + ", ".join(sin_perfil))

    configuracion = obtener_configuracion()
    contexto.informar(10, "Buscando claves y relaciones")
    perfiladas = [
        FuentePerfilada(fuente.nombre_tabla, fuente.esquema, PerfilFuente.model_validate(fuente.perfil)) for fuente in fuentes
    ]
    conexion = obtener_motor().conexion(workspace.id, fuentes, contexto.almacen)
    try:
        propuesta = proponer_modelo(
            conexion,
            perfiladas,
            umbral_inclusion=configuracion.umbral_inclusion_fk,
            umbral_nombre=configuracion.umbral_similitud_nombre,
        )
    finally:
        conexion.close()

    contexto.informar(60, "Fusionando con el modelo actual")
    version_anterior = operaciones.version_actual(contexto.sesion, workspace)
    modelo = fusionar(operaciones.modelo_de(version_anterior) if version_anterior else None, propuesta)

    contexto.informar(80, "Validando")
    errores = validar_estructura(modelo)
    if not errores:
        errores = validar_contra_fuentes(modelo, operaciones.esquemas_del_workspace(contexto.sesion, workspace))
    if errores:
        raise ErrorApp("E-INF-04", "; ".join(f"{error.codigo} {error.ubicacion}" for error in errores[:5]))

    version = operaciones.guardar_version(
        contexto.sesion, workspace, modelo, operacion=OPERACION_PROPONER, autor_id=contexto.tarea.creada_por_id
    )
    contexto.informar(95, "Listo")
    return {
        "version": version.numero,
        "resumen": modelo.resumen(),
        "entidades": [{"id": entidad.id, "tipo": entidad.tipo, "clave_primaria": entidad.clave_primaria} for entidad in modelo.entidades],
        "relaciones": [
            {"id": relacion.id, "desde": relacion.desde.referencia, "hacia": relacion.hacia.referencia, "confianza": relacion.confianza, "estado": relacion.estado}
            for relacion in modelo.relaciones
        ],
        "metricas": [{"id": metrica.id, "estado": metrica.estado} for metrica in modelo.metricas],
    }
