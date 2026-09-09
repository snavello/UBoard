/* Tipos de lo que devuelve la API. Espejo de los esquemas Pydantic del backend. */

export type Rol = "plataforma" | "constructor" | "visualizador";

export interface OrganizacionResumen {
  id: number;
  nombre: string;
  activa: boolean;
}

export interface Usuario {
  id: number;
  email: string;
  nombre: string;
  rol: Rol;
  activo: boolean;
  organizacion: OrganizacionResumen | null;
  workspace_id: number | null;
  ultimo_acceso: string | null;
}

export interface ErrorValidacion {
  codigo: string;
  ubicacion: string;
  mensaje: string;
}

export interface ErrorApiCuerpo {
  codigo: string;
  mensaje: string;
  detalle?: string;
  errores?: ErrorValidacion[];
  ref?: string;
}

export interface Salud {
  estado: string;
  version: string;
  fecha_version: string;
  entorno: string;
}

export interface ResultadoTarea {
  // ingesta.procesar_archivo
  fuentes?: { id: number; nombre_tabla: string; filas: number; reemplazada: boolean }[];
  // inferencia.proponer_modelo
  version?: number;
  resumen?: string;
  relaciones?: { id: string; desde: string; hacia: string; confianza: number; estado: string }[];
}

export interface Tarea {
  id: string;
  tipo: string;
  estado: "pendiente" | "corriendo" | "terminada" | "error";
  progreso: number;
  mensaje: string | null;
  resultado: ResultadoTarea | null;
  error: string | null;
  creada_en: string;
}

export interface ColumnaFuente {
  nombre: string;
  nombre_origen: string | null;
  tipo: string;
  nulos: number;
  invalidos: number;
  detalle: Record<string, unknown>;
}

export interface Fuente {
  id: number;
  nombre: string;
  nombre_tabla: string;
  archivo_origen: string;
  hoja: string | null;
  formato: string;
  huella: string;
  filas: number;
  estado: "lista" | "error";
  error: string | null;
  columnas: ColumnaFuente[];
  opciones: Record<string, unknown>;
  perfilada: boolean;
  creada_en: string;
  actualizada_en: string;
}

export interface TopValor {
  valor: unknown;
  cantidad: number;
}

export interface PerfilColumna {
  nombre: string;
  tipo: string;
  nulos: number;
  distintos: number;
  unica: boolean;
  minimo: unknown;
  maximo: unknown;
  promedio: number | null;
  longitud_minima: number | null;
  longitud_maxima: number | null;
  top_valores: TopValor[];
  patron: string | null;
}

export interface PerfilFuente {
  nombre_tabla: string;
  filas: number;
  columnas: PerfilColumna[];
  candidatas_clave: string[];
}

export interface Muestra {
  columnas: string[];
  tipos: string[];
  filas: unknown[][];
  total: number;
}

export interface VersionResumen {
  numero: number;
  operacion: string;
  resumen: string | null;
  autor_id: number | null;
  creada_en: string;
  diff?: Record<string, unknown> | null;
  modelo_version?: number;
}

export interface VersionCompleta extends VersionResumen {
  contenido: Record<string, unknown>;
}

export interface ResultadoValidacion {
  valido: boolean;
  errores: ErrorValidacion[];
  resumen?: string | null;
}

export interface FiltroSpec {
  id: string;
  campo: string;
  tipo: "rango_fecha" | "lista";
  etiqueta?: string | null;
}

export interface KpiSpec {
  id: string;
  metrica: string;
  titulo?: string | null;
}

export interface GraficoSpec {
  id: string;
  tipo: "linea" | "barras" | "torta";
  metrica: string;
  dimension: string;
  granularidad?: string | null;
  top?: number | null;
  titulo?: string | null;
}

export interface PestaniaSpec {
  entidad: string;
  titulo?: string | null;
  columnas: string[];
  metricas: string[];
  tamanio_pagina: number;
}

export interface SpecDashboard {
  version: number;
  modelo_version: number | null;
  titulo: string | null;
  filtros: FiltroSpec[];
  kpis: KpiSpec[];
  graficos: GraficoSpec[];
  explorador: { pestanias: PestaniaSpec[] };
}

export interface DashboardSalida extends VersionResumen {
  modelo_version: number;
  contenido: SpecDashboard;
  advertencias: ErrorValidacion[];
}

export type Formato = "moneda" | "entero" | "decimal" | "porcentaje";

export interface KpiSalida {
  id: string;
  metrica: string;
  titulo: string;
  formato: Formato;
  valor: number | null;
}

export interface ColumnaSalida {
  nombre: string;
  tipo: string;
  clase: string;
  granularidad: string | null;
}

export interface GraficoSalida {
  id: string;
  tipo: "linea" | "barras" | "torta";
  titulo: string;
  metrica: { id: string; nombre: string; formato: Formato };
  dimension: ColumnaSalida;
  filas: [unknown, number | null][];
}

export interface ColumnaExplorador {
  alias: string;
  titulo: string;
  tipo: string;
  clase: "dimension" | "metrica";
  oculta: boolean;
  formato: Formato | null;
}

export interface ExploradorSalida {
  entidad: string;
  titulo: string;
  columnas: ColumnaExplorador[];
  filas: unknown[][];
  pagina: number;
  tamanio: number;
  total: number;
}

export interface OpcionesSalida {
  filtro: string;
  tipo: "rango_fecha" | "lista";
  valores: unknown[] | null;
  minimo: string | null;
  maximo: string | null;
}

export interface OrganizacionPlataforma {
  id: number;
  nombre: string;
  activa: boolean;
  workspace_id: number | null;
  cantidad_usuarios: number;
}

/* Filtros activos del dashboard: {id_filtro: valor} tal cual viaja en ?filtros= */
export type FiltrosActivos = Record<string, unknown>;
