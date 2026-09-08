"""Tipado determinista de columnas que llegan como texto.

`decidir_tipo(valores)` mira una muestra de valores distintos y elige entero,
decimal (con coma o punto), fecha, fecha_hora, booleano o texto. Un tipo se
adopta si al menos UMBRAL_TIPADO de los valores convierte; el resto queda
NULL y se cuenta como invalido en el esquema (nunca se descarta la fila).
`expresion_sql` traduce la decision a SQL de DuckDB sobre la columna VARCHAR.
"""
import re
from dataclasses import dataclass, field
from datetime import datetime

UMBRAL_TIPADO = 0.95
TAMANIO_MUESTRA = 5000
MAX_DIGITOS_ENTERO = 18

TOKENS_NULOS = ("", "null", "none", "na", "n/a", "nan", "-", "s/d", "sin dato", "#n/a")

# Orden = prioridad: en Argentina 05/03 es 5 de marzo
FORMATOS_FECHA = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d", "%d.%m.%Y", "%d/%m/%y"]
FORMATOS_FECHA_HORA = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
]
VERDADEROS = {"si", "sí", "s", "true", "verdadero", "v", "yes", "y", "x"}
FALSOS = {"no", "n", "false", "falso", "f"}

_RE_ENTERO = re.compile(r"^[+-]?\d+$")
_RE_DECIMAL_PUNTO = re.compile(r"^[+-]?\d+\.\d+$")
_RE_DECIMAL_COMA = re.compile(r"^[+-]?(\d{1,3}(\.\d{3})+|\d+),\d+$")
_RE_MILES_PUNTO = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+$")
_RE_DECIMAL_EN_US = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$")
_RE_MONEDA = re.compile(r"^[$\s]+|\s+$|(?<=\d)\s+(?=\d)")


@dataclass
class DecisionTipo:
    tipo: str  # entero | decimal | fecha | fecha_hora | booleano | texto
    detalle: dict = field(default_factory=dict)


def _sin_moneda(valor: str) -> str:
    return re.sub(r"[$\s]", "", valor)


def _es_entero_seguro(valor: str) -> bool:
    if not _RE_ENTERO.match(valor):
        return False
    digitos = valor.lstrip("+-")
    # Con cero adelante es un codigo ("00123"), no una cantidad
    if len(digitos) > 1 and digitos.startswith("0"):
        return False
    return len(digitos) <= MAX_DIGITOS_ENTERO


def _decidir_decimal(valores: list[str]) -> DecisionTipo | None:
    limpios = [_sin_moneda(valor) for valor in valores]
    estilos = {
        "coma": sum(1 for v in limpios if _RE_DECIMAL_COMA.match(v) or _RE_MILES_PUNTO.match(v) or _RE_ENTERO.match(v)),
        "punto": sum(1 for v in limpios if _RE_DECIMAL_PUNTO.match(v) or _RE_ENTERO.match(v)),
        "en_us": sum(1 for v in limpios if _RE_DECIMAL_EN_US.match(v) or _RE_DECIMAL_PUNTO.match(v) or _RE_ENTERO.match(v)),
    }
    # "1.234" solo cuenta como miles si en la columna tambien hay comas decimales
    if not any("," in v for v in limpios):
        estilos["coma"] = 0
    mejor = max(estilos, key=lambda estilo: (estilos[estilo], estilo == "punto"))
    if estilos[mejor] / len(limpios) < UMBRAL_TIPADO:
        return None
    return DecisionTipo("decimal", {"estilo_decimal": mejor})


def _parsear_fecha(valor: str, formatos: list[str]) -> str | None:
    for formato in formatos:
        try:
            datetime.strptime(valor, formato)
            return formato
        except ValueError:
            continue
    return None


def _decidir_fecha(valores: list[str]) -> DecisionTipo | None:
    formatos = FORMATOS_FECHA_HORA + FORMATOS_FECHA
    usados: dict[str, int] = {}
    for valor in valores:
        formato = _parsear_fecha(valor, formatos)
        if formato is not None:
            usados[formato] = usados.get(formato, 0) + 1
    if sum(usados.values()) / len(valores) < UMBRAL_TIPADO:
        return None
    ordenados = sorted(usados, key=lambda formato: -usados[formato])
    tipo = "fecha_hora" if any("%H" in formato for formato in ordenados) else "fecha"
    return DecisionTipo(tipo, {"formatos": ordenados})


def decidir_tipo(valores: list[str]) -> DecisionTipo:
    """`valores`: muestra de valores DISTINTOS, no nulos, ya recortados."""
    valores = [valor for valor in valores if valor is not None and valor.strip() != ""]
    if not valores:
        return DecisionTipo("texto")
    minusculas = [valor.strip().lower() for valor in valores]
    if all(valor in VERDADEROS or valor in FALSOS for valor in minusculas):
        return DecisionTipo("booleano")
    if all(_es_entero_seguro(_sin_moneda(valor)) for valor in valores):
        return DecisionTipo("entero")
    if any(_RE_ENTERO.match(_sin_moneda(v)) and not _es_entero_seguro(_sin_moneda(v)) for v in valores) and all(
        _RE_ENTERO.match(_sin_moneda(v)) for v in valores
    ):
        return DecisionTipo("texto", {"motivo": "codigos con ceros adelante o demasiado largos"})
    decimal = _decidir_decimal(valores)
    if decimal is not None:
        return decimal
    fecha = _decidir_fecha(valores)
    if fecha is not None:
        return fecha
    return DecisionTipo("texto")


# ---------- SQL ----------
def columna_sql(nombre: str) -> str:
    return '"' + nombre.replace('"', '""') + '"'


def expresion_limpia(nombre: str) -> str:
    """Texto recortado, con los tokens de nulo convertidos a NULL."""
    tokens = ", ".join(f"'{token}'" for token in TOKENS_NULOS)
    columna = columna_sql(nombre)
    return f"(CASE WHEN lower(trim({columna})) IN ({tokens}) THEN NULL ELSE trim({columna}) END)"


def expresion_sql(nombre: str, decision: DecisionTipo) -> str:
    """Expresion que convierte la columna VARCHAR al tipo decidido. Lo que no
    convierte da NULL (TRY_CAST / TRY_STRPTIME), nunca error."""
    limpio = expresion_limpia(nombre)
    sin_moneda = f"regexp_replace({limpio}, '[$\\s]', '', 'g')"
    if decision.tipo == "entero":
        return f"TRY_CAST({sin_moneda} AS BIGINT)"
    if decision.tipo == "decimal":
        estilo = decision.detalle.get("estilo_decimal", "punto")
        if estilo == "coma":
            return f"TRY_CAST(replace(replace({sin_moneda}, '.', ''), ',', '.') AS DOUBLE)"
        if estilo == "en_us":
            return f"TRY_CAST(replace({sin_moneda}, ',', '') AS DOUBLE)"
        return f"TRY_CAST({sin_moneda} AS DOUBLE)"
    if decision.tipo in ("fecha", "fecha_hora"):
        intentos = ", ".join(f"TRY_STRPTIME({limpio}, '{formato}')" for formato in decision.detalle["formatos"])
        coalesce = f"COALESCE({intentos})"
        return f"CAST({coalesce} AS DATE)" if decision.tipo == "fecha" else f"CAST({coalesce} AS TIMESTAMP)"
    if decision.tipo == "booleano":
        verdaderos = ", ".join(f"'{v}'" for v in sorted(VERDADEROS))
        falsos = ", ".join(f"'{v}'" for v in sorted(FALSOS))
        return f"(CASE WHEN lower({limpio}) IN ({verdaderos}) THEN TRUE WHEN lower({limpio}) IN ({falsos}) THEN FALSE END)"
    return limpio


def tipo_duckdb(tipo: str) -> str:
    """Tipo DuckDB que produce cada tipo logico (para validar el Parquet)."""
    return {
        "entero": "BIGINT",
        "decimal": "DOUBLE",
        "fecha": "DATE",
        "fecha_hora": "TIMESTAMP",
        "booleano": "BOOLEAN",
        "texto": "VARCHAR",
    }[tipo]
