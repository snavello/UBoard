# UBoard — Fase 2: lectura, dudas, decisiones técnicas, plan y skills

Fecha: 2026-09-09. Estado: para aprobación de Sd antes de escribir código.
Fuente: `docs/especificacion-v1.md` §1 (principio 3 y 4), §4, §6 (pasos 2 a 6), §9, §10.

## (1) Lectura de la fase 2

Objetivo: que el sistema **proponga** el modelo semántico y el dashboard solo.
Subiendo los 5 CSV desde cero, sin pegar ningún JSON, el constructor tiene un
modelo propuesto con semáforos, lo revisa en un wizard, y al confirmar recibe
un dashboard inicial propuesto por Claude. Todo lo que hoy se escribe a mano
(`modelo.json`, `spec.json`) pasa a ser el resultado de la inferencia más las
correcciones del usuario.

Principio rector (§1.3): **inferencia en capas**. Primero heurísticas
deterministas y baratas con score de confianza; Claude solo para lo semántico
(nombres legibles, tipos dudosos, métricas, sinónimos, hechos vs dimensión) y
para armar el spec. Claude nunca decide claves ni relaciones: eso lo hacen los
datos.

Entra en la fase 2 (§6 pasos 2 a 6):
1. **Perfilado** por columna (nulos, únicos, cardinalidad, mín/máx, top
   valores, patrones) y por tabla (filas, candidatas a clave).
2. **Heurísticas**: claves primarias (unicidad + sin nulos), claves foráneas
   (inclusión/Jaccard de valores entre columnas de distintas tablas +
   similitud de nombre + cardinalidad), tipos semánticos por patrón. Cada
   propuesta con `confianza`, `origen: heuristica`, `estado: propuesta` y
   `evidencia` (jaccard, huérfanos, nombre_similar) visible en el wizard.
3. **Claude**: recibe el perfil compacto + una muestra de filas por tabla y
   devuelve JSON estricto con nombres legibles, tipos semánticos dudosos,
   métricas, sinónimos y tipo de entidad. Toda salida pasa por Pydantic +
   validación del modelo; se reintenta con el error como feedback (§10).
4. **Wizard** con semáforo por confianza: el usuario confirma, corrige o
   rechaza entidades, campos, claves, relaciones y métricas. Cada acción es
   una **operación del §4** (`renombrar_campo`, `confirmar_relacion`, ...),
   la misma que usará el chat en la fase 3.
5. **Spec inicial**: al confirmar, Claude propone un `SpecDashboard` con las
   métricas y dimensiones confirmadas; se valida compilando cada panel (lo
   que ya hace el paso 6 de la fase 1) y se guarda como versión.
6. Costo y caché: perfil compacto, muestra acotada, caché de inferencias por
   huella de esquema, modelo más barato donde alcance (§10).

No entra (fases 3 y 4): chat constructor, preguntas del visualizador,
historial con deshacer, filtrado asociativo, resubida con diff de esquema,
texto estructurado, calidad de datos, R2 y Render.

Aceptación (§9): subiendo los 5 CSV desde cero, el sistema propone el modelo
correcto con **al menos 80 % de las relaciones acertadas sin intervención**, y
el resto se resuelve en el wizard. Con los 4 relaciones del modelo de prueba,
80 % significa las 4 (3 de 4 es 75 %). Se agrega como criterio propio: el
dashboard propuesto por Claude carga sin errores de validación y muestra al
menos los KPIs y 3 gráficos que hoy están en `spec.json` o equivalentes.

## (2) Dudas y ambigüedades (cada una con propuesta)

Claude y costos
1. **Clave de API.** Hace falta una `ANTHROPIC_API_KEY` en el `.env` (y en la
   imagen Docker por variable de entorno). La pone Sd; el repo nunca la ve.
   ¿La cuenta es la de Sd? ¿Hay tope de gasto que respetar?
2. **Qué modelo de Claude.** Propuesta: una sola variable `MODELO_CLAUDE`,
   por defecto `claude-sonnet-5` para la semántica y el spec (son dos
   llamadas por workspace, no vale la pena bajar a Haiku 4.5 salvo que el
   costo importe). Configurable por entorno.
3. **Muestra de filas enviada a Claude.** La spec dice 100 filas por tabla.
   Son datos de las organizaciones que salen a la API de Anthropic.
   Propuesta: `FILAS_MUESTRA_LLM=30` por tabla (alcanza para entender
   semántica; el perfil ya lleva top valores) y una variable
   `ENVIAR_MUESTRA_LLM=true|false` para que una organización pueda apagarla
   y Claude trabaje solo con el perfil (nombres, tipos, estadísticas).
4. **Caché de inferencias.** Propuesta: tabla `inferencia` con (workspace,
   huella combinada de los esquemas de las fuentes, modelo de Claude,
   respuesta cruda, tokens). Misma huella = no se vuelve a llamar. Se guarda
   también para auditar qué propuso Claude.
5. **Tests sin red.** Los tests nunca llaman a Anthropic: el cliente va
   detrás de una interfaz (`ClienteLLM`) con una implementación falsa que
   devuelve respuestas grabadas. Habrá un test "en vivo" marcado
   `@pytest.mark.en_vivo` que se salta sin clave; se corre a mano antes de
   cerrar un paso.

Flujo del constructor
6. **Cuándo se infiere.** Propuesta: **a pedido**, con un botón "Proponer
   modelo" en Fuentes (las subidas vienen de a varias y no tiene sentido
   inferir después de cada archivo). Es una tarea en la cola con progreso
   por polling. Alternativa: automático cuando termina cada ingesta.
7. **Volver a inferir con un modelo ya trabajado.** Propuesta: fusionar. Lo
   `confirmado` y lo `rechazado` por el usuario se respeta; solo se
   reproponen los elementos `propuesta` y los que son nuevos (fuente nueva o
   columna nueva). Alternativa: reemplazar todo (pierde el trabajo del
   wizard).
8. **Operaciones granulares del §4.** El wizard necesita `renombrar_campo`,
   `asignar_tipo_semantico`, `marcar_clave_primaria`, `crear/confirmar/
   rechazar/eliminar_relacion`, `crear/editar/eliminar_metrica`,
   `agregar_sinonimo`, más `confirmar_campo`, `rechazar_campo`,
   `confirmar_metrica`, `rechazar_metrica` y `asignar_tipo_entidad` que la
   spec no lista pero el semáforo exige. Propuesta: implementarlas todas en
   esta fase como `POST /modelo/operaciones` (una operación = una versión
   nueva con `operacion` y `diff`, columnas que ya existen). `deshacer` queda
   para la fase 3 junto con el historial visible.
9. **Editor JSON actual.** Propuesta: queda como pestaña "Avanzado" en la
   pantalla de Modelo (sirve para depurar y para cargar `modelo.json`); el
   wizard pasa a ser la pantalla principal del constructor.
10. **Confirmación en bloque.** ¿El wizard tiene "Confirmar todo lo verde"?
    Propuesta: sí, por sección (campos, relaciones, métricas), porque
    confirmar 40 campos uno por uno no lo va a hacer nadie. Lo amarillo y lo
    rojo se resuelven de a uno.
11. **Spec inicial.** Propuesta: un generador **determinista** arma un spec
    base (KPI por cada métrica confirmada, gráfico de línea por la primera
    dimensión de tiempo, barras por las 2 o 3 categorías con mejor
    cardinalidad, explorador con una pestaña por entidad) y Claude lo
    **cura**: elige qué KPI es el protagonista, qué gráficos valen la pena,
    títulos y orden. Si Claude falla o no hay clave, se guarda el spec base.
    Así el dashboard nunca queda vacío.
12. **Idioma y tono de lo que propone Claude.** Castellano rioplatense,
    nombres cortos ("Total ventas", "Ticket promedio"), sin mayúsculas
    innecesarias. Se fija en el prompt del sistema.

Alcance
13. **SSE.** El CLAUDE.md decía "SSE en fase 2". Propuesta: **no** en esta
    fase; el polling funciona, está probado y la inferencia es una tarea
    más. SSE entra cuando haya chat (fase 3), que sí lo necesita para
    streaming.
14. **Expresiones aritméticas libres entre métricas.** Sd las pidió "más
    adelante". Propuesta: fase 3, cuando el chat las pida en lenguaje
    natural. Si Sd las quiere ahora, entran como paso extra al final.
15. **Umbrales de las heurísticas** (propuesta, ajustables por config):
    - Clave primaria: 100 % únicos y 0 nulos; si hay varias candidatas,
      gana la que se parece a `id`/`codigo`/nombre de la tabla, después la
      primera columna. Confianza 0.98 si única candidata, 0.85 si hubo que
      elegir.
    - Clave foránea: la columna del lado "muchos" tiene ≥ 95 % de sus
      valores distintos incluidos en la clave primaria del lado "uno" (los
      huérfanos son evidencia, no descarte), el tipo coincide, y la
      cardinalidad efectiva es n:1. Confianza base 0.7 por inclusión,
      +0.2 si el nombre es similar (`difflib`, stdlib, sin dependencia
      nueva), +0.05 si la inclusión es 100 %. Solo ≥ 0.9 entra sin confirmar
      (§10: nunca confirmar automáticamente por debajo).
    - Si una columna calza con dos claves primarias, se proponen las dos
      con la confianza repartida y el wizard decide (no hay ciclos porque
      el modelo efectivo solo toma la de mayor confianza si supera el
      umbral; si las dos superan, se baja una a 0.89).
    - Tipos semánticos por patrón: `identificador` (PK), `clave_foranea`,
      `fecha` (tipo temporal), `booleano`, `monto` (decimal con nombre
      monto/importe/precio/total/neto), `cantidad` (entero no clave),
      `porcentaje` (decimal 0-100 o 0-1 con nombre porc/pct/%), `categoria`
      (texto con cardinalidad ≤ 50 o ≤ 5 % de las filas), `texto_libre`
      (el resto), `geo` (nombre provincia/ciudad/pais/localidad). Lo dudoso
      queda con confianza 0.6 y se lo pregunta a Claude.

## (3) Decisiones técnicas propuestas

Backend
- `anthropic==1.4.0` (SDK oficial, última estable) en `requirements.txt`.
  Cliente propio en `app/inferencia/llm.py` detrás de `ClienteLLM`
  (`completar_json(sistema, usuario, esquema) -> dict`) con implementación
  real y falsa. La salida JSON se fuerza con **tool use** (un tool cuyo
  `input_schema` sale de `model_json_schema()` del Pydantic de la
  respuesta), `max_tokens` acotado, reintento hasta 2 veces con el error de
  validación como feedback. Timeout 120 s. Nunca se loguea la muestra.
- Config nueva (`nucleo/config.py`): `ANTHROPIC_API_KEY` (opcional: sin
  clave, las heurísticas funcionan y Claude se salta con aviso `E-INF-01`),
  `MODELO_CLAUDE`, `FILAS_MUESTRA_LLM`, `ENVIAR_MUESTRA_LLM`,
  `UMBRAL_INCLUSION_FK`, etc.
- `app/perfilado/`: `perfilar_fuente(conexion, nombre_tabla, esquema)` con
  DuckDB (`approx_count_distinct` no: conteo exacto, las tablas son chicas),
  resultado Pydantic `PerfilFuente` guardado en `fuente.perfil` (JSONB, nueva
  migración) al final de la ingesta. Endpoint `GET /fuentes/{id}/perfil`.
- `app/inferencia/`: `heuristicas.py` (claves, relaciones, tipos →
  `ModeloSemantico` propuesto con evidencia), `semantica.py` (prompt y
  fusión de la respuesta de Claude), `fusion.py` (mezcla propuesta nueva con
  modelo existente respetando confirmado/rechazado), `tarea.py`
  (`inferencia.proponer_modelo`, `inferencia.proponer_spec`). Tabla
  `inferencia` para la caché.
- `Relacion.evidencia` ya existe en el esquema del §4; se agrega
  `Campo.evidencia` opcional (patrón detectado, cardinalidad) para el
  semáforo.
- `app/modelo/operaciones.py` crece con las operaciones granulares:
  `aplicar_operacion(modelo, operacion, parametros) -> modelo` puro y
  testeable, y el endpoint que valida en tres capas y guarda versión.
- `app/dashboard/generador.py`: spec base determinista; `inferencia/spec.py`
  pide a Claude la curación y valida con `validar_spec` (compila paneles).
- Tests: heurísticas contra los 5 CSV (las 4 relaciones, las 5 PK, tipos
  semánticos esperados), perfilado puro en DuckDB, operaciones puras,
  fusión, cliente falso con respuestas grabadas en `tests/respuestas_llm/`,
  API de operaciones y de inferencia con la cola sincrónica de los tests.

Frontend
- `constructor/Revision/` (wizard): tres secciones con semáforo
  (verde ≥ 0.9, amarillo 0.6 a 0.9, rojo < 0.6 o conflicto): Entidades y
  campos (nombre editable, tipo semántico, clave primaria), Relaciones
  (con la evidencia: inclusión, huérfanos, nombre), Métricas (nombre,
  formato, confirmar/rechazar, crear a mano). Botones "Confirmar todo lo
  verde" por sección y "Proponer dashboard" al final. Cada acción llama a
  `POST /modelo/operaciones` y refresca. Mismo estilo editorial; el semáforo
  usa la paleta validada (no rojo/verde puros: se distinguen por forma e
  ícono además del color).
- Fuentes: botón "Proponer modelo" (encola la tarea, polling, redirige al
  wizard); "Ver perfil" por fuente.
- Modelo: pestañas "Revisión" (wizard) y "Avanzado" (editor JSON actual).

## (4) Plan por pasos (cada uno: tests en verde, CLAUDE.md, commit, resumen)

- **Paso 9 — Perfilado.** `app/perfilado/`, `fuente.perfil` (migración),
  cálculo al final de la ingesta, endpoint y vista en Fuentes. v0.9.01.
- **Paso 10 — Heurísticas.** Claves primarias, relaciones, tipos
  semánticos, modelo propuesto con evidencia; tarea `inferencia.proponer_modelo`
  **sin Claude todavía**; test de aceptación: 4 de 4 relaciones y 5 de 5
  claves con los CSV sintéticos. v0.10.01.
- **Paso 11 — Claude.** SDK, `ClienteLLM` real y falso, prompt de
  semántica, fusión con lo heurístico y con el modelo existente, caché,
  test en vivo. v0.11.01. Necesita la clave de Sd.
- **Paso 12 — Operaciones granulares.** `aplicar_operacion` + endpoint +
  versiones con diff. v0.12.01.
- **Paso 13 — Wizard.** Pantalla Revisión con semáforos, confirmación en
  bloque, botón en Fuentes, pestaña Avanzado. v0.13.01.
- **Paso 14 — Spec inicial.** Generador determinista + curación por
  Claude + botón "Proponer dashboard". v0.14.01.
- **Paso 15 — Integración y aceptación.** Flujo desde cero con los 5 CSV
  en Docker, `docs/fase2-aceptacion.md`, `cargar_prueba.py --inferir` para
  reproducirlo por script. v0.14.02.

## (5) Skills y herramientas a usar

- `frontend-design` del repo para el wizard (misma dirección editorial).
- `dataviz` de Claude Code para el semáforo y la evidencia (colores de
  estado accesibles, validados con `validate_palette.js`).
- Agente `claude-code-guide` para confirmar la forma vigente de forzar JSON
  con el SDK (tool use / salida estructurada) antes del paso 11.
- Lo demás sigue igual: pytest por archivo, vitest, Docker Compose.

## (6) Qué se necesita de Sd

- Respuestas a las dudas 1 a 15 (se preguntan de a una).
- La `ANTHROPIC_API_KEY` en el `.env` local antes del paso 11.
- Si tiene los 5 CSV reales, ahora es el momento: las heurísticas se
  calibran contra ellos.

## (7) Respuestas de Sd (2026-09-09)

Aprobado el plan. Respuestas a las dudas:
1. Cuenta de API propia de Sd; **tope de gasto USD 10** para toda la fase. La
   clave la pone Sd en el `.env` local (Claude Code no la escribe).
2. `MODELO_CLAUDE` por defecto `claude-sonnet-5`, configurable.
3. 30 filas de muestra por tabla, `ENVIAR_MUESTRA_LLM` para apagarla.
4. Tabla `inferencia` como caché por huella y auditoría de tokens.
5. Tests sin red con cliente falso; test en vivo que se salta sin clave.
6. Inferencia **a pedido** con el botón "Proponer modelo", pero la pantalla
   de Fuentes avisa al terminar las ingestas que ese es el momento de
   proponer el modelo, y el botón se deshabilita mientras haya ingestas
   corriendo.
7. Reinferir **fusiona**: respeta lo confirmado y lo rechazado.
8. Todas las operaciones granulares en esta fase; deshacer en la 3.
9. Editor JSON queda como pestaña "Avanzado".
10. "Confirmar todo lo verde" por sección.
11. Spec base determinista curado por Claude; sin Claude se guarda el base.
12. Rioplatense, nombres cortos.
13. Sin SSE en esta fase.
14. Expresiones aritméticas libres en la fase 3.
15. Umbrales propuestos aprobados, ajustables por configuración.
