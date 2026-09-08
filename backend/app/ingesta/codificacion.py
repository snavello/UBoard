"""Deteccion de encoding. UTF-8 primero (el caso comun, y decodificar es la
prueba definitiva); si falla, charset-normalizer; si tampoco, cp1252, que es
lo que exportan Excel y los sistemas viejos en Argentina."""
import codecs

from charset_normalizer import from_bytes

ENCODING_POR_DEFECTO = "cp1252"
# Las codepages de un byte se parecen todas y el detector las confunde con
# frecuencia (en un archivo chico eligio cp775, baltico, para texto en
# castellano). Solo se le cree cuando detecta un encoding multibyte; para todo
# lo demas la respuesta correcta en Argentina es cp1252, superconjunto de
# latin-1 en lo imprimible.
_MULTIBYTE_CONFIABLES = {
    "utf_16", "utf_16_le", "utf_16_be", "utf_32", "utf_32_le", "utf_32_be", "utf_7",
    "gb2312", "gbk", "gb18030", "big5", "big5hkscs", "shift_jis", "cp932", "euc_jp", "euc_kr", "cp949",
}


def decodificar(datos: bytes) -> tuple[str, str]:
    """Devuelve (texto, encoding usado). Quita el BOM si lo hay."""
    if datos.startswith(codecs.BOM_UTF8):
        return datos[len(codecs.BOM_UTF8) :].decode("utf-8", errors="replace"), "utf-8-sig"
    if datos.startswith(codecs.BOM_UTF16_LE) or datos.startswith(codecs.BOM_UTF16_BE):
        return datos.decode("utf-16", errors="replace"), "utf-16"
    try:
        return datos.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        pass
    mejor = from_bytes(datos).best()
    encoding = (mejor.encoding if mejor is not None else None) or ENCODING_POR_DEFECTO
    if encoding.lower().replace("-", "_") not in _MULTIBYTE_CONFIABLES:
        encoding = ENCODING_POR_DEFECTO
    try:
        return datos.decode(encoding), encoding
    except (UnicodeDecodeError, LookupError):
        return datos.decode(ENCODING_POR_DEFECTO, errors="replace"), ENCODING_POR_DEFECTO
