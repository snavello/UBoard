"""La ingesta como tarea en segundo plano."""
import tempfile
from dataclasses import asdict
from pathlib import Path

from app.catalogo.tablas import Workspace
from app.consultas.motor import obtener_motor
from app.ingesta.procesador import ingestar_archivo, registrar_fuentes
from app.nucleo.errores import ErrorApp
from app.tareas import ContextoTarea, registrar_tarea

TIPO_TAREA_INGESTA = "ingesta.procesar_archivo"


@registrar_tarea(TIPO_TAREA_INGESTA)
def procesar_archivo(contexto: ContextoTarea, parametros: dict) -> dict:
    """parametros: ruta_original (en el almacen), nombre_archivo (como lo subio
    el usuario). Resultado: las fuentes creadas o reemplazadas."""
    workspace = contexto.sesion.get(Workspace, contexto.workspace_id)
    if workspace is None:
        raise ErrorApp("E-WS-01", f"id: {contexto.workspace_id}")
    nombre_archivo = parametros["nombre_archivo"]

    contexto.informar(5, f"Leyendo {nombre_archivo}")
    datos = contexto.almacen.leer(parametros["ruta_original"])

    with tempfile.TemporaryDirectory(prefix="uboard-ingesta-") as temporal:
        contexto.informar(20, "Detectando estructura y tipos")
        resultados = ingestar_archivo(datos, nombre_archivo, Path(temporal))
        contexto.informar(70, f"Guardando {len(resultados)} tabla(s)")
        registradas = registrar_fuentes(
            contexto.sesion,
            contexto.almacen,
            workspace,
            resultados,
            archivo_origen=nombre_archivo,
            ruta_original=parametros["ruta_original"],
            usuario_id=contexto.tarea.creada_por_id,
        )

    obtener_motor().invalidar(workspace.id)
    contexto.informar(95, "Listo")
    return {
        "fuentes": [
            {
                "id": fuente.id,
                "nombre_tabla": fuente.nombre_tabla,
                "filas": fuente.filas,
                "reemplazada": reemplazada,
                # Resubida con deteccion de cambios (fase 4): solo hay diff
                # cuando se reemplazo una fuente existente, no en un alta.
                **({"diff_esquema": asdict(diff)} if diff is not None else {}),
            }
            for fuente, reemplazada, diff in registradas
        ]
    }
