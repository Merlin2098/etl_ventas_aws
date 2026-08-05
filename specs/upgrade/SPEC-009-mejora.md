
# SPEC-009 - Segunda Iteración del Laboratorio Retail Data Platform

## Objetivo

Este documento recopila las oportunidades de mejora identificadas después de finalizar la primera versión del laboratorio.

El propósito **no es modificar el alcance del webinar actual**, sino servir como backlog de evolución para una segunda iteración del proyecto, incrementando su realismo, valor arquitectónico y cercanía con escenarios empresariales.

---

# Objetivos de la segunda iteración

La evolución del laboratorio buscará que deje de percibirse únicamente como un pipeline ETL sobre AWS y pase a representar una plataforma moderna de datos.

Los principales objetivos serán:

- Incrementar el realismo del caso de negocio.
- Simular problemas frecuentes en proyectos reales.
- Dar mayor protagonismo a la calidad de datos.
- Convertir Gold en un verdadero Data Product.
- Incorporar métricas operativas.
- Generar una narrativa más orientada al negocio.

---

# 1. Evolucionar el caso de negocio

## Situación actual

Actualmente el laboratorio representa cuatro divisiones que generan archivos en distintos formatos.

Aunque esto demuestra heterogeneidad tecnológica, todavía transmite la sensación de un ejercicio académico.

---

## Propuesta

Cada división deberá representar un sistema empresarial completamente diferente.

| División    | Sistema simulado      |
| ------------ | --------------------- |
| Electrónica | ERP corporativo       |
| Supermercado | Sistema POS Legacy    |
| Moda         | Plataforma E-Commerce |
| Marketplace  | API de terceros       |

El foco dejará de ser únicamente "cuatro formatos distintos" y pasará a ser "integración de múltiples sistemas empresariales".

---

# 2. Incrementar la complejidad funcional de los datasets

Actualmente las diferencias entre datasets son principalmente el formato de almacenamiento.

La segunda versión deberá incorporar diferencias funcionales propias de cada dominio.

## Electrónica

Campos adicionales

- serial_number
- warranty_months
- manufacturer
- model

---

## Marketplace

Campos adicionales

- seller_id
- marketplace_fee
- commission_pct
- shipping_provider

---

## Moda

Campos adicionales

- size
- color
- collection
- season
- return_reason

---

## Supermercado

Campos adicionales

- cashier
- loyalty_points
- promotion_applied
- register_number

Esto permitirá demostrar procesos ETL más cercanos a escenarios reales.

---

# 3. Dar mayor protagonismo a Data Quality

Actualmente la cuarentena existe como componente técnico.

En la siguiente iteración deberá convertirse en uno de los objetivos principales del laboratorio.

Se recomienda introducir indicadores como:

- Filas procesadas
- Filas válidas
- Filas rechazadas
- Porcentaje de calidad
- Errores por categoría
- Tiempo de procesamiento

La calidad de datos deberá mostrarse como un entregable del pipeline y no únicamente como un efecto secundario.

---

# 4. Introducir una narrativa analítica desde el inicio

Actualmente Athena aparece al finalizar el pipeline.

Se propone comenzar el laboratorio con preguntas de negocio que el usuario aún no puede responder.

Ejemplos

- ¿Cuál es la categoría más rentable?
- ¿Qué división genera mayor facturación?
- ¿Cuál es el ticket promedio?
- ¿Qué productos concentran la mayor parte de los ingresos?

Durante el webinar se construirá el pipeline necesario para responder dichas preguntas.

---

# 5. Convertir Gold en un Data Product

Actualmente Gold se presenta como una capa del Data Lake.

En la siguiente iteración deberá tratarse como un producto de datos.

Ejemplo

Sales Analytics Dataset

Características

- Contrato estable
- Esquema versionado
- Consumo analítico
- Fuente oficial para Athena

El objetivo es introducir el concepto de Data Products sin aumentar significativamente la complejidad técnica.

---

# 6. Incorporar métricas operativas

Además del procesamiento ETL, el laboratorio debería producir información operacional.

Ejemplo

Data Quality Report

- Total de registros recibidos
- Total procesados
- Total rechazados
- Tiempo de ejecución
- Cantidad de archivos
- Tiempo promedio por archivo

Esto acerca el laboratorio al funcionamiento de plataformas de datos reales.

---

# 7. Enriquecer la historia de los datasets

Actualmente los datos representan ventas genéricas.

La siguiente versión podría incorporar campañas comerciales.

Ejemplos

Electrónica

- Cyber Days
- Lanzamiento de consolas

Supermercado

- Campaña Escolar
- Navidad

Moda

- Colección Primavera
- Liquidación de temporada

Marketplace

- Black Friday
- Hot Sale

Esto permitirá construir consultas analíticas más interesantes.

---

# 8. Incrementar el realismo de los datos

Incorporar problemas habituales encontrados en producción.

Ejemplos

- Clientes duplicados
- Productos escritos de distintas maneras
- Fechas inconsistentes
- Monedas distintas
- JSON embebidos
- Campos opcionales
- Cambios de esquema
- Catálogos inconsistentes
- Archivos parcialmente corruptos

El objetivo es demostrar procesos reales de normalización.

---

# 9. Separar claramente la lógica técnica de la lógica de negocio

Continuar fortaleciendo la separación entre:

- Parsing del archivo
- Validación
- Normalización
- Reglas de negocio
- Publicación del Data Product

Esto facilitará futuras evoluciones del pipeline.

---

# 10. Reforzar el posicionamiento del proyecto

Actualmente el laboratorio puede percibirse como una demostración de servicios AWS.

La segunda iteración debería posicionarlo como una plataforma de datos moderna.

Mensaje actual

> Pipeline ETL Serverless sobre AWS.

Mensaje propuesto

> Plataforma moderna de ingeniería de datos basada en eventos, contratos de datos, calidad de datos e Infraestructura como Código.

Este cambio mejora significativamente el posicionamiento del repositorio, especialmente para fines educativos y de portafolio profesional.

---

# Mejoras futuras (fuera de alcance)

Las siguientes iniciativas se consideran evoluciones naturales del proyecto, pero quedan fuera del alcance de la segunda iteración.

- Step Functions
- Kinesis Data Streams
- EventBridge Scheduler
- Glue Jobs con Spark
- Iceberg Tables
- Lake Formation
- QuickSight
- CI/CD
- Observabilidad avanzada
- Extracción inteligente de PDFs mediante IA

---

# Resultado esperado

La segunda iteración deberá transformar el laboratorio desde un ejercicio técnico de ETL hacia una plataforma de datos mucho más cercana a un proyecto empresarial real, manteniendo el mismo nivel de simplicidad para fines didácticos, pero incrementando considerablemente el valor arquitectónico, la narrativa del negocio y la calidad del contenido presentado durante el webinar.
