# Glosario de SPECs

**Proyecto:** Data Lake Serverless para Retail con AWS
**Metodología:** Spec Driven Development (SDD)
**Cantidad de SPECs:** 8

Índice de referencia rápida de las specs del proyecto: qué cubre cada una y
dónde vive. El contenido completo (objetivo, decisiones, contrato de datos,
código de referencia) vive en el propio documento de cada spec — este archivo
no lo duplica, solo ayuda a encontrar cuál leer.

---

## Índice

| SPEC | Título | Ubicación | Qué resuelve |
| ---- | ------ | --------- | ------------ |
| SPEC-001 | Visión General del Proyecto | [`SPEC-001_Vision_General.md`](SPEC-001_Vision_General.md) | Contexto de negocio, arquitectura de alto nivel, alcance del webinar y evoluciones futuras (incluye el backlog de segunda iteración). |
| SPEC-002 | Modelo de Datos y Datasets | [`pipeline/SPEC-002_Modelo_Datos_Datasets.md`](pipeline/SPEC-002_Modelo_Datos_Datasets.md) | Contrato de datos: divisiones, esquema Gold/Silver unificado, campos específicos por división, reglas de transformación. |
| SPEC-003 | Pipeline de Procesamiento | [`pipeline/SPEC-003_Pipeline_Procesamiento.md`](pipeline/SPEC-003_Pipeline_Procesamiento.md) | Flujo funcional completo: generación → S3 → EventBridge → Lambda → capas del Data Lake → cuarentena. |
| SPEC-004 | Infraestructura como Código (Terraform) | [`pipeline/SPEC-004_Infraestructura_Terraform.md`](pipeline/SPEC-004_Infraestructura_Terraform.md) | Módulos Terraform, recursos AWS, variables/outputs, dependencias entre módulos, flujo de despliegue y destrucción. |
| SPEC-005 | Implementación de la Lambda | [`pipeline/SPEC-005_Implementacion_Lambda.md`](pipeline/SPEC-005_Implementacion_Lambda.md) | Arquitectura interna de las Lambdas: parsers, Docker/ECR, validaciones, esquemas pyarrow, logging. |
| SPEC-006 | Analítica y Validación End-to-End | [`pipeline/SPEC-006_Analitica_Validacion_E2E.md`](pipeline/SPEC-006_Analitica_Validacion_E2E.md) | Glue Data Catalog, consultas Athena, criterios de aceptación y validación E2E del laboratorio completo. |
| SPEC-007 | Generadores de Datos Sintéticos | [`generadores/SPEC-007_Generadores_Datos_Sinteticos.md`](generadores/SPEC-007_Generadores_Datos_Sinteticos.md) | Script generador: estructura, writers por formato, selección de campos por división, errores intencionales, carga a S3. |
| SPEC-008 | Complejización del Generador de Datasets Retail | [`generadores/SPEC-008_Consideraciones.md`](generadores/SPEC-008_Consideraciones.md) | Propuestas de realismo de datos (inconsistencias, catálogos, formatos) y su estado de implementación frente a SPEC-002/007. |

---

## Dependencia entre SPECs

```text
SPEC-001
│
├── SPEC-002
│      │
│      └── SPEC-007
│             │
│             └── SPEC-008
│
├── SPEC-003
│      │
│      └── SPEC-005
│
├── SPEC-004
│
└── SPEC-006
```

---

## Cómo mantener este glosario al día

Este archivo es un índice, no el lugar para documentar contenido nuevo.
Actualizarlo solo cuando:

- Se agrega, elimina o renombra una spec.
- Cambia la ubicación de un archivo de spec.
- Cambia la relación de dependencia entre specs.

El contenido técnico (qué dice cada spec, su estado de implementación, su
bitácora de decisiones) se edita en el propio documento de la spec — no acá.
