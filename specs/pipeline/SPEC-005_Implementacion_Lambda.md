# SPEC-005 - Implementación de la Lambda

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir la arquitectura interna de las funciones Lambda responsables del procesamiento de archivos, dos etapas por división (ingesta y transformación, ver SPEC-004), incluyendo el contrato compartido de los parsers, validaciones, manejo de errores, logging y empaquetado Docker.

---

# Arquitectura interna

Cada función Lambda es un despliegue independiente (función propia, rol IAM propio — ver SPEC-004), pero las 8 (4 divisiones × 2 etapas) comparten un **paquete de código común** para evitar duplicar validación, escritura en S3 y logging. Las Lambdas de ingesta y transformación de una misma división comparten además la misma imagen Docker (ver "Uso de Docker y Amazon ECR").

```
Lambda de ingesta (division):
  handler (division) → parser (division) → normalize_silver (común) → write silver/quarantine (común)

Lambda de transformación (division):
  handler (transform, genérico) → read Parquet Silver → validate_and_normalize (común) → write gold/quarantine (común)
```

`normalize_silver` y `validate_and_normalize` comparten un helper interno (`_normalize_core` en `common/schema.py`) para las reglas de campo (fecha, categoría, producto, cantidad, precio, currency, status), evitando duplicar esa lógica entre etapas — ver "Validaciones".

## Contrato del evento de entrada

Ambos handlers reciben `(event, context)` desde Lambda. `event` puede llegar en dos formas
distintas según el origen de la invocación (ver SPEC-003 "Eventos de S3"):

- **Notificación S3 directa** (mecanismo previo a la migración a EventBridge): `event["Records"][0]["s3"]`, con `["bucket"]["name"]` y `["object"]["key"]`. La `key` viene **URL-encoded** por S3 (espacios como `+`).
- **EventBridge** (mecanismo actual): `event["detail"]`, con `["bucket"]["name"]` y `["object"]["key"]`. La `key` llega **sin codificar**.

`common/s3_event.py` expone `extract_s3_location(event) -> tuple[str, str]`, el único punto
de entrada que ambos `handler_base.py` y `transform_handler_base.py` usan para leer
`(bucket, key)`: detecta cuál de las dos formas recibió (`"Records" in event` vs.
`"detail" in event`) y aplica el `unquote_plus` solo cuando corresponde. Aceptar ambos
envelopes en el mismo binario permite desplegar el código antes que el cambio de
infraestructura, sin que ninguna de las dos formas rompa el handler.

---

# Organización del código

```
src/
├── lambda_ingestion/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── schema.py                    # esquemas Silver/Gold (SPEC-002) + validación de fila
│   │   ├── errors.py                    # jerarquía de excepciones tipadas
│   │   ├── logging_config.py            # JsonFormatter + PipelineLogger (ver "Logging")
│   │   ├── s3_writer.py                 # escritura Parquet a silver/gold, JSON a quarantine/
│   │   ├── parser_base.py               # contrato abstracto de parser (ver "Contrato de los parsers")
│   │   ├── handler_base.py              # flujo Lambda de ingesta: parse → normalize_silver → write silver/quarantine
│   │   └── transform_handler_base.py    # flujo Lambda de transformación: read silver → validate_and_normalize → write gold/quarantine
│   ├── electronica/
│   │   ├── handler.py                   # Lambda de ingesta
│   │   └── parser.py                    # CSV
│   ├── supermercado/
│   │   ├── handler.py                   # Lambda de ingesta
│   │   └── parser.py                    # Excel (.xlsx)
│   ├── moda/
│   │   ├── handler.py                   # Lambda de ingesta
│   │   └── parser.py                    # JSON
│   ├── marketplace/
│   │   ├── handler.py                   # Lambda de ingesta
│   │   └── parser.py                    # PDF
│   └── transform/
│       └── handler.py                   # Lambda de transformación, genérico (una sola vez, no por división)
docker/
└── Dockerfile              # único, parametrizado con ARG DIVISION (ver "Uso de Docker y Amazon ECR")
```

Siguiendo `ai/skills/aws/lambda_packaging.md`, que exige un único `docker/Dockerfile` en
la raíz del proyecto (no un archivo por división): se usa **un solo Dockerfile** con
`ARG DIVISION`, invocado 4 veces con distinto `--build-arg DIVISION=<division>` por el
script de build (ver `scripts/docker_push.sh`, SPEC-004 "Flujo de despliegue"). Cada build
copia `common/` (que incluye tanto `handler_base.py` como `transform_handler_base.py`, más
`transform/handler.py`) más la carpeta de la división indicada por el `ARG`, manteniendo la
imagen resultante mínima igual que con Dockerfiles separados, sin duplicar 4 archivos casi
idénticos (Policy 008 — simplicidad).

La Lambda de transformación de cada división **reutiliza la misma imagen** que su Lambda de
ingesta (no requiere un build adicional): `transform/handler.py` no depende del formato de
origen, solo de la división vía variable de entorno `DIVISION`, exactamente como hoy la
Lambda de ingesta la resuelve por `ARG DIVISION`. La única diferencia entre ambas funciones
Lambda de una misma división es el comando de entrada (`image_config.command` en Terraform,
ver SPEC-004), que apunta a `lambda_ingestion.<division>.handler.handler` para ingesta o a
`lambda_ingestion.transform.handler.handler` para transformación.

---

# Uso de Docker y Amazon ECR

Adaptando el patrón de `ai/skills/aws/lambda_packaging.md` para soportar 4 divisiones (8
funciones Lambda: ingesta + transformación por división) con un único Dockerfile
parametrizado:

```dockerfile
FROM public.ecr.aws/lambda/python:3.12
ARG DIVISION
ENV DIVISION=${DIVISION}
COPY src/lambda_ingestion/requirements-lambda.txt .
RUN pip install -r requirements-lambda.txt --no-cache-dir
COPY src/lambda_ingestion/common/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/common/
COPY src/lambda_ingestion/transform/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/transform/
COPY src/lambda_ingestion/${DIVISION}/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/${DIVISION}/
CMD ["lambda_ingestion.__DIVISION__.handler.handler"]
```

`transform/` se copia en todo build junto con `common/`, ya que la Lambda de transformación
de esta división reutilizará esta misma imagen (ver "Organización del código"); el `CMD` por
defecto de la imagen sigue siendo el de la Lambda de ingesta, y Terraform lo sobreescribe con
`image_config.command` para la función de transformación (ver SPEC-004).

**Importante:** Lambda exige que `CMD` esté en forma exec (array JSON), y Docker **no**
sustituye variables de `ARG`/`ENV` dentro de la forma exec de `CMD` en tiempo de build
(solo lo hace para `ENV`, `LABEL`, `COPY`, etc.). Por eso `${DIVISION}` no puede usarse
dentro de `CMD` — se usa el placeholder literal `__DIVISION__`, que
`scripts/docker_push.sh` reemplaza con `sed` sobre una copia temporal del Dockerfile antes
de invocar `docker build`, una vez por división:

```bash
sed "s/__DIVISION__/electronica/g" docker/Dockerfile > /tmp/Dockerfile.electronica
docker build --platform linux/amd64 --provenance=false \
  --build-arg DIVISION=electronica \
  --file /tmp/Dockerfile.electronica \
  -t "$REPO_URL_ELECTRONICA:$IMAGE_TAG" .
```

`requirements-lambda.txt` (compartido, mínimo):

```
boto3
pyarrow
openpyxl        # parser Excel (supermercado)
pdfplumber       # parser PDF (marketplace)
```

Reglas (heredadas de `ai/skills/aws/lambda_packaging.md`):

- Build con `--platform linux/amd64 --provenance=false` obligatorio.
- `image_uri` en Terraform debe referenciar un tag específico (SHA), nunca `latest`.
- El build/push de las 4 imágenes (una por división; cada una sirve tanto a la función de ingesta como a la de transformación de esa división) es responsabilidad de un script externo a Terraform (ver SPEC-004, "Flujo de despliegue").

---

# Contrato de los parsers

Todo parser implementa la misma interfaz, definida en `common/parser_base.py`:

```python
from abc import ABC, abstractmethod
from typing import Iterator

class SalesParser(ABC):
    division: str  # ej. "electronica"

    @abstractmethod
    def parse(self, raw_bytes: bytes) -> Iterator[dict]:
        """Yields raw rows as dicts, sin normalizar, tal como vienen en el archivo de origen."""
```

- `parse()` **no** valida ni normaliza — solo extrae filas crudas del formato de origen (CSV/Excel/JSON/PDF) a `dict`.
- La normalización a Silver (`normalize_silver`) y la validación completa a Gold (`validate_and_normalize`) ocurren en `common/schema.py`, común a las 4 divisiones, para no duplicar reglas de negocio entre etapas (ver "Validaciones").
- Cada `handler.py` de división (Lambda de ingesta) es responsable de instanciar su parser concreto e invocar el flujo común: `parse → normalize_silver → write silver/quarantine` (`common/handler_base.py`).
- `transform/handler.py` (Lambda de transformación, sin parser propio) invoca el flujo común: `read Parquet silver → validate_and_normalize → write gold/quarantine` (`common/transform_handler_base.py`).

## Parser PDF (Marketplace)

- Usa **pdfplumber** para extraer texto y tablas del PDF generado por el script sintético de Marketplace.
- Asume que el PDF contiene una tabla de ventas extraíble vía `page.extract_table()`; si la extracción no produce filas, se trata como archivo ilegible (ver "Manejo de errores", nivel archivo).
- El formato "texto libre" de `date` declarado en SPEC-007 (`date_format="texto_libre"`) se
  fija de forma concreta y determinista como: **`"<día> de <mes en palabra, español> de <año>"`**,
  ej. `"1 de agosto de 2026"`. El parser resuelve el mes mediante un mapa fijo
  (`{"enero": 1, "febrero": 2, ..., "diciembre": 12}`) en `common/schema.py`, reutilizado
  por el paso de normalización de fecha (ver "Validaciones"). Una fecha que no siga este
  patrón (incluida la corrupción intencional "fecha mal formateada" de SPEC-007, ej.
  `"ayer"`) no matchea el mapa de meses y la fila se enruta a cuarentena por
  `RowValidationError`, comportamiento esperado.

---

# Estrategia para soportar múltiples formatos

- No hay detección de formato en tiempo de ejecución: cada Lambda ya sabe su formato porque está vinculada a un único parser (ver SPEC-003 y SPEC-004 — la regla de EventBridge filtra por división antes de invocar).
- Agregar una división nueva en el futuro implica: nuevo parser que implemente `SalesParser`, nuevo `Dockerfile.<division>`, nuevo módulo Terraform de función Lambda — sin tocar el código de las divisiones existentes.

---

# Validaciones

Implementadas en `common/schema.py`. Las reglas de campo son comunes a ambas etapas (factorizadas
en un helper interno `_normalize_core`, reutilizado por `normalize_silver` y `validate_and_normalize`
para no duplicar lógica); `sale_id` y `total` son responsabilidad exclusiva de la etapa Gold.

## Reglas de campo (Silver y Gold)

Aplicadas a cada fila cruda devuelta por el parser (etapa Silver) y reaplicadas de forma
idempotente sobre la fila Silver ya tipada (etapa Gold, `_normalize_core` acepta ambas formas):

| Campo | Regla |
|-------|-------|
| `date` | Debe ser parseable según el formato declarado por la división (ver SPEC-002); se normaliza a `YYYY-MM-DD`. |
| `store` | Se asigna de forma fija según la división del handler que invoca. |
| `category`, `product` | Deben ser strings no vacíos. |
| `quantity` | Entero, > 0. |
| `price` | Decimal, > 0. |
| `currency`, `status` | Se normalizan a mayúsculas; si el origen no los trae, se usa el valor por defecto (`DEFAULT_CURRENCY`/`DEFAULT_STATUS`). |

## Reglas exclusivas de Gold

Resueltas únicamente en `validate_and_normalize` (Lambda de transformación), nunca en la etapa Silver:

| Campo | Regla |
|-------|-------|
| `sale_id` | Debe ser un UUID v4 válido; si el origen (o la fila Silver) no lo trae, se genera en este paso. En Silver, un `sale_id` ausente o inválido queda como `null` (passthrough), sin generarse. |
| `total` | Siempre recalculado como `quantity * price`; cualquier valor de origen se descarta. No existe en el esquema Silver. |

Una fila que falle cualquiera de las reglas de campo se considera **inválida** y se enruta a cuarentena (no interrumpe el procesamiento del resto del archivo) — ver SPEC-003 "Flujo de errores".

## Esquemas Parquet explícitos

`common/schema.py` declara dos `pyarrow.schema()` explícitos con los tipos exigidos por
SPEC-002, para no depender de la inferencia de tipos de pyarrow a partir de `dict` de
Python (que no garantiza `date` como tipo `date32` ni `price`/`total` como `decimal`):

```python
import pyarrow as pa

# Division-specific fields (SPEC-002 "Campos específicos por división",
# SPEC-009 §2). Always nullable — one flat table for all 4 divisions.
EXTRA_FIELDS = [
    pa.field("serial_number", pa.string(), nullable=True),
    pa.field("warranty_months", pa.int32(), nullable=True),
    pa.field("manufacturer", pa.string(), nullable=True),
    pa.field("model", pa.string(), nullable=True),
    pa.field("cashier", pa.string(), nullable=True),
    pa.field("loyalty_points", pa.int32(), nullable=True),
    pa.field("promotion_applied", pa.bool_(), nullable=True),
    pa.field("register_number", pa.string(), nullable=True),
    pa.field("size", pa.string(), nullable=True),
    pa.field("color", pa.string(), nullable=True),
    pa.field("collection", pa.string(), nullable=True),
    pa.field("season", pa.string(), nullable=True),
    pa.field("return_reason", pa.string(), nullable=True),
    pa.field("seller_id", pa.string(), nullable=True),
    pa.field("marketplace_fee", pa.decimal128(10, 2), nullable=True),
    pa.field("commission_pct", pa.decimal128(5, 2), nullable=True),
    pa.field("shipping_provider", pa.string(), nullable=True),
]

SILVER_SCHEMA = pa.schema([
    pa.field("sale_id", pa.string(), nullable=True),
    pa.field("category", pa.string(), nullable=False),
    pa.field("product", pa.string(), nullable=False),
    pa.field("quantity", pa.int32(), nullable=False),
    pa.field("price", pa.decimal128(10, 2), nullable=False),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("status", pa.string(), nullable=False),
    *EXTRA_FIELDS,
])

GOLD_SCHEMA = pa.schema([
    pa.field("sale_id", pa.string(), nullable=False),
    pa.field("category", pa.string(), nullable=False),
    pa.field("product", pa.string(), nullable=False),
    pa.field("quantity", pa.int32(), nullable=False),
    pa.field("price", pa.decimal128(10, 2), nullable=False),
    pa.field("total", pa.decimal128(10, 2), nullable=False),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("status", pa.string(), nullable=False),
    *EXTRA_FIELDS,
])
```

Los campos de `EXTRA_FIELDS` no tienen regla de validación en `_normalize_core`
(SPEC-005 "Validaciones" solo cubre los campos base): un valor ausente o mal
formado se guarda como `null` en vez de enviar la fila a cuarentena — son
metadata opcional por división, no parte del contrato mínimo de una venta
(ver SPEC-002 "Campos específicos por división" para el detalle por campo).

`store` y `date` **no** forman parte de ninguno de los dos esquemas: son columnas de partición Hive
(codificadas en el path `silver/store=<division>/date=<fecha>/` o `gold/store=<division>/date=<fecha>/`,
ver SPEC-002/SPEC-003) y se excluyen de cada fila normalizada antes de construir la tabla pyarrow,
para evitar que el Glue Crawler registre columnas duplicadas (una como dato, otra como partición) al
catalogar la tabla (ver SPEC-006). La Lambda de transformación obtiene `date` a partir del propio
key S3 del objeto Silver leído (segmento `date=YYYY-MM-DD/`), no de una columna del Parquet.

---

# Manejo de errores

Jerarquía de excepciones tipadas en `common/errors.py`, siguiendo `ai/skills/python/error_handling_pipeline.md` (adaptado: sin Step Functions, ya que el pipeline no usa una state machine — la invocación llega vía EventBridge, no directamente desde S3):

```python
class PipelineError(Exception):
    def __init__(self, stage: str, cause: str, sale_id: str = "", correlation_id: str = ""):
        self.stage = stage
        self.cause = cause
        self.sale_id = sale_id
        self.correlation_id = correlation_id
        super().__init__(f"[{stage}] {cause}")

class RowValidationError(PipelineError):
    """Fila individual inválida — se enruta a cuarentena, no interrumpe el archivo."""

class FileParseError(PipelineError):
    """Archivo completo ilegible o corrupto — no genera salida en la capa siguiente."""
```

## Flujo de errores por nivel (alineado con SPEC-003)

| Nivel | Excepción | Acción del handler |
|-------|-----------|---------------------|
| Fila | `RowValidationError` (capturada internamente por `schema.py`, en `normalize_silver` o `validate_and_normalize`) | La fila se escribe en `quarantine/`; el procesamiento continúa con la siguiente fila. No se re-lanza al handler. |
| Archivo | `FileParseError` | Se lanza desde el parser de la Lambda de ingesta (ej. PDF sin tabla extraíble, CSV con encoding irreconocible). El handler la captura, registra `ERROR` en CloudWatch y termina la invocación sin escribir en Silver. No se reintenta desde el propio código — el reintento sigue la política por defecto del target de EventBridge (hasta 185 intentos durante 24 horas), no la de una invocación asíncrona directa desde S3. La Lambda de transformación no tiene parser propio (lee Parquet ya homogéneo), por lo que no está sujeta a este tipo de error. |
| Lambda | Excepción no controlada | Se registra en `ERROR` con el logger estructurado y se re-lanza (nunca catch-and-swallow), consistente con `ai/skills/python/logging_structured.md`. Aplica igual en ambas etapas. |

- **Nunca** se hace catch-and-swallow: toda excepción a nivel archivo o Lambda se registra y se re-lanza.
- Las filas inválidas son la única excepción a "siempre re-lanzar": se capturan, se enrutan a cuarentena, y el procesamiento continúa (comportamiento esperado, no un fallo).

---

# Conversión a Parquet

- `common/s3_writer.py` implementa `write_silver` y `write_gold`, con la misma forma: acumulan las filas válidas y normalizadas de la invocación (sin `store` ni `date`, ver "Esquemas Parquet explícitos") en un `pyarrow.Table` construido con `SILVER_SCHEMA` o `GOLD_SCHEMA` respectivamente, y lo escriben como un único archivo Parquet en `silver/store=<division>/date=<fecha>/part-<request_id>.parquet` o `gold/store=<division>/date=<fecha>/part-<request_id>.parquet`.
- **Antes de escribir**, ambas funciones listan y borran (`list_objects_v2` + `delete_objects`) los objetos existentes bajo su propia partición (delete-then-write). Esto implementa el comportamiento "último gana" declarado en SPEC-003 en ambas capas: como el nombre del archivo incluye `request_id` (distinto en cada invocación), sin este borrado los reprocesamientos se acumularían en vez de sobrescribirse. Silver sigue este mismo contrato (no el de cuarentena) porque es dato derivado sujeto a reprocesamiento, no un log de errores.
- Las filas inválidas se escriben como un archivo JSON (lista de objetos `{row, error}`) en `quarantine/store=<division>/date=<fecha>/errors-<request_id>.json`, tanto desde la Lambda de ingesta (fallas de campo detectadas en `normalize_silver`) como desde la de transformación (fallas detectadas en `validate_and_normalize`, en la práctica solo si se reprocesara un Parquet Silver alterado manualmente). La cuarentena **no** aplica delete-then-write: los archivos de error de distintas invocaciones se acumulan, preservando el historial de errores para inspección.
- Si el archivo de origen no produce ninguna fila válida, no se escribe archivo Parquet vacío en Silver ni en Gold (evita particiones vacías que confundan al Glue Crawler). El borrado de la partición existente sí ocurre en este caso (un reprocesamiento que ahora falla completamente no debe dejar datos obsoletos de una corrida anterior).

---

# Logging

Reutiliza el patrón documentado en `ai/skills/python/logging_structured.md` (JsonFormatter + `LoggerAdapter`), sin AWS Lambda Powertools ni dependencias adicionales de observabilidad.

- Campo `document_id` del patrón genérico se usa como `sale_id` (o `"file"` a nivel de archivo, antes de tener filas individuales).
- `correlation_id` = `context.aws_request_id`.
- `stage` toma valores: `"parse"`, `"silver_normalize"` (Lambda de ingesta), `"validate"` (Lambda de transformación), `"write_silver"`, `"write_gold"`, `"write_quarantine"`.
- `service` = nombre de la función Lambda (incluye división y etapa, ej. `retail-data-lake-dev-ingestion-electronica` o `retail-data-lake-dev-transform-electronica`).

```python
from lambda_ingestion.common.logging_config import get_logger
from lambda_ingestion.common.s3_event import extract_s3_location

def handler(event, context):
    log = get_logger(
        service=context.function_name,
        stage="parse",
        document_id="file",
        correlation_id=context.aws_request_id,
    )
    bucket, key = extract_s3_location(event)
    log.info("Processing started", extra={"bucket": bucket, "key": key})
```

Nivel `INFO` para inicio/fin de invocación y conteo de filas válidas/inválidas; `WARNING` por cada fila individual enrutada a cuarentena; `ERROR` únicamente para `FileParseError` y excepciones no controladas.

---

# Variables de entorno

| Variable | Descripción | Lambda |
|----------|-------------|--------|
| `DIVISION` | Nombre de la división (`electronica`, `supermercado`, `moda`, `marketplace`); usado para fijar `store` y las rutas de escritura. | Ambas |
| `DATA_BUCKET` | Bucket de datos (bronze/silver/gold/quarantine). | Ambas |
| `SILVER_PREFIX` | Prefijo base de la capa Silver (default `silver/`). | Ambas (ingesta escribe, transformación lee) |
| `GOLD_PREFIX` | Prefijo base de la capa Gold (default `gold/`). | Transformación |
| `QUARANTINE_PREFIX` | Prefijo base de la capa Quarantine (default `quarantine/`). | Ambas |
| `LOG_LEVEL` | Nivel de log (default `INFO`). | Ambas |

Todas se inyectan vía Terraform (`environment.variables` en `aws_lambda_function`, ver SPEC-004), nunca hardcodeadas (Policy 003 — Configuration Over Hardcoding).

---

# Fuera de alcance

- Reintentos manuales o backoff propio dentro del handler (se apoya en la política de reintento por defecto del target de EventBridge).
- Métricas custom (EMF) o tracing distribuido (X-Ray) — no se usa AWS Lambda Powertools en esta demo.
- Procesamiento por lotes de múltiples archivos en una sola invocación.
- Extracción de PDFs asistida por IA (mencionada como evolución futura en SPEC-001).
