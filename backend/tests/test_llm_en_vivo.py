"""Prueba EN VIVO contra la API de Anthropic. Se salta sin ANTHROPIC_API_KEY.
El pytest.ini lo deselecciona (`-m "not en_vivo"`); correr a mano antes de
cerrar un paso que toque el prompt:

    ../.venv/Scripts/python.exe -m pytest tests/test_llm_en_vivo.py -m en_vivo -s

Gasta unos centavos (perfil + 5 filas de muestra por tabla)."""
import duckdb
import pytest

from app.inferencia.heuristicas import FuentePerfilada, proponer_modelo
from app.inferencia.llm import fijar_cliente_llm, obtener_cliente_llm
from app.inferencia.semantica import aplicar_semantica, armar_pedido, consultar_semantica
from app.ingesta.procesador import ingestar_archivo
from app.modelo.validacion import validar_estructura
from app.nucleo.config import obtener_configuracion
from app.perfilado import PerfilFuente
from scripts.generar_datos_prueba import generar

pytestmark = pytest.mark.en_vivo


@pytest.mark.skipif(not obtener_configuracion().anthropic_api_key, reason="sin ANTHROPIC_API_KEY")
def test_claude_propone_semantica_valida_sobre_los_5_csv(tmp_path):
    conexion = duckdb.connect()
    fuentes, perfiles, muestras = [], {}, {}
    for nombre, ruta in generar(tmp_path / "csv").items():
        directorio = tmp_path / f"ingesta_{nombre}"
        directorio.mkdir()
        resultado = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
        uri = resultado.ruta_parquet_temporal.as_posix()
        conexion.execute(f'CREATE VIEW "{resultado.nombre_tabla}" AS SELECT * FROM read_parquet(\'{uri}\')')
        perfil = PerfilFuente.model_validate(resultado.perfil)
        perfiles[resultado.nombre_tabla] = perfil
        fuentes.append(FuentePerfilada(resultado.nombre_tabla, resultado.esquema_como_dicts(), perfil))
        filas = conexion.execute(f'SELECT * FROM "{resultado.nombre_tabla}" LIMIT 5').fetchall()
        columnas = [c["nombre"] for c in resultado.esquema_como_dicts()]
        muestras[resultado.nombre_tabla] = [dict(zip(columnas, map(str, fila))) for fila in filas]
    modelo = proponer_modelo(conexion, fuentes)

    fijar_cliente_llm(None)  # el conftest instala un cliente falso en todos los tests; aca queremos el real
    cliente = obtener_cliente_llm()
    respuesta, cruda = consultar_semantica(cliente, modelo, armar_pedido(modelo, perfiles, muestras))
    enriquecido = aplicar_semantica(modelo, respuesta)

    print(f"\nClaude {cruda.modelo}: {cruda.tokens_entrada} tokens de entrada, {cruda.tokens_salida} de salida")
    for entidad in enriquecido.entidades:
        print(f"  {entidad.id}: {entidad.nombre!r} ({entidad.tipo}) sinonimos={entidad.sinonimos}")
        for campo in entidad.campos:
            print(f"      {campo.id}: {campo.nombre!r} {campo.tipo_semantico} {campo.confianza}")
    for metrica in enriquecido.metricas:
        print(f"  metrica {metrica.id}: {metrica.nombre!r} {metrica.expresion} {metrica.formato}")

    assert validar_estructura(enriquecido) == []
    assert 3 <= len(enriquecido.metricas) <= 8
    assert enriquecido.entidad("ventas").tipo == "hechos" and enriquecido.entidad("productos").tipo == "dimension"
    assert all(entidad.nombre and entidad.nombre[0].isupper() for entidad in enriquecido.entidades)
    assert cruda.tokens_entrada < 20000, "el pedido tiene que seguir siendo compacto"


@pytest.mark.skipif(not obtener_configuracion().anthropic_api_key, reason="sin ANTHROPIC_API_KEY")
def test_claude_cura_el_spec_base_sobre_los_5_csv(tmp_path):
    """Mismo dataset que la prueba de semantica, pero para la curacion del
    spec (paso 14): perfilar, proponer, confirmar todo, generar el spec base
    y pedirle a Claude que lo cure."""
    from app.dashboard.generador import generar_spec_base
    from app.dashboard.validacion import validar_spec
    from app.inferencia.spec import aplicar_curacion, armar_pedido as armar_pedido_spec, consultar_curacion
    from app.modelo.validacion import modelo_efectivo

    conexion = duckdb.connect()
    fuentes, perfiles, muestras = [], {}, {}
    for nombre, ruta in generar(tmp_path / "csv").items():
        directorio = tmp_path / f"ingesta_{nombre}"
        directorio.mkdir()
        resultado = ingestar_archivo(ruta.read_bytes(), ruta.name, directorio)[0]
        uri = resultado.ruta_parquet_temporal.as_posix()
        conexion.execute(f'CREATE VIEW "{resultado.nombre_tabla}" AS SELECT * FROM read_parquet(\'{uri}\')')
        perfil = PerfilFuente.model_validate(resultado.perfil)
        perfiles[resultado.nombre_tabla] = perfil
        fuentes.append(FuentePerfilada(resultado.nombre_tabla, resultado.esquema_como_dicts(), perfil))
        filas = conexion.execute(f'SELECT * FROM "{resultado.nombre_tabla}" LIMIT 5').fetchall()
        columnas = [c["nombre"] for c in resultado.esquema_como_dicts()]
        muestras[resultado.nombre_tabla] = [dict(zip(columnas, map(str, fila))) for fila in filas]
    modelo = proponer_modelo(conexion, fuentes)

    fijar_cliente_llm(None)
    cliente = obtener_cliente_llm()
    respuesta, _ = consultar_semantica(cliente, modelo, armar_pedido(modelo, perfiles, muestras))
    modelo = aplicar_semantica(modelo, respuesta)
    # Confirmar todo (equivalente a "Confirmar todo lo verde" del wizard) para
    # que el modelo efectivo tenga metricas y dimensiones
    contenido = modelo.model_dump()
    for entidad in contenido["entidades"]:
        for campo in entidad["campos"]:
            campo["estado"] = "confirmada"
    for relacion in contenido["relaciones"]:
        relacion["estado"] = "confirmada"
    for metrica in contenido["metricas"]:
        metrica["estado"] = "confirmada"
    from app.modelo.esquema import ModeloSemantico

    efectivo = modelo_efectivo(ModeloSemantico.model_validate(contenido))
    base = generar_spec_base(efectivo)
    assert validar_spec(base, efectivo) == []

    curado, cruda = consultar_curacion(cliente, base, armar_pedido_spec(base, efectivo))
    final = aplicar_curacion(base, curado)

    print(f"\nClaude {cruda.modelo}: {cruda.tokens_entrada} tokens de entrada, {cruda.tokens_salida} de salida")
    print(f"titulo: {final.titulo!r}")
    print("kpis:", [(k.id, k.titulo) for k in final.kpis])
    print("graficos:", [(g.id, g.titulo) for g in final.graficos], "(base tenia", len(base.graficos), ")")
    print("pestanias:", [(p.entidad, p.titulo) for p in final.explorador.pestanias])

    assert validar_spec(final, efectivo) == []
    assert final.titulo and len(final.kpis) == len(base.kpis) and len(final.explorador.pestanias) == len(base.explorador.pestanias)
    assert 1 <= len(final.graficos) <= len(base.graficos)
    assert cruda.tokens_entrada < 8000, "el pedido de curacion tiene que ser chico"


@pytest.mark.skipif(not obtener_configuracion().anthropic_api_key, reason="sin ANTHROPIC_API_KEY")
def test_claude_usa_las_herramientas_del_asistente(cliente, datos, ingresar, cargar_datos_prueba, modelo_prueba, spec_prueba, sesion_db, almacen_temporal):
    """El motor del asistente (paso 19) contra Claude de verdad: le pedimos
    en criollo que cree una métrica y un gráfico, y que conteste una
    pregunta sobre los datos reales."""
    from app.asistente import motor
    from app.catalogo.tablas import Workspace
    from app.dashboard import operaciones as dashboard_operaciones

    ingresar("constructor@acme.test")
    workspace_id = datos.acme_workspace_id
    cargar_datos_prueba(workspace_id)
    assert cliente.put(f"/api/workspaces/{workspace_id}/modelo", json=modelo_prueba).status_code == 201
    assert cliente.put(f"/api/workspaces/{workspace_id}/dashboard", json=spec_prueba).status_code == 201
    workspace = sesion_db.get(Workspace, workspace_id)

    fijar_cliente_llm(None)  # el conftest instala un cliente falso en todos los tests; aca queremos el real
    cliente_llm = obtener_cliente_llm()

    respuesta = motor.conversar(
        cliente_llm,
        usuario=datos.acme_constructor,
        sesion=sesion_db,
        workspace=workspace,
        almacen=almacen_temporal,
        mensaje="Creá un gráfico de barras del total de ventas por sucursal.",
        contexto=motor.armar_contexto(sesion_db, workspace),
    )
    print(f"\nrespuesta: {respuesta.texto}")
    print("acciones:", [(a.herramienta, a.entrada, a.resultado) for a in respuesta.acciones])
    print(f"tokens: {respuesta.tokens_entrada} entrada, {respuesta.tokens_salida} salida")
    assert any(a.herramienta == "crear_grafico" for a in respuesta.acciones)
    spec_actual = dashboard_operaciones.spec_de(dashboard_operaciones.exigir_version_actual(sesion_db, workspace))
    assert any(g.dimension == "vendedores.sucursal" for g in spec_actual.graficos)

    respuesta_pregunta = motor.conversar(
        cliente_llm,
        usuario=datos.acme_visualizador,
        sesion=sesion_db,
        workspace=workspace,
        almacen=almacen_temporal,
        mensaje="¿Cuántas ventas hubo en total?",
        contexto=motor.armar_contexto(sesion_db, workspace),
    )
    print(f"\nrespuesta pregunta: {respuesta_pregunta.texto}")
    assert any(a.herramienta == "consultar" for a in respuesta_pregunta.acciones)
    assert "3000" in respuesta_pregunta.texto or "3.000" in respuesta_pregunta.texto
