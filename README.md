# POC — Sistema RAG de Reformas de Vehículos

> Diseño de parsers, enriquecimiento e indexación  
> Sección I del Manual de Reformas · Reglamento (UE) 2018/858

---

## Índice

1. [Visión general](#1-visión-general)
2. [Parsers](#2-parsers)
3. [Enriquecimiento](#3-enriquecimiento)
4. [Indexación](#4-indexación)
5. [Relaciones entre documentos](#5-relaciones-entre-documentos)
6. [Scripts y flujo de trabajo](#6-scripts-y-flujo-de-trabajo)
7. [Pendiente](#7-pendiente)

---

## 1. Visión general

El objetivo de la POC es construir un sistema RAG (Retrieval-Augmented Generation) que permita consultar y redactar proyectos técnicos de reformas de vehículos a partir del Manual de Reformas de la DGT (Sección I) y normativa europea aplicable.

El sistema tiene dos funciones principales:

- **Chatbot de consulta** — responde preguntas sobre qué documentación exige una reforma, qué categorías de vehículo aplican, qué actos reglamentarios hay que cumplir, etc.
- **Redacción de proyecto técnico** — workflow guiado (n8n) que genera el proyecto técnico a partir de los datos del vehículo y la reforma.

### 1.1 Scope de la POC

La POC se limita a la **Sección I** del Manual de Reformas, que cubre las categorías M, N y O (turismos, furgonetas, camiones y remolques).

Quedan **fuera del scope**: secciones II, III y IV del manual, normativa externa completa (directivas, RD 866/2010), e interfaz de usuario final.

### 1.2 Documentos parseados

| Documento | Fuente | Output JSON | Chunks / Fichas |
|---|---|---|---|
| Fichas CR (Sección I) | Manual de Reformas DGT | `fichas_cr_seccion1.json` | 76 fichas |
| Preámbulo (Sección I) | Manual de Reformas DGT | `preambulo_seccion1.json` | 9 chunks |
| Reglamento (UE) 2018/858 | DOUE L 151, 14.6.2018 | `reglamento_ue_2018_858.json` | 8 chunks |

---

## 2. Parsers

### 2.1 Fichas CR — `parser_cr_seccion1.py`

Extrae las 76 fichas CR de la Sección I usando `pdfplumber` con arquitectura híbrida:
- `extract_tables()` → tablas de campo de aplicación y actos reglamentarios
- `extract_text()` → campos de texto libre

#### Campos extraídos por ficha

| Campo | Tipo | Descripción |
|---|---|---|
| `cr` | str | Código de reforma (ej. `2.1`, `8.52`) |
| `grupo_numero` | int | Número de grupo (1-11) |
| `descripcion_grupo` | str | Descripción del grupo de reforma |
| `descripcion_cr` | str | Descripción específica de la reforma |
| `campo_aplicacion` | dict | SI/NO por cada categoría M1-O4 |
| `categorias_aplicables` | list | Solo las categorías con SI |
| `actos_reglamentarios` | list | ARs con aplicabilidad por categoría |
| `documentacion_necesaria` | dict | PT / CFO / IC / CT / Doc adicional: SI o NO |
| `via_tramitacion` | str | Vía A, B, C o D |
| `via_tramitacion_desc` | str | Descripción legible de la vía |
| `keywords_reformas` | list | Términos del cliente (vacío hasta enriquecimiento) |
| `inspeccion_especifica` | str | Capítulos ITV a inspeccionar |
| `informacion_adicional` | str | Notas y condiciones especiales |
| `conjunto_funcional` | str / null | Referencia a conjunto funcional si aplica |
| `paginas` | list[int] | Páginas del PDF `[inicio, fin]` |

#### 2.1.1 Vías de tramitación

Cada ficha se clasifica en una de cuatro vías según la documentación exigible. Esta clasificación es clave para el retrieval condicional y el workflow de redacción.

| Vía | Condición | Documentación exigible | Fichas |
|---|---|---|---|
| **A** | Proyecto Técnico = SI | PT + CFO + IC + CT | 39 |
| **B** | PT = NO, IC = SI | IC + CT | 34 |
| **C** | Solo CT | Certificado de Taller | 2 |
| **D** | Solo doc. adicional | Documentación específica | 1 |

---

### 2.2 Preámbulo — `parser_preambulo.py`

Extrae el preámbulo en 9 chunks semánticos. Cada chunk tiene metadatos que controlan cómo se recupera en el RAG.

| Chunk | Páginas | Uso en RAG |
|---|---|---|
| `marco_legal` | 3 | Contexto general |
| `estructura_manual` | 4 | Contexto general |
| `estructura_ficha` | 5 | Contexto general |
| `interpretacion_ars` | 5 | **Inyectado en todas las fichas CR al indexar** |
| `proyecto_tecnico` | 6-8 | Retrieval condicional (vía A) |
| `informe_conformidad` | 8-10 | Retrieval condicional (vía B) |
| `certificado_taller` | 10-11 | Retrieval condicional (vías C y D) |
| `apartados_6_al_10` | 11-12 | Conjunto funcional, inspección, normalización |
| `glosario_siglas` | — | Chunk estático, no extraído del PDF |

#### Chunk `interpretacion_ars`

Es especial: no se indexa como documento independiente, sino que su texto se **inyecta directamente dentro del texto de embedding de cada ficha CR**. Esto garantiza que el modelo siempre tenga el contexto de qué significan los valores `(1)`, `(2)`, `(3)`, `-` y `x` en las tablas de actos reglamentarios, sin depender del retriever para encontrarlo.

#### Chunk `glosario_siglas`

Chunk estático (no extraído del PDF) con las siglas del dominio. Se define directamente en el parser como la constante `GLOSARIO_SIGLAS`:

```
AR, CR, IC, ITV, DGT, PT, CFO, CT, MMTA, MMA, CEPE/ONU, RD, DOUE
```

---

### 2.3 Reglamento (UE) 2018/858 — `parser_reglamento_ue.py`

Extrae los artículos 3 y 4 y el Anexo I del reglamento europeo que **deroga la Directiva 2007/46/CE**. Es la fuente oficial para las definiciones de categorías de vehículos M, N y O.

| Chunk | Páginas | Contenido |
|---|---|---|
| `art3_definiciones` | 11-14 | 58 definiciones (homologación, fabricante, matrícula...) |
| `art4_categorias_vehiculos` | 14 | Definiciones oficiales M1-M3, N1-N3, O1-O4 |
| `anexo1_intro_definiciones` | 66-67 | Plaza de asiento, masa máxima, mercancías |
| `anexo1_criterios_categorizacion` | 67-72 | Criterios para clasificar en M, N, O y subcategoría G |
| `anexo1_tipos_carroceria_M1` | 73-75 | Tipos de carrocería para M1 |
| `anexo1_tipos_carroceria_M2_M3` | 75-76 | Tipos de carrocería para M2 y M3 |
| `anexo1_tipos_carroceria_N_O` | 76-83 | Tipos de carrocería para N y O |
| `anexo1_apendice_todoterreno` | 84-86 | Procedimiento de verificación subcategoría G |

> **Nota técnica:** El PDF tiene los subíndices (M₁, N₁...) extraídos en líneas separadas (`M` en una línea, `1` en la siguiente). El parser normaliza este patrón con un post-proceso línea a línea antes de guardar el JSON.

---

## 3. Enriquecimiento

El campo `keywords_reformas` de cada ficha CR nace vacío. El enriquecimiento es el proceso de rellenar ese campo con términos reales de taller que el cliente aporta desde su experiencia.

### 3.1 CSV de keywords — `keywords_reformas.csv`

Fichero editable en Excel con cuatro columnas:

| Columna | Obligatoria | Descripción |
|---|---|---|
| `cr` | Sí | Código de reforma (ej. `2.1`). Debe existir en el JSON. |
| `keyword` | Sí | Término del cliente (ej. `cold air intake`, `turbo`) |
| `fuente` | No | Origen: `cliente`, `tecnico` o `admin` |
| `fecha_añadido` | No | Fecha de alta para trazabilidad (`YYYY-MM-DD`) |

Ejemplo:

```csv
cr,keyword,fuente,fecha_añadido
2.1,filtro de aire,cliente,2025-01-01
2.1,cold air intake,cliente,2025-01-01
2.1,snorkel,cliente,2025-01-01
2.4,conversión eléctrica,cliente,2025-01-01
```

El script **deduplica automáticamente** (case-insensitive) y avisa si un CR del CSV no existe en el JSON.

### 3.2 Script — `enriquecimiento.py`

Solo modifica `fichas_cr_seccion1.json`. Los JSONs del preámbulo y del reglamento no tienen keywords porque sus chunks son texto normativo fijo.

```bash
python enriquecimiento.py                        # usa paths por defecto
python enriquecimiento.py --csv otro.csv         # CSV alternativo
python enriquecimiento.py --csv otro.csv --fichas otra_ruta.json
```

---

## 4. Indexación

### 4.1 Base vectorial: ChromaDB

Se usa ChromaDB por su simplicidad para la POC local: un `pip install`, sin servidor, persiste en disco. La arquitectura es **dockerizable**: en el `docker-compose` final Chroma corre como servicio y el script usa `HttpClient` en lugar de `PersistentClient`.

### 4.2 Embeddings: `text-embedding-3-small` (OpenAI)

Se usa el modelo definitivo desde el principio, sin modelos intermedios. Razones:

- **Comprensión semántica real en español técnico**: `sistema de admisión` y `cold air intake` quedan cerca en el espacio vectorial.
- **Coste negligible**: el indexado inicial de 93 documentos cuesta menos de 0,01 USD.
- **Consistencia**: el modelo de indexado y el de consulta deben ser siempre el mismo. Usar el modelo definitivo desde el principio evita tener que reindexar.

La API key se carga desde `.env` (`OPENAI_API_KEY=sk-...`) y nunca se hardcodea en el código.

### 4.3 Colecciones en Chroma

| Colección | Documentos | Filtros de metadatos disponibles |
|---|---|---|
| `fichas_cr` | 76 | `via_tramitacion`, `categorias`, `grupo_numero`, `requiere_proyecto` |
| `preambulo` | 9 | `tipo`, `apartado`, `retrieval_condicional`, `inyectar_en_fichas` |
| `reglamento_ue` | 8 | `tipo`, `articulo`, `parte`, `categorias` |

### 4.4 Texto de embedding por tipo de documento

#### Fichas CR

El texto que se embeddea no es el texto plano de la ficha sino un **bloque enriquecido** que combina:

1. CR + descripción de la reforma
2. Grupo y descripción del grupo
3. Categorías de vehículos aplicables
4. Vía de tramitación y descripción
5. Documentación exigible (PT, CFO, IC, CT)
6. Inspección ITV específica
7. Información adicional
8. Keywords del cliente (tras enriquecimiento)
9. **Texto completo de interpretación de ARs** (inyectado siempre)

#### Preámbulo y reglamento

Se indexa el texto extraído directamente del PDF. Los metadatos controlan el retrieval condicional.

### 4.5 Metadatos para filtrado

Los metadatos de Chroma solo admiten tipos primitivos (`str`, `int`, `float`, `bool`). Las listas se convierten a string separado por comas:

```python
# En lugar de:
"categorias_aplicables": ["M1", "M2", "N1"]

# Se indexa como:
"categorias": "M1,M2,N1"
```

Esto permite filtrar en consulta por vía de tramitación, categoría de vehículo, o si requiere proyecto técnico.

---

## 5. Relaciones entre documentos

Los tres conjuntos de documentos no son independientes. Hay cuatro tipos de relación gestionadas en el pipeline:

| Relación | Documentos implicados | Solución |
|---|---|---|
| Interpretación de ARs | Fichas CR ← Preámbulo | Inyección en indexado: texto de `interpretacion_ars` incluido en cada ficha |
| Referencias cruzadas entre fichas | Ficha CR ↔ Ficha CR | Campo `crs_relacionados` en metadatos (regex sobre `informacion_adicional`) |
| Documentación exigible | Fichas CR ← Preámbulo (5.1-5.4) | Retrieval condicional según `via_tramitacion` de la ficha recuperada |
| Categorías de vehículos | Fichas CR ← Reglamento UE | Colección separada; el retriever la consulta cuando la query menciona M1, N1, etc. |

---

## 6. Scripts y flujo de trabajo

### Preparación inicial (una sola vez)

```bash
python parser_cr_seccion1.py       # → fichas_cr_seccion1.json
python parser_preambulo.py         # → preambulo_seccion1.json
python parser_reglamento_ue.py     # → reglamento_ue_2018_858.json

# El cliente rellena keywords_reformas.csv

python enriquecimiento.py          # → fichas_cr_seccion1.json (actualizado)
python indexado.py --reset         # → chroma_db/
```

### Actualización de keywords (recurrente)

```bash
# El cliente añade filas en keywords_reformas.csv
python enriquecimiento.py
python indexado.py --reset --solo fichas
```

### Verificación

```bash
python inspect_chroma.py                              # resumen de todas las colecciones
python inspect_chroma.py --col fichas_cr              # detalle de la colección
python inspect_chroma.py --col fichas_cr --id cr_2_1  # documento concreto
python indexado.py --test                             # queries de prueba
```

### Requisitos (`requirements.txt`)

| Paquete | Uso |
|---|---|
| `pdfplumber` | Extracción de texto y tablas de los PDFs |
| `chromadb` | Base vectorial local |
| `openai` | Embeddings (`text-embedding-3-small`) |
| `python-dotenv` | Carga de `OPENAI_API_KEY` desde `.env` |

---

## 7. Pendiente

- [ ] Chatbot RAG: lógica de retrieval + generación con Claude/GPT
- [ ] Workflow de redacción de proyecto técnico (n8n)
- [ ] Interfaz de usuario (Streamlit o similar)
- [ ] Dockerización: `docker-compose` con Chroma como servicio + app
- [ ] Secciones II, III y IV del Manual de Reformas
- [ ] Normativa externa completa (RD 866/2010, directivas referenciadas en ARs)
