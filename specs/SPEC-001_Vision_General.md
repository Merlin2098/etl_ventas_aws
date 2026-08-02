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
| Hogar | CSV |
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
S3 Event Notification

        │
        ▼
 Lambda (Docker) — una función por división/formato

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
- Gold

---

## AWS Lambda

Procesamiento automático de cada archivo. Se despliega **una función Lambda por división/formato** (5 en total), cada una empaquetada en su propia imagen Docker con el parser correspondiente.

Responsabilidades:

- Detectar formato
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

- Particionado por fecha.
- Medallion Architecture (Bronze / Silver / Gold).
- EventBridge Scheduler para cargas automáticas.
- Step Functions para orquestación.
- Glue Jobs con Spark.
- Lake Formation.
- Iceberg Tables.
- QuickSight para visualización.
- Integración con IA para extracción inteligente de PDFs.