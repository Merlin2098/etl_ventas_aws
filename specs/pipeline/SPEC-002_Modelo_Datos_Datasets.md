# SPEC-002 - Modelo de Datos y Datasets

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir el contrato de datos que utilizará todo el proyecto, desde los archivos de entrada generados por cada división de RetailCorp hasta el esquema unificado (Gold) consumido por Athena.

---

# Divisiones de negocio

| División    | Formato       | store (valor fijo) |
| ------------ | ------------- | ------------------ |
| Electrónica | CSV           | `electronica`    |
| Supermercado | Excel (.xlsx) | `supermercado`   |
| Moda         | JSON          | `moda`           |
| Marketplace  | PDF           | `marketplace`    |

El campo `store` del esquema unificado identifica la división de origen; no existen tiendas/sucursales adicionales dentro de cada división en el alcance de este laboratorio.

---

# Datos sintéticos

- Cada división cuenta con un script Python generador independiente (`scripts/generators/<division>.py` o equivalente), que simula el archivo de ventas diario de esa división.
- Volumen: fijo y moderado por ejecución (orden de 200-500 filas), priorizando claridad didáctica sobre realismo de volumen.
- Cada ejecución genera datos para una fecha (por defecto, la fecha de ejecución).
- **Datos con errores intencionales**: cada generador debe producir un porcentaje pequeño y controlado de filas inválidas (campos faltantes, tipos incorrectos, fechas mal formateadas, valores negativos donde no corresponde, encoding irregular en CSV, etc.), con el fin de ejercitar las validaciones y el flujo de cuarentena del pipeline (ver SPEC-003 y SPEC-005). El porcentaje exacto y el catálogo de errores simulados se definen en SPEC-005 (contrato de los parsers).

---

# sale_id

- Se genera como **UUID v4** en el momento de la creación del registro sintético.
- Garantiza unicidad global sin necesidad de coordinación entre generadores de distintas divisiones.
- El generador (SPEC-007) siempre lo incluye; no forma parte del catálogo de corrupciones
  intencionales (SPEC-007, "Errores intencionales"). La validación de la Lambda (SPEC-005)
  es defensiva: si por alguna razón una fila llegara sin `sale_id` o con un valor no-UUID,
  la Lambda genera uno nuevo en el paso de normalización en vez de rechazar la fila
  únicamente por ese campo. Este comportamiento defensivo no es la vía esperada en el
  flujo normal, solo una salvaguarda.

---

# Formatos de origen por división

Cada división exporta su archivo en un formato y con una estructura de columnas propia (no unificada), reflejando que cada área usa tecnología distinta. El detalle línea por línea del esquema de origen de cada formato (nombres de columnas, delimitadores, hojas de Excel, estructura JSON, layout de PDF) se define al implementar cada generador, pero debe respetar como mínimo los siguientes campos equivalentes al esquema Gold:

| Campo Gold | Presente en origen | Notas                                                                                      |
| ---------- | ------------------ | ------------------------------------------------------------------------------------------ |
| sale_id    | Sí                | UUID v4                                                                                    |
| date       | Sí                | Formato de fecha varía por división (ver sección Fechas)                                |
| store      | Implícito         | Se asigna por división al normalizar, no siempre viene explícito en el archivo de origen |
| category   | Sí                | Categoría de producto dentro de la división                                              |
| product    | Sí                | Nombre o descripción del producto                                                         |
| quantity   | Sí                | Entero positivo                                                                            |
| price      | Sí                | Precio unitario                                                                            |
| total      | Sí o derivado     | Si no viene en el origen, se calcula como`quantity * price` durante la transformación   |

---

# Fechas

- Cada división emite fechas en un formato distinto en su archivo de origen (por ejemplo: `DD/MM/YYYY`, `MM-DD-YYYY`, timestamp ISO 8601, fecha como texto libre en PDF), reflejando la heterogeneidad real de sistemas de origen.
- La normalización a un formato único (`YYYY-MM-DD`, tipo `date`) ocurre durante la transformación en la Lambda, antes de escribir en la capa Gold (detalle de implementación en SPEC-005).
- El formato de fecha esperado por división debe quedar documentado en el propio generador de esa división.

---

# Esquema unificado (Gold)

Todos los formatos de origen deben converger en el siguiente esquema. `store` y `date`
son **columnas de partición** (codificadas en la ruta S3 `gold/store=<division>/date=<fecha>/`,
ver SPEC-003) y por lo tanto **no se escriben como columnas dentro del archivo Parquet**;
Athena las expone igual en el `SELECT` porque el Glue Crawler las registra como columnas
de partición de la tabla. Escribirlas también dentro del Parquet produciría columnas
duplicadas al catalogar (ver SPEC-005, "Conversión a Parquet").

| Campo    | Tipo                  | Nullable | Dónde vive                | Descripción                                                                                  |
| -------- | --------------------- | -------- | -------------------------- | ----------------------------------------------------------------------------------------------- |
| sale_id  | string (UUID)         | No       | Columna Parquet            | Identificador único de la venta                                                              |
| date     | date (`YYYY-MM-DD`) | No       | Partición Hive (`date=`)  | Fecha de la venta, normalizada                                                                |
| store    | string                | No       | Partición Hive (`store=`) | División de origen (`electronica`, `supermercado`, `moda`, `marketplace`) |
| category | string                | No       | Columna Parquet            | Categoría del producto                                                                       |
| product  | string                | No       | Columna Parquet            | Nombre del producto                                                                           |
| quantity | integer               | No       | Columna Parquet            | Cantidad vendida, entero positivo                                                             |
| price    | decimal               | No       | Columna Parquet            | Precio unitario                                                                               |
| total    | decimal               | No       | Columna Parquet            | `quantity * price`, recalculado en transformación para consistencia                        |

Este esquema (columnas Parquet + columnas de partición) es el contrato que consume Athena
vía Glue Data Catalog (ver SPEC-006). El esquema pyarrow explícito que fija estos tipos al
escribir se define en SPEC-005.

---

# Esquema intermedio (Silver)

Capa intermedia entre Bronze y Gold, producida por la Lambda de ingesta (ver SPEC-003/SPEC-005)
antes de la validación completa. Contiene los mismos campos que Gold, con dos diferencias:
`sale_id` es *nullable* (passthrough del origen si viene, sin generarse aquí) y `total` no
existe (se recalcula únicamente en la etapa Gold). `store` y `date` son columnas de partición
Hive igual que en Gold (`silver/store=<division>/date=<fecha>/`), no columnas del Parquet.

| Campo    | Tipo                  | Nullable | Dónde vive                | Descripción                                                    |
| -------- | --------------------- | -------- | -------------------------- | ---------------------------------------------------------------- |
| sale_id  | string (UUID)         | Sí      | Columna Parquet            | Passthrough del origen si es un UUID v4 válido; si no, `null` |
| date     | date (`YYYY-MM-DD`) | No       | Partición Hive (`date=`)  | Fecha de la venta, normalizada                                |
| store    | string                | No       | Partición Hive (`store=`) | División de origen                                             |
| category | string                | No       | Columna Parquet            | Categoría del producto                                         |
| product  | string                | No       | Columna Parquet            | Nombre del producto                                             |
| quantity | integer               | No       | Columna Parquet            | Cantidad vendida, entero positivo                               |
| price    | decimal               | No       | Columna Parquet            | Precio unitario                                                   |

Una fila que no complete estos campos (fecha no parseable, categoría/producto vacío,
cantidad/precio no numérico o negativo) se considera inválida en esta misma etapa y se
enruta a cuarentena — no llega a generarse una fila Silver para ella (ver SPEC-005).

---

# Reglas básicas de transformación

- `total` siempre se recalcula como `quantity * price` en la capa Gold, independientemente de si el origen trae un campo de total propio (evita inconsistencias entre divisiones).
- `store` se asigna de forma fija según la división de origen del archivo (no se extrae de una columna del archivo, salvo que el archivo ya la traiga explícita, en cuyo caso debe coincidir).
- `date` se normaliza siempre a `YYYY-MM-DD` a partir del formato propio de cada división.
- Todos los campos del esquema Gold son obligatorios (`nullable: No`); una fila que no pueda completarlos tras la transformación se considera inválida.

---

# Manejo de filas/archivos inválidos

- Las filas que no cumplan el esquema Gold (campo faltante, tipo inválido, fecha no parseable, cantidad o precio no numérico/negativo) se envían a una zona de **cuarentena en S3** (por ejemplo `s3://<bucket>/quarantine/`), en lugar de descartarse silenciosamente o de invalidar el archivo completo.
- El resto de las filas válidas del mismo archivo continúan su procesamiento normal hacia Gold.
- El detalle operativo de cuarentena (estructura de carpetas, formato del registro de error, reintentos) se define en SPEC-003 (Pipeline de Procesamiento) y SPEC-005 (Implementación de la Lambda).

---

# Convenciones de nombres (definido en SPEC-003)

La organización de rutas en S3 Bronze/Gold se define en SPEC-003 (Pipeline de Procesamiento): Bronze se particiona solo por fecha (los datos se reciben tal cual, sin partición por división); Gold se particiona por división y fecha.

---

# Fuera de alcance

- Definición de particionado físico en S3 (se resuelve en SPEC-003/004).
- Formato de columnas exacto de cada archivo de origen (se resuelve al implementar cada generador).
- Reglas de deduplicación o versionado de ventas re-enviadas (no contempladas en esta demo).
