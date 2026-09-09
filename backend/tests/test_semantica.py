"""Claude en la inferencia, sin red: armado del pedido, validacion de la
respuesta, reintento con feedback, aplicacion sobre el modelo heuristico."""
import json

import duckdb
import pytest

from app.inferencia.heuristicas import FuentePerfilada, proponer_modelo
from app.inferencia.llm import ClienteFalso
from app.inferencia.semantica import (
    RespuestaSemantica,
    aplicar_semantica,
    armar_pedido,
    consultar_semantica,
    huella_pedido,
    validar_respuesta,
)
from app.ingesta.procesador import ingestar_archivo
from app.modelo.esquema import ModeloSemantico
from app.modelo.validacion import modelo_efectivo, validar_estructura
from app.nucleo.errores import ErrorApp
from app.perfilado import PerfilFuente
from scripts.generar_datos_prueba import generar


@pytest.fixture(scope="module")
def heuristico(tmp_path_factory) -> tuple[ModeloSemantico, dict[str, PerfilFuente], dict[str, list[dict]]]:
    raiz = tmp_path_factory.mktemp("semantica")
    conexion = duckdb.connect()
    fuentes, perfiles, muestras = [], {}, {}
    for nombre, ruta in generar(raiz / "csv").items():
        directorio = raiz / f"ingesta_{nombre}"
        directorio.mkdir()
        resultado = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
        uri = resultado.ruta_parquet_temporal.as_posix()
        conexion.execute(f'CREATE VIEW "{resultado.nombre_tabla}" AS SELECT * FROM read_parquet(\'{uri}\')')
        perfil = PerfilFuente.model_validate(resultado.perfil)
        perfiles[resultado.nombre_tabla] = perfil
        fuentes.append(FuentePerfilada(resultado.nombre_tabla, resultado.esquema_como_dicts(), perfil))
        filas = conexion.execute(f'SELECT * FROM "{resultado.nombre_tabla}" LIMIT 3').fetchall()
        columnas = [c["nombre"] for c in resultado.esquema_como_dicts()]
        muestras[resultado.nombre_tabla] = [dict(zip(columnas, map(str, fila))) for fila in filas]
    return proponer_modelo(conexion, fuentes), perfiles, muestras


def respuesta_valida(modelo: ModeloSemantico) -> dict:
    """Una respuesta como la que daria Claude, construida desde el modelo."""
    nombres = {"ventas": "Ventas", "vendedores": "Vendedores", "productos": "Productos", "pagos": "Pagos", "medios_pago": "Medios de pago"}
    entidades = []
    for entidad in modelo.entidades:
        campos = [{"id": campo.id, "nombre": campo.nombre.capitalize(), "tipo_semantico": campo.tipo_semantico} for campo in entidad.campos]
        entidades.append({"id": entidad.id, "nombre": nombres[entidad.id], "tipo": entidad.tipo, "sinonimos": ["operaciones"], "descripcion": "x", "campos": campos})
    metricas = [
        {"id": "total_ventas", "nombre": "Total ventas", "tipo": "agregacion", "agregacion": "suma", "campo": "ventas.importe", "formato": "moneda"},
        {"id": "cantidad_ventas", "nombre": "Cantidad de ventas", "tipo": "agregacion", "agregacion": "conteo", "campo": "ventas.id_venta", "formato": "entero"},
        {"id": "ticket_promedio", "nombre": "Ticket promedio", "tipo": "cociente", "numerador": "total_ventas", "denominador": "cantidad_ventas", "formato": "moneda"},
    ]
    return {"entidades": entidades, "metricas": metricas}


def test_el_pedido_es_compacto_y_lleva_perfil_relaciones_y_muestra(heuristico):
    modelo, perfiles, muestras = heuristico
    pedido = json.loads(armar_pedido(modelo, perfiles, muestras))
    assert {e["id"] for e in pedido["entidades"]} == {"ventas", "vendedores", "productos", "pagos", "medios_pago"}
    ventas = next(e for e in pedido["entidades"] if e["id"] == "ventas")
    assert ventas["filas"] == 3000 and ventas["clave_primaria"] == ["id_venta"]
    vendedor = next(c for c in ventas["campos"] if c["id"] == "vendedor")
    assert vendedor["tipo_semantico_tentativo"] == "clave_foranea" and vendedor["perfil"]["nulos"] > 0
    assert len(ventas["muestra"]) == 3 and set(ventas["muestra"][0]) == {c["id"] for c in ventas["campos"]}
    assert len(pedido["relaciones_ya_decididas"]) == 4
    assert any(m["id"] == "total_importe" for m in pedido["metricas_tentativas"])
    # Sin muestra (ENVIAR_MUESTRA_LLM=false): ni una fila de datos
    sin_muestra = armar_pedido(modelo, perfiles, {})
    assert '"muestra":[]' in sin_muestra and len(sin_muestra) < len(armar_pedido(modelo, perfiles, muestras))
    assert huella_pedido("claude-sonnet-5", "s", sin_muestra) != huella_pedido("claude-sonnet-5", "s", armar_pedido(modelo, perfiles, muestras))


def test_validar_respuesta_detecta_ids_inventados_y_metricas_rotas(heuristico):
    modelo, _, _ = heuristico
    respuesta = respuesta_valida(modelo)
    assert validar_respuesta(modelo, RespuestaSemantica.model_validate(respuesta)) == []

    rota = json.loads(json.dumps(respuesta))
    rota["entidades"][0]["campos"].append({"id": "inventado", "nombre": "X", "tipo_semantico": "monto"})
    rota["entidades"][1]["campos"][0]["tipo_semantico"] = "categoria"  # era identificador
    del rota["entidades"][2]
    rota["metricas"].append({"id": "m1", "nombre": "M", "tipo": "agregacion", "agregacion": "suma", "campo": "ventas.fecha", "formato": "decimal"})
    rota["metricas"].append({"id": "m2", "nombre": "M", "tipo": "cociente", "numerador": "m1", "denominador": "nada", "formato": "decimal"})
    errores = validar_respuesta(modelo, RespuestaSemantica.model_validate(rota))
    assert any("inventado" in e for e in errores)
    assert any("identificador" in e for e in errores)
    assert any("faltan las entidades" in e for e in errores)
    assert any("no es numérico" in e for e in errores)
    assert any("cociente 'm2'" in e for e in errores)


def test_consultar_reintenta_una_vez_con_el_error_como_feedback(heuristico):
    modelo, perfiles, muestras = heuristico
    buena = respuesta_valida(modelo)
    mala = json.loads(json.dumps(buena))
    mala["metricas"][0]["campo"] = "ventas.no_existe"
    cliente = ClienteFalso([mala, buena])
    pedido = armar_pedido(modelo, perfiles, muestras)
    respuesta, cruda = consultar_semantica(cliente, modelo, pedido)
    assert respuesta.metricas[0].campo == "ventas.importe"
    assert len(cliente.pedidos) == 2
    assert "ventas.no_existe" in cliente.pedidos[1]["usuario"] and "corregilos" in cliente.pedidos[1]["usuario"]
    assert cruda.tokens_entrada == 100

    # Dos veces mal: E-INF-05, y la heuristica sigue valiendo (lo decide la tarea)
    cliente = ClienteFalso([mala, mala])
    with pytest.raises(ErrorApp) as error:
        consultar_semantica(cliente, modelo, pedido)
    assert error.value.codigo == "E-INF-05"


def test_aplicar_semantica_pone_nombres_tipos_y_metricas_sin_tocar_claves(heuristico):
    modelo, _, _ = heuristico
    respuesta = respuesta_valida(modelo)
    # Claude cambia un tipo dudoso (0.6) y uno seguro (0.9): solo el dudoso entra
    ventas = next(e for e in respuesta["entidades"] if e["id"] == "ventas")
    campos = {c["id"]: c for c in ventas["campos"]}
    campos["cantidad"]["tipo_semantico"] = "categoria"  # heuristica 0.9: no se toca
    medios = next(e for e in respuesta["entidades"] if e["id"] == "medios_pago")
    medios["tipo"] = "dimension"
    enriquecido = aplicar_semantica(modelo, RespuestaSemantica.model_validate(respuesta))

    assert validar_estructura(enriquecido) == []
    assert enriquecido.entidad("medios_pago").nombre == "Medios de pago"
    assert enriquecido.entidad("medios_pago").origen == "llm" and enriquecido.entidad("medios_pago").sinonimos == ["operaciones"]
    assert enriquecido.entidad("ventas").campo("cantidad").tipo_semantico == "cantidad"
    assert enriquecido.entidad("ventas").campo("id_venta").estado == "confirmada"  # la clave sigue confirmada
    assert enriquecido.entidad("ventas").campo("importe").origen == "llm"
    assert [r.desde.referencia for r in enriquecido.relaciones] == [r.desde.referencia for r in modelo.relaciones]
    assert [m.id for m in enriquecido.metricas] == ["total_ventas", "cantidad_ventas", "ticket_promedio"]
    ticket = enriquecido.metrica("ticket_promedio")
    assert ticket.expresion.numerador == "total_ventas" and ticket.origen == "llm" and ticket.estado == "propuesta" and ticket.confianza == 0.8
    assert modelo_efectivo(enriquecido).metricas == [], "siguen propuestas hasta que alguien confirme"
    # El original no se modifico
    assert modelo.entidad("medios_pago").nombre == "Medios pago"


def test_un_tipo_dudoso_si_lo_cambia_claude():
    modelo = ModeloSemantico.model_validate(
        {
            "entidades": [
                {
                    "id": "t",
                    "nombre": "T",
                    "fuente": "t",
                    "tipo": "dimension",
                    "clave_primaria": ["id"],
                    "origen": "heuristica",
                    "campos": [
                        {"id": "id", "columna_origen": "id", "nombre": "Id", "tipo_dato": "entero", "tipo_semantico": "identificador", "origen": "heuristica"},
                        {"id": "x", "columna_origen": "x", "nombre": "X", "tipo_dato": "decimal", "tipo_semantico": "monto", "confianza": 0.6, "origen": "heuristica", "estado": "propuesta"},
                    ],
                }
            ]
        }
    )
    respuesta = RespuestaSemantica.model_validate(
        {
            "entidades": [{"id": "t", "nombre": "Tabla", "tipo": "dimension", "campos": [{"id": "x", "nombre": "Descuento", "tipo_semantico": "porcentaje"}]}],
            "metricas": [],
        }
    )
    campo = aplicar_semantica(modelo, respuesta).entidad("t").campo("x")
    assert campo.tipo_semantico == "porcentaje" and campo.confianza == 0.8 and campo.nombre == "Descuento"
    assert campo.evidencia["tentativo"] == "monto" and campo.evidencia["cambiado_por"] == "llm"
