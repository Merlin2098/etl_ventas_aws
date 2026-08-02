# SPEC-006 - Analítica y Validación End-to-End

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir la capa analítica del laboratorio (Glue Data Catalog + Athena) y los criterios que permitirán validar que la solución funciona correctamente de punta a punta durante el webinar.

---

# Glue Data Catalog

## Base de datos

- Una única `aws_glue_catalog_database` para el proyecto (ver naming en SPEC-004: `${name_prefix}_catalog`).

## Tablas

- No se declara `aws_glue_catalog_table` explícita en Terraform. El esquema se descubre mediante **Glue Crawler**, consistente con SPEC-004 (`glue_crawler_schedule` vacío = ejecución manual, sin scheduling automático).
- El Crawler apunta a `gold/` y registra una única tabla (ej. `sales`), con particiones `store` y `date` inferidas de la estructura de carpetas definida en SPEC-003 (`gold/store=<division>/date=<fecha>/`).
- El esquema de columnas resultante debe coincidir con el esquema Gold de SPEC-002 (`sale_id`, `date`, `store`, `category`, `product`, `quantity`, `price`, `total`); si el Crawler infiere tipos distintos a los esperados (ej. `price` como `string` en vez de `decimal`), se considera un defecto a corregir en el parser de origen, no en el Crawler.

## Descubrimiento de datos

Flujo operativo durante el webinar:

1. Ejecutar generadores → suben archivos a `bronze/`.
2. Las Lambdas procesan y escriben en `gold/` (y `quarantine/` si aplica).
3. **Ejecutar el Glue Crawler manualmente** (consola AWS o `aws glue start-crawler`) para que detecte la tabla y/o las particiones nuevas.
4. Esperar a que el estado del Crawler sea `READY` (consultable con `aws glue get-crawler`) antes de consultar en Athena.

No se usa `MSCK REPAIR TABLE` ni `ALTER TABLE ADD PARTITION` manual: **toda actualización de particiones pasa por una re-ejecución del Crawler**, manteniendo un único mecanismo de descubrimiento (más simple de explicar y depurar en vivo durante el webinar que combinar Crawler + comandos DDL manuales).

---

# Amazon Athena

## Configuración

- Workgroup dedicado (`modules/athena`, ver SPEC-004), con ubicación de resultados propia en S3.
- Todas las consultas se ejecutan contra la tabla única de `gold/` descubierta por el Crawler.

## Consultas SQL de ejemplo

Alineadas con las "Consultas de negocio" listadas en `Spec_General.md`:

```sql
-- Ventas por categoría
SELECT category, SUM(total) AS total_sales
FROM sales
GROUP BY category
ORDER BY total_sales DESC;

-- Top 10 productos por ingresos
SELECT product, SUM(total) AS revenue
FROM sales
GROUP BY product
ORDER BY revenue DESC
LIMIT 10;

-- Ventas por tienda (división)
SELECT store, SUM(total) AS total_sales, COUNT(*) AS num_sales
FROM sales
GROUP BY store
ORDER BY total_sales DESC;

-- Ticket promedio por división
SELECT store, AVG(total) AS avg_ticket
FROM sales
GROUP BY store;

-- Ventas por día
SELECT date, SUM(total) AS total_sales
FROM sales
GROUP BY date
ORDER BY date;

-- Productos con mayores ingresos por categoría
SELECT category, product, SUM(total) AS revenue
FROM sales
GROUP BY category, product
ORDER BY category, revenue DESC;
```

## Preguntas de negocio y resultados esperados

| Pregunta | Query | Resultado esperado |
|----------|-------|---------------------|
| ¿Qué categoría vende más? | "Ventas por categoría" | Una fila por categoría presente en los datos generados, ordenadas de mayor a menor `total_sales`. |
| ¿Cuáles son los 10 productos más vendidos? | "Top 10 productos" | Exactamente 10 filas (o menos si hay menos de 10 productos distintos en el dataset). |
| ¿Qué división genera más ingresos? | "Ventas por tienda" | 5 filas, una por división (`electronica`, `supermercado`, `moda`, `hogar`, `marketplace`). |
| ¿Cuál es el ticket promedio por división? | "Ticket promedio" | 5 filas con `avg_ticket > 0`. |
| ¿Cómo se distribuyen las ventas en el tiempo? | "Ventas por día" | Una fila por cada fecha para la que se generaron y procesaron archivos. |

---

# Validación End-to-End

## Criterios de aceptación

El laboratorio se considera funcionando correctamente cuando, tras ejecutar los 5 generadores para una fecha dada:

1. Los 5 archivos de origen existen en `bronze/date=<fecha>/`.
2. Cada archivo disparó su Lambda correspondiente (evidencia: logs de CloudWatch, ver abajo).
3. Existen archivos Parquet en `gold/store=<division>/date=<fecha>/` para las 5 divisiones.
4. Existen archivos de error en `quarantine/store=<division>/date=<fecha>/` para las filas inválidas generadas intencionalmente (SPEC-002).
5. El Glue Crawler, tras ejecutarse, registra la tabla `sales` con las particiones de la fecha procesada.
6. Las queries de la sección anterior se ejecutan sin error en Athena y devuelven resultados consistentes con los criterios de la tabla "Preguntas de negocio".

## Validación funcional

- **Conteo de filas Gold vs Bronze**: por cada división, `filas_validas_en_gold + filas_en_quarantine == filas_totales_en_archivo_origen`. Una discrepancia indica filas perdidas silenciosamente (defecto a corregir, ver SPEC-005 — nunca se debe descartar una fila sin registrarla en cuarentena).
- **Revisión de quarantine**: las filas en `quarantine/` deben corresponder a los errores intencionales sembrados por los generadores (SPEC-002) — mismo tipo de error, mismo `stage` en el registro. Si aparecen filas en cuarentena sin causa esperada, o si faltan las esperadas, se considera un defecto del parser o de las reglas de validación.

## Validación del despliegue

- `terraform plan` sin cambios pendientes tras el último `apply` (infraestructura declarada = infraestructura real).
- Las 5 funciones Lambda existen y referencian una imagen ECR válida (no `latest`, ver SPEC-004/SPEC-005).
- Los outputs de Terraform (`lambda_function_arns`, `glue_database_name`, `athena_workgroup_name`, etc., ver SPEC-004) resuelven a recursos existentes.

## Validación del procesamiento

- **Logs de CloudWatch por Lambda**: cada log group (`/aws/lambda/${name_prefix}-ingestion-<division>`) debe mostrar, para la invocación de la fecha probada:
  - Un registro `INFO` de inicio (`stage="parse"`).
  - Un registro `INFO` de fin con conteo de filas válidas/inválidas.
  - Ningún registro `ERROR` no esperado (una `FileParseError` solo es esperada si el archivo de prueba fue deliberadamente corrupto).

## Validación de consultas

- Cada query de la sección "Consultas SQL de ejemplo" debe ejecutarse sin error de sintaxis ni de esquema (columnas/tipos coinciden con SPEC-002).
- Los resultados deben ser explicables a partir de los datos sintéticos generados (por ejemplo, si un generador produjo 0 filas válidas para una división en la fecha probada, esa división no debe aparecer en agregaciones "por tienda" para esa fecha, y esto es un resultado válido, no un error).

## Evidencias esperadas

Para dar por validado el laboratorio durante el webinar, se recopila:

1. Resultados (capturas o export) de las queries Athena de la sección anterior.
2. Logs de CloudWatch de las 5 Lambdas para la invocación de prueba.
3. Conteo de filas Gold vs Bronze por división (manual o vía query auxiliar `SELECT store, COUNT(*) FROM sales WHERE date = '<fecha>' GROUP BY store`, comparado contra el conteo de filas del archivo de origen).
4. Listado de objetos en `quarantine/store=<division>/date=<fecha>/` con su contenido, confirmando que los errores intencionales fueron capturados.

---

# Fuera de alcance

- Automatización de la validación E2E (tests automatizados contra AWS real); esta demo usa verificación manual/guiada durante el webinar. Tests boto3 en `tests/aws/` (Policy 009) pueden añadirse como evolución futura pero no son parte del alcance mínimo de esta demo.
- Alertas o dashboards de monitoreo continuo (QuickSight, CloudWatch Dashboards) — mencionado como evolución futura en SPEC-001.
- Validación de performance o carga (el volumen de datos es intencionalmente pequeño, ver SPEC-002).
