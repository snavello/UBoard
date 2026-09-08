# Datos de prueba

Cinco CSV de una cadena de almacenes ficticia (tres sucursales, un año de
ventas). **Son sintéticos**, generados por
`backend/scripts/generar_datos_prueba.py` (determinista: misma semilla,
mismos archivos). Cuando Sd entregue los CSV reales, reemplazan a estos.

Cada archivo trae la suciedad típica de un export real, a propósito, para
que la ingesta la resuelva y los tests lo comprueben:

| Archivo | Encoding | Separador | Suciedad |
|---|---|---|---|
| `vendedores.csv` | UTF-8 | `,` | Nombres con espacios sobrantes; emails vacíos. |
| `productos.csv` | **latin-1** | `;` | Precios con coma decimal y punto de miles (`1.250,50`); nombres con ñ y tildes; `activo` como Si/No. |
| `medios_pago.csv` | UTF-8 **con BOM** | `,` | El BOM no debe quedar pegado al primer encabezado. |
| `ventas.csv` | UTF-8 | `,` | Encabezados en CamelCase y con espacios (`IdVenta`, `Precio Unitario`); fechas en tres formatos mezclados (`2026-03-05`, `05/03/2026`, `5/3/2026`); 3% de ventas sin vendedor y 2% con vendedor huérfano (id 99); 1% de productos huérfanos (id 999); 2% de importes con `$ ` adelante. |
| `pagos.csv` | UTF-8 | `;` | **Dos filas de título** antes del encabezado; montos con coma decimal; fechas `dd/mm/aaaa`; 1% de pagos de ventas huérfanas (id 99999); 10% de ventas pagadas en dos partes. |

Relaciones esperadas: `ventas.vendedor → vendedores.id_vendedor`,
`ventas.id_producto → productos.id_producto`, `pagos.id_venta → ventas.id_venta`,
`pagos.id_medio_pago → medios_pago.id_medio_pago`.

`modelo.json` y `spec.json` (modelo semántico y spec de dashboard escritos a
mano para la fase 1) se agregan en los pasos 4 y 6.
