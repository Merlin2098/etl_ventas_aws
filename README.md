# Data Lake Serverless para Retail en AWS

Laboratorio completo de un pipeline ETL **event-driven y 100% serverless** sobre
AWS: ingiere archivos de ventas en cuatro formatos distintos (CSV, Excel, JSON,
PDF), los normaliza a un esquema único en capas Bronze → Silver → Gold, y los
deja consultables con SQL en Amazon Athena.

Este repositorio es el material de un **webinar de ETL en AWS**. Está pensado
para leerse en orden: primero el problema de negocio, después la arquitectura
que lo resuelve, y al final cómo desplegarlo y operarlo paso a paso.

---

## 1. El caso de negocio

**RetailCorp** es una empresa de retail con cuatro divisiones que operan de
forma independiente. Cada una genera diariamente un archivo con las ventas del
día — y cada una lo exporta desde un sistema distinto, en un formato distinto:

| División | Sistema de origen simulado | Formato | Formato de fecha |
|----------|---------------------------|---------|------------------|
| Electrónica | ERP propio | CSV | `DD/MM/YYYY` |
| Supermercado | Sistema POS | Excel (`.xlsx`) | `MM-DD-YYYY` |
| Moda | Plataforma E-commerce | JSON | ISO 8601 |
| Marketplace | API de terceros | PDF | `"4 de agosto de 2026"` |

El equipo de Data Engineering recibe estos cuatro archivos cada día y necesita
responder preguntas de negocio que cruzan todas las divisiones:

- ¿Qué categoría vende más?
- ¿Cuáles son los 10 productos con mayores ingresos?
- ¿Qué división genera más facturación? ¿Cuál es su ticket promedio?
- ¿Cómo se distribuyen las ventas en el tiempo?

**El problema:** no se puede responder ninguna de esas preguntas mientras los
datos vivan en cuatro formatos incompatibles. Y hay un problema adicional, más
realista todavía: **los datos vienen sucios**. Fechas mal formateadas, cantidades
como `"N/A"`, precios negativos, campos faltantes, y hasta bytes con encoding
corrupto en el CSV. Un pipeline que se caiga con la primera fila mala no sirve.

**Lo que hay que construir:** una plataforma que reciba los archivos tal como
llegan, los unifique en un esquema común, **aísle las filas defectuosas sin
perder el resto del archivo**, y publique el resultado para consulta SQL — todo
sin administrar un solo servidor.

### El esquema unificado (Gold)

Los cuatro formatos convergen aquí. Este es el contrato que consume Athena:

| Campo | Tipo | Dónde vive | Descripción |
|-------|------|------------|-------------|
| `sale_id` | string (UUID v4) | Columna Parquet | Identificador único de la venta |
| `date` | date (`YYYY-MM-DD`) | Partición Hive | Fecha de la venta, normalizada |
| `store` | string | Partición Hive | División de origen |
| `category` | string | Columna Parquet | Categoría del producto |
| `product` | string | Columna Parquet | Nombre del producto |
| `quantity` | integer > 0 | Columna Parquet | Cantidad vendida |
| `price` | decimal(10,2) > 0 | Columna Parquet | Precio unitario |
| `total` | decimal(10,2) | Columna Parquet | `quantity * price`, **siempre recalculado** |

> **Detalle didáctico importante:** `store` y `date` **no** se escriben dentro
> del archivo Parquet. Van codificadas en la ruta S3 como particiones Hive
> (`gold/store=electronica/date=2026-08-04/`). Athena las expone igual en el
> `SELECT` porque el Glue Crawler las registra como columnas de partición.
> Escribirlas también dentro del Parquet produciría **columnas duplicadas** al
> catalogar — un error clásico al construir un data lake por primera vez.

---

## 2. La arquitectura

### Flujo de datos end-to-end

```
Generadores Python (ejecución manual)
        │  PutObject
        ▼
┌─────────────────────────────────────────────┐
│ S3  bronze/<division>/date=<fecha>/          │  ← archivo tal cual llegó
└─────────────────────────────────────────────┘
        │  Object Created → EventBridge (bus por defecto)
        ▼
   EventBridge rule "ingestion-<division>"   (filtra prefix bronze/<division>/)
        │  invoke
        ▼
   Lambda ingestion-<division>   (Docker sobre ECR)
        │  parse (parser propio del formato) → normalize_silver
        ├──► S3 silver/store=<division>/date=<fecha>/   (Parquet)
        └──► S3 quarantine/store=<division>/date=<fecha>/  (filas inválidas, JSON)
        │
        │  Object Created → EventBridge
        ▼
   EventBridge rule "transform-<division>"   (filtra prefix silver/store=<division>/)
        │  invoke
        ▼
   Lambda transform-<division>   (misma imagen Docker, distinto CMD)
        │  validate_and_normalize (genera sale_id, recalcula total)
        ├──► S3 gold/store=<division>/date=<fecha>/   (Parquet)
        └──► S3 quarantine/store=<division>/date=<fecha>/
        │
        ▼
   Glue Crawler → Glue Data Catalog → Amazon Athena (SQL)
```

**4 divisiones × 2 etapas = 8 funciones Lambda, 8 reglas de EventBridge, 4
repositorios ECR** (cada imagen se comparte entre la ingesta y la transformación
de su división).

El diagrama fuente en Graphviz está en
[docs/arquitectura/architecture.dot](docs/arquitectura/architecture.dot). Para
renderizarlo:

```bash
dot -Tsvg docs/arquitectura/architecture.dot -o docs/arquitectura/architecture.svg
```

### Por qué tres capas y no una

Esta es la decisión de diseño más importante del laboratorio, y la que más se
transfiere a proyectos reales:

| Capa | Qué contiene | Quién la escribe | Por qué existe |
|------|--------------|------------------|----------------|
| **Bronze** | El archivo original, sin tocar (CSV/XLSX/JSON/PDF) | El generador (`PutObject`) | Trazabilidad. Si el parser tiene un bug, se reprocesa desde el dato crudo — nunca se pierde el original. |
| **Silver** | Parquet homogéneo, tipos ya normalizados. Sin `sale_id` generado ni `total`. | Lambda de ingesta | Separa **"entender el formato"** de **"aplicar reglas de negocio"**. A partir de aquí ningún componente sabe si el dato vino de un PDF o de un Excel. |
| **Gold** | Parquet listo para consulta, contrato completo | Lambda de transformación | Es lo único que ve el analista. Esquema estable, tipado, particionado. |
| **Quarantine** | Filas inválidas + metadata del error (JSON) | Ambas Lambdas | Las filas malas **no se descartan en silencio**: quedan auditables, con la regla que incumplieron. |

Un pipeline de una sola etapa mezclaría el parseo de PDF con la regla de negocio
"`total = quantity * price`". Al separarlas, el parser de PDF sólo tiene que
saber leer un PDF — y las reglas de negocio se escriben una sola vez, en un
módulo común compartido por las cuatro divisiones.

### Decisiones de diseño vigentes

- **Trigger vía EventBridge, no notificación S3 directa.** Cada regla tiene su
  propio `aws_lambda_permission` scopeado al ARN de la regla. Esta no fue la
  primera opción — se migró después de un incidente real. Ver
  [§7 Aprendizajes del terreno](#7-aprendizajes-del-terreno-lo-que-salió-mal).
- **Un solo bucket con prefijos** (`bronze/`, `silver/`, `gold/`, `quarantine/`,
  `athena-results/`), no un bucket por capa. Un recurso menos que administrar y
  que destruir, sin diferencia funcional para esta demo.
- **Una imagen Docker por división, compartida entre ambas etapas.** La Lambda
  de transformación no tiene parser propio; sólo cambia el `CMD` vía
  `image_config.command` en Terraform. Cuatro builds, ocho funciones.
- **Sin detección de formato en runtime.** Cada Lambda ya sabe qué formato lee,
  porque la regla de EventBridge la seleccionó por prefijo. No hay `if
  archivo.endswith(".csv")` en ninguna parte — el enrutamiento vive en la
  infraestructura.
- **IAM least-privilege por función**, declarado en el módulo Terraform que
  posee el recurso protegido.
- **`force_destroy` / `force_delete` en todo recurso con estado.** Es un entorno
  de demo efímero: `terraform destroy` debe funcionar sin pasos manuales.
- **"Último gana" (delete-then-write).** Reprocesar un archivo Bronze borra la
  partición Silver/Gold correspondiente antes de escribir. Como el nombre del
  Parquet incluye el `request_id` de la invocación, sin ese borrado los
  reprocesamientos se acumularían y **duplicarían filas en Athena**.

### Componentes AWS

| Servicio | Rol en el pipeline |
|----------|--------------------|
| **Amazon S3** | Almacenamiento del Data Lake (4 capas por prefijo) + resultados de Athena |
| **Amazon EventBridge** | Enruta cada evento `Object Created` a la Lambda correcta según el prefijo de la key |
| **AWS Lambda** | Procesamiento: 4 funciones de ingesta (una por formato) + 4 de transformación |
| **Amazon ECR** | Aloja las 4 imágenes Docker (permite dependencias pesadas como `pdfplumber`/`pyarrow`, imposibles en un ZIP) |
| **AWS Glue** | Data Catalog + Crawler que descubre tabla y particiones sobre `gold/` |
| **Amazon Athena** | Consulta SQL sobre S3, sin base de datos que administrar |
| **CloudWatch Logs** | Un log group explícito por función, con logging estructurado en JSON |
| **Terraform** | Toda la infraestructura como código, en módulos por servicio |

> **¿Por qué Lambda con Docker y no un ZIP?** Los parsers necesitan `pyarrow`,
> `openpyxl` y `pdfplumber`. Con paquetes ZIP habría que pelear contra el límite
> de 250 MB descomprimidos y armar layers a mano. Con imágenes de contenedor el
> límite sube a 10 GB y el build es un `Dockerfile` normal.

---

## 3. Estructura del repositorio

```
.
├── specs/                    # Spec Driven Development — el diseño, antes del código
│   ├── SPEC-001_Vision_General.md
│   ├── pipeline/             # SPEC-002..006: datos, pipeline, infra, Lambda, analítica
│   └── generadores/          # SPEC-007..008: generadores de datos sintéticos
├── docs/
│   ├── arquitectura/         # architecture.md (bitácora viva) + architecture.dot
│   ├── consideraciones/      # glue_crawler.md, athena_queries.md — guías operativas
│   └── indicentes/           # INCIDENTE-001 — postmortem completo
├── infra/                    # Terraform
│   ├── main.tf, variables.tf, outputs.tf, providers.tf
│   └── modules/
│       ├── s3_data_lake/     # bucket + notificaciones a EventBridge
│       ├── ecr/              # 4 repositorios
│       ├── lambda_ingestion/ # 8 funciones + IAM + log groups
│       ├── eventbridge/      # 8 reglas + 8 targets + 8 permisos
│       ├── glue_catalog/     # database + crawler
│       └── athena/           # workgroup
├── src/
│   ├── lambda_ingestion/
│   │   ├── common/           # schema, errores, logging, escritura S3, handlers base
│   │   ├── electronica/      # parser CSV     + handler
│   │   ├── supermercado/     # parser Excel   + handler
│   │   ├── moda/             # parser JSON    + handler
│   │   ├── marketplace/      # parser PDF     + handler
│   │   └── transform/        # handler genérico Silver → Gold
│   └── generators/
│       ├── detalle-data.yaml # ← catálogo de divisiones/categorías/productos (data-driven)
│       └── engine/           # motor de generación + writers por formato
├── scripts/
│   ├── data_generator/generate_sales.py
│   ├── testing/              # run_local_ingestion, run_pytest, run_cloud_tests, ruff
│   ├── docker_build.sh / docker_push.sh
│   └── python/setup_env.sh
├── docker/Dockerfile         # único, parametrizado con ARG DIVISION
└── tests/
    ├── unit/                 # parsers, schema, generadores, eventos S3
    ├── e2e/                  # test_pipeline_local.py (sin AWS) + test_pipeline_aws.py
    └── aws/                  # smoke tests contra infra desplegada
```

**Nota sobre `specs/`:** este proyecto se construyó con *Spec Driven
Development*. Cada decisión de diseño está especificada antes de implementarse.
Si querés entender **por qué** algo está hecho así, la respuesta está en la SPEC
correspondiente, no en el código.

| SPEC | Tema |
|------|------|
| [SPEC-001](specs/SPEC-001_Vision_General.md) | Visión general, contexto de negocio, alcance |
| [SPEC-002](specs/pipeline/SPEC-002_Modelo_Datos_Datasets.md) | Modelo de datos, esquemas Silver/Gold |
| [SPEC-003](specs/pipeline/SPEC-003_Pipeline_Procesamiento.md) | Pipeline, capas del lake, flujo de errores |
| [SPEC-004](specs/pipeline/SPEC-004_Infraestructura_Terraform.md) | Infraestructura, módulos, despliegue |
| [SPEC-005](specs/pipeline/SPEC-005_Implementacion_Lambda.md) | Código de las Lambdas, parsers, Docker |
| [SPEC-006](specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md) | Glue, Athena y validación E2E |
| [SPEC-007](specs/generadores/SPEC-007_Generadores_Datos_Sinteticos.md) | Generadores de datos sintéticos |
| [SPEC-008](specs/generadores/SPEC-008_Consideraciones.md) | Complejización realista de los datasets |

---

## 4. Empezar sin AWS (recomendado para seguir el webinar)

**El pipeline completo corre en tu máquina, sin credenciales ni recursos en la
nube.** Esta es la mejor forma de entender la lógica antes de pelear con IAM.

### Requisitos

- Python 3.12+
- Docker (sólo si vas a desplegar en AWS)
- Terraform 1.x + AWS CLI (sólo para el despliegue)

### Instalación

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
```

O con el script del proyecto (Git Bash):

```bash
./scripts/python/setup_env.sh --include-dev
```

### Paso 1 — Generar los datos sintéticos

```bash
# Las 4 divisiones, fecha de hoy, sólo local (no sube a S3)
python scripts/data_generator/generate_sales.py

# Una división concreta, fecha específica, reproducible
python scripts/data_generator/generate_sales.py --division electronica --date 2026-08-04 --seed 42
```

| Argumento | Descripción | Default |
|-----------|-------------|---------|
| `--division` | `electronica`, `supermercado`, `moda`, `marketplace` o `all` | `all` |
| `--date` | Fecha de negocio a generar (`YYYY-MM-DD`) | Hoy |
| `--rows` | Cantidad de filas | 200-500 |
| `--error-rate` | Proporción de filas con errores intencionales | `0.05` (5%) |
| `--seed` | Semilla para reproducir el dataset exacto | aleatorio |
| `--upload` / `--no-upload` | Subir a S3 Bronze (requiere `DATA_BUCKET`) | `--no-upload` |
| `--output-dir` | Carpeta de salida local | `data/` |

Los archivos aparecen en `data/` con el nombre
`<division>_<fecha>.<ext>`. **Ábrilos**: son la materia prima del laboratorio, y
verlos lado a lado (un CSV, un Excel, un JSON y un PDF con la misma información
estructurada de forma distinta) es la mejor introducción al problema.

> **Los errores están sembrados a propósito.** Un 5% de las filas trae campos
> faltantes, `quantity = "N/A"`, precios negativos, fechas como `"ayer"`, o un
> byte fuera de UTF-8 en el CSV. Es lo que hace que la cuarentena tenga algo que
> mostrar.

### Paso 2 — Correr el pipeline completo, localmente

`run_local_ingestion.py` ejecuta **exactamente las mismas funciones** que las
Lambdas (`process_event` y `process_transform_event`), pero leyendo y escribiendo
en disco en vez de S3:

```bash
# Las 4 divisiones, ambas etapas
python scripts/testing/run_local_ingestion.py

# Una división, un archivo concreto
python scripts/testing/run_local_ingestion.py \
  --division electronica --file data/electronica_2026-08-04.csv --stage both
```

| Argumento | Descripción | Default |
|-----------|-------------|---------|
| `--division` | División específica o `all` | `all` |
| `--file` | Ruta a un archivo Bronze (sólo con una división específica) | resuelto desde `--date` |
| `--date` | Fecha para resolver `--file` | Hoy |
| `--stage` | `silver`, `gold` o `both` | `both` |
| `--out-dir` | Carpeta de salida | `data/local_run/` |

El resultado en `data/local_run/` tiene el **mismo formato** que la Lambda
escribiría en S3: Parquet en `silver/` y `gold/`, JSON en `quarantine/`.

**Qué mirar:** abrí `data/local_run/quarantine/` y leé un archivo de error. Cada
entrada tiene la fila original más la regla que incumplió. Después contá las
filas: `silver + quarantine == filas del archivo original`. Ninguna fila se
pierde en silencio — ese es el invariante del pipeline.

### Paso 3 — Los tests

```bash
python scripts/testing/run_pytest.py       # unit + e2e local, sin AWS
python scripts/testing/run_ruff_check.py   # lint
python scripts/testing/run_cloud_tests.py  # sólo tests marcados `cloud` (requieren credenciales)
```

`tests/e2e/test_pipeline_local.py` genera datos con semilla fija, corre las dos
etapas y verifica el contrato completo: los esquemas Parquet coinciden con
`SILVER_SCHEMA`/`GOLD_SCHEMA`, los conteos de filas son consistentes,
`total == price * quantity` en cada fila Gold, y no aparecen caracteres de
reemplazo (`�`) en los campos de texto.

---

## 5. Desplegar en AWS

El despliegue es en **dos fases**, y el orden importa: `aws_lambda_function` con
`package_type = "Image"` exige que la imagen ya exista en ECR al crear el
recurso. No se puede crear todo de una.

```bash
cd infra
cp terraform.tfvars.example terraform.tfvars   # ajustar project_name, region, owner
terraform init
```

**Fase 1 — crear los repositorios ECR:**

```bash
terraform apply -target=module.ecr
```

**Fase 2 — construir y publicar las imágenes:**

```bash
cd ..
./scripts/docker_build.sh    # build local de las 4 imágenes (sin credenciales AWS)
./scripts/docker_push.sh     # login a ECR + push; imprime el tag a usar
```

Ambos scripts etiquetan con el SHA corto del commit (`git rev-parse --short
HEAD`). `docker_push.sh` termina imprimiendo la línea exacta para pegar en
`terraform.tfvars`:

```hcl
lambda_image_tag = {
  electronica = "a241be4", supermercado = "a241be4",
  moda = "a241be4", marketplace = "a241be4"
}
```

> **Nunca usar el tag `latest`.** Terraform no detectaría el cambio de imagen y
> las Lambdas se quedarían con código viejo sin ninguna señal de error.

**Fase 3 — desplegar el resto:**

```bash
cd infra
terraform apply    # Lambdas, S3, EventBridge, Glue, Athena
```

**Iteraciones posteriores de código:** repetir build → push → actualizar
`lambda_image_tag` → `terraform apply`.

**Destruir todo:**

```bash
terraform destroy
```

Funciona sin pasos manuales: los buckets tienen `force_destroy = true` y los
repositorios ECR `force_delete = true`.

### Variables principales

| Variable | Descripción |
|----------|-------------|
| `divisions` | Lista de divisiones; genera todos los recursos repetidos vía `for_each` |
| `lambda_image_tag` | Map división → tag de imagen ECR |
| `lambda_memory_size` / `lambda_timeout` | Recursos de cada función |
| `glue_crawler_schedule` | Cron del Crawler; vacío = ejecución manual |
| `data_bucket_force_destroy` | Permite destruir buckets con objetos dentro |

---

## 6. Ejecutar la demo en vivo

Una vez desplegado, el ciclo completo del webinar:

### 1. Generar y subir archivos

```bash
export DATA_BUCKET=$(terraform -chdir=infra output -raw data_bucket_name)
python scripts/data_generator/generate_sales.py --date 2026-08-04 --upload
```

A partir de acá **el pipeline corre solo**: EventBridge dispara las 4 Lambdas de
ingesta, que escriben a Silver, lo que dispara las 4 de transformación, que
escriben a Gold. Sin intervención manual.

### 2. Ver el pipeline reaccionando

```bash
# Objetos que van apareciendo por capa
aws s3 ls s3://$DATA_BUCKET/silver/ --recursive
aws s3 ls s3://$DATA_BUCKET/gold/   --recursive
aws s3 ls s3://$DATA_BUCKET/quarantine/ --recursive

# Logs estructurados de una Lambda
aws logs tail /aws/lambda/data-platform-dev-ingestion-electronica --follow
```

Los logs son JSON con `stage`, `correlation_id` (el `aws_request_id`) y conteos
de filas válidas/inválidas — buen momento para mostrar por qué el logging
estructurado importa cuando hay 8 funciones corriendo en paralelo.

### 3. Correr el Glue Crawler ⚠️ paso manual

```bash
aws glue start-crawler --name data-platform-dev-gold-crawler

# Esperar a que vuelva a READY
aws glue get-crawler --name data-platform-dev-gold-crawler --query 'Crawler.State' --output text
```

> **El punto más fácil de confundir en una demo en vivo.** Que el dato esté en
> `gold/` **no** significa que Athena lo vea. El descubrimiento de particiones
> es manual en este proyecto. Consultar sin haber corrido el Crawler devuelve
> resultados vacíos o desactualizados — **no un error**, lo que hace parecer que
> el pipeline falló cuando en realidad el dato ya está en S3.
>
> Anunciá el paso explícitamente: *"ahora le decimos a Glue que vaya a mirar qué
> hay nuevo"*. Detalle completo en
> [docs/consideraciones/glue_crawler.md](docs/consideraciones/glue_crawler.md).

### 4. Consultar en Athena

La tabla se llama **`gold`** — el Crawler deriva el nombre del último segmento
del path S3, y no hay `table_prefix` configurado.

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

-- Ventas por división y ticket promedio
SELECT store, SUM(total) AS total_sales, AVG(total) AS avg_ticket, COUNT(*) AS num_sales
FROM gold
GROUP BY store
ORDER BY total_sales DESC;

-- Top 3 productos dentro de cada división (window function)
SELECT store, product, revenue, rnk
FROM (
  SELECT store, product, SUM(total) AS revenue,
         RANK() OVER (PARTITION BY store ORDER BY SUM(total) DESC) AS rnk
  FROM gold
  GROUP BY store, product
)
WHERE rnk <= 3
ORDER BY store, rnk;
```

> **Trampa a mostrar en vivo:** la partición `date` se cataloga como `varchar`,
> no como tipo `date` — es el comportamiento por defecto de Glue al inferir
> particiones Hive desde el path. Por eso:
>
> ```sql
> WHERE date = '2026-08-04'         -- ✅ correcto
> WHERE date = DATE '2026-08-04'    -- ❌ TYPE_MISMATCH: Cannot apply operator: varchar = date
> ```

Más queries verificadas contra el despliegue real — self-joins entre fechas,
window functions y `CREATE TABLE AS SELECT` — en
[docs/consideraciones/athena_queries.md](docs/consideraciones/athena_queries.md).

### 5. Validar que todo funcionó

Los criterios de aceptación completos están en
[SPEC-006](specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md). Los tres que
más valen la pena mostrar:

- **Conteo consistente entre etapas:** `filas_silver + filas_quarantine ==
  filas_del_archivo_origen`, y `filas_gold == filas_silver`. Cualquier
  discrepancia significa filas perdidas en silencio — un defecto, nunca un
  resultado aceptable.
- **La cuarentena tiene lo que debe tener:** las filas ahí deben corresponder a
  los errores que el generador sembró a propósito, con el mismo tipo de error.
- **Sin mojibake:** ningún `category` o `product` en Gold contiene caracteres de
  reemplazo (`�`). Ver el aprendizaje sobre encoding más abajo.

```bash
python scripts/testing/run_cloud_tests.py    # smoke tests + E2E contra AWS real
```

---

## 7. Aprendizajes del terreno (lo que salió mal)

Esta sección es material de webinar en sí misma. Todos estos son bugs reales
encontrados durante la construcción, con su postmortem documentado.

### El trigger que no disparaba — INCIDENTE-001

**Síntoma:** el pipeline llegaba hasta Silver y se detenía. Los objetos Parquet
se escribían correctamente en `silver/store=<division>/`, pero la Lambda de
transformación **nunca se invocaba**. Ningún error, ninguna métrica, ningún log
— simplemente no pasaba nada.

Lo desconcertante: el trigger equivalente `bronze/<division>/` →
`ingestion-<division>` funcionaba perfectamente, con configuración
estructuralmente idéntica. Se verificó vía API que las 8 reglas de notificación
existían, que los resource policies estaban bien, que no había drift contra el
state de Terraform. Invocar la Lambda a mano funcionaba. Se recreó la
configuración de notificaciones desde cero. Nada.

**La hipótesis tentadora y equivocada:** que el carácter `=` en el prefijo
`silver/store=` rompía las notificaciones de S3. Encajaba con la evidencia — era
la única diferencia estructural visible entre el prefijo que andaba y el que no
— y casi termina en un caso de soporte con AWS.

**La causa raíz real:** un `depends_on` mal cableado en Terraform, con dos
errores independientes en tres líneas:

```hcl
# infra/main.tf — versión con el bug
lambda_permission_dependency = merge(
  module.lambda_ingestion.function_names,
  module.lambda_ingestion.transform_function_names,
)
```

1. El `depends_on` apuntaba a **nombres de función**, no a los recursos
   `aws_lambda_permission`. Un `depends_on` sobre un valor que no referencia el
   recurso de permisos **no crea ninguna arista en el grafo de dependencias**.
2. El `merge()` de dos mapas con las mismas claves de división colapsaba **8
   entradas en 4**: las de transform pisaban a las de ingesta.

S3 valida los permisos **en el momento** de la llamada a
`PutBucketNotificationConfiguration`. Los permisos de ingesta se crearon antes
por orden fortuito del grafo; los de transform no tenían esa garantía. La
configuración *se escribía* correctamente — por eso aparecía bien en la API —
pero la suscripción de entrega nunca quedaba activa del lado de S3.

**La solución:** migrar a EventBridge. Y esto no es un rodeo al bug, lo corrige
de raíz para esta *clase* de problema: `source_arn =
aws_cloudwatch_event_rule...arn` es una **referencia real de Terraform**, así que
**es** la arista de dependencia que faltaba. Además, regla y permiso viven en el
mismo módulo, así que ese ordenamiento no puede volver a romperse en silencio
entre módulos.

**La lección de ingeniería:** cuando la evidencia apunta a "bug de la
plataforma", casi siempre es tuyo. Y `depends_on` sobre un valor calculado no es
una dependencia — es un comentario. Postmortem completo en
[docs/indicentes/INCIDENTE-001](docs/indicentes/INCIDENTE-001_Trigger_S3_Silver_Transform_No_Dispara.md).

### Una fila corrupta que arruinaba las otras 349

`CsvSalesParser.parse()` decodificaba el archivo completo con un único
`raw_bytes.decode("utf-8")`, con fallback a `latin-1` si fallaba. El generador
siembra un byte no-UTF-8 en `product` en **una sola fila** por archivo — y esa
única fila hacía fallar el decode de **todo el archivo**, degradando a `latin-1`
y convirtiendo tildes y ñ perfectamente válidas en mojibake en las 349 filas
restantes.

**Corrección:** decodificar línea por línea, con el mismo fallback aplicado *por
fila*. La corrupción queda aislada a la fila que la contiene (que sigue cayendo
a cuarentena, como corresponde) sin contaminar el resto. Cubierto ahora por dos
tests de regresión en `tests/e2e/`.

### El 100% de las filas en cuarentena

`transform_handler_base.py` no inyectaba la fecha de la partición Hive antes de
validar. Como `SILVER_SCHEMA` **no incluye** la columna `date` (vive en el path,
no en el Parquet), `parse_date(None)` devolvía `None` para toda fila — y las 341
filas iban a cuarentena con `cause=invalid_date`. La Lambda de transformación
tiene que sacar `date` del propio key S3 del objeto que está leyendo.

### Un permiso IAM que no se deduce

El rol del Glue Crawler necesita `glue:BatchGetPartition` explícitamente, además
de `glue:GetPartitions`, `glue:BatchCreatePartition` y `glue:BatchUpdatePartition`.
El Crawler la invoca para reconciliar particiones ya catalogadas contra las
nuevas — y **no queda cubierta implícitamente** por las otras acciones de
partición. Sin ella, `start-crawler` termina en `FAILED` con
`AccessDeniedException` y ninguna tabla queda disponible en Athena.

### El workgroup que rechaza `external_location`

`enforce_workgroup_configuration = true` fuerza toda ejecución a la ubicación de
resultados centralizada — incluido `CREATE TABLE AS SELECT`. Un CTAS con su
propia cláusula `external_location` falla con `InvalidRequestException`. Hay que
omitirla y dejar que Athena coloque la tabla bajo `athena-results/tables/`.

---

## 8. Objetivos de aprendizaje

Al terminar, deberías poder:

- Diseñar un Data Lake por capas (Bronze/Silver/Gold) y justificar por qué son tres.
- Construir un pipeline **event-driven** con S3 + EventBridge + Lambda, entendiendo
  por qué el enrutamiento vive en la infraestructura y no en el código.
- Empaquetar Lambdas con Docker sobre ECR y manejar el ciclo build → push → apply.
- Escribir Parquet particionado con esquema explícito, y evitar la trampa de las
  columnas de partición duplicadas.
- Diseñar un flujo de cuarentena que **nunca pierde una fila en silencio**.
- Administrar todo con Terraform en módulos, con IAM least-privilege.
- Catalogar con Glue y consultar con Athena, incluyendo window functions y CTAS.
- Validar un pipeline de datos end-to-end con criterios objetivos.

---

## 9. Alcance y evoluciones futuras

**Deliberadamente fuera de alcance** (para mantener el laboratorio enseñable):
streaming, Apache Spark, Glue Jobs, Kinesis, orquestación compleja, CI/CD,
múltiples entornos.

**Evoluciones naturales** para versiones posteriores:

- EventBridge **Scheduler** para disparar la generación periódica de archivos
  (distinto del enrutamiento de eventos `Object Created` que ya usa el pipeline —
  son dos capacidades distintas del mismo servicio).
- Step Functions para orquestación explícita.
- Glue Jobs con Spark para volúmenes que Lambda no aguante.
- Lake Formation para gobierno de acceso a nivel de columna.
- Iceberg Tables para time travel y evolución de esquema.
- QuickSight para visualización.
- Extracción de PDFs asistida por IA (Textract/Bedrock) en lugar de `pdfplumber`.

---

## Referencias rápidas

| Necesito... | Ir a |
|-------------|------|
| Entender el contexto y el alcance | [SPEC-001](specs/SPEC-001_Vision_General.md) |
| El esquema de datos exacto | [SPEC-002](specs/pipeline/SPEC-002_Modelo_Datos_Datasets.md) |
| Cómo fluyen los datos y los errores | [SPEC-003](specs/pipeline/SPEC-003_Pipeline_Procesamiento.md) |
| Qué recursos crea Terraform | [SPEC-004](specs/pipeline/SPEC-004_Infraestructura_Terraform.md) |
| Cómo está escrito el código de la Lambda | [SPEC-005](specs/pipeline/SPEC-005_Implementacion_Lambda.md) |
| Queries y criterios de validación | [SPEC-006](specs/pipeline/SPEC-006_Analitica_Validacion_E2E.md) |
| Correr el Crawler | [docs/consideraciones/glue_crawler.md](docs/consideraciones/glue_crawler.md) |
| Queries listas para pegar | [docs/consideraciones/athena_queries.md](docs/consideraciones/athena_queries.md) |
| El diagrama y su bitácora de cambios | [docs/arquitectura/architecture.md](docs/arquitectura/architecture.md) |
| El postmortem del trigger roto | [INCIDENTE-001](docs/indicentes/INCIDENTE-001_Trigger_S3_Silver_Transform_No_Dispara.md) |
| Las reglas de trabajo del repo | [AGENTS.md](AGENTS.md) |
