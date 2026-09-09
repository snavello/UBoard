"""Fusionar una propuesta nueva con el modelo que ya existe (decision de Sd:
volver a inferir no pisa el trabajo del wizard).

Regla: lo que el usuario confirmo o rechazo (cualquier origen) y lo que
creo a mano (origen `usuario`) se respeta tal cual; lo que seguia
`propuesta` se reemplaza por la propuesta nueva (con su evidencia fresca);
lo propuesto que ya no aparece se descarta. Las entidades se emparejan por
fuente, los campos por columna de origen, las relaciones por sus extremos y
las metricas por id. Los atributos de entidad (nombre, tipo, sinonimos,
descripcion) se conservan si la entidad existente es `origen: usuario`; si
la habia nombrado la heuristica o Claude, se toman de la propuesta (que
puede traer nombres mejores). La clave primaria se conserva siempre.
"""
from app.modelo.esquema import Campo, DimensionTiempo, Entidad, ExpresionAgregacion, Metrica, ModeloSemantico, Relacion


def _tocado(estado: str, origen: str) -> bool:
    return estado != "propuesta" or origen == "usuario"


def _fusionar_campos(existentes: list[Campo], propuestos: list[Campo]) -> list[Campo]:
    por_columna = {campo.columna_origen: campo for campo in existentes}
    resultado: list[Campo] = []
    vistas: set[str] = set()
    for propuesto in propuestos:
        vistas.add(propuesto.columna_origen)
        existente = por_columna.get(propuesto.columna_origen)
        if existente is not None and _tocado(existente.estado, existente.origen):
            resultado.append(existente)
        elif existente is not None:
            # Sigue propuesto: evidencia nueva, pero el id no cambia (hay
            # relaciones y metricas que lo referencian)
            resultado.append(propuesto.model_copy(update={"id": existente.id}))
        else:
            resultado.append(propuesto)
    # Campos confirmados cuya columna ya no viene en la propuesta se conservan:
    # si la columna desaparecio de la fuente, la validacion lo va a decir.
    for campo in existentes:
        if campo.columna_origen not in vistas and _tocado(campo.estado, campo.origen):
            resultado.append(campo)
    return resultado


def _fusionar_entidades(existentes: list[Entidad], propuestas: list[Entidad]) -> list[Entidad]:
    por_fuente = {entidad.fuente: entidad for entidad in existentes}
    resultado: list[Entidad] = []
    for propuesta in propuestas:
        existente = por_fuente.get(propuesta.fuente)
        if existente is None:
            resultado.append(propuesta)
            continue
        campos = _fusionar_campos(existente.campos, propuesta.campos)
        ids_campos = {campo.id for campo in campos}
        clave = [campo for campo in existente.clave_primaria if campo in ids_campos] or propuesta.clave_primaria
        base = existente if existente.origen == "usuario" else propuesta
        resultado.append(
            base.model_copy(update={"id": existente.id, "campos": campos, "clave_primaria": clave})
        )
    return resultado


def _fusionar_relaciones(existentes: list[Relacion], propuestas: list[Relacion], ids_campos: set[str]) -> list[Relacion]:
    def extremos(relacion: Relacion) -> tuple[str, str]:
        return relacion.desde.referencia, relacion.hacia.referencia

    por_extremos = {extremos(relacion): relacion for relacion in existentes}
    resultado: list[Relacion] = []
    vistas: set[tuple[str, str]] = set()
    for propuesta in propuestas:
        vistas.add(extremos(propuesta))
        existente = por_extremos.get(extremos(propuesta))
        if existente is not None and _tocado(existente.estado, "usuario" if existente.evidencia.get("origen") == "usuario" else "heuristica"):
            resultado.append(existente)
        elif existente is not None:
            resultado.append(propuesta.model_copy(update={"id": existente.id, "propagar": existente.propagar}))
        else:
            resultado.append(propuesta)
    for relacion in existentes:
        if extremos(relacion) in vistas or relacion.estado == "propuesta":
            continue
        if relacion.desde.referencia in ids_campos and relacion.hacia.referencia in ids_campos:
            resultado.append(relacion)
    # Ids repetidos entre una conservada y una nueva con otros extremos
    ids_usados: set[str] = set()
    for posicion, relacion in enumerate(resultado):
        identificador = relacion.id
        while identificador in ids_usados:
            identificador = f"{identificador}_2"[:60]
        if identificador != relacion.id:
            resultado[posicion] = relacion.model_copy(update={"id": identificador})
        ids_usados.add(identificador)
    return resultado


def _remapear_propuesta(entidades_fusionadas: list[Entidad], propuesta: ModeloSemantico) -> ModeloSemantico:
    """La propuesta nombra entidades y campos a su manera (`ventas.vendedor`);
    si el modelo existente ya tenia ese campo con otro id (`id_vendedor`,
    misma columna de origen), las relaciones, metricas y dimensiones de la
    propuesta tienen que apuntar al id que quedo."""
    por_fuente = {entidad.fuente: entidad for entidad in entidades_fusionadas}
    mapa_entidad: dict[str, str] = {}
    mapa_campo: dict[str, str] = {}
    for entidad in propuesta.entidades:
        fusionada = por_fuente.get(entidad.fuente)
        if fusionada is None:
            continue
        mapa_entidad[entidad.id] = fusionada.id
        por_columna = {campo.columna_origen: campo.id for campo in fusionada.campos}
        for campo in entidad.campos:
            if campo.columna_origen in por_columna:
                mapa_campo[f"{entidad.id}.{campo.id}"] = f"{fusionada.id}.{por_columna[campo.columna_origen]}"

    def referencia(valor: str) -> str:
        return mapa_campo.get(valor, valor)

    relaciones = [
        relacion.model_copy(
            update={
                "desde": relacion.desde.model_copy(update=dict(zip(("entidad", "campo"), referencia(relacion.desde.referencia).split(".")))),
                "hacia": relacion.hacia.model_copy(update=dict(zip(("entidad", "campo"), referencia(relacion.hacia.referencia).split(".")))),
            }
        )
        for relacion in propuesta.relaciones
    ]
    metricas = [
        metrica.model_copy(update={"expresion": metrica.expresion.model_copy(update={"campo": referencia(metrica.expresion.campo)})})
        if isinstance(metrica.expresion, ExpresionAgregacion)
        else metrica
        for metrica in propuesta.metricas
    ]
    dimensiones = [DimensionTiempo(campo=referencia(dimension.campo), granularidades=dimension.granularidades) for dimension in propuesta.dimensiones_tiempo]
    return propuesta.model_copy(update={"relaciones": relaciones, "metricas": metricas, "dimensiones_tiempo": dimensiones})


def _fusionar_metricas(existentes: list[Metrica], propuestas: list[Metrica]) -> list[Metrica]:
    por_id = {metrica.id: metrica for metrica in existentes}
    resultado: list[Metrica] = []
    vistas: set[str] = set()
    for propuesta in propuestas:
        vistas.add(propuesta.id)
        existente = por_id.get(propuesta.id)
        if existente is not None and _tocado(existente.estado, existente.origen):
            resultado.append(existente)
        else:
            resultado.append(propuesta)
    for metrica in existentes:
        if metrica.id not in vistas and _tocado(metrica.estado, metrica.origen):
            resultado.append(metrica)
    return resultado


def fusionar(existente: ModeloSemantico | None, propuesta: ModeloSemantico) -> ModeloSemantico:
    if existente is None:
        return propuesta
    entidades = _fusionar_entidades(existente.entidades, propuesta.entidades)
    propuesta = _remapear_propuesta(entidades, propuesta)
    ids_campos = {f"{entidad.id}.{campo.id}" for entidad in entidades for campo in entidad.campos}
    relaciones = _fusionar_relaciones(existente.relaciones, propuesta.relaciones, ids_campos)
    metricas = _fusionar_metricas(existente.metricas, propuesta.metricas)
    campos_tiempo = {dimension.campo for dimension in existente.dimensiones_tiempo}
    dimensiones = list(existente.dimensiones_tiempo) + [
        dimension for dimension in propuesta.dimensiones_tiempo if dimension.campo not in campos_tiempo
    ]
    dimensiones = [dimension for dimension in dimensiones if dimension.campo in ids_campos]
    return existente.model_copy(
        update={"entidades": entidades, "relaciones": relaciones, "metricas": metricas, "dimensiones_tiempo": dimensiones}
    )
