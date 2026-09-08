"""SpecDashboard: esquema, validacion contra el modelo (compilando cada
panel), filtros activos y armado de paneles. Puro."""
import copy
import json

import pytest

from app.dashboard import filtros as modulo_filtros
from app.dashboard import paneles, validacion
from app.dashboard.validacion import parsear_spec, validar_spec
from app.modelo.validacion import modelo_efectivo, parsear_modelo
from app.nucleo.errores import ErrorApp
from tests.conftest import DATOS_PRUEBA

MODELO = modelo_efectivo(parsear_modelo(json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))))
SPEC_BASE = json.loads((DATOS_PRUEBA / "spec.json").read_text(encoding="utf-8"))


@pytest.fixture
def spec() -> dict:
    return copy.deepcopy(SPEC_BASE)


def _codigos(spec_dict: dict) -> list[str]:
    return [error.codigo for error in validar_spec(parsear_spec(spec_dict), MODELO)]


def _grafico(spec_dict: dict, grafico_id: str) -> dict:
    return next(grafico for grafico in spec_dict["graficos"] if grafico["id"] == grafico_id)


def test_el_spec_a_mano_es_valido(spec):
    parseado = parsear_spec(spec)
    assert validar_spec(parseado, MODELO) == []
    assert parseado.resumen() == "5 filtros, 5 KPIs, 4 gráficos, 4 pestañas"
    assert parseado.grafico("g_mes").orden_efectivo == "dimension"
    assert parseado.grafico("g_vendedores").orden_efectivo == "metrica"


def test_clave_desconocida_e_ids(spec):
    spec["graficos"][0]["color"] = "rojo"
    with pytest.raises(ErrorApp) as error:
        parsear_spec(spec)
    assert error.value.codigo == "E-SPEC-01"
    assert error.value.extra["errores"][0]["codigo"] == validacion.JSON_INVALIDO

    spec = copy.deepcopy(SPEC_BASE)
    spec["kpis"][0]["id"] = "f_fecha"  # repetido con un filtro
    spec["explorador"]["pestanias"].append(copy.deepcopy(spec["explorador"]["pestanias"][0]))
    assert _codigos(spec).count(validacion.ID_DUPLICADO) == 2


def test_filtros_invalidos(spec):
    spec["filtros"][0]["campo"] = "ventas.importe"  # rango de fecha sobre un decimal
    spec["filtros"][1]["tipo"] = "rango_fecha"  # lista de sucursal como rango
    spec["filtros"][2]["campo"] = "vendedores.legajo"
    spec["filtros"][3] = {"id": "f_x", "campo": "ventas.fecha", "tipo": "lista"}
    assert _codigos(spec) == [validacion.FILTRO_TIPO, validacion.FILTRO_TIPO, validacion.FILTRO_CAMPO, validacion.FILTRO_TIPO]


def test_kpi_y_grafico_con_referencias_rotas(spec):
    spec["kpis"][0]["metrica"] = "ganancia"
    _grafico(spec, "g_vendedores")["metrica"] = "ganancia"
    _grafico(spec, "g_categorias")["dimension"] = "productos.rubro"
    assert _codigos(spec) == [validacion.KPI_METRICA, validacion.GRAFICO_METRICA, validacion.GRAFICO_DIMENSION]


def test_granularidad_obligatoria_en_fechas_y_prohibida_en_lo_demas(spec):
    del _grafico(spec, "g_mes")["granularidad"]
    _grafico(spec, "g_categorias")["granularidad"] = "mes"
    assert _codigos(spec) == [validacion.GRAFICO_GRANULARIDAD, validacion.GRAFICO_GRANULARIDAD]


def test_un_grafico_que_multiplica_filas_no_pasa(spec):
    _grafico(spec, "g_medios")["metrica"] = "total_ventas"  # ventas por medio de pago
    errores = validar_spec(parsear_spec(spec), MODELO)
    assert [error.codigo for error in errores] == [validacion.CONSULTA]
    assert errores[0].ubicacion == "graficos.g_medios"
    assert "multiplicaría filas" in errores[0].mensaje


def test_pestanias_invalidas(spec):
    pestanias = spec["explorador"]["pestanias"]
    pestanias[0]["columnas"].append("marca")
    pestanias[1]["metricas"].append("ganancia")
    pestanias.append({"entidad": "sucursales", "columnas": ["nombre"]})
    # medios_pago con total_ventas: la metrica no llega a la entidad base sin multiplicar
    pestanias.append({"entidad": "medios_pago", "columnas": ["nombre"], "metricas": ["total_ventas"]})
    assert _codigos(spec) == [
        validacion.PESTANIA_COLUMNA,
        validacion.PESTANIA_METRICA,
        validacion.PESTANIA_ENTIDAD,
        validacion.CONSULTA,
    ]


def test_un_filtro_que_ningun_panel_puede_aplicar(spec):
    # Sin relacion con nada: una entidad aislada en el modelo no existe en el
    # de prueba, asi que simulamos con un modelo sin la relacion pagos_venta.
    modelo_json = json.loads((DATOS_PRUEBA / "modelo.json").read_text(encoding="utf-8"))
    modelo_json["relaciones"] = [r for r in modelo_json["relaciones"] if r["id"] != "pagos_venta"]
    modelo_partido = modelo_efectivo(parsear_modelo(modelo_json))
    errores = validar_spec(parsear_spec(spec), modelo_partido)
    # El filtro por medio de pago ya no llega a ventas: KPIs y graficos de ventas fallan
    ubicaciones = {error.ubicacion for error in errores if error.codigo == validacion.CONSULTA}
    assert "kpis" in ubicaciones and "graficos.g_mes" in ubicaciones


# ---------- Filtros activos ----------
def test_filtros_activos_a_filtros_de_consulta(spec):
    parseado = parsear_spec(spec)
    activos = modulo_filtros.parsear_filtros_activos('{"f_fecha": ["2026-01-01", null], "f_sucursal": ["Norte"], "f_vendedor": [], "f_categoria": null}')
    filtros = modulo_filtros.a_filtros_de_consulta(parseado, activos)
    assert [(f.campo, f.operador, f.valor) for f in filtros] == [
        ("ventas.fecha", "entre", ["2026-01-01", None]),
        ("vendedores.sucursal", "en", ["Norte"]),
    ]
    assert modulo_filtros.parsear_filtros_activos(None) == {}
    assert modulo_filtros.a_filtros_de_consulta(parseado, {"f_fecha": [None, None]}) == []


@pytest.mark.parametrize(
    "crudo, codigo",
    [("no es json", "E-CONS-06"), ("[1, 2]", "E-CONS-06")],
)
def test_filtros_activos_mal_formados(crudo, codigo):
    with pytest.raises(ErrorApp) as error:
        modulo_filtros.parsear_filtros_activos(crudo)
    assert error.value.codigo == codigo


@pytest.mark.parametrize(
    "activos, codigo",
    [
        ({"f_nada": ["x"]}, "E-SPEC-04"),
        ({"f_fecha": "2026-01-01"}, "E-CONS-06"),
        ({"f_fecha": ["2026-01-01"]}, "E-CONS-06"),
        ({"f_sucursal": "Norte"}, "E-CONS-06"),
    ],
)
def test_valores_de_filtro_invalidos(spec, activos, codigo):
    with pytest.raises(ErrorApp) as error:
        modulo_filtros.a_filtros_de_consulta(parsear_spec(spec), activos)
    assert error.value.codigo == codigo


# ---------- Paneles ----------
def test_columnas_del_explorador_anteponen_la_clave_oculta(spec):
    parseado = parsear_spec(spec)
    columnas = paneles.columnas_explorador(MODELO, parseado.pestania("ventas"))
    assert [(c.alias, c.campo, c.oculta) for c in columnas][:3] == [
        ("__pk_id_venta", "ventas.id_venta", True),
        ("fecha", "ventas.fecha", False),
        ("importe", "ventas.importe", False),
    ]
    assert columnas[-1].campo == "productos.nombre"
    consulta, _ = paneles.consulta_explorador(MODELO, parseado.pestania("ventas"), [], pagina=3, tamanio=20)
    assert (consulta.entidad_base, consulta.limite, consulta.desplazamiento) == ("ventas", 20, 40)
    assert consulta.orden[0].por == "__pk_id_venta"
    with pytest.raises(ErrorApp) as error:
        paneles.consulta_explorador(MODELO, parseado.pestania("ventas"), [], orden_por="precio")
    assert error.value.codigo == "E-CONS-08"


def test_consulta_de_grafico_ordena_segun_el_tipo(spec):
    parseado = parsear_spec(spec)
    linea = paneles.consulta_grafico(parseado.grafico("g_mes"), [])
    assert linea.orden[0].por == "dimension" and linea.orden[0].direccion == "asc" and linea.limite is None
    barras = paneles.consulta_grafico(parseado.grafico("g_vendedores"), [])
    assert barras.orden[0].por == "total_ventas" and barras.orden[0].direccion == "desc" and barras.limite == 10
