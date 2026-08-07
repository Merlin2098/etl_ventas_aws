# SPEC-007 - Generadores de Datos Sintéticos

## Estado

Borrador v0.1 (Línea Base)

---

# Objetivo

Definir el script Python que genera los datasets sintéticos de ventas para las 4 divisiones de RetailCorp (ver SPEC-002), en los formatos de origen correspondientes (CSV, Excel, JSON, PDF), y los sube a la capa Bronze del Data Lake (ver SPEC-003).

---

# Librerías a utilizar (criterio de decisión)

| Necesidad | Librería elegida | Alternativa considerada | Por qué |
|-----------|-------------------|--------------------------|---------|
| Datos falsos realistas (nombres de producto, categorías, direcciones) | **Faker** | `random.choice` sobre listas fijas (stdlib) | Ya está declarada en el proyecto (`requirements-dev.txt`); da variedad realista sin mantener catálogos curados a mano. Se promueve a dependencia de **runtime** (ver "Cambios a requirements.txt") porque los generadores no son código de test. |
| Escritura CSV | **csv (stdlib)** | pandas `to_csv` | CSV es el formato más simple de los cuatro; no amerita traer pandas solo para esto. Se usa `csv.DictWriter` directamente, alineado con la política de simplicidad (Policy 008 — preferir stdlib antes que dependencias). |
| Escritura Excel (.xlsx) | **openpyxl** | XlsxWriter | Ambas ya están en `requirements.txt`. Se elige openpyxl por ser la que ya se usa como motor de lectura de Excel en otras partes del framework (`fastexcel`/`openpyxl` en `requirements.txt`), evitando tener dos librerías distintas de Excel en el proyecto sin necesidad. |
| Escritura JSON | **json (stdlib)** | — | Sin alternativa relevante; `json.dump` cubre el caso por completo. |
| Escritura PDF | **reportlab** | fpdf2 | Ninguna de las dos estaba en el proyecto. Se elige reportlab por soporte maduro de tablas (`reportlab.platypus.Table`), necesario para producir un PDF con estructura tabular que luego `pdfplumber` (SPEC-005) pueda extraer de forma confiable vía `extract_table()`. Se agrega como nueva dependencia de runtime. |
| Subida a S3 | **boto3** | — | Ya está en `requirements.txt` (sección cloud); es el cliente estándar del framework para AWS. |

## Cambios a `requirements.txt` / `requirements-dev.txt`

- Mover `faker` de `requirements-dev.txt` a la sección `local` de `requirements.txt` (deja de ser solo dependencia de testing).
- Agregar `reportlab` a la sección `local` de `requirements.txt`.
- No se requieren más cambios: `openpyxl`, `boto3` ya están declarados.

---

# Estructura del script

Siguiendo `ai/skills/python/python_project_guidance.md` (lógica en `src/`, orquestación visible en `scripts/`):

```
scripts/
└── data_generator/
    └── generate_sales.py        # entrypoint CLI único, parametrizado por --division

src/
└── generators/
    ├── __init__.py
    ├── detalle-data.yaml         # fuente única de verdad: divisiones, formato, fecha, catálogo
    └── engine/                    # código interno — no se edita para agregar/ajustar una división
        ├── __init__.py
        ├── common.py               # Faker seed, inyección de errores (maybe_corrupt), generate_row
        ├── config.py                # carga detalle-data.yaml -> DIVISIONS / DIVISION_ORDER
        ├── schema.py                # dataclass SaleRecord (campos "de origen", antes de normalizar)
        ├── uploader.py               # subida a Bronze (boto3)
        └── writers/
            ├── csv_writer.py         # electronica
            ├── excel_writer.py       # supermercado
            ├── json_writer.py        # moda
            └── pdf_writer.py         # marketplace
```

`detalle-data.yaml` es lo primero visible al abrir `src/generators/` (junto a
`__init__.py`), deliberadamente separado del código en `engine/`: todo lo que varía por
división (formato de origen, formato de fecha, extensión, y el catálogo de
categorías/productos/rango de precio) vive ahí, no hardcodeado en Python — agregar o
ajustar una división es editar el YAML, sin tocar `engine/`, salvo que el nuevo formato de
origen requiera un writer nuevo (ver "Selección de writer por división").

---

# Entrypoint CLI

Un único script parametrizado, no 4 scripts separados:

```
python scripts/data_generator/generate_sales.py --division electronica
python scripts/data_generator/generate_sales.py --division all   # las 4 en secuencia
python scripts/data_generator/generate_sales.py                  # las 4 (default)
```

La fecha (o rango de fechas) no se pasa por flag: el script la pide
interactivamente por stdin, siempre:

```
Fecha inicio (YYYY-MM-DD): 2026-08-01
Fecha fin (YYYY-MM-DD, Enter para un solo día):
```

Dejar la fecha fin en blanco genera un único día (la fecha de inicio);
completarla genera todos los días del rango indicado, inclusive, uno por
división y por fecha — sin límite de longitud de rango.

| Argumento | Descripción | Default |
|-----------|-------------|---------|
| `--division` | `electronica`, `supermercado`, `moda`, `marketplace`, o `all` (ejecuta las 4 en secuencia) | `all` |
| `--rows` | Cantidad de filas a generar | 200-500 (ver SPEC-002) |
| `--error-rate` | Proporción de filas con errores intencionales (0.0-1.0) | 0.05 (5%, ver "Errores intencionales") |
| `--upload / --no-upload` | Si se sube el archivo generado a S3 Bronze o solo se escribe localmente | `--no-upload` (requiere `DATA_BUCKET` explícito para subir, ver "Carga hacia Amazon S3") |
| `--output-dir` | Carpeta local donde se escribe el archivo antes de subir (o en vez de subir con `--no-upload`) | `data/` en la raíz del proyecto |

`--division all` invoca internamente la misma lógica de generación por cada división, en el orden de la tabla de SPEC-002 (Electrónica, Supermercado, Moda, Marketplace), consistente con SPEC-003 ("el presentador corre cada script o los cuatro en secuencia").

---

# Selección de writer por división

`src/generators/engine/config.py` carga `src/generators/detalle-data.yaml` y resuelve
cada división a un `DivisionConfig`, evitando un `if/elif` disperso en el entrypoint:

```yaml
# src/generators/detalle-data.yaml
divisions:
  electronica:
    format: csv
    date_format: "%d/%m/%Y"
    ext: csv
    categories:
      Audio:
        products: ["Audífonos Bluetooth", "Parlante Portátil", "Barra de Sonido"]
        price_min: 15
        price_max: 300
      # ...

  supermercado:
    format: excel
    date_format: "%m-%d-%Y"
    ext: xlsx
    categories: { ... }

  moda:
    format: json
    date_format: iso8601
    ext: json
    categories: { ... }

  marketplace:
    format: pdf
    date_format: free_text_es
    ext: pdf
    categories: { ... }

division_order: [electronica, supermercado, moda, marketplace]
```

`format` es un string (`csv`/`excel`/`json`/`pdf`) resuelto a la función writer real vía un
diccionario fijo `FORMAT_WRITERS` en `engine/config.py` — el catálogo YAML no serializa
código Python, solo el nombre del formato. Agregar una división con un formato de origen ya
soportado (ej. otro CSV) es puramente editar el YAML; un formato nuevo (ej. XML) todavía
requiere implementar su writer en `engine/writers/` y registrarlo en `FORMAT_WRITERS`.

`date_format` acepta tres formas: un patrón `strftime` literal (ej. `"%d/%m/%Y"`), o uno de
los dos formatos con nombre resueltos por `engine/config.py`:

- `iso8601` → `date.isoformat()` (Moda).
- `free_text_es` → el patrón concreto `"<día> de <mes en palabra, español> de <año>"` (ej.
  `"1 de agosto de 2026"`), generado con un mapa fijo de meses en español en `common.py`
  (Marketplace). Es "texto libre" en el sentido de que no es un formato estructurado como
  `%d/%m/%Y` (requiere un parser dedicado, no `strptime` directo), pero el patrón en sí es
  fijo y determinista — necesario para que el parser PDF de la Lambda (SPEC-005, "Parser
  PDF") pueda normalizarlo de forma confiable.

El formato de fecha por división refleja la heterogeneidad definida en SPEC-002 ("Fechas"
— varía por división de forma realista); cada writer es responsable de formatear `date`
según su propia convención antes de escribirla en el archivo de origen.

---

# Generación de filas

Cada fila generada, antes de pasar por el writer específico, se modela como:

```python
@dataclass
class SaleRecord:
    sale_id: str        # uuid4, ver SPEC-002
    date: datetime.date
    category: str
    product: str
    quantity: int
    price: Decimal
    currency: str        # SPEC-008 #5
    status: str          # SPEC-008 #10
    # total NO se incluye: se calcula en la Lambda (SPEC-002/005), no en el generador

    # Campos específicos por división (SPEC-009 §2), todos Optional = None por
    # defecto. generate_row solo los puebla para la división a la que pertenecen
    # (ej. serial_number únicamente en filas de Electrónica); en las demás
    # divisiones quedan en None y no se escriben al archivo de esa división
    # (ver "Selección de campos por división" abajo).
    serial_number: Optional[str] = None       # Electrónica
    warranty_months: Optional[int] = None      # Electrónica
    manufacturer: Optional[str] = None         # Electrónica
    model: Optional[str] = None                # Electrónica
    cashier: Optional[str] = None              # Supermercado
    loyalty_points: Optional[int] = None       # Supermercado
    promotion_applied: Optional[bool] = None   # Supermercado
    register_number: Optional[str] = None      # Supermercado
    size: Optional[str] = None                 # Moda
    color: Optional[str] = None                # Moda
    collection: Optional[str] = None           # Moda
    season: Optional[str] = None               # Moda
    return_reason: Optional[str] = None        # Moda (opcional incluso dentro de Moda)
    seller_id: Optional[str] = None            # Marketplace
    marketplace_fee: Optional[Decimal] = None  # Marketplace
    commission_pct: Optional[Decimal] = None   # Marketplace
    shipping_provider: Optional[str] = None    # Marketplace
```

- `category` y `product` se eligen aleatoriamente del catálogo curado por división
  declarado en `src/generators/detalle-data.yaml` (ej. Electrónica: "Audio",
  "Computación", "Telefonía", cada una con su lista fija de productos plausibles). El
  catálogo es data-driven — no hardcodeado en `engine/common.py` — para poder ajustar
  categorías, productos o rangos de precio sin tocar código.
- `quantity`: entero aleatorio 1-10.
- `price`: decimal aleatorio dentro del rango `price_min`-`price_max` de la categoría
  elegida (declarado en el YAML, ej. Electrónica más caro que Moda), con redondeo a 2
  decimales.
- `currency`/`status`: elegidos aleatoriamente del catálogo `currencies`/`statuses`
  de la división en el YAML (SPEC-008 #5/#10); ambas listas pueden repetir valores
  para sesgar la frecuencia (ej. la mayoría de ventas de Supermercado en `PEN`).
- `store` **no** se genera aquí: lo asigna la Lambda según la división de origen (SPEC-002).
- `total` **no** se genera aquí: se recalcula en la Lambda (SPEC-002, "Reglas básicas de transformación").

## Selección de campos por división (SPEC-009 §2)

`generate_row` puebla los campos específicos de la división actual mediante
`_generate_extra_fields` (`engine/common.py`), que combina dos fuentes:

- **Catálogo cerrado** (ej. `manufacturer`, `size`, `cashier`): valores listados
  en `extra_fields` dentro de `detalle-data.yaml`, elegidos con `random.choice`
  — mismo patrón que `currencies`/`statuses`.
- **Identificador libre** (ej. `serial_number`, `seller_id`, `register_number`,
  `model`): generado directamente en Python (no en el YAML, no son un catálogo
  cerrado de valores posibles), con un prefijo fijo por campo para que sea
  reconocible en la demo (ej. `SN-XXXXXXXXXX`, `SELLER-NNNN`).

`config.fieldnames` (`DivisionConfig`, `engine/config.py`) resuelve, para cada
división, la lista ordenada de columnas propias (los 8 campos base +
`extra_fields.keys()` + los identificadores libres de esa división). Antes de
escribir, `generate_division` filtra el dict completo de `SaleRecord` a solo
`config.fieldnames` — así el archivo de Electrónica no expone una columna
`seller_id` vacía, por ejemplo. Los 4 writers (`csv_writer`, `excel_writer`,
`json_writer`, `pdf_writer`) reciben `fieldnames` como parámetro explícito en
vez de una constante global compartida (antes de SPEC-009 los 4 asumían el
mismo esquema de 8 campos para toda división).

---

# Errores intencionales

Implementado en `common.py` como una función `maybe_corrupt(row: dict, error_rate: float) -> dict`, aplicada antes de pasar la fila al writer:

| Tipo de error | Ejemplo de corrupción aplicada |
|----------------|----------------------------------|
| Campo faltante | Eliminar `product` o `category` de la fila. |
| Tipo inválido | Reemplazar `quantity` por un string no numérico (`"N/A"`). |
| Fecha mal formateada | Escribir la fecha en un formato distinto al esperado por esa división, o como texto libre inválido (`"ayer"`). |
| Valor negativo | `quantity` o `price` negativo. |
| Encoding irregular (solo CSV) | Insertar un carácter fuera de UTF-8/Latin-1 en `product`. |

- La proporción de filas corrompidas por archivo es `--error-rate` (default 5%), aplicada por muestreo aleatorio sobre el total de filas (`--rows`).
- El tipo de corrupción a aplicar en cada fila afectada se elige aleatoriamente entre los tipos de la tabla anterior (equiprobable), salvo "Encoding irregular", que solo aplica a Electrónica (única división CSV).
- Este comportamiento es el que SPEC-002 y SPEC-006 asumen como fuente de las filas que terminan en `quarantine/`.

---

# Carga hacia Amazon S3

- Tras escribir el archivo localmente en `--output-dir`, si `--upload` está activo (opt-in explícito; el default es `--no-upload`, generación local únicamente), el script lo sube a Bronze usando boto3, con la convención de ruta definida en SPEC-003 (partición por fecha y luego división):

```
s3://<bucket>/bronze/date=<fecha>/<division>/<division>_<fecha>.<ext>
```

- El nombre de bucket se lee de una variable de entorno (`DATA_BUCKET`), nunca hardcodeado (Policy 003 — Configuration Over Hardcoding), consistente con el resto del framework.
- La subida es un `PutObject` simple (`boto3.client("s3").upload_file(...)`), sin multipart, alineado con SPEC-003.

---

# Reproducibilidad

- El script acepta `--seed` (opcional) para fijar la semilla de Faker y `random`, permitiendo regenerar exactamente el mismo dataset en ensayos previos al webinar.
- Sin `--seed`, cada ejecución genera datos distintos (comportamiento por defecto para simular variabilidad real).

---

# Fuera de alcance

- Validación de que el archivo generado es "parseable" por la Lambda correspondiente antes de subirlo — la corrupción intencional es exactamente lo que debe fallar validación en el pipeline (SPEC-005), no en el generador.
- Simulación de llegada fuera de horario o con delay artificial (los archivos se suben inmediatamente tras generarse).
