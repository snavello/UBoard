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
  claude?: { usado: boolean; cache: boolean; modelo?: string; tokens_entrada?: number; tokens_salida?: number; advertencia?: string };
  // inferencia.proponer_spec, ademas de version, resumen y claude
  titulo?: string | null;
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

/* Modelo semantico (espejo de app/modelo/esquema.py). */
export type Formato = "moneda" | "entero" | "decimal" | "porcentaje";
export type TipoDato = "entero" | "decimal" | "fecha" | "fecha_hora" | "booleano" | "texto";
export type TipoSemantico =
  | "identificador"
  | "clave_foranea"
  | "fecha"
  | "monto"
  | "cantidad"
  | "porcentaje"
  | "categoria"
  | "texto_libre"
  | "booleano"
  | "geo";
export type OrigenCampo = "heuristica" | "llm" | "usuario";
export type EstadoElemento = "propuesta" | "confirmada" | "rechazada";
export type TipoEntidad = "hechos" | "dimension";
export type Cardinalidad = "n:1" | "1:1" | "1:n";
export type Agregacion = "suma" | "conteo" | "conteo_distinto" | "promedio" | "minimo" | "maximo";
export type Granularidad = "dia" | "semana" | "mes" | "trimestre" | "anio";

export interface Campo {
  id: string;
  columna_origen: string;
  nombre: string;
  tipo_dato: TipoDato;
  tipo_semantico: TipoSemantico;
  confianza: number;
  origen: OrigenCampo;
  estado: EstadoElemento;
  descripcion: string | null;
  evidencia: Record<string, unknown>;
}

export interface EntidadModelo {
  id: string;
  nombre: string;
  fuente: string;
  tipo: TipoEntidad;
  clave_primaria: string[];
  campos: Campo[];
  sinonimos: string[];
  descripcion: string | null;
  origen: OrigenCampo;
}

export interface ExtremoRelacion {
  entidad: string;
  campo: string;
}

export interface RelacionModelo {
  id: string;
  desde: ExtremoRelacion;
  hacia: ExtremoRelacion;
  cardinalidad: Cardinalidad;
  confianza: number;
  evidencia: Record<string, unknown>;
  estado: EstadoElemento;
  propagar: boolean;
}

export interface ExpresionAgregacion {
  agregacion: Agregacion;
  campo: string;
}

export interface ExpresionCociente {
  numerador: string;
  denominador: string;
}

export type OperacionFormula = "suma" | "resta" | "multiplicacion" | "division";

// Un operando es el id de otra metrica, una constante, o (para anidar) otra formula embebida.
export type Operando = string | number | ExpresionFormula;

export interface ExpresionFormula {
  operacion: OperacionFormula;
  izquierda: Operando;
  derecha: Operando;
}

export type ExpresionMetrica = ExpresionAgregacion | ExpresionCociente | ExpresionFormula;

export interface MetricaModelo {
  id: string;
  nombre: string;
  expresion: ExpresionMetrica;
  formato: Formato;
  confianza: number;
  origen: OrigenCampo;
  estado: EstadoElemento;
  descripcion: string | null;
}

export interface DimensionTiempoModelo {
  campo: string;
  granularidades: Granularidad[];
}

export interface ModeloSemantico {
  version: number;
  entidades: EntidadModelo[];
  relaciones: RelacionModelo[];
  metricas: MetricaModelo[];
  dimensiones_tiempo: DimensionTiempoModelo[];
  umbral_confianza: number;
}

export function esExpresionAgregacion(expresion: ExpresionMetrica): expresion is ExpresionAgregacion {
  return "agregacion" in expresion;
}

export function esExpresionCociente(expresion: ExpresionMetrica): expresion is ExpresionCociente {
  return "numerador" in expresion;
}

export function esExpresionFormula(expresion: ExpresionMetrica): expresion is ExpresionFormula {
  return "operacion" in expresion;
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

// Asistente (fase 3, paso 19-20): cada pedido al chat es independiente,
// la conversacion no se persiste en el backend.
export interface AccionAsistente {
  herramienta: string;
  entrada: Record<string, unknown>;
  resultado: string;
}

export interface RespuestaAsistente {
  texto: string;
  acciones: AccionAsistente[];
}
