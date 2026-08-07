
# SPEC-008 - Complejización del Generador de Datasets Retail

## Objetivo

Incrementar el nivel de realismo de los datasets utilizados durante el laboratorio para que representen escenarios similares a los encontrados en proyectos empresariales de Data Engineering sobre AWS.

El objetivo **no es generar más columnas**, sino introducir problemas reales de integración, calidad de datos y diferencias entre sistemas de origen.

---

# Categorías consideradas

Se trabajarán únicamente cuatro dominios de negocio.

| Categoría   | Representa            |
| ------------ | --------------------- |
| Electrónica | ERP propio            |
| Marketplace  | API de terceros       |
| Supermercado | Sistema POS           |
| Moda         | Plataforma E-commerce |

Cada categoría simula un sistema distinto con reglas de negocio propias.

---

# Principios de diseño

El generador deberá producir datasets que presenten:

- Diferencias de estructura
- Calidad de datos imperfecta
- Esquemas variables
- Valores opcionales
- Tipos de datos distintos
- Reglas de negocio específicas

El objetivo es obligar al pipeline a realizar transformaciones reales durante el proceso ETL.

---

# Propuestas de complejización

## 1. Esquemas diferentes por categoría

Cada categoría posee columnas exclusivas.

> **Estado: implementado** (ver SPEC-002 "Campos específicos por división",
> `src/generators/engine/schema.py` `SaleRecord` y
> `src/lambda_ingestion/common/schema.py` `GOLD_SCHEMA`), con ligeras
> diferencias de nombre/alcance respecto a la propuesta original de esta
> sección, resueltas al implementar:
> - Supermercado: `cash_register` se implementó como `register_number`.
> - Marketplace: `coupon_code` no se implementó (queda para una fase de
>   "campos opcionales"/promociones futura, punto 2/13 de este mismo spec).
> - Moda: `return_window_days` se implementó como `return_reason` (motivo de
>   devolución en vez de ventana de días), consistente con la sección "14.
>   Devoluciones" más abajo en este mismo documento, y solo se puebla para una
>   fracción de filas `RETURNED`/`EXCHANGED` — no es una columna siempre
>   presente en Moda, a diferencia de las otras 3 columnas de esta división.
>
> Todos los campos se implementaron como nullable, sin regla de validación de
> negocio propia (esa parte — "Calidad de datos", punto 3 de este documento —
> queda fuera de esta fase, ver SPEC-001 "Evoluciones futuras").

### Electrónica

| Campo           |
| --------------- |
| serial_number   |
| warranty_months |
| manufacturer    |
| model           |

---

### Marketplace

| Campo             |
| ----------------- |
| seller_id         |
| marketplace_fee   |
| commission_pct    |
| shipping_provider |
| coupon_code       |

---

### Supermercado

| Campo             |
| ----------------- |
| cashier           |
| cash_register     |
| loyalty_points    |
| promotion_applied |

---

### Moda

| Campo              |
| ------------------ |
| size               |
| color              |
| season             |
| collection         |
| return_window_days |

---

## 2. Campos opcionales

No todos los registros contienen toda la información.

Ejemplos:

- coupon_code
- promotion_code
- discount_reason
- warranty_number

Esto permite demostrar manejo de NULLs durante lambda.

---

## 3. Calidad de datos

Introducir registros inválidos de forma controlada.

Ejemplos:

### Precio

```
120.50
NULL
-25
"100 USD"
```

### Cantidad

```
1
2
0
-1
NULL
```

---

## 4. Formatos de fecha diferentes

Cada sistema genera fechas distintas.

| Categoría   | Formato    |
| ------------ | ---------- |
| Electrónica | YYYY-MM-DD |
| Marketplace  | DD/MM/YYYY |
| Supermercado | MM-DD-YYYY |
| Moda         | YYYYMMDD   |

lambda deberá normalizar el formato.

---

## 5. Múltiples monedas

No todas las ventas utilizan la misma moneda.

Valores posibles:

- PEN
- USD
- EUR

Permite incorporar posteriormente tablas de tipo de cambio.

---

## 6. Impuestos distintos

Cada origen maneja impuestos diferentes.

Ejemplos

Electrónica

- IGV

Marketplace

- Commission
- Seller Fee
- Marketplace Fee

Moda

- VAT

Posteriormente deberán homologarse.

---

## 7. Catálogos inconsistentes

Una misma categoría puede venir escrita de distintas maneras.

Ejemplos

```
Electronica
Electrónica
ELEC
Electronic
```

El pipeline deberá estandarizar estos valores.

---

## 8. Clientes duplicados

Ejemplos

```
Juan Perez

JUAN PEREZ

Juan Pérez

juan perez
```

Permite demostrar procesos de limpieza.

---

## 9. Productos inconsistentes

Ejemplos

```
Laptop HP

HP Laptop

Laptop HP 15"

Laptop HP 15
```

Ideal para reglas de homologación.

---

## 10. Estados distintos

Cada sistema utiliza su propio catálogo.

Marketplace

- PAID
- SHIPPED
- DELIVERED

Supermercado

- COMPLETED

Moda

- RETURNED
- EXCHANGED

Electrónica

- PENDING
- INVOICED

El pipeline deberá generar un estado estándar.

---

## 11. JSON embebido

Marketplace puede incluir columnas JSON.

Ejemplo

```json
{
    "carrier": "DHL",
    "tracking": "ABC123",
    "insurance": true
}
```

lambda deberá extraer los atributos.

---

## 12. Arrays

Algunas columnas contendrán listas.

Ejemplo

```json
[
    "Mouse",
    "Keyboard",
    "Monitor"
]
```

Posteriormente podrán utilizarse transformaciones tipo explode.

---

## 13. Promociones

Agregar distintos tipos de descuento.

Valores posibles

- Coupon
- Flash Sale
- Loyalty
- Black Friday
- Employee
- Bundle

---

## 14. Devoluciones

Principalmente para Moda.

Campos sugeridos

- return_reason
- return_date
- exchange_flag

Valores

- Wrong Size
- Damaged
- Changed Mind

---

## 15. Información logística

Especialmente para Marketplace.

Campos

- shipping_cost
- warehouse
- carrier
- estimated_delivery
- actual_delivery

---

## 16. Diferente granularidad

Cada categoría representa una unidad distinta.

| Categoría   | Granularidad     |
| ------------ | ---------------- |
| Electrónica | Factura          |
| Marketplace  | Producto vendido |
| Supermercado | Ticket           |
| Moda         | Prenda           |

Esto obliga al proceso ETL a comprender la unidad de análisis antes de consolidar la información.

---

## 17. Evolución del esquema

Durante distintas ejecuciones podrán aparecer nuevos campos.

Ejemplo

Primera ejecución

```
customer_id
```

Ejecución posterior

```
customer_uuid
membership_level
```

Esto permite demostrar manejo de Schema Evolution.

---

## 18. Archivos corruptos

Un pequeño porcentaje de archivos deberá contener errores.

Ejemplos

- Columnas desplazadas
- Encabezados incompletos
- Filas vacías
- Delimitadores incorrectos

Estos archivos podrán enviarse posteriormente a una zona de cuarentena.

---

# Beneficios para el laboratorio

La incorporación de estas características permitirá demostrar:

- Validación de calidad de datos
- Normalización de esquemas
- Limpieza de información
- Manejo de NULLs
- Parsing de JSON
- Explode de arrays
- Homologación de catálogos
- Schema Evolution
- Procesamiento de datos corruptos
- Transformaciones ETL más cercanas a escenarios reales

---

# Resultado esperado

Los cuatro datasets dejarán de ser simples tablas con información similar y pasarán a representar cuatro sistemas empresariales distintos, cada uno con sus propias reglas de negocio, formatos, inconsistencias y problemas de calidad de datos.

Esto permitirá que el laboratorio muestre un proceso ETL mucho más cercano a un proyecto real de Data Engineering sobre AWS.
