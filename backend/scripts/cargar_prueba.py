"""Carga de punta a punta contra un servidor corriendo: sube los 5 CSV de
datos_prueba/, espera la ingesta, carga modelo.json y spec.json.

Uso (con uvicorn levantado y la organizacion Demo creada por
crear_organizacion.py demo):

  .venv/Scripts/python.exe backend/scripts/cargar_prueba.py [--url http://localhost:8000]
      [--email constructor@demo.local --clave demo-constructor-1] [--datos datos_prueba]
"""
import argparse
import json
import sys
import time
from pathlib import Path

import httpx

RAIZ_REPO = Path(__file__).resolve().parents[2]
ARCHIVOS = ["ventas.csv", "vendedores.csv", "productos.csv", "pagos.csv", "medios_pago.csv"]


def fallar(mensaje: str) -> None:
    print(f"ERROR: {mensaje}", file=sys.stderr)
    raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Carga los datos de prueba, el modelo y el spec en un UBoard corriendo.")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--email", default="constructor@demo.local")
    parser.add_argument("--clave", default="demo-constructor-1")
    parser.add_argument("--datos", default=str(RAIZ_REPO / "datos_prueba"))
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
