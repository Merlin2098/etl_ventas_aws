# Queries de ejemplo para Athena

Consultas listas para pegar en el editor de Athena, alineadas con las
"Consultas de negocio" de `SPEC-001_Vision_General.md` y con el esquema Gold
de `SPEC-002_Modelo_Datos_Datasets.md`. Corridas y verificadas contra el
despliegue real el 2026-08-04 (ver `SPEC-006_Analitica_Validacion_E2E.md`,
sección "Validación End-to-End").

## Antes de correr: qué configurar

| Dónde                               | Qué es                                                                                          | Cómo obtenerlo                                                                                                                                                                           |
| ------------------------------------ | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workgroup de Athena                  | Contexto de ejecución de la query                                                               | `terraform -chdir=infra output athena_workgroup_name` (ej. `data-platform-dev-workgroup`)                                                                                             |
| Base de datos                        | Contexto (`QueryExecutionContext.Database` por CLI, o selector de base de datos en la consola) | `terraform -chdir=infra output glue_database_name` (ej. `data_platform_dev_catalog`)                                                                                                  |
| Tabla                                | Nombre usado en cada`FROM` de este documento                                                   | **`gold`** — el Glue Crawler no tiene `table_prefix` configurado, así que deriva el nombre del último segmento del path S3 (`gold/`), no `sales` (ver SPEC-006 "Tablas") |
| Fecha en filtros`WHERE date = ...` | Debe coincidir con una partición realmente cargada                                              | Sustituir el literal`'2026-08-04'` por la fecha que hayas procesado (`bronze/date=<fecha>/<división>/`)                                                                              |

**Requisito previo:** el Glue Crawler debe haber corrido con éxito antes de
consultar datos recién cargados — el descubrimiento de particiones es manual
en este proyecto. Ver `docs/consideraciones/glue_crawler.md` para cómo
correrlo y por qué no es automático.

## Por qué `date` es un string, no un `DATE`

El Crawler cataloga la partición `date` (codificada en el path como
`gold/store=<division>/date=YYYY-MM-DD/`) como **`varchar`**, no como tipo
`date`. Es el comportamiento por defecto de Glue al inferir particiones Hive
desde el path, no un defecto del parser (ver SPEC-006 "Tablas").

Consecuencia práctica: cualquier filtro por fecha debe comparar contra un
**string literal**.

```sql
-- Correcto
WHERE date = '2026-08-04'

-- Falla con TYPE_MISMATCH: Cannot apply operator: varchar = date
WHERE date = DATE '2026-08-04'
```

## Queries

```sql
-- Ventas por categoría
SELECT category, SUM(total) AS total_sales
FROM gold
GROUP BY category
ORDER BY total_sales DESC;

-- Top 10 productos por ingresos
SELECT product, SUM(total) AS revenue
FROM gold
GROUP BY product
ORDER BY revenue DESC
LIMIT 10;

-- Ventas por tienda (división)
SELECT store, SUM(total) AS total_sales, COUNT(*) AS num_sales
FROM gold
GROUP BY store
ORDER BY total_sales DESC;

-- Ticket promedio por división
SELECT store, AVG(total) AS avg_ticket
FROM gold
GROUP BY store;

-- Ventas por día
SELECT date, SUM(total) AS total_sales
FROM gold
GROUP BY date
ORDER BY date;

-- Productos con mayores ingresos por categoría
SELECT category, product, SUM(total) AS revenue
FROM gold
GROUP BY category, product
ORDER BY category, revenue DESC;

-- Filtrar por una fecha específica (sustituir el literal, ver tabla arriba)
SELECT store, date, COUNT(*) AS num_sales
FROM gold
WHERE date = '2026-08-04'
GROUP BY store, date
ORDER BY store;

-- Conteo Gold vs. Bronze por división para una fecha (validación de consistencia,
-- ver SPEC-006 "Validación funcional" — comparar el resultado contra el conteo de
-- filas del archivo de origen en bronze/date=<fecha>/<division>/)
SELECT store, COUNT(*) AS num_sales
FROM gold
WHERE date = '2026-08-04'
GROUP BY store;

-- Ventas por moneda y por estado (SPEC-008 #5/#10 — sin homologar entre
-- divisiones: cada una usa su propio catálogo de currency/status, ver
-- "Columnas específicas por división" más abajo)
SELECT store, currency, status, COUNT(*) AS num_sales, SUM(total) AS total_sales
FROM gold
GROUP BY store, currency, status
ORDER BY store, total_sales DESC;
```

## Columnas específicas por división (SPEC-009 §2)

Más allá del esquema común (`sale_id`, `category`, `product`, `quantity`,
`price`, `total`, `currency`, `status`), cada división aporta sus propias
columnas — reflejando que cada una simula un sistema empresarial distinto
(ERP, POS, e-commerce, marketplace de terceros). Todas son **nullable**: una
fila de Electrónica trae `NULL` en las columnas de Marketplace, y viceversa —
`gold` sigue siendo una única tabla, sin tabla por división. Detalle completo
del esquema en
[SPEC-002](../../specs/pipeline/SPEC-002_Modelo_Datos_Datasets.md#campos-específicos-por-división-spec-009-2).

| División    | Columnas propias                                                              |
| ------------ | ----------------------------------------------------------------------------- |
| Electrónica | `serial_number`, `warranty_months`, `manufacturer`, `model`           |
| Supermercado | `cashier`, `loyalty_points`, `promotion_applied`, `register_number`   |
| Moda         | `size`, `color`, `collection`, `season`, `return_reason`            |
| Marketplace  | `seller_id`, `marketplace_fee`, `commission_pct`, `shipping_provider` |

Estas columnas no tienen regla de validación de negocio en esta fase (una
fila con `manufacturer` ausente o mal formado no va a cuarentena solo por
eso), así que pueden aparecer como `NULL` incluso dentro de su propia
división — filtrar por `IS NOT NULL` cuando corresponda.

> Las queries de esta sección y "Ventas por moneda y por estado" (arriba) son
> nuevas junto con estas columnas (SPEC-009 §2) — sintácticamente válidas
> contra `GOLD_SCHEMA`, pero **no** corridas todavía contra un despliegue
> real (a diferencia del resto del documento, verificado el 2026-08-04). Si
> encontrás algo que no coincide con el resultado real, es la primera fuente
> a corregir.

```sql
-- Electrónica: ventas por fabricante, con garantía promedio
SELECT manufacturer, COUNT(*) AS num_sales, SUM(total) AS total_sales, AVG(warranty_months) AS avg_warranty_months
FROM gold
WHERE store = 'electronica' AND manufacturer IS NOT NULL
GROUP BY manufacturer
ORDER BY total_sales DESC;

-- Supermercado: ventas y puntos de lealtad otorgados por cajero
SELECT cashier, COUNT(*) AS num_sales, SUM(total) AS total_sales, SUM(loyalty_points) AS total_loyalty_points
FROM gold
WHERE store = 'supermercado' AND cashier IS NOT NULL
GROUP BY cashier
ORDER BY total_sales DESC;

-- Supermercado: impacto de las promociones en el ticket promedio
SELECT promotion_applied, COUNT(*) AS num_sales, AVG(total) AS avg_ticket
FROM gold
WHERE store = 'supermercado' AND promotion_applied IS NOT NULL
GROUP BY promotion_applied;

-- Moda: devoluciones por motivo (return_reason solo está presente en una
-- fracción de filas RETURNED/EXCHANGED, no en toda la división — ver SPEC-007)
SELECT return_reason, COUNT(*) AS num_returns
FROM gold
WHERE store = 'moda' AND return_reason IS NOT NULL
GROUP BY return_reason
ORDER BY num_returns DESC;

-- Moda: ventas por colección y talla
SELECT collection, size, COUNT(*) AS num_sales, SUM(total) AS total_sales
FROM gold
WHERE store = 'moda'
GROUP BY collection, size
ORDER BY collection, total_sales DESC;

-- Marketplace: comisión total retenida por vendedor
SELECT seller_id, COUNT(*) AS num_sales, SUM(total) AS gross_sales, SUM(marketplace_fee) AS total_fees
FROM gold
WHERE store = 'marketplace' AND seller_id IS NOT NULL
GROUP BY seller_id
ORDER BY gross_sales DESC;

-- Marketplace: ventas por transportista logístico
SELECT shipping_provider, COUNT(*) AS num_sales, SUM(total) AS total_sales
FROM gold
WHERE store = 'marketplace' AND shipping_provider IS NOT NULL
GROUP BY shipping_provider
ORDER BY total_sales DESC;
```

## Resultados esperados

| Pregunta                                                       | Query                            | Resultado esperado                                                                                                                             |
| -------------------------------------------------------------- | -------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| ¿Qué categoría vende más?                                  | "Ventas por categoría"          | Una fila por categoría presente en los datos generados, ordenadas de mayor a menor`total_sales`.                                            |
| ¿Cuáles son los 10 productos más vendidos?                  | "Top 10 productos"               | Exactamente 10 filas (o menos si hay menos de 10 productos distintos en el dataset).                                                           |
| ¿Qué división genera más ingresos?                         | "Ventas por tienda"              | 4 filas, una por división (`electronica`, `supermercado`, `moda`, `marketplace`).                                                     |
| ¿Cuál es el ticket promedio por división?                   | "Ticket promedio"                | 4 filas con`avg_ticket > 0`.                                                                                                                 |
| ¿Cómo se distribuyen las ventas en el tiempo?                | "Ventas por día"                | Una fila por cada fecha para la que se generaron y procesaron archivos.                                                                        |
| ¿En qué moneda y estado están las ventas de cada división? | "Ventas por moneda y por estado" | Varias filas por división — cada una usa su propio catálogo de`currency`/`status` (ver `detalle-data.yaml`), sin homologar entre sí. |

## Más allá del SELECT simple: joins, window functions y CTAS

`gold` es una única tabla aplanada (sin dimensiones separadas), así que no hay
joins "clásicos" tabla-hecho contra tabla-dimensión. Pero sí hay patrones
útiles para una demo que van más allá de `SELECT ... GROUP BY`, todos
corridos y verificados contra el despliegue real (2026-08-04).

### Self-join: comparar una partición contra otra

Útil para "¿cómo cambiaron las ventas de una fecha a otra?" — cada lado del
join es una subquery filtrada a una fecha distinta, unidas por `store`:

```sql
SELECT
  hoy.store,
  hoy.date AS fecha_actual,
  hoy.total_sales AS ventas_hoy,
  ayer.total_sales AS ventas_dia_anterior,
  hoy.total_sales - ayer.total_sales AS variacion
FROM
  (SELECT store, date, SUM(total) AS total_sales FROM gold WHERE date = '2026-08-04' GROUP BY store, date) hoy
JOIN
  (SELECT store, date, SUM(total) AS total_sales FROM gold WHERE date = '2026-08-02' GROUP BY store, date) ayer
  ON hoy.store = ayer.store
ORDER BY hoy.store;
```

Ajustar ambas fechas del `WHERE` a particiones que existan (ver la nota sobre
`date` como `varchar` arriba).

### Window functions: rankings dentro de cada grupo

No requieren join — resuelven "top N por grupo" en una sola pasada con
`RANK()`/`ROW_NUMBER()` particionado por `store`:

```sql
-- Top 3 productos por ingresos, dentro de cada división
SELECT store, product, revenue, rnk
FROM (
  SELECT
    store,
    product,
    SUM(total) AS revenue,
    RANK() OVER (PARTITION BY store ORDER BY SUM(total) DESC) AS rnk
  FROM gold
  GROUP BY store, product
)
WHERE rnk <= 3
ORDER BY store, rnk;
```

### CTAS: materializar un agregado como tabla nueva

`CREATE TABLE AS SELECT` no es solo lectura — escribe el resultado como una
tabla Parquet nueva en S3, útil para mostrar una capa "gold agregado" derivada
sin tocar el pipeline de Lambdas.

**Importante:** el workgroup de este proyecto fuerza una ubicación de
resultados centralizada (`enforce_workgroup_configuration = true`, ver
`infra/modules/athena/main.tf`) — un CTAS con `external_location` propio falla
con `InvalidRequestException`. Omitir esa cláusula; Athena coloca la tabla
bajo `athena-results/tables/` automáticamente:

```sql
CREATE TABLE gold_daily_summary
WITH (format = 'PARQUET', write_compression = 'SNAPPY') AS
SELECT
  store,
  date,
  category,
  COUNT(*) AS num_sales,
  SUM(total) AS total_sales,
  AVG(total) AS avg_ticket
FROM gold
GROUP BY store, date, category;
```

La tabla queda registrada en el mismo catálogo (`data_platform_dev_catalog`) y
se consulta como cualquier otra: `SELECT * FROM gold_daily_summary`. Para
limpiarla después de la demo: `DROP TABLE gold_daily_summary` (no elimina el
Parquet subyacente en S3 automáticamente — si se quiere liberar espacio,
borrar también el prefijo `athena-results/tables/<uuid>/` reportado por
`aws glue get-table --name gold_daily_summary`).

**Hallazgo real al probar CTAS**: agrupar por `category` sobre los datos
sintéticos expone variantes sin normalizar de la misma categoría real (ej.
`Telefonía`, `TEL`, `Computacion`, `Computación` como valores distintos en
Electrónica) — esto es intencional (SPEC-006 menciona los alias de categoría
con tilde/ñ sembrados por los generadores), no un defecto del pipeline. Buen
ejemplo en vivo de por qué una capa de agregación adicional necesitaría
normalizar categorías antes de agrupar, si se quisiera un reporte "limpio".

## Ver también

- `docs/consideraciones/glue_crawler.md` — cómo y cuándo correr el Crawler antes de que estas queries vean datos nuevos.
- `specs/pipeline/SPEC-002_Modelo_Datos_Datasets.md` — esquema Gold completo, incluidas las columnas específicas por división.
- `specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md` — especificación completa de Glue/Athena y criterios de validación E2E.
- `specs/pipeline/SPEC-004_Infraestructura_Terraform.md` — definición de los módulos `glue_catalog` y `athena`.
- `docs/architecture.md` — flujo de datos y bitácora de cambios estructurales.
