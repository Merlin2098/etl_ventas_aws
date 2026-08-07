# SPEC-001 - Visión General del Proyecto

## Webinar: Data Lake Serverless para Retail con AWS

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Construir de principio a fin una plataforma de datos moderna utilizando servicios serverless de AWS para procesar información diaria proveniente de distintas áreas de una empresa de retail.

Durante el webinar se mostrará cómo automatizar la ingesta, transformación y consulta de datos utilizando Infraestructura como Código (Terraform), funciones Lambda empaquetadas en Docker y consultas analíticas con Athena.

---

# Contexto del negocio

RetailCorp es una empresa de retail con múltiples divisiones de negocio.

Cada división opera de forma independiente y genera diariamente un archivo con las ventas del día.

El problema es que cada área utiliza una tecnología distinta para exportar su información.

Como consecuencia, el equipo de Data Engineering recibe múltiples formatos que deben ser unificados para generar indicadores de negocio.

---

# Formatos recibidos

| División | Formato |
|----------|----------|
| Electrónica | CSV |
| Supermercado | Excel (.xlsx) |
| Moda | JSON |
| Marketplace | PDF |

Todos los archivos llegan diariamente al Data Lake.

---

# Objetivo técnico

Construir un pipeline completamente serverless capaz de:

- Recibir archivos diariamente.
- Detectar automáticamente el formato recibido.
- Procesar cada archivo.
- Estandarizar el esquema de datos.
- Almacenar la información procesada.
- Consultar los datos mediante SQL utilizando Athena.

---

# Arquitectura propuesta

```
Python Generators
        │
        ▼
 Amazon S3 (Bronze)

        │
EventBridge

        │
        ▼
 Lambda de ingesta (Docker) — una función por división/formato

        │
        ▼
 Amazon S3 (Silver)

        │
EventBridge

        │
        ▼
 Lambda de transformación (Docker) — una función por división

        │
        ▼
 Amazon S3 (Gold)

        │
        ▼
 Glue Data Catalog

        │
        ▼
 Amazon Athena
```

---

# Componentes AWS

## Amazon S3

Almacenamiento del Data Lake.

Capas:

- Bronze
- Silver
- Gold

---

## AWS Lambda

Procesamiento automático de cada archivo, en dos etapas encadenadas por eventos enrutados vía EventBridge:

- **Lambda de ingesta** (Bronze → Silver): **una función por división/formato** (4 en total, una por formato: CSV, Excel, JSON, PDF), cada una empaquetada en su propia imagen Docker con el parser correspondiente.
- **Lambda de transformación** (Silver → Gold): una función por división (4 en total), sin parser de formato (Silver ya es Parquet homogéneo), comparte imagen Docker con la Lambda de ingesta de su división.

Responsabilidades:

- Detectar formato (solo la Lambda de ingesta)
- Validar estructura
- Transformar datos
- Normalizar columnas
- Exportar Parquet

---

## Amazon ECR

Repositorio de imágenes Docker utilizadas por Lambda.

Permitirá utilizar dependencias externas sin las limitaciones de los ZIP tradicionales.

---

## AWS Glue Data Catalog

Catalogará automáticamente las tablas almacenadas en S3.

---

## Amazon Athena

Permitirá consultar la información mediante SQL sin necesidad de desplegar una base de datos.

---

## Terraform

Toda la infraestructura será creada mediante Infraestructura como Código.

Recursos aproximados:

- S3
- IAM
- Lambda
- EventBridge
- ECR
- Glue Database
- Glue Crawler
- Athena
- CloudWatch

---

# Generación de datos

Para simplificar el laboratorio, los archivos serán generados mediante scripts de Python.

Durante la explicación se asumirá que dichos archivos provienen diariamente de los distintos sistemas internos de la empresa.

Cada script simulará el comportamiento de una división distinta.

---

# Procesamiento esperado

Cada formato tendrá un parser independiente.

Ejemplo conceptual:

```
CSV Parser

Excel Parser

JSON Parser

PDF Parser
```

Todos producirán exactamente el mismo esquema.

---

# Esquema unificado

Ejemplo:

- sale_id
- date
- store
- category
- product
- quantity
- price
- total

De esta forma Athena podrá consultar todos los datos sin importar su origen.

---

# Consultas de negocio

Ejemplos:

- Ventas por categoría.
- Top 10 productos.
- Ventas por tienda.
- Ticket promedio.
- Ventas por día.
- Productos con mayores ingresos.

---

# Tecnologías utilizadas

- Python
- Docker
- Terraform
- AWS Lambda
- Amazon ECR
- Amazon S3
- Amazon EventBridge
- AWS Glue
- Amazon Athena

---

# Objetivos de aprendizaje

Al finalizar el webinar el participante será capaz de:

- Diseñar un Data Lake sencillo en AWS.
- Automatizar el procesamiento de archivos utilizando Lambda.
- Empaquetar Lambdas mediante Docker.
- Administrar infraestructura utilizando Terraform.
- Consultar datos almacenados en S3 mediante Athena.
- Comprender una arquitectura serverless orientada a datos.

---

# Alcance

Este webinar prioriza la simplicidad para fines educativos.

No se abordarán temas avanzados como:

- Streaming
- Apache Spark
- Glue Jobs
- Kinesis
- Orquestación compleja
- CI/CD

Estos temas podrán desarrollarse en webinars posteriores.

---

# Evoluciones futuras

Posibles versiones posteriores del laboratorio:

- EventBridge Scheduler para cargas automáticas (distinto del enrutamiento de eventos `Object Created` ya implementado — ver "Arquitectura propuesta" y SPEC-003; Scheduler dispararía la *generación* periódica de archivos, no el paso entre etapas del pipeline).
- Step Functions para orquestación.
- Glue Jobs con Spark.
- Lake Formation.
- Iceberg Tables.
- QuickSight para visualización.
- Integración con IA para extracción inteligente de PDFs.
- Frontend de carga para el usuario final (formulario web + API Gateway/Lambda
  que emite una URL prefirmada de S3 hacia `bronze/date=<fecha>/<division>/`),
  como alternativa a la carga manual por CLI/generadores/consola S3. Aditivo,
  no reemplaza el enrutamiento S3 + EventBridge ya implementado — solo agrega
  una capa de recepción delante de Bronze. Para la demo actual se optó por una
  alternativa más simple sin infraestructura nueva: carga por consola web de
  S3 (drag-and-drop de `data/date=<fecha>/`, un día completo con las 4
  divisiones a la vez, mismo layout que Bronze) — ver
  [carga_web_bronze.md](../docs/consideraciones/carga_web_bronze.md). Esta
  entrada queda como evolución posible si en el futuro se necesita servir
  carga a usuarios sin acceso a la consola AWS.
- CI/CD para el pipeline de despliegue (Terraform + build/push de imágenes).
- Observabilidad avanzada (dashboards, alertas más allá de CloudWatch Logs +
  AWS Budgets).
- Kinesis Data Streams, como alternativa a la ingesta por archivo cuando el
  caso de uso lo justifique.

## Backlog de segunda iteración (fuera de alcance del webinar actual)

Los siguientes puntos amplían el laboratorio desde "pipeline ETL sobre AWS"
hacia una plataforma de datos más cercana a un proyecto empresarial real —
mayor realismo de negocio, calidad de datos como entregable, y Gold como
producto de datos versionado. Quedan fuera del alcance de la demo actual
(mantener la simplicidad didáctica del webinar); se documentan acá como
backlog para no perder la propuesta, no como trabajo planificado.

**Evolucionar el caso de negocio.** Actualmente las 4 divisiones demuestran
heterogeneidad de formato de archivo, pero se perciben como un ejercicio
académico. Se propone que cada división represente explícitamente un sistema
empresarial distinto — Electrónica como ERP corporativo, Supermercado como
POS legacy, Moda como plataforma e-commerce, Marketplace como API de
terceros — para que el foco pase de "cuatro formatos distintos" a
"integración de múltiples sistemas empresariales" (los campos específicos por
división que ya reflejan parte de esta heterogeneidad están implementados,
ver SPEC-002 "Campos específicos por división").

**Mayor protagonismo de Data Quality.** La cuarentena existe hoy como
componente técnico; se propone convertirla en uno de los objetivos
principales del laboratorio, con indicadores explícitos (filas procesadas,
válidas, rechazadas, % de calidad, errores por categoría, tiempo de
procesamiento) mostrados como un entregable del pipeline, no solo como efecto
secundario. Relacionado: reforzar el realismo de los datos con problemas
habituales de producción (clientes duplicados, catálogos inconsistentes,
fechas inconsistentes, JSON embebidos, campos opcionales, cambios de esquema,
archivos parcialmente corruptos) — la mayoría de estos problemas de
integración base ya están cubiertos por SPEC-008; lo pendiente es la
capa de *medición* de calidad sobre ellos, no los problemas en sí.

**Narrativa analítica desde el inicio.** En vez de que Athena aparezca solo
al final, comenzar el laboratorio planteando preguntas de negocio que el
usuario todavía no puede responder (¿categoría más rentable?, ¿división de
mayor facturación?, ¿ticket promedio?, ¿productos que concentran más
ingresos?) y construir el pipeline en función de responderlas durante el
webinar.

**Gold como Data Product.** Tratar la capa Gold no solo como una capa del
Data Lake sino como un producto de datos con contrato estable, esquema
versionado y consumo analítico explícito (ej. "Sales Analytics Dataset"),
sin aumentar significativamente la complejidad técnica actual.

**Métricas operativas.** Además del procesamiento ETL, producir información
operacional tipo "Data Quality Report" (total recibido/procesado/rechazado,
tiempo de ejecución, cantidad de archivos, tiempo promedio por archivo).

**Enriquecer la historia de los datasets** con campañas comerciales por
división (ej. Cyber Days/lanzamientos en Electrónica, Campaña Escolar/Navidad
en Supermercado, Colección Primavera/Liquidación en Moda, Black Friday/Hot
Sale en Marketplace), para dar pie a consultas analíticas más interesantes.

**Separar más claramente lógica técnica y de negocio** dentro del pipeline
(parsing, validación, normalización, reglas de negocio, publicación del Data
Product) para facilitar estas evoluciones futuras sin acoplarlas.

**Reposicionamiento del proyecto.** Si se retoma esta segunda iteración,
migrar el mensaje de "Pipeline ETL Serverless sobre AWS" a "Plataforma
moderna de ingeniería de datos basada en eventos, contratos de datos, calidad
de datos e Infraestructura como Código" — mejor alineado con fines educativos
y de portafolio profesional.

Fuera de alcance incluso para esa segunda iteración (evoluciones más
lejanas): Glue Jobs con Spark, Iceberg Tables, Lake Formation, QuickSight,
extracción inteligente de PDFs mediante IA — superpuesto con la lista general
de evoluciones futuras de arriba.