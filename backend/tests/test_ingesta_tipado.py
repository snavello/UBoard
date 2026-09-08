"""Decision de tipo por columna y las expresiones SQL que convierten. Puro,
con DuckDB en memoria."""
from datetime import date, datetime

import duckdb
import pytest

from app.ingesta.tipado import DecisionTipo, decidir_tipo, expresion_limpia, expresion_sql


def _convertir(valores: list[str | None], decision: DecisionTipo | None = None) -> list:
    """Aplica la expresion SQL de la decision (o la que decida el tipado) a la
    lista de valores y devuelve los resultados en orden."""
    conexion = duckdb.connect()
    conexion.execute("CREATE TABLE t (orden INTEGER, v VARCHAR)")
    conexion.executemany("INSERT INTO t VALUES (?, ?)", list(enumerate(valores)))
    if decision is None:
        muestra = [fila[0] for fila in conexion.execute(f"SELECT DISTINCT {expresion_limpia('v')} FROM t").fetchall()]
        decision = decidir_tipo([valor for valor in muestra if valor is not None])
    filas = conexion.execute(f"SELECT {expresion_sql('v', decision)} FROM t ORDER BY orden").fetchall()
    return [fila[0] for fila in filas]


def test_enteros_con_signo_y_moneda():
    decision = decidir_tipo(["1", "2", "-3", "$ 4", " 5 "])
    assert decision.tipo == "entero"
    # Un valor que no convierte queda NULL, la fila no se pierde
    assert _convertir(["1", "2", "-3", "$ 4", "abc", None], decision) == [1, 2, -3, 4, None, None]


def test_codigos_con_ceros_adelante_son_texto():
    decision = decidir_tipo(["00123", "00456", "789"])
    assert decision.tipo == "texto"
    assert _convertir(["00123", "00456"]) == ["00123", "00456"]


def test_enteros_demasiado_largos_son_texto():
    assert decidir_tipo(["12345678901234567890", "1"]).tipo == "texto"


def test_decimal_con_punto():
    decision = decidir_tipo(["1250.50", "3.10", "7"])
    assert decision == DecisionTipo("decimal", {"estilo_decimal": "punto"})
    assert _convertir(["1250.50", "3.10", "7", "x"], decision) == [1250.5, 3.1, 7.0, None]


def test_decimal_con_coma_y_punto_de_miles():
    decision = decidir_tipo(["1.250,50", "3,10", "12", "$ 1.000.000,00"])
    assert decision == DecisionTipo("decimal", {"estilo_decimal": "coma"})
    assert _convertir(["1.250,50", "3,10", "12", "$ 1.000.000,00"]) == [1250.5, 3.1, 12.0, 1000000.0]


def test_decimal_estilo_en_us():
    decision = decidir_tipo(["1,250.50", "3.10", "2,000"])
    assert decision == DecisionTipo("decimal", {"estilo_decimal": "en_us"})
    assert _convertir(["1,250.50", "3.10", "2,000"]) == [1250.5, 3.1, 2000.0]


def test_miles_con_punto_sin_coma_se_leen_como_decimal_punto():
    # "1.234" sin ninguna coma en la columna es 1.234, no 1234
    assert decidir_tipo(["1.234", "5.5"]).detalle["estilo_decimal"] == "punto"


def test_fechas_mezcladas_hasta_el_umbral():
    # La muestra son valores DISTINTOS: 30 ISO, 10 dd/mm/aaaa, 3 d/m/aaaa
    valores = (
        [f"2026-03-{dia:02d}" for dia in range(1, 31)]
        + [f"{dia:02d}/04/2026" for dia in range(1, 11)]
        + [f"{dia}/5/2026" for dia in range(1, 4)]
    )
    decision = decidir_tipo(valores)
    assert decision.tipo == "fecha"
    assert decision.detalle["formatos"][0] == "%Y-%m-%d"  # el mas frecuente primero
    assert set(decision.detalle["formatos"]) == {"%Y-%m-%d", "%d/%m/%Y"}
    assert _convertir(["2026-03-05", "05/03/2026", "5/3/2026", "ayer"], decision) == [
        date(2026, 3, 5),
        date(2026, 3, 5),
        date(2026, 3, 5),
        None,
    ]


def test_dia_mes_antes_que_mes_dia():
    # 05/03 es 5 de marzo (es-AR), no 3 de mayo
    assert _convertir(["05/03/2026"]) == [date(2026, 3, 5)]


def test_columna_con_muchas_fechas_invalidas_queda_como_texto():
    valores = [f"2026-01-{dia:02d}" for dia in range(1, 21)] + ["s/f", "pendiente", "??", "no aplica", "-"]
    assert decidir_tipo(valores).tipo == "texto"


def test_fecha_hora():
    decision = decidir_tipo(["2026-01-01 10:00:00", "2026-01-02 11:30:00", "2026-01-03T08:15:00"])
    assert decision.tipo == "fecha_hora"
    assert _convertir(["2026-01-01 10:00:00", "basura"], decision) == [datetime(2026, 1, 1, 10, 0, 0), None]


def test_booleanos_si_no():
    decision = decidir_tipo(["Si", "No", "si", "NO", "Sí"])
    assert decision.tipo == "booleano"
    assert _convertir(["Si", "No", "si", "NO", "Sí", "quizas", None], decision) == [True, False, True, False, True, None, None]
    # Si aparece un valor que no es si/no, la columna entera es texto
    assert decidir_tipo(["Si", "No", "quizas"]).tipo == "texto"
    assert decidir_tipo(["true", "false"]).tipo == "booleano"
    # 1/0 son enteros, no booleanos
    assert decidir_tipo(["1", "0"]).tipo == "entero"


def test_todo_nulo_o_vacio_es_texto():
    assert decidir_tipo([]).tipo == "texto"
    assert decidir_tipo(["", "  "]).tipo == "texto"


def test_mezcla_sin_mayoria_es_texto():
    assert decidir_tipo(["12", "hola", "2026-01-01", "3,5"]).tipo == "texto"


def test_expresion_limpia_convierte_tokens_de_nulo():
    assert _convertir(["  hola ", "NULL", "-", "n/a", "", "  ", "s/d"], DecisionTipo("texto")) == [
        "hola",
        None,
        None,
        None,
        None,
        None,
        None,
    ]
