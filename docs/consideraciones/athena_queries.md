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
| Fecha en filtros`WHERE date = ...` | Debe coincidir con una partición realmente cargada                                              | Sustituir el literal`'2026-08-04'` por la fecha que hayas procesado (`bronze/<división>/date=<fecha>/`)                                                                              |

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
-- filas del archivo de origen en bronze/<division>/date=<fecha>/)
SELECT store, COUNT(*) AS num_sales
FROM gold
WHERE date = '2026-08-04'
GROUP BY store;
```

## Resultados esperados

| Pregunta                                        | Query                   | Resultado esperado                                                                                  |
| ----------------------------------------------- | ----------------------- | --------------------------------------------------------------------------------------------------- |
| ¿Qué categoría vende más?                   | "Ventas por categoría" | Una fila por categoría presente en los datos generados, ordenadas de mayor a menor`total_sales`. |
| ¿Cuáles son los 10 productos más vendidos?   | "Top 10 productos"      | Exactamente 10 filas (o menos si hay menos de 10 productos distintos en el dataset).                |
| ¿Qué división genera más ingresos?          | "Ventas por tienda"     | 4 filas, una por división (`electronica`, `supermercado`, `moda`, `marketplace`).          |
| ¿Cuál es el ticket promedio por división?    | "Ticket promedio"       | 4 filas con`avg_ticket > 0`.                                                                      |
| ¿Cómo se distribuyen las ventas en el tiempo? | "Ventas por día"       | Una fila por cada fecha para la que se generaron y procesaron archivos.                             |

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
- `specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md` — especificación completa de Glue/Athena y criterios de validación E2E.
- `specs/pipeline/SPEC-004_Infraestructura_Terraform.md` — definición de los módulos `glue_catalog` y `athena`.
- `docs/architecture.md` — flujo de datos y bitácora de cambios estructurales.
