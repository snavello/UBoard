"""Tablas del catalogo. Importar este modulo registra todas en Base.metadata,
que es lo que Alembic compara para autogenerar migraciones.

Paso 1 (auth y tenancy): organizacion, workspace, usuario.
Paso 2 (cola de tareas): tarea.
Paso 3 (ingesta): fuente.
Paso 4 (modelo semantico): version_modelo.
Paso 6 (dashboard): version_spec.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.catalogo.base import Base


def _enum_por_valor(clase: type[enum.Enum], nombre: str, largo: int = 20) -> Enum:
    """Enum guardado como VARCHAR + CHECK (no como tipo nativo de Postgres:
    agregar un valor seria un ALTER TYPE), persistiendo el .value y no el nombre."""
    return Enum(
        clase,
        name=nombre,
        native_enum=False,
        length=largo,
        create_constraint=True,
        values_callable=lambda enumeracion: [miembro.value for miembro in enumeracion],
    )


class RolUsuario(enum.StrEnum):
    """plataforma: da de alta organizaciones y usuarios, sin organizacion propia.
    constructor: sube fuentes y edita modelo y spec de su organizacion.
    visualizador: ve el dashboard, filtra y pregunta; ninguna ruta de escritura."""

    PLATAFORMA = "plataforma"
    CONSTRUCTOR = "constructor"
    VISUALIZADOR = "visualizador"


class Organizacion(Base):
    """Tenant logico. Todo dato de negocio cuelga de una organizacion a traves
    de sus workspaces; los usuarios pertenecen a una sola."""

    __tablename__ = "organizacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspaces: Mapped[list[Workspace]] = relationship(
        back_populates="organizacion", cascade="all, delete-orphan", order_by="Workspace.id"
    )
    usuarios: Mapped[list[Usuario]] = relationship(back_populates="organizacion", order_by="Usuario.id")


class Workspace(Base):
    """Espacio de trabajo: fuentes, modelo semantico y dashboard. En v1 cada
    organizacion tiene uno solo (se crea con ella), pero la tabla existe para
    que manana pueda tener varios sin migrar datos."""

    __tablename__ = "workspace"
    __table_args__ = (UniqueConstraint("organizacion_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organizacion_id: Mapped[int] = mapped_column(ForeignKey("organizacion.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    organizacion: Mapped[Organizacion] = relationship(back_populates="workspaces")


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (
        # El rol plataforma es el unico sin organizacion, y el unico que puede no tenerla.
        CheckConstraint("(rol = 'plataforma') = (organizacion_id IS NULL)", name="plataforma_sin_organizacion"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    organizacion_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizacion.id", ondelete="CASCADE"), index=True, nullable=True
    )
    # Se guarda normalizado (sin espacios, en minusculas); ver catalogo.operaciones
    email: Mapped[str] = mapped_column(String(254), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    # "sal$hash" PBKDF2-HMAC-SHA256, ver nucleo.auth
    clave_hash: Mapped[str] = mapped_column(String(200))
    rol: Mapped[RolUsuario] = mapped_column(_enum_por_valor(RolUsuario, "rol_usuario"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ultimo_acceso: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organizacion: Mapped[Organizacion | None] = relationship(back_populates="usuarios")


class EstadoTarea(enum.StrEnum):
    PENDIENTE = "pendiente"
    CORRIENDO = "corriendo"
    TERMINADA = "terminada"
    ERROR = "error"


class Tarea(Base):
    """Trabajo en segundo plano (ingesta, y mas adelante perfilado e
    inferencia). El frontend consulta esta fila por polling. El id es un UUID
    para que no se puedan adivinar tareas ajenas por numeracion."""

    __tablename__ = "tarea"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspace.id", ondelete="CASCADE"), index=True, nullable=True
    )
    creada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    # Nombre registrado del manejador, ver app.tareas.registro
    tipo: Mapped[str] = mapped_column(String(80))
    estado: Mapped[EstadoTarea] = mapped_column(
        _enum_por_valor(EstadoTarea, "estado_tarea"), default=EstadoTarea.PENDIENTE
    )
    progreso: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    mensaje: Mapped[str | None] = mapped_column(String(300), nullable=True)
    parametros: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    resultado: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # "E-XXX-NN: mensaje" cuando estado == error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    iniciada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    workspace: Mapped[Workspace | None] = relationship()


class EstadoFuente(enum.StrEnum):
    LISTA = "lista"
    ERROR = "error"


class Fuente(Base):
    """Un archivo (o una hoja de Excel) ya normalizado a Parquet. `nombre_tabla`
    es el identificador que ve el modelo semantico y el nombre de la vista
    DuckDB; resubir un archivo con el mismo nombre_tabla reemplaza la fuente.
    `esquema` guarda las columnas con nombre, nombre_origen, tipo, nulos e
    invalidos; `huella` resume nombre + columnas + tipos."""

    __tablename__ = "fuente"
    __table_args__ = (UniqueConstraint("workspace_id", "nombre_tabla"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"), index=True)
    creada_por_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(120), default="")
    nombre_tabla: Mapped[str] = mapped_column(String(80))
    archivo_origen: Mapped[str] = mapped_column(String(255), default="")
    hoja: Mapped[str | None] = mapped_column(String(120), nullable=True)
    formato: Mapped[str] = mapped_column(String(10), default="csv")
    huella: Mapped[str] = mapped_column(String(16), default="")
    esquema: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    filas: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    ruta_parquet: Mapped[str] = mapped_column(String(300), default="")
    ruta_original: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # Como se leyo el archivo: codificacion, delimitador, filas saltadas, hoja
    opciones: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # PerfilFuente (perfilado/perfil.py); None en fuentes ingestadas antes del paso 9
    perfil: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    estado: Mapped[EstadoFuente] = mapped_column(_enum_por_valor(EstadoFuente, "estado_fuente"), default=EstadoFuente.LISTA)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    actualizada_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    workspace: Mapped[Workspace] = relationship()


class Inferencia(Base):
    """Cada consulta a Claude (fase 2): cache por huella del pedido y
    auditoria de tokens para vigilar el gasto."""

    __tablename__ = "inferencia"
    __table_args__ = (UniqueConstraint("workspace_id", "huella"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(40))  # semantica | spec
    huella: Mapped[str] = mapped_column(String(32))
    modelo_claude: Mapped[str] = mapped_column(String(80))
    respuesta: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tokens_entrada: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    tokens_salida: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship()


class VersionModelo(Base):
    """Cada cambio al modelo semantico es una fila nueva con el modelo ENTERO
    (`contenido`), asi deshacer es volver a la version anterior. `operacion`
    dice que lo produjo (hoy solo `cargar_json`; despues `renombrar_campo`,
    `crear_relacion`, ...) y `diff` que cambio respecto de la anterior."""

    __tablename__ = "version_modelo"
    __table_args__ = (UniqueConstraint("workspace_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    contenido: Mapped[dict[str, Any]] = mapped_column(JSONB)
    operacion: Mapped[str] = mapped_column(String(60))
    diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    resumen: Mapped[str | None] = mapped_column(String(300), nullable=True)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship()


class VersionSpec(Base):
    """Versiones del SpecDashboard, espejo de version_modelo. `modelo_version`
    es la version del modelo contra la que se valido: si el modelo cambia
    despues, el dashboard se revalida al abrirlo y avisa que paneles ya no
    cierran."""

    __tablename__ = "version_spec"
    __table_args__ = (UniqueConstraint("workspace_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspace.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    modelo_version: Mapped[int] = mapped_column(Integer)
    contenido: Mapped[dict[str, Any]] = mapped_column(JSONB)
    operacion: Mapped[str] = mapped_column(String(60))
    resumen: Mapped[str | None] = mapped_column(String(300), nullable=True)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id", ondelete="SET NULL"), nullable=True)
    creada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    workspace: Mapped[Workspace] = relationship()
