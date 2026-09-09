"""Fusionar una propuesta nueva con un modelo trabajado: lo confirmado y lo
rechazado se respeta, lo propuesto se reemplaza, lo nuevo entra."""
from app.inferencia.fusion import fusionar
from app.modelo.esquema import ModeloSemantico


def _campo(id, tipo="texto", **extra):
    base = {"id": id, "columna_origen": id, "nombre": id, "tipo_dato": tipo, "tipo_semantico": "categoria", "origen": "heuristica", "estado": "propuesta", "confianza": 0.7}
    return {**base, **extra}


def _modelo(**cambios) -> ModeloSemantico:
    base = {
        "entidades": [
            {
                "id": "ventas",
                "nombre": "Ventas",
                "fuente": "ventas",
                "tipo": "hechos",
                "clave_primaria": ["id_venta"],
                "campos": [
                    _campo("id_venta", "entero", tipo_semantico="identificador", estado="confirmada", confianza=0.98),
                    _campo("vendedor", "entero", tipo_semantico="clave_foranea", confianza=0.9),
                    _campo("importe", "decimal", tipo_semantico="monto", confianza=0.9),
                ],
            },
            {
                "id": "vendedores",
                "nombre": "Vendedores",
                "fuente": "vendedores",
                "tipo": "dimension",
                "clave_primaria": ["id_vendedor"],
                "campos": [
                    _campo("id_vendedor", "entero", tipo_semantico="identificador", estado="confirmada", confianza=0.98),
                    _campo("nombre", confianza=0.9),
                ],
            },
        ],
        "relaciones": [
            {"id": "ventas_vendedor", "desde": {"entidad": "ventas", "campo": "vendedor"}, "hacia": {"entidad": "vendedores", "campo": "id_vendedor"}, "confianza": 0.9, "estado": "propuesta", "evidencia": {"inclusion": 0.98}}
        ],
        "metricas": [
            {"id": "total_importe", "nombre": "Total importe", "expresion": {"agregacion": "suma", "campo": "ventas.importe"}, "formato": "moneda", "origen": "heuristica", "estado": "propuesta", "confianza": 0.85}
        ],
        "dimensiones_tiempo": [],
    }
    return ModeloSemantico.model_validate({**base, **cambios})


def test_sin_modelo_previo_la_propuesta_queda_tal_cual():
    propuesta = _modelo()
    assert fusionar(None, propuesta) == propuesta


def test_lo_confirmado_y_lo_rechazado_se_respeta_y_lo_propuesto_se_actualiza():
    existente = _modelo()
    ventas = existente.entidad("ventas")
    ventas.nombre = "Operaciones"  # atributo de entidad tocado por el usuario
    ventas.campo("importe").estado = "confirmada"
    ventas.campo("importe").nombre = "Monto facturado"
    ventas.campo("vendedor").estado = "rechazada"
    existente.relaciones[0].estado = "confirmada"
    existente.metricas[0].estado = "rechazada"

    propuesta = _modelo()
    propuesta.entidad("ventas").campo("importe").nombre = "Importe (heuristica de nuevo)"
    propuesta.entidad("ventas").campo("vendedor").confianza = 0.95
    propuesta.entidad("vendedores").campo("nombre").confianza = 0.6  # evidencia fresca
    propuesta.relaciones[0].evidencia = {"inclusion": 0.99}

    fusionado = fusionar(existente, propuesta)
    ventas_f = fusionado.entidad("ventas")
    assert ventas_f.nombre == "Operaciones"
    assert ventas_f.campo("importe").estado == "confirmada" and ventas_f.campo("importe").nombre == "Monto facturado"
    assert ventas_f.campo("vendedor").estado == "rechazada" and ventas_f.campo("vendedor").confianza == 0.9
    assert fusionado.entidad("vendedores").campo("nombre").confianza == 0.6, "lo propuesto toma la evidencia nueva"
    assert fusionado.relaciones[0].estado == "confirmada" and fusionado.relaciones[0].evidencia == {"inclusion": 0.98}
    assert fusionado.metricas[0].estado == "rechazada"


def test_lo_nuevo_entra_y_lo_propuesto_que_desaparece_se_va():
    existente = _modelo()
    existente.metricas.append(
        existente.metricas[0].model_copy(update={"id": "mia", "origen": "usuario", "estado": "confirmada"})
    )
    propuesta = _modelo()
    propuesta.metricas = []  # la heuristica ya no propone total_importe
    propuesta.entidades[0].campos.append(propuesta.entidades[0].campos[2].model_copy(update={"id": "descuento", "columna_origen": "descuento"}))
    propuesta.dimensiones_tiempo = []
    propuesta.entidades.append(
        propuesta.entidades[1].model_copy(update={"id": "sucursales", "fuente": "sucursales", "nombre": "Sucursales"})
    )

    fusionado = fusionar(existente, propuesta)
    assert [metrica.id for metrica in fusionado.metricas] == ["mia"], "la del usuario queda, la propuesta vieja se va"
    assert fusionado.entidad("ventas").campo("descuento") is not None
    assert [entidad.id for entidad in fusionado.entidades] == ["ventas", "vendedores", "sucursales"]


def test_una_fuente_que_ya_no_esta_se_va_con_sus_relaciones_propuestas():
    existente = _modelo()
    propuesta = _modelo()
    propuesta.entidades = [propuesta.entidades[0]]
    propuesta.relaciones = []
    fusionado = fusionar(existente, propuesta)
    assert [entidad.id for entidad in fusionado.entidades] == ["ventas"]
    assert fusionado.relaciones == []


def test_el_id_de_un_campo_propuesto_se_conserva_aunque_cambie_la_propuesta():
    """Las relaciones y metricas referencian ids de campo: si el usuario no
    toco el campo pero la heuristica lo repropone, el id no cambia."""
    existente = _modelo()
    propuesta = _modelo()
    propuesta.entidad("ventas").campo("importe").id = "importe_v2"
    fusionado = fusionar(existente, propuesta)
    assert fusionado.entidad("ventas").campo("importe") is not None
    assert fusionado.entidad("ventas").campo("importe_v2") is None


def test_las_referencias_de_la_propuesta_se_traducen_a_los_ids_del_modelo_existente():
    """El modelo a mano llama `id_vendedor` al campo de la columna `vendedor`;
    la heuristica lo llama `vendedor`. La relacion propuesta tiene que apuntar
    a `ventas.id_vendedor`, y no puede chocar por id con la confirmada."""
    from app.modelo.validacion import validar_estructura

    existente = _modelo()
    ventas = existente.entidad("ventas")
    campo_vendedor = ventas.campo("vendedor")
    campo_vendedor.id = "id_vendedor"
    campo_vendedor.estado = "confirmada"
    existente.relaciones[0].desde.campo = "id_vendedor"
    existente.relaciones[0].estado = "confirmada"
    existente.metricas[0].id = "facturacion"
    existente.metricas[0].estado = "confirmada"
    existente.dimensiones_tiempo = []

    propuesta = _modelo()  # con `vendedor`, relacion `ventas_vendedor` y metrica `total_importe`
    propuesta.entidades[0].campos[2].id = "importe_x"  # y un id distinto para importe, para forzar la traduccion
    propuesta.metricas[0].expresion.campo = "ventas.importe_x"

    fusionado = fusionar(existente, propuesta)
    assert validar_estructura(fusionado) == []
    assert fusionado.entidad("ventas").campo("id_vendedor") is not None and fusionado.entidad("ventas").campo("vendedor") is None
    assert [(r.id, r.desde.referencia, r.estado) for r in fusionado.relaciones] == [("ventas_vendedor", "ventas.id_vendedor", "confirmada")]
    assert {m.id: m.expresion.campo for m in fusionado.metricas} == {"facturacion": "ventas.importe", "total_importe": "ventas.importe"}
