# SPEC-005 - Implementación de la Lambda

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir la arquitectura interna de las funciones Lambda responsables del procesamiento de archivos, una por división (ver SPEC-004), incluyendo el contrato compartido de los parsers, validaciones, manejo de errores, logging y empaquetado Docker.

---

# Arquitectura interna

Cada Lambda es un despliegue independiente (imagen Docker propia en ECR, función propia, rol IAM propio — ver SPEC-004), pero las 5 comparten un **paquete de código común** para evitar duplicar validación, escritura en S3 y logging entre divisiones.

```
handler (division) → parser (division) → validate + normalize (común) → write gold/quarantine (común)
```

---

# Organización del código

```
src/
├── lambda_ingestion/
│   ├── common/
│   │   ├── __init__.py
│   │   ├── schema.py           # esquema Gold (SPEC-002) + validación de fila
│   │   ├── errors.py           # jerarquía de excepciones tipadas
│   │   ├── logging_config.py   # JsonFormatter + PipelineLogger (ver "Logging")
│   │   ├── s3_writer.py        # escritura Parquet a gold/, JSON a quarantine/
│   │   └── parser_base.py      # contrato abstracto de parser (ver "Contrato de los parsers")
│   ├── electronica/
│   │   ├── handler.py
│   │   └── parser.py           # CSV
│   ├── supermercado/
│   │   ├── handler.py
│   │   └── parser.py           # Excel (.xlsx)
│   ├── moda/
│   │   ├── handler.py
│   │   └── parser.py           # JSON
│   ├── hogar/
│   │   ├── handler.py
│   │   └── parser.py           # CSV
│   └── marketplace/
│       ├── handler.py
│       └── parser.py           # PDF
docker/
└── Dockerfile              # único, parametrizado con ARG DIVISION (ver "Uso de Docker y Amazon ECR")
```

Siguiendo `ai/skills/aws/lambda_packaging.md`, que exige un único `docker/Dockerfile` en
la raíz del proyecto (no un archivo por división): se usa **un solo Dockerfile** con
`ARG DIVISION`, invocado 5 veces con distinto `--build-arg DIVISION=<division>` por el
script de build (ver `scripts/docker_push.sh`, SPEC-004 "Flujo de despliegue"). Cada build
copia `common/` más la carpeta de la división indicada por el `ARG`, manteniendo la imagen
resultante mínima igual que con Dockerfiles separados, sin duplicar 5 archivos casi
idénticos (Policy 008 — simplicidad).

---

# Uso de Docker y Amazon ECR

Adaptando el patrón de `ai/skills/aws/lambda_packaging.md` para soportar 5 divisiones con
un único Dockerfile parametrizado:

```dockerfile
FROM public.ecr.aws/lambda/python:3.12
ARG DIVISION
ENV DIVISION=${DIVISION}
COPY src/lambda_ingestion/requirements-lambda.txt .
RUN pip install -r requirements-lambda.txt --no-cache-dir
COPY src/lambda_ingestion/common/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/common/
COPY src/lambda_ingestion/${DIVISION}/ ${LAMBDA_TASK_ROOT}/lambda_ingestion/${DIVISION}/
CMD ["lambda_ingestion.__DIVISION__.handler.handler"]
```

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
- El build/push de las 5 imágenes es responsabilidad de un script externo a Terraform (ver SPEC-004, "Flujo de despliegue").

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
- La validación y normalización al esquema Gold (SPEC-002) ocurre en `common/schema.py`, común a las 5 divisiones, para no duplicar reglas de negocio (recalculo de `total`, normalización de `date`, asignación de `store`).
- Cada `handler.py` de división es responsable de instanciar su parser concreto e invocar el flujo común: `parse → validate_and_normalize → write`.

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

- No hay detección de formato en tiempo de ejecución: cada Lambda ya sabe su formato porque está vinculada a un único parser (ver SPEC-003 y SPEC-004 — la S3 Event Notification filtra por división antes de invocar).
- Agregar una división nueva en el futuro implica: nuevo parser que implemente `SalesParser`, nuevo `Dockerfile.<division>`, nuevo módulo Terraform de función Lambda — sin tocar el código de las divisiones existentes.

---

# Validaciones

Implementadas en `common/schema.py`, aplicadas a cada fila cruda devuelta por el parser:

| Campo | Regla |
|-------|-------|
| `sale_id` | Debe ser un UUID v4 válido; si el origen no lo trae, se genera en este paso. |
| `date` | Debe ser parseable según el formato declarado por la división (ver SPEC-002); se normaliza a `YYYY-MM-DD`. |
| `store` | Se asigna de forma fija según la división del handler que invoca. |
| `category`, `product` | Deben ser strings no vacíos. |
| `quantity` | Entero, > 0. |
| `price` | Decimal, > 0. |
| `total` | Siempre recalculado como `quantity * price`; cualquier valor de origen se descarta. |

Una fila que falle cualquiera de estas reglas se considera **inválida** y se enruta a cuarentena (no interrumpe el procesamiento del resto del archivo).

## Esquema Parquet explícito

`common/schema.py` declara un `pyarrow.schema()` explícito con los tipos exigidos por
SPEC-002, para no depender de la inferencia de tipos de pyarrow a partir de `dict` de
Python (que no garantiza `date` como tipo `date32` ni `price`/`total` como `decimal`):

```python
import pyarrow as pa

GOLD_SCHEMA = pa.schema([
    pa.field("sale_id", pa.string(), nullable=False),
    pa.field("category", pa.string(), nullable=False),
    pa.field("product", pa.string(), nullable=False),
    pa.field("quantity", pa.int32(), nullable=False),
    pa.field("price", pa.decimal128(10, 2), nullable=False),
    pa.field("total", pa.decimal128(10, 2), nullable=False),
])
```

`store` y `date` **no** forman parte de `GOLD_SCHEMA`: son columnas de partición Hive
(codificadas en el path `gold/store=<division>/date=<fecha>/`, ver SPEC-002/SPEC-003) y
se excluyen de cada fila normalizada antes de construir la tabla pyarrow, para evitar que
el Glue Crawler registre columnas duplicadas (una como dato, otra como partición) al
catalogar la tabla (ver SPEC-006).

---

# Manejo de errores

Jerarquía de excepciones tipadas en `common/errors.py`, siguiendo `ai/skills/python/error_handling_pipeline.md` (adaptado: sin Step Functions, ya que el pipeline no usa una state machine — la invocación es directa desde S3):

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
    """Archivo completo ilegible o corrupto — no genera salida en Gold."""
```

## Flujo de errores por nivel (alineado con SPEC-003)

| Nivel | Excepción | Acción del handler |
|-------|-----------|---------------------|
| Fila | `RowValidationError` (capturada internamente por `schema.py`) | La fila se escribe en `quarantine/`; el procesamiento continúa con la siguiente fila. No se re-lanza al handler. |
| Archivo | `FileParseError` | Se lanza desde el parser (ej. PDF sin tabla extraíble, CSV con encoding irreconocible). El handler la captura, registra `ERROR` en CloudWatch y termina la invocación sin escribir en Gold. No se reintenta desde el propio código — el comportamiento de reintento de Lambda ante invocaciones S3 asíncronas es el que aplica por defecto. |
| Lambda | Excepción no controlada | Se registra en `ERROR` con el logger estructurado y se re-lanza (nunca catch-and-swallow), consistente con `ai/skills/python/logging_structured.md`. |

- **Nunca** se hace catch-and-swallow: toda excepción a nivel archivo o Lambda se registra y se re-lanza.
- Las filas inválidas son la única excepción a "siempre re-lanzar": se capturan, se enrutan a cuarentena, y el procesamiento continúa (comportamiento esperado, no un fallo).

---

# Conversión a Parquet

- `common/s3_writer.py` acumula las filas válidas y normalizadas de la invocación (sin `store` ni `date`, ver "Esquema Parquet explícito") en un `pyarrow.Table` construido con `GOLD_SCHEMA`, y lo escribe como un único archivo Parquet en `gold/store=<division>/date=<fecha>/part-<request_id>.parquet`.
- **Antes de escribir**, `s3_writer.py` lista y borra (`list_objects_v2` + `delete_objects`) los objetos existentes bajo `gold/store=<division>/date=<fecha>/` (delete-then-write). Esto implementa el comportamiento "último gana" declarado en SPEC-003: como el nombre del archivo incluye `request_id` (distinto en cada invocación), sin este borrado los reprocesamientos se acumularían en vez de sobrescribirse.
- Las filas inválidas se escriben como un archivo JSON (lista de objetos `{row, error}`) en `quarantine/store=<division>/date=<fecha>/errors-<request_id>.json`. La cuarentena **no** aplica delete-then-write: los archivos de error de distintas invocaciones se acumulan, preservando el historial de errores para inspección.
- Si el archivo de origen no produce ninguna fila válida, no se escribe archivo Parquet vacío en Gold (evita particiones vacías que confundan al Glue Crawler). El borrado de la partición existente sí ocurre en este caso (un reprocesamiento que ahora falla completamente no debe dejar datos obsoletos de una corrida anterior).

---

# Logging

Reutiliza el patrón documentado en `ai/skills/python/logging_structured.md` (JsonFormatter + `LoggerAdapter`), sin AWS Lambda Powertools ni dependencias adicionales de observabilidad.

- Campo `document_id` del patrón genérico se usa como `sale_id` (o `"file"` a nivel de archivo, antes de tener filas individuales).
- `correlation_id` = `context.aws_request_id`.
- `stage` toma valores: `"parse"`, `"validate"`, `"write_gold"`, `"write_quarantine"`.
- `service` = nombre de la función Lambda (incluye división, ej. `retail-data-lake-dev-ingestion-electronica`).

```python
from lambda_ingestion.common.logging_config import get_logger

def handler(event, context):
    log = get_logger(
        service=context.function_name,
        stage="parse",
        document_id="file",
        correlation_id=context.aws_request_id,
    )
    log.info("Processing started", extra={"bucket": ..., "key": ...})
```

Nivel `INFO` para inicio/fin de invocación y conteo de filas válidas/inválidas; `WARNING` por cada fila individual enrutada a cuarentena; `ERROR` únicamente para `FileParseError` y excepciones no controladas.

---

# Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `DIVISION` | Nombre de la división (`electronica`, `supermercado`, `moda`, `hogar`, `marketplace`); usado para fijar `store` y las rutas de escritura. |
| `DATA_BUCKET` | Bucket de datos (bronze/gold/quarantine). |
| `GOLD_PREFIX` | Prefijo base de la capa Gold (default `gold/`). |
| `QUARANTINE_PREFIX` | Prefijo base de la capa Quarantine (default `quarantine/`). |
| `LOG_LEVEL` | Nivel de log (default `INFO`). |

Todas se inyectan vía Terraform (`environment.variables` en `aws_lambda_function`, ver SPEC-004), nunca hardcodeadas (Policy 003 — Configuration Over Hardcoding).

---

# Fuera de alcance

- Reintentos manuales o backoff propio dentro del handler (se apoya en el comportamiento por defecto de Lambda ante invocaciones S3).
- Métricas custom (EMF) o tracing distribuido (X-Ray) — no se usa AWS Lambda Powertools en esta demo.
- Procesamiento por lotes de múltiples archivos en una sola invocación.
- Extracción de PDFs asistida por IA (mencionada como evolución futura en SPEC-001).
