# AutoBI (nombre provisorio) — Especificación v1 y arranque con Claude Code

Fecha: 2026-09-07
Estado: borrador para iniciar desarrollo

---

## 1. Visión

Un BI que se construye solo. El usuario sube archivos (CSV, Excel, texto estructurado), el sistema infiere estructura, campos, semántica y relaciones, pregunta lo mínimo necesario, arma un **modelo semántico** y a partir de él propone un **dashboard asociativo** (filtros, KPIs, gráficos, explorador por pestañas). Todo se modifica por wizard o por lenguaje natural.

### Principios de diseño

1. **El modelo semántico es el producto.** Todo lo demás (filtros, KPIs, explorador, respuestas del asistente) se deriva de él. Nada referencia columnas crudas.
2. **Dos artefactos declarativos, versionados:** `ModeloSemantico` y `SpecDashboard`. Ambos JSON validados con Pydantic.
3. **Inferencia en capas:** primero heurísticas deterministas y baratas, con score de confianza; Claude solo para lo semántico y lo ambiguo.
4. **Un solo motor, dos interfaces:** el wizard y el chat ejecutan las mismas operaciones sobre el modelo. Historial y deshacer salen gratis.
5. **Empezar sin IA.** La fase 1 debe funcionar con modelo armado a mano. Si el modelo y el spec no se sostienen solos, la IA no los va a arreglar.
6. **Simple ahora, extensible después.** Storage y tareas pasan por interfaces (`AlmacenArchivos`, `encolar_tarea`) para migrar a S3/Redis sin rediseño.

---

## 2. Alcance v1

**Incluye**
- Multi-tenant lógico: organización → usuarios → rol (`constructor`, `visualizador`).
- Fuentes: CSV y Excel. Texto estructurado en fase 4.
- Profiling completo (los datos son chicos: hasta cientos de miles de filas por tenant).
- Inferencia de tipos, claves y relaciones + propuesta semántica con Claude.
- Wizard de confirmación con inferencias precargadas.
- Chat constructor: agregar gráfico, agregar fuente, corregir modelo.
- Dashboard: área de filtros, KPIs, gráficos, explorador con pestañas por entidad, sensible a filtros.
- Visualizador: filtrar + preguntar en lenguaje natural sobre los datos (solo lectura).
- Resubida de un archivo ya conocido con detección de cambios de esquema.

**Fuera de alcance v1**
- Conexión a bases externas o APIs.
- Refresh automático / scheduler.
- Vistas guardadas por visualizador.
- RLS en Postgres, workers separados, Redis, Clerk/Keycloak.
- Filtrado asociativo con relaciones circulares (se detectan y se pide al usuario cortar).

---

## 3. Arquitectura simplificada

Dos contenedores en Docker Compose:

| Servicio | Contenido |
|---|---|
| `app` | FastAPI + React compilado servido como estático. DuckDB embebido. Tareas largas con `BackgroundTasks`. |
| `postgres` | Catálogo: organizaciones, usuarios, fuentes, versiones de modelo, dashboards, historial de operaciones, conversaciones. |

Archivos (Parquet + DuckDB por workspace): interfaz `AlmacenArchivos` con dos implementaciones desde el día uno: `AlmacenLocal` (dev) y `AlmacenS3` (Cloudflare R2 en Render; el disco de Render es efímero).

LLM: Claude API con tool use. Haiku para tareas rutinarias (nombrar, resumir), Sonnet para inferencia semántica y traducción de preguntas.

Frontend: React + Vite + ECharts + TanStack Query. Progreso de tareas por SSE.

Auth v1: JWT propio con FastAPI (mismo esquema que Mi Trabajo). Migrable a proveedor externo.

### Estructura de repo propuesta

```
autobi/
  backend/
    app/
      api/            # routers FastAPI
      nucleo/         # config, auth, errores
      ingesta/        # normalización a Parquet
      perfilado/      # estadísticas por columna y tabla
      inferencia/     # heurísticas + llamadas a Claude
      modelo/         # ModeloSemantico, operaciones, historial
      consultas/      # compilador modelo -> SQL DuckDB
      asociativo/     # estados de selección
      dashboard/      # SpecDashboard, generador inicial
      asistente/      # orquestación de tools por rol
      almacen/        # AlmacenArchivos (local, s3)
    tests/
    alembic/
  frontend/
    src/
      constructor/    # wizard, chat constructor
      visualizador/   # dashboard, explorador, chat de preguntas
      compartido/
  docker-compose.yml
  CLAUDE.md
  docs/
```

Convención de idioma: todo en español (identificadores, comentarios, UI, docs). Identificadores sin tildes ni ñ (`organizacion`, `anio`).

---

## 4. Modelo semántico

Esquema (Pydantic, serializado a JSON, versionado por workspace):

```json
{
  "version": 3,
  "entidades": [
    {
      "id": "ventas",
      "nombre": "Ventas",
      "fuente_id": "src_01",
      "tipo": "hechos",
      "clave_primaria": ["id_venta"],
      "campos": [
        {
          "id": "id_venta", "columna_origen": "IdVenta",
          "nombre": "ID venta", "tipo_dato": "entero",
          "tipo_semantico": "identificador",
          "confianza": 0.98, "origen": "heuristica"
        },
        {
          "id": "fecha", "columna_origen": "Fecha",
          "nombre": "Fecha", "tipo_dato": "fecha",
          "tipo_semantico": "fecha",
          "confianza": 0.99, "origen": "heuristica"
        },
        {
          "id": "monto", "columna_origen": "Importe",
          "nombre": "Monto", "tipo_dato": "decimal",
          "tipo_semantico": "monto",
          "confianza": 0.9, "origen": "llm"
        },
        {
          "id": "id_vendedor", "columna_origen": "Vend",
          "nombre": "Vendedor", "tipo_dato": "entero",
          "tipo_semantico": "clave_foranea",
          "confianza": 0.85, "origen": "heuristica"
        }
      ],
      "sinonimos": ["operaciones", "facturación"]
    },
    {
      "id": "vendedores", "nombre": "Vendedores", "fuente_id": "src_02",
      "tipo": "dimension", "clave_primaria": ["id_vendedor"], "campos": ["..."]
    }
  ],
  "relaciones": [
    {
      "id": "rel_01",
      "desde": {"entidad": "ventas", "campo": "id_vendedor"},
      "hacia": {"entidad": "vendedores", "campo": "id_vendedor"},
      "cardinalidad": "n:1",
      "confianza": 0.91,
      "evidencia": {"jaccard": 0.97, "huerfanos": 12, "nombre_similar": true},
      "estado": "confirmada"
    }
  ],
  "metricas": [
    {
      "id": "total_ventas", "nombre": "Total ventas",
      "expresion": {"agregacion": "suma", "campo": "ventas.monto"},
      "formato": "moneda", "origen": "llm", "estado": "propuesta"
    },
    {
      "id": "cantidad_ventas", "nombre": "Cantidad de ventas",
      "expresion": {"agregacion": "conteo", "campo": "ventas.id_venta"}
    }
  ],
  "dimensiones_tiempo": [{"campo": "ventas.fecha", "granularidades": ["dia", "mes", "anio"]}]
}
```

Tipos semánticos v1: `identificador`, `clave_foranea`, `fecha`, `monto`, `cantidad`, `porcentaje`, `categoria`, `texto_libre`, `booleano`, `geo`.

Estados de cada elemento inferido: `propuesta` → `confirmada` | `rechazada`. Solo lo confirmado (o con confianza ≥ umbral configurable, por defecto 0.9) entra al dashboard.

### Operaciones sobre el modelo (las mismas para wizard y chat)

- `renombrar_campo`, `asignar_tipo_semantico`, `marcar_clave_primaria`
- `crear_relacion`, `confirmar_relacion`, `rechazar_relacion`, `eliminar_relacion`
- `crear_metrica`, `editar_metrica`, `eliminar_metrica`
- `agregar_sinonimo`
- `deshacer` (historial en Postgres, una fila por operación con diff)

Cada operación valida el modelo resultante (referencias existentes, sin ciclos no autorizados, claves consistentes) antes de persistir la nueva versión.

---

## 5. Spec de dashboard

```json
{
  "version": 1,
  "modelo_version": 3,
  "filtros": [
    {"id": "f_fecha", "campo": "ventas.fecha", "tipo": "rango_fecha"},
    {"id": "f_vendedor", "campo": "vendedores.nombre", "tipo": "lista"},
    {"id": "f_sucursal", "campo": "sucursales.nombre", "tipo": "lista"}
  ],
  "kpis": [
    {"id": "k1", "metrica": "total_ventas"},
    {"id": "k2", "metrica": "cantidad_ventas"},
    {"id": "k3", "metrica": "ticket_promedio"}
  ],
  "graficos": [
    {"id": "g1", "tipo": "linea", "metrica": "total_ventas",
     "dimension": "ventas.fecha", "granularidad": "mes", "titulo": "Ventas por mes"},
    {"id": "g2", "tipo": "barras", "metrica": "total_ventas",
     "dimension": "vendedores.nombre", "top": 10, "titulo": "Top vendedores"},
    {"id": "g3", "tipo": "torta", "metrica": "total_ventas",
     "dimension": "medios_pago.nombre", "titulo": "Por medio de pago"}
  ],
  "explorador": {
    "pestanias": [
      {"entidad": "productos", "columnas": ["nombre", "categoria", "precio"],
       "metricas": ["total_ventas", "cantidad_ventas"]},
      {"entidad": "vendedores", "columnas": ["nombre", "sucursal"],
       "metricas": ["total_ventas"]},
      {"entidad": "ventas", "columnas": ["fecha", "monto", "vendedor", "producto"]}
    ]
  }
}
```

Operaciones sobre el spec (tools del chat constructor): `agregar_grafico`, `editar_grafico`, `eliminar_grafico`, `agregar_filtro`, `agregar_kpi`, `agregar_pestania_explorador`, `reordenar`. Todas validan contra el modelo.

---

## 6. Flujos

### Constructor: carga y modelado

1. Sube uno o varios archivos → `ingesta` normaliza (encoding, separador, encabezados corridos, hojas múltiples) → Parquet en el almacén → tabla registrada en DuckDB.
2. `perfilado` por columna: tipo inferido, nulos, únicos, cardinalidad, min/max, top valores, patrones (fechas, ids, montos). Por tabla: filas, candidatos a clave.
3. `inferencia` heurística: claves primarias (unicidad + no nulos), FKs (Jaccard de valores entre columnas de distintas tablas + similitud de nombre + cardinalidad), tipos semánticos por patrón.
4. `inferencia` con Claude: recibe perfil + 100 filas de muestra por tabla → propone nombres legibles, tipos semánticos dudosos, métricas, sinónimos, tipo de entidad (hechos/dimensión). Respuesta en JSON estricto.
5. Wizard: muestra entidades, campos y relaciones con semáforo por confianza. El usuario confirma, corrige o rechaza. Cada acción es una operación del §4.
6. Al confirmar, Claude propone `SpecDashboard` inicial con las métricas y dimensiones confirmadas.
7. Render. El chat constructor queda disponible para ajustes.

### Resubida de fuente

Se detecta por huella (nombre + esquema). Si el esquema cambió, se informa qué columnas aparecieron/desaparecieron/cambiaron de tipo y qué partes del modelo se ven afectadas, antes de reemplazar.

### Visualizador

1. Aplica filtros → `asociativo` calcula, por entidad, valores compatibles (verde) e incompatibles (gris) propagando por el grafo de relaciones. Una consulta DuckDB por entidad, con cache por combinación de filtros.
2. KPIs, gráficos y explorador se recalculan con los filtros activos vía `consultas` (modelo → SQL).
3. Pregunta en lenguaje natural: Claude recibe el modelo semántico (no el esquema físico) y los filtros activos, devuelve una **consulta semántica** (métrica, dimensiones, filtros adicionales, tipo de gráfico sugerido). El compilador la traduce a SQL. Claude nunca escribe SQL directo. Respuesta en texto + gráfico opcional.

---

## 7. Motor de consultas

Entrada: consulta semántica `{metricas, dimensiones, filtros, granularidad, orden, limite}`.
Proceso: resolver entidades involucradas → calcular camino de joins en el grafo de relaciones (BFS; error si hay ambigüedad o ciclo) → generar SQL DuckDB parametrizado → ejecutar → devolver tabla tipada.

Es el único punto donde el modelo se convierte en SQL. Todo (KPIs, gráficos, explorador, asociativo, preguntas) pasa por acá. Testear exhaustivamente.

---

## 8. Roles

| Capacidad | Constructor | Visualizador |
|---|---|---|
| Subir fuentes, wizard, editar modelo/spec | sí | no |
| Chat constructor (tools de escritura) | sí | no |
| Ver dashboard y filtrar | sí | sí |
| Preguntar en lenguaje natural (solo lectura) | sí | sí |

El asistente recibe un conjunto de tools distinto según el rol. El visualizador no tiene ninguna tool de escritura disponible, no es un permiso que se chequea, es que la tool no existe en su contexto.

---

## 9. Fases y criterios de aceptación

**Fase 1 — Cimientos, sin IA**
Ingesta CSV/Excel → Parquet → DuckDB. Modelo semántico armado a mano (JSON). Compilador a SQL. Dashboard fijo desde spec a mano. Filtros simples (sin asociativo). Auth y roles.
*Aceptación:* con los 5 CSV de prueba y un modelo escrito a mano, el dashboard muestra KPIs, 3 gráficos y explorador con pestañas, y los filtros afectan todo.

**Fase 2 — Inferencia y wizard**
Profiling, heurísticas de claves y relaciones, Claude proponiendo semántica, wizard con semáforos, generación de spec inicial por Claude.
*Aceptación:* subiendo los 5 CSV desde cero, el sistema propone el modelo correcto con al menos 80% de relaciones acertadas sin intervención, y el resto se resuelve en el wizard.

**Fase 3 — Asistente**
Chat constructor con tools sobre modelo y spec. Preguntas del visualizador con consulta semántica. Historial y deshacer.
*Aceptación:* "agregá un gráfico de ventas por sucursal por mes" produce el gráfico correcto; "¿cuánto vendió Pérez en marzo?" responde bien respetando los filtros activos.

**Fase 4 — Profundidad**
Filtrado asociativo completo. Texto estructurado con parser propuesto por Claude. Reporte de calidad de datos. Resubida con detección de cambios. Almacén S3/R2 y deploy en Render.

---

## 10. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Claves sucias (ids reutilizados, nombres inconsistentes) | Jaccard con umbral + huérfanos como evidencia visible en el wizard; nunca confirmar automáticamente por debajo de 0.9 |
| Costo de tokens | Perfil compacto + muestra acotada; cache de inferencias por huella de esquema; Haiku donde alcance |
| Relaciones circulares en el asociativo | Detectar en validación del modelo; pedir al usuario marcar una relación como "no propagar" |
| Claude proponiendo algo inválido | Toda salida del LLM pasa por validación Pydantic + validación contra el modelo; se reintenta con el error como feedback |
| Frontend complejo | Spec declarativo → componentes genéricos; el frontend no sabe de negocio |

---

## 11. Prompt de arranque para Claude Code

Pegar en Claude Code dentro de un repo vacío con este documento en `docs/especificacion-v1.md`.

```
Vas a construir AutoBI, un BI que se autoconstruye a partir de archivos subidos.
La especificación completa está en docs/especificacion-v1.md. Leela entera antes de hacer nada.

Reglas de trabajo:
- Preguntá antes de decidir ante cualquier ambigüedad. No asumas.
- Trabajamos por fases secuenciales. Ahora es solo la FASE 1 (cimientos, sin IA).
- Antes de escribir código: presentame (1) tu lectura de la fase 1, (2) dudas y ambigüedades,
  (3) decisiones técnicas que proponés con justificación (librerías, estructura),
  (4) plan de trabajo en pasos. Esperá mi aprobación.
- Todo el código, comentarios, UI y documentación en español. Identificadores sin tildes ni ñ.
- Stack fijo: FastAPI, Pydantic v2, SQLAlchemy + Alembic, Postgres, DuckDB, React + Vite +
  TypeScript + ECharts + TanStack Query, Docker Compose con dos servicios (app, postgres).
- Storage y tareas detrás de interfaces (AlmacenArchivos, encolar_tarea) con implementación
  local en esta fase.
- Tests con pytest para ingesta y para el compilador modelo -> SQL desde el principio.
- Creá y mantené CLAUDE.md con: propósito, arquitectura, convenciones, estado de cada fase
  y decisiones tomadas. Actualizalo al cerrar cada paso.
- Al terminar cada paso del plan, resumí qué hiciste, qué falta y qué necesitás de mí.

Datos de prueba: voy a dejar 5 CSV en datos_prueba/ (ventas, vendedores, productos, pagos,
medios_pago). Si todavía no están, pedímelos antes de empezar la ingesta.

Empezá por el punto (1).
```

---

## 12. Lo que aporta el usuario

- Los 5 CSV de prueba, idealmente reales o realistas y con suciedad típica (nulos, ids huérfanos, fechas en formatos mezclados).
- Cuenta en Cloudflare R2 (fase 4) y variables de entorno en Render.
- Revisión y aprobación al cierre de cada fase.
- Decisiones de producto: qué pregunta el wizard, qué muestra el dashboard por defecto, qué tono tiene el asistente.
