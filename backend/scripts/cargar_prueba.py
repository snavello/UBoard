"""Carga de punta a punta contra un servidor corriendo: sube los 5 CSV de
datos_prueba/, espera la ingesta, y arma el modelo y el dashboard de una de
dos formas.

Por defecto (fase 1), carga `modelo.json` y `spec.json` escritos a mano:

  .venv/Scripts/python.exe backend/scripts/cargar_prueba.py [--url http://localhost:8000]
      [--email constructor@demo.local --clave demo-constructor-1] [--datos datos_prueba]

Con `--inferir` (fase 2, paso 15), en vez de eso le pide a UBoard que
proponga el modelo (heurísticas + Claude) y el dashboard, confirmando todo
lo que haya quedado propuesto en el medio (así el spec no queda vacío: ver
CLAUDE.md, "confirmar_todo" con `minimo_confianza: 0` es el equivalente
automático de revisar el wizard a mano). Es la forma de reproducir por
script la aceptación de la fase 2 (`docs/fase2-aceptacion.md`):

  .venv/Scripts/python.exe backend/scripts/cargar_prueba.py --inferir [--url ...]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

# La consola de Windows a veces arranca en cp1252: los resúmenes con tildes
# o "≥" (confirmar_todo) rompen el print. utf-8 explícito, sin drama si el
# stdout ya no es reconfigurable (por ejemplo, redirigido a un pipe raro).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

RAIZ_REPO = Path(__file__).resolve().parents[2]
ARCHIVOS = ["ventas.csv", "vendedores.csv", "productos.csv", "pagos.csv", "medios_pago.csv"]


def fallar(mensaje: str) -> None:
    print(f"ERROR: {mensaje}", file=sys.stderr)
    raise SystemExit(1)


def _esperar_tarea(cliente: httpx.Client, workspace_id: int, tarea_id: str, *, segundos: int = 180) -> dict:
    limite = time.time() + segundos
    while time.time() < limite:
        time.sleep(1.5)
        tarea = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea_id}").json()
        if tarea["estado"] == "terminada":
            return tarea["resultado"]
        if tarea["estado"] == "error":
            fallar(f"la tarea {tarea['tipo']} falló: {tarea['error']}")
    fallar(f"la tarea {tarea_id} no terminó en {segundos} segundos")
    raise AssertionError  # fallar() no vuelve; esto es solo para el tipado


def _proponer(cliente: httpx.Client, workspace_id: int, ruta: str, *, segundos: int = 180) -> dict:
    respuesta = cliente.post(f"/api/workspaces/{workspace_id}/{ruta}/proponer")
    if respuesta.status_code != 202:
        fallar(f"proponer {ruta} {respuesta.status_code}: {respuesta.text}")
    return _esperar_tarea(cliente, workspace_id, respuesta.json()["id"], segundos=segundos)


def _confirmar_todo(cliente: httpx.Client, workspace_id: int) -> None:
    """Equivalente automático de revisar el wizard a mano: confirma TODO lo
    propuesto, sin importar la confianza. Solo para este script; el wizard
    de verdad usa el umbral por defecto (0.9) en "Confirmar todo lo verde"."""
    respuesta = cliente.post(
        f"/api/workspaces/{workspace_id}/modelo/operaciones",
        json={"operacion": "confirmar_todo", "seccion": "todo", "minimo_confianza": 0},
    )
    if respuesta.status_code != 201:
        fallar(f"confirmar_todo {respuesta.status_code}: {respuesta.text}")
    print(f"  {respuesta.json()['resumen']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga los datos de prueba, el modelo y el spec en un UBoard corriendo.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--email", default="constructor@demo.local")
    parser.add_argument("--clave", default="demo-constructor-1")
    parser.add_argument("--datos", default=str(RAIZ_REPO / "datos_prueba"))
    parser.add_argument(
        "--inferir",
        action="store_true",
        help="En vez de cargar modelo.json/spec.json, pide la propuesta (heurísticas + Claude) y confirma todo.",
    )
    argumentos = parser.parse_args(argv)
    datos = Path(argumentos.datos)

    with httpx.Client(base_url=argumentos.url, timeout=60) as cliente:
        respuesta = cliente.post("/api/auth/login", json={"email": argumentos.email, "clave": argumentos.clave})
        if respuesta.status_code != 200:
            fallar(f"login {respuesta.status_code}: {respuesta.text}")
        workspace_id = respuesta.json()["workspace_id"]
        print(f"Sesión como {argumentos.email}, workspace {workspace_id}")

        archivos = [("archivos", (nombre, (datos / nombre).read_bytes(), "application/octet-stream")) for nombre in ARCHIVOS]
        respuesta = cliente.post(f"/api/workspaces/{workspace_id}/fuentes", files=archivos)
        if respuesta.status_code != 202:
            fallar(f"subida {respuesta.status_code}: {respuesta.text}")
        pendientes = {tarea["id"] for tarea in respuesta.json()}
        print(f"Subidos {len(ARCHIVOS)} archivos, esperando {len(pendientes)} tareas...")
        limite = time.time() + 120
        while pendientes and time.time() < limite:
            time.sleep(1)
            for tarea_id in list(pendientes):
                tarea = cliente.get(f"/api/workspaces/{workspace_id}/tareas/{tarea_id}").json()
                if tarea["estado"] == "terminada":
                    for fuente in tarea["resultado"]["fuentes"]:
                        print(f"  {fuente['nombre_tabla']}: {fuente['filas']} filas{' (reemplazada)' if fuente['reemplazada'] else ''}")
                    pendientes.discard(tarea_id)
                elif tarea["estado"] == "error":
                    fallar(f"ingesta fallida: {tarea['error']}")
        if pendientes:
            fallar("la ingesta no terminó en 120 segundos")

        if argumentos.inferir:
            print("Proponiendo el modelo (heurísticas + Claude)...")
            resultado = _proponer(cliente, workspace_id, "modelo")
            claude = resultado.get("claude", {})
            print(f"  modelo versión {resultado['version']}: {resultado['resumen']}")
            print(f"  relaciones: {[(r['desde'], r['hacia'], r['confianza']) for r in resultado.get('relaciones', [])]}")
            print(f"  claude: {'usado, ' + ('caché' if claude.get('cache') else str(claude.get('tokens_entrada', 0) + claude.get('tokens_salida', 0)) + ' tokens') if claude.get('usado') else claude.get('advertencia', 'no usado')}")
            print("Confirmando todo lo propuesto (equivalente automático del wizard)...")
            _confirmar_todo(cliente, workspace_id)
            print("Proponiendo el dashboard...")
            resultado = _proponer(cliente, workspace_id, "dashboard")
            print(f"  dashboard versión {resultado['version']} {resultado.get('titulo')!r}: {resultado['resumen']}")
        else:
            for nombre, ruta in (("modelo", "modelo"), ("spec", "dashboard")):
                contenido = json.loads((datos / f"{nombre}.json").read_text(encoding="utf-8"))
                respuesta = cliente.put(f"/api/workspaces/{workspace_id}/{ruta}", json=contenido)
                if respuesta.status_code != 201:
                    fallar(f"{nombre} {respuesta.status_code}: {respuesta.text}")
                print(f"{nombre} cargado: versión {respuesta.json()['numero']}, {respuesta.json()['resumen']}")

        kpis = cliente.get(f"/api/workspaces/{workspace_id}/dashboard/kpis").json()
        print("KPIs: " + ", ".join(f"{kpi['titulo']} = {kpi['valor']}" for kpi in kpis))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
