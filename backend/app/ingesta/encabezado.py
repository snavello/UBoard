"""Separador, fila de encabezado y nombres de columna.

Heuristicas deterministas sobre las primeras lineas del archivo. Nada de
esto usa IA: es lo que un humano hace mirando el archivo en un editor.
"""
import csv
import re
import unicodedata

DELIMITADORES = [",", ";", "\t", "|"]
MAX_LINEAS_MUESTRA = 200
LARGO_MAXIMO_NOMBRE = 60

_RE_NUMERO = re.compile(r"^[+-]?[\d.,]+$")


def dividir(linea: str, delimitador: str) -> list[str]:
    """Separa respetando comillas ("a;b" cuenta como un campo)."""
    return next(csv.reader([linea], delimiter=delimitador, quotechar='"'), [])


def detectar_delimitador(lineas: list[str]) -> str:
    """El delimitador que parte la mayor cantidad de lineas en el mismo numero
    de campos (con al menos 2). Empate: el que da mas campos."""
    mejor, mejor_puntaje = ",", (0, 0)
    for delimitador in DELIMITADORES:
        conteos = [len(dividir(linea, delimitador)) for linea in lineas if linea.strip()]
        validos = [conteo for conteo in conteos if conteo >= 2]
        if not validos:
            continue
        moda = max(set(validos), key=validos.count)
        puntaje = (sum(1 for conteo in conteos if conteo == moda), moda)
        if puntaje > mejor_puntaje:
            mejor, mejor_puntaje = delimitador, puntaje
    return mejor


def _celdas_con_dato(fila: list[str | None]) -> int:
    return sum(1 for celda in fila if celda is not None and str(celda).strip())


def _parece_encabezado(fila: list[str | None]) -> bool:
    """Un encabezado tiene mayoria de celdas que no son numeros y sin repetidas."""
    celdas = [str(celda).strip() for celda in fila if celda is not None and str(celda).strip()]
    if not celdas:
        return False
    textos = [celda for celda in celdas if not _RE_NUMERO.match(celda)]
    return len(textos) * 2 >= len(celdas) and len(set(c.lower() for c in celdas)) == len(celdas)


def detectar_fila_encabezado(filas: list[list[str | None]]) -> tuple[int | None, bool]:
    """Devuelve (indice de la fila de encabezado, tiene_encabezado).

    La tabla empieza en la primera fila cuyo ancho (celdas con dato) coincide
    con el ancho mas frecuente del archivo: las filas de titulo tipo "Listado
    de pagos" tienen 1 o 2 celdas y quedan afuera. Si esa fila parece datos
    (mayoria de numeros), no hay encabezado y los nombres se generan.
    (None, False) si no hay ninguna fila con dato."""
    con_dato = [(indice, fila) for indice, fila in enumerate(filas) if _celdas_con_dato(fila) > 0]
    if not con_dato:
        return None, False
    anchos = [_celdas_con_dato(fila) for _, fila in con_dato]
    candidatos = [ancho for ancho in anchos if ancho >= 2] or anchos
    moda = max(set(candidatos), key=candidatos.count)
    for posicion, (indice, fila) in enumerate(con_dato):
        if anchos[posicion] == moda:
            return indice, _parece_encabezado(fila)
    return con_dato[0][0], _parece_encabezado(con_dato[0][1])


def normalizar_nombre_columna(nombre: str | None, posicion: int) -> str:
    """'IdVenta' -> 'id_venta', 'Precio Unitario' -> 'precio_unitario',
    'Año' -> 'anio', '' -> 'columna_3'. Identificador seguro para SQL."""
    texto = (nombre or "").strip()
    texto = texto.replace("ñ", "ni").replace("Ñ", "Ni")
    texto = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", texto)  # CamelCase -> Camel_Case
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    if not texto:
        return f"columna_{posicion + 1}"
    if texto[0].isdigit():
        texto = f"c_{texto}"
    return texto[:LARGO_MAXIMO_NOMBRE]


def nombres_unicos(nombres: list[str]) -> list[str]:
    """Repetidos reciben sufijo _2, _3, ..."""
    vistos: dict[str, int] = {}
    resultado = []
    for nombre in nombres:
        if nombre in vistos:
            vistos[nombre] += 1
            candidato = f"{nombre}_{vistos[nombre]}"
            while candidato in vistos:
                vistos[nombre] += 1
                candidato = f"{nombre}_{vistos[nombre]}"
            vistos[candidato] = 1
            resultado.append(candidato)
        else:
            vistos[nombre] = 1
            resultado.append(nombre)
    return resultado


def nombres_de_columnas(encabezado: list[str | None]) -> list[str]:
    return nombres_unicos([normalizar_nombre_columna(celda, posicion) for posicion, celda in enumerate(encabezado)])
