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
- El Crawler apunta a `gold/` y registra una única tabla, con particiones `store` y `date` inferidas de la estructura de carpetas definida en SPEC-003 (`gold/store=<division>/date=<fecha>/`). Sin `table_prefix` configurado en `aws_glue_crawler`, el nombre de la tabla lo deriva el Crawler del último segmento del path S3 (`gold/` → tabla **`gold`**, confirmado en despliegue real el 2026-08-04); las queries de esta spec usan ese nombre, no `sales`.
- El esquema de columnas resultante debe coincidir con el esquema Gold de SPEC-002 (`sale_id`, `date`, `store`, `category`, `product`, `quantity`, `price`, `total`); si el Crawler infiere tipos distintos a los esperados (ej. `price` como `string` en vez de `decimal`), se considera un defecto a corregir en el parser de origen, no en el Crawler. **Excepción conocida:** la partición `date` se cataloga como `varchar`, no como `date` tipado — comportamiento por defecto del Crawler al inferir particiones Hive desde el path (`date=YYYY-MM-DD/`), no un defecto del parser. Las queries que filtran por fecha deben comparar contra un string literal (`date = '2026-08-04'`), no `DATE '2026-08-04'` (falla con `TYPE_MISMATCH: Cannot apply operator: varchar = date`), ver "Consultas SQL de ejemplo".

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
- `enforce_workgroup_configuration = true` (ver SPEC-004) fuerza toda ejecución, incluido `CREATE TABLE AS SELECT`, a la ubicación de resultados del workgroup: un CTAS con `external_location` propio falla con `InvalidRequestException`. Ver `docs/consideraciones/athena_queries.md` para el patrón correcto (CTAS sin esa cláusula) y más ejemplos de queries que van más allá del `SELECT` simple (self-joins, window functions).

## Consultas SQL de ejemplo

Alineadas con las "Consultas de negocio" listadas en `SPEC-001_Vision_General.md`:

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

-- Filtrar por fecha: `date` se cataloga como varchar (ver "Tablas"), comparar
-- contra string literal, nunca DATE 'YYYY-MM-DD' (TYPE_MISMATCH).
SELECT store, date, COUNT(*) AS num_sales
FROM gold
WHERE date = '2026-08-04'
GROUP BY store, date
ORDER BY store;
```

## Preguntas de negocio y resultados esperados

| Pregunta | Query | Resultado esperado |
|----------|-------|---------------------|
| ¿Qué categoría vende más? | "Ventas por categoría" | Una fila por categoría presente en los datos generados, ordenadas de mayor a menor `total_sales`. |
| ¿Cuáles son los 10 productos más vendidos? | "Top 10 productos" | Exactamente 10 filas (o menos si hay menos de 10 productos distintos en el dataset). |
| ¿Qué división genera más ingresos? | "Ventas por tienda" | 4 filas, una por división (`electronica`, `supermercado`, `moda`, `marketplace`). |
| ¿Cuál es el ticket promedio por división? | "Ticket promedio" | 4 filas con `avg_ticket > 0`. |
| ¿Cómo se distribuyen las ventas en el tiempo? | "Ventas por día" | Una fila por cada fecha para la que se generaron y procesaron archivos. |

---

# Validación End-to-End

## Criterios de aceptación

El laboratorio se considera funcionando correctamente cuando, tras ejecutar los 4 generadores para una fecha dada:

1. Los 4 archivos de origen existen en `bronze/<division>/date=<fecha>/`.
2. Cada archivo disparó, vía EventBridge, su Lambda de ingesta correspondiente (evidencia: logs de CloudWatch, ver abajo).
3. Existen archivos Parquet en `silver/store=<division>/date=<fecha>/` para las 4 divisiones, lo que a su vez disparó, vía EventBridge, la Lambda de transformación correspondiente.
4. Existen archivos Parquet en `gold/store=<division>/date=<fecha>/` para las 4 divisiones.
5. Existen archivos de error en `quarantine/store=<division>/date=<fecha>/` para las filas inválidas generadas intencionalmente (SPEC-002).
6. El Glue Crawler, tras ejecutarse, registra la tabla `gold` con las particiones de la fecha procesada (ver "Tablas" para el nombre real).
7. Las queries de la sección anterior se ejecutan sin error en Athena y devuelven resultados consistentes con los criterios de la tabla "Preguntas de negocio".

## Validación funcional

- **Conteo de filas consistente entre etapas**: por cada división, `filas_en_silver + filas_en_quarantine_de_ingesta == filas_totales_en_archivo_origen`, y `filas_en_gold == filas_en_silver` (las reglas de Gold reaplican las mismas validaciones de campo que Silver ya superó, ver SPEC-005 — no deberían rechazarse filas adicionales en esa segunda pasada). Una discrepancia indica filas perdidas silenciosamente (defecto a corregir — nunca se debe descartar una fila sin registrarla en cuarentena).
- **Revisión de quarantine**: las filas en `quarantine/` deben corresponder a los errores intencionales sembrados por los generadores (SPEC-002) — mismo tipo de error, mismo `stage` en el registro. Si aparecen filas en cuarentena sin causa esperada, o si faltan las esperadas, se considera un defecto del parser o de las reglas de validación.
- **Integridad de encoding**: los valores de `category`/`product` en Gold no deben contener caracteres de reemplazo (`�`, U+FFFD) ni mojibake — una fila con corrupción intencional de encoding (SPEC-007, "Errores intencionales") no debe degradar la codificación de ninguna otra fila del mismo archivo (ver "Validación local pre-despliegue" para el test automatizado que cubre esta regresión).

## Validación del despliegue

- `terraform plan` sin cambios pendientes tras el último `apply` (infraestructura declarada = infraestructura real).
- Las 8 funciones Lambda (4 de ingesta + 4 de transformación) existen y referencian una imagen ECR válida (no `latest`, ver SPEC-004/SPEC-005).
- Las 8 reglas de EventBridge (4 de ingesta + 4 de transformación) existen, están `ENABLED`, y cada una tiene exactamente un target apuntando a la Lambda correcta. Cada Lambda tiene un `aws_lambda_permission` con `principal = events.amazonaws.com` scopeado al ARN de su regla (ver SPEC-004) — esta verificación es la que faltaba y permitió que INCIDENTE-001 pasara desapercibido hasta la corrida E2E.
- El bucket de datos tiene las notificaciones a EventBridge habilitadas (`EventBridgeConfiguration` no nulo).
- Los outputs de Terraform (`lambda_function_arns`, `eventbridge_rule_names`, `glue_database_name`, `athena_workgroup_name`, etc., ver SPEC-004) resuelven a recursos existentes.
- El rol IAM del Glue Crawler incluye `glue:BatchGetPartition` (ver SPEC-004 `modules/glue_catalog`): sin este permiso, `start-crawler` termina en `Status: FAILED` con `AccessDeniedException` al reconciliar particiones, y ninguna tabla queda disponible para Athena — detectado por primera vez en la validación E2E del 2026-08-04.

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
2. Logs de CloudWatch de las 4 Lambdas para la invocación de prueba.
3. Conteo de filas Gold vs Bronze por división (manual o vía query auxiliar `SELECT store, COUNT(*) FROM gold WHERE date = '<fecha>' GROUP BY store`, comparado contra el conteo de filas del archivo de origen).
4. Listado de objetos en `quarantine/store=<division>/date=<fecha>/` con su contenido, confirmando que los errores intencionales fueron capturados.
5. Resultado en verde de `tests/aws/` (ver "Tests automatizados de infraestructura").

---

# Validación local pre-despliegue

Antes de desplegar infraestructura en AWS, el pipeline completo (parseo, normalización
Silver, validación Gold, cuarentena) puede ejercitarse enteramente en el equipo local, sin
credenciales AWS ni recursos en la nube. Esto permite detectar defectos de lógica de negocio
(reglas de validación, normalización de fecha, encoding) antes de invertir tiempo en
`terraform apply` y en la depuración vía CloudWatch.

## Simulación manual (`run_local_ingestion.py`)

`scripts/testing/run_local_ingestion.py` reproduce localmente el mismo flujo de las dos
Lambdas (`handler_base.process_event` y `transform_handler_base.process_transform_event`,
ver SPEC-005), leyendo/escribiendo archivos en disco en vez de S3:

```
python scripts/testing/run_local_ingestion.py
```

Sin argumentos, corre las 4 divisiones (`--division all`, default) contra
`data/<division>_<fecha-de-hoy>.<ext>` (mismo esquema de nombres que usa el generador, ver
SPEC-007). También admite una sola división con archivo explícito:

```
python scripts/testing/run_local_ingestion.py --division electronica --file data/electronica_2026-08-02.csv --stage both
```

| Argumento | Descripción | Default |
|-----------|-------------|---------|
| `--division` | División específica, o `all` para las 4 en secuencia | `all` |
| `--file` | Ruta a un archivo Bronze. Solo válido con una división específica (error si se combina con `all`); si se omite, se resuelve como `data/<division>_<fecha>.<ext>` | resuelto desde `--date` |
| `--date` | Fecha usada para resolver `--file` por defecto | Fecha de ejecución (hoy) |
| `--stage` | `silver` (solo Bronze→Silver), `gold` (asume Silver ya calculado en memoria y corre Silver→Gold), o `both` | `both` |
| `--out-dir` | Carpeta local de salida (`silver/`, `gold/`, `quarantine/`) | `data/local_run/` |

La salida local usa el mismo formato que la Lambda real escribiría en S3: Parquet para
`silver/` y `gold/` (con `SILVER_SCHEMA`/`GOLD_SCHEMA` de `common/schema.py`, no JSON), y
JSON para `quarantine/` (mismo formato `{row, error}` que `write_quarantine`). Un archivo
faltante para alguna división se reporta como `SKIPPED` sin detener el resto de divisiones.

## Test E2E automatizado (`tests/e2e/`)

`tests/e2e/test_pipeline_local.py` automatiza la misma simulación con pytest, sin AWS:

- Genera datos Bronze frescos para las 4 divisiones con semilla fija (reproducible),
  reutilizando `generate_division()` (SPEC-007) directamente — no reimplementa el
  generador.
- Corre cada archivo por `run_bronze_to_silver`/`run_silver_to_gold` (las mismas funciones
  que usa la simulación manual descrita arriba).
- Por división, verifica: el Parquet Silver y Gold cumplen exactamente su esquema
  (`SILVER_SCHEMA`/`GOLD_SCHEMA`), tienen filas, los conteos de filas son consistentes entre
  Silver y Gold, `total == price * quantity` en cada fila Gold, y no aparecen caracteres de
  reemplazo (`�`) en `category`/`product` — esta última es una guarda de regresión
  específica para el bug de encoding descrito abajo.
- Una prueba adicional cruza los alias de categoría con tilde/ñ declarados en
  `src/generators/detalle-data.yaml` contra lo que efectivamente aparece en Gold, para
  detectar corrupción de encoding de forma más agresiva que revisar filas al azar.

Se ejecuta junto al resto de unit tests (`scripts/testing/run_pytest.py`), sin marcador
`cloud` — no requiere credenciales AWS ni red.

## Regresión de encoding en el parser CSV (Electrónica)

Durante esta validación local se detectó y corrigió un defecto real: `CsvSalesParser.parse()`
(`src/lambda_ingestion/electronica/parser.py`) decodificaba el archivo completo con un único
`raw_bytes.decode("utf-8")`, con fallback a `latin-1` si fallaba. Como el generador siembra
una corrupción intencional de encoding en una sola fila por archivo (SPEC-007, "Errores
intencionales" — un byte no-UTF-8 suelto en `product`), esa única fila corrupta hacía fallar
el `decode()` de **todo el archivo**, degradando a `latin-1` — que reinterpreta los caracteres
UTF-8 multibyte válidos (tildes, ñ) de las 349 filas restantes como mojibake, aunque estuvieran
correctamente codificadas en el archivo de origen.

**Corrección aplicada**: el parser decodifica línea por línea (helper `_decode_line`), con el
mismo fallback UTF-8 → Latin-1 aplicado por fila en vez de por archivo. Esto aísla la
corrupción intencional a la fila que la contiene (que sigue cayendo a cuarentena, comportamiento
esperado) sin afectar la codificación de las demás filas. Cubierto por
`test_gold_output_has_no_mojibake_in_text_fields` y
`test_all_known_category_aliases_appear_uncorrupted_in_gold` en `tests/e2e/`.

---

# Tests automatizados de infraestructura

Siguiendo Policy 009 (Required, `ai/policies/global.md`), toda infraestructura AWS
desplegada debe incluir tests de humo en `tests/aws/`, generados según la plantilla de
`ai/skills/aws/aws_smoke_testing.md`:

- `tests/aws/conftest.py`: fixture `aws_client` (boto3, credenciales desde
  `infra/env/.env.credentials` o variables de entorno) y `tf_outputs` (lee
  `terraform output -json`). Si no hay credenciales, los tests hacen **skip**, nunca fallan.
- `tests/aws/test_smoke.py`: valida, contra los outputs reales de Terraform (nunca ARNs
  hardcodeados) — identidad STS, existencia del bucket de datos, las 8 funciones Lambda
  (ingesta + transformación por división), sus log groups, la base de datos y el crawler
  de Glue, y el workgroup de Athena.
- Se ejecutan con `python scripts/testing/run_cloud_tests.py` (marcador `pytest.mark.cloud`,
  ver `pytest.ini`), separados de los tests unitarios (`make test` / `run_pytest.py`), que
  nunca requieren credenciales AWS.

Estos tests son un complemento a la validación E2E manual descrita arriba, no un
reemplazo: dan una señal rápida de "la infraestructura existe y es accesible" antes de
invertir tiempo en la validación funcional completa durante el webinar.

Además, `tests/e2e/test_pipeline_aws.py` (marcador `pytest.mark.cloud`, mismo mecanismo de
ejecución) sí ejercita el pipeline end-to-end **contra AWS real**: sube un archivo de origen
real por división a `bronze/`, deja que el trigger de EventBridge dispare ambas etapas sin
intervención manual, y hace polling sobre S3 hasta encontrar los objetos Silver y Gold
esperados (o falla por timeout, ver `POLL_TIMEOUT_SECONDS`). Es el criterio de cierre de
INCIDENTE-001.

---

# Fuera de alcance

- Alertas o dashboards de monitoreo continuo (QuickSight, CloudWatch Dashboards) — mencionado como evolución futura en SPEC-001.
- Validación de performance o carga (el volumen de datos es intencionalmente pequeño, ver SPEC-002).
