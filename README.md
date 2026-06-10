# Sistema RAG — Reformas de Vehículos + Generador de Proyectos Técnicos

> Manual de Reformas DGT (Revisión 7.2 — Secciones I, II, III y IV) · Reglamento (UE) 2018/858
> RAG de consulta (220 fichas CR) + Generación automática de proyectos técnicos Vía A

---

## Índice

1. [Visión general](#1-visión-general)
2. [Arquitectura del sistema](#2-arquitectura-del-sistema)
3. [Módulo RAG — Parsers e indexación](#3-módulo-rag--parsers-e-indexación)
4. [Módulo Generador de Proyectos Técnicos](#4-módulo-generador-de-proyectos-técnicos)
5. [Flujo completo de generación](#5-flujo-completo-de-generación)
6. [API REST (FastAPI)](#6-api-rest-fastapi)
7. [Frontend Streamlit](#7-frontend-streamlit)
8. [Generación del documento Word](#8-generación-del-documento-word)
9. [Scripts y puesta en marcha](#9-scripts-y-puesta-en-marcha)
10. [Configuración de modelos](#10-configuración-de-modelos)
11. [Tests](#11-tests)
12. [Estructura del proyecto](#12-estructura-del-proyecto)
13. [Pendiente / Roadmap](#13-pendiente--roadmap)

---

## 1. Visión general

El sistema tiene dos módulos principales:

### 1.1 Chatbot RAG de consulta (`/frontend`, `/backend`)

Responde preguntas sobre el Manual de Reformas DGT (las cuatro secciones): qué documentación exige una reforma, qué categorías de vehículo aplican, qué Actos Reglamentarios hay que cumplir, qué vía de tramitación corresponde, etc.

- **Sección I** — Vehículos M, N, O (turismos, furgonetas, camiones, remolques) — 76 fichas
- **Sección II** — Vehículos L, Quads y UTV (motos, ciclomotores, triciclos) — 54 fichas
- **Sección III** — Vehículos agrícolas (tractores, maquinaria automotriz) — 45 fichas
- **Sección IV** — Vehículos de obras y/o servicios — 45 fichas

### 1.2 Generador de Proyectos Técnicos Vía A (`/proyecto_tecnico`)

Genera automáticamente el proyecto técnico completo para una reforma de vehículo (Vía A) a partir de los datos introducidos por el ingeniero. El sistema:

1. Identifica los CRs aplicables consultando la ChromaDB
2. Filtra los Actos Reglamentarios por categoría del vehículo
3. Redacta todas las secciones del proyecto técnico usando LLMs
4. Permite al ingeniero revisar, aprobar o solicitar reescritura de cada sección
5. Genera el documento Word final maquetado (portada, índice, tablas, cabecera/pie)

---

## 2. Arquitectura del sistema

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend Streamlit                    │
│         proyecto_tecnico/frontend/proyecto_tecnico_app.py│
└──────────────────────────┬──────────────────────────────┘
                           │ llama directamente al grafo
┌──────────────────────────▼──────────────────────────────┐
│              LangGraph (proyecto_tecnico/graph.py)        │
│                                                          │
│  identificador_cr ──► [redactor_memoria               ]  │
│                        [redactor_pliego    ] (paralelo)  │
│                        [redactor_conclusiones          ]  │
│                              │                           │
│                        revision_humana ◄── interrupt     │
│                              │                           │
│                         ensamblador                      │
│                              │                           │
│                          .docx                           │
└──────────────────────────┬──────────────────────────────┘
                           │ filtro seccion=I
┌──────────────────────────▼──────────────────────────────┐
│              ChromaDB (scripts_index/chroma_db/)         │
│  fichas_cr · 220 fichas (Sec. I: 76 · II: 54 · III+IV: 90)│
│  + graph.json · Grafo KAG · 220 nodos · 362 edges       │
└─────────────────────────────────────────────────────────┘
```

**Modelos usados (configurables vía `.env` — ver [sección 10](#10-configuración-de-modelos)):**

| Agente | Variable `.env` | Default | Rol |
|---|---|---|---|
| Identificador CR | `MODELO_RAZONAMIENTO` | `gpt-4o` | Análisis semántico + filtrado de ARs |
| Validador CRs | `MODELO_RAZONAMIENTO` | `gpt-4o` | Validación de vías + CRs adicionales |
| Redactor Memoria | `MODELO_REDACCION` | `gpt-4o-mini` | Secciones 0, 1.1, 1.2, 1.3.1, 1.4 |
| Redactor Pliego | `MODELO_REDACCION` | `gpt-4o-mini` | Secciones 3.1, 3.2, 3.3, 3.4 |
| Redactor Conclusiones | `MODELO_REDACCION` | `gpt-4o-mini` | Sección 8 |
| Ensamblador | — | Node.js (`docx`) | Documento Word final |
| Embeddings | `MODELO_EMBEDDING` | `text-embedding-3-small` | Indexación y búsqueda semántica |

---

## 3. Módulo RAG — Parsers e indexación

### 3.1 Documentos parseados

| Documento | Fuente | Output JSON | Chunks / Fichas |
|---|---|---|---|
| Fichas CR — Sección I (M, N, O) | Manual Rev. 7.2 págs. 18–212 | `fichas_cr_seccion1_v3.json` | 76 fichas |
| Fichas CR — Secciones II, III, IV | Manual Rev. 7.2 págs. 218–828 | `fichas_cr_secciones_ii_iii_iv.json` | 144 fichas |
| Preámbulo | Manual Rev. 7.2 págs. 3–12 | `preambulo_seccion1.json` | 9 chunks |
| Reglamento (UE) 2018/858 | DOUE L 151, 14.6.2018 | `reglamento_ue_2018_858.json` | 8 chunks |

### 3.2 Parsers

- **`scripts_parser/parser_cr_seccion1.py`** — Extrae las 76 fichas de Sección I (M, N, O) con `pdfplumber`. Arquitectura híbrida: `extract_tables()` para tablas de campo de aplicación y ARs (12 columnas), `extract_text()` para campos de texto libre.
- **`scripts_parser/parser_cr_secciones_ii_iii_iv.py`** — Extrae las 144 fichas de Secciones II (11 cols: Quad/L1e–L7e), III y IV (15 cols: T1–MAR). Reutiliza la misma lógica de texto; la extracción de tablas de ARs es flexible por número de columnas.
- **`scripts_parser/parser_preambulo_updated.py`** — 9 chunks semánticos del nuevo PDF. El chunk `interpretacion_ars` se inyecta en el texto de embedding de cada ficha CR.
- **`scripts_parser/parser_reglamento_ue.py`** — Artículos 3 y 4 + Anexo I del Reglamento (UE) 2018/858. Normaliza subíndices (M₁→M1) extraídos en líneas separadas.

### 3.3 Vías de tramitación

| Vía | Condición | Documentación exigible |
|---|---|---|
| **A** | Proyecto Técnico = SI | PT + CFO + IC + CT |
| **B** | PT = NO, IC = SI | IC + CT |
| **C** | Solo CT | Certificado de Taller |
| **D** | Solo doc. adicional | Documentación específica |

### 3.4 Indexación — ChromaDB

**Embeddings:** `text-embedding-3-small` (OpenAI). Mismo modelo en indexación y consulta.

| Colección | Docs / Chunks | Cuándo se consulta | Metadatos clave |
|---|---|---|---|
| `fichas_cr` | 220 fichas | Siempre | `via_tramitacion`, `seccion`, `cr`, `categorias` |
| `preambulo` | 9 chunks | Si menciona documentación / tramitación | `apartado`, `retrieval_condicional` |
| `reglamento_ue` | 8 chunks | Si menciona categorías de vehículo | `articulo`, `categorias` |
| `directivas_ar` | 3 442 chunks (103 normativas) | Si la query contiene una referencia AR (`71/320/CEE`, `R(UE)...`) o palabras como "directiva", "qué establece", "derogada" | `referencia`, `celex`, `derogada`, `secciones` |

IDs de fichas_cr: `cr_{seccion}_{cr}` (ej. `cr_I_5_1`) para evitar colisiones entre secciones. El generador siempre filtra `seccion="I"`.

Las directivas derogadas se recuperan normalmente pero el LLM está instruido para advertirlo de forma explícita antes de dar cualquier información.

El texto de embedding de cada ficha CR incluye: descripción, categorías, vía, documentación, keywords del cliente e **interpretación de ARs inyectada**.

### 3.5 Enriquecimiento de keywords

```bash
# El cliente añade términos reales de taller en:
scripts_enrich/keywords_reformas.csv

# Aplicar enriquecimiento:
python scripts_enrich/enriquecimiento.py
python scripts_index/indexado.py --reset
```

---

## 4. Módulo Generador de Proyectos Técnicos

### 4.1 Secciones generadas automáticamente

| Sección | ID interno | Agente |
|---|---|---|
| 0. Peticionario | `peticionario` | Redactor Memoria |
| 1.1 Objeto | `objeto` | Redactor Memoria |
| 1.2 Antecedentes | `antecedentes` | Redactor Memoria |
| 1.3.1 Identificación del vehículo | `identificacion_vehiculo` | Redactor Memoria |
| 1.4 Descripción de la reforma | `descripcion_reforma` | Redactor Memoria |
| 3.1 Calidad de materiales | `calidad_materiales` | Redactor Pliego |
| 3.2 Normas de ejecución | `normas_ejecucion` | Redactor Pliego |
| 3.3 Certificados y autorizaciones | `certificados` | Redactor Pliego |
| 3.4 Taller ejecutor | `taller_ejecutor` | Redactor Pliego |
| 8. Conclusiones | `conclusiones` | Redactor Conclusiones |

### 4.2 Secciones completadas por el ingeniero (con uploader)

| Sección | Marcador en el Word |
|---|---|
| 1.3.2 Características antes de la reforma | Caja de texto editable en revisión; si se deja vacía → `[COMPLETAR]` en rojo |
| 1.3.3 Características después de la reforma | Caja de texto editable en revisión; si se deja vacía → `[COMPLETAR]` en rojo |
| 2. Cálculos justificativos | Fichero adjunto o `[COMPLETAR]` |
| 4. Presupuesto | Fichero adjunto o `[COMPLETAR]` |
| 5. Planos | Fichero adjunto o `[COMPLETAR]` |
| 6. Reportaje fotográfico | Imagen incrustada o `[COMPLETAR]` |
| 7. Documentación del vehículo | Fichero adjunto o `[COMPLETAR]` |

### 4.3 Agentes

#### `identificador_cr.py` (Agente 1 — `MODELO_RAZONAMIENTO`)

- Si el ingeniero indica CRs → recuperación exacta por metadato `cr` en ChromaDB (sin búsqueda semántica)
- Si no indica CRs → búsqueda semántica en ChromaDB sobre la descripción de la reforma
- Filtra los ARs de cada ficha CR por la categoría del vehículo
- Detecta CRs adicionales mencionados en `informacion_adicional`
- Usa **tool calling** (`with_structured_output`) para obtener la respuesta del LLM como objeto Pydantic validado, sin parsing manual de JSON

#### `redactor_memoria.py` (Agente 2 — `MODELO_REDACCION`)

Genera las secciones 0, 1.1, 1.2, 1.3.1 y 1.4 en paralelo. Los prompts instruyen al LLM a:
- **1.2 Antecedentes**: solo texto en párrafos (sin tablas markdown). Las tablas de CRs y ARs las añade el ensamblador.
- **1.3.1 Identificación del vehículo**: solo 1-2 frases introductorias. La ficha técnica la añade el ensamblador como tabla Word.

#### `redactor_pliego.py` (Agente 3 — `MODELO_REDACCION`)

Genera las secciones 3.1, 3.2, 3.3 y 3.4 del Pliego de Condiciones.

#### `redactor_conclusiones.py` (Agente 4 — `MODELO_REDACCION`)

Genera la sección 8 (Conclusiones) con declaración de viabilidad técnica, CRs aplicables, ARs a verificar en ITV y bloque de firma del ingeniero.

#### `ensamblador.py` (Agente 5 — Node.js)

Genera el `.docx` final. Funcionalidades especiales:
- **Sección 1.2**: añade tabla Word de CRs + tabla Word de ARs tras el texto introductorio
- **Sección 1.3.1**: añade tabla Word con todos los datos del vehículo (Marca, Modelo, VIN, Matrícula, Categoría, Fecha de matriculación, Color, Kilometraje)
- **Secciones del ingeniero**: incrusta imágenes (JPG/PNG) directamente en el documento; para PDFs/DWG muestra indicador `📎 Adjunto: nombre.pdf`

### 4.4 Validador de CRs (`validador_crs.py`)

Endpoint previo a la generación que:
1. Recupera cada CR indicado por búsqueda exacta en ChromaDB
2. Clasifica en Vía A (incluir) y otras vías (excluir)
3. Analiza `informacion_adicional` con el LLM para detectar CRs adicionales vía A
4. Si ningún CR es Vía A → devuelve `valido=False` bloqueando la generación

---

## 5. Flujo completo de generación

```
Ingeniero rellena formulario (datos vehículo, reforma, taller, ingeniero)
        │
        ▼
[Opcional] Validar CRs → resumen de CRs incluidos/excluidos/adicionales
        │
        ▼
Generar proyecto técnico
        │
        ▼
Agente 1: Identificador CR
  - Recupera fichas CR de ChromaDB (exacto o semántico)
  - Filtra ARs por categoría del vehículo
        │
        ▼
Agentes 2, 3, 4 en paralelo:
  - Redactor Memoria   → secciones 0, 1.1, 1.2, 1.3.1, 1.4
  - Redactor Pliego    → secciones 3.1, 3.2, 3.3, 3.4
  - Redactor Conclusiones → sección 8
        │
        ▼
interrupt_before("revision_humana")
  → Frontend muestra secciones al ingeniero (tabs)
  → El ingeniero puede: Aprobar | Solicitar reescritura (con motivo)
        │
        ├─ Si hay reescrituras → agentes correspondientes regeneran
        │  (solo las secciones marcadas, con contexto del motivo)
        │
        ▼
Ingeniero sube ficheros (cálculos, presupuesto, planos, fotos, documentación)
        │
        ▼
Generar documento Word
  → Ensamblador Node.js construye el .docx
  → Portada + Índice automático + Secciones + Tablas + Imágenes
        │
        ▼
Descarga del .docx
```

### 5.1 Lógica de reescritura

Cuando el ingeniero solicita reescritura de una sección:
- El grafo reanuda desde `revision_humana` vía `update_state(as_node="revision_humana")`
- `enrutar_regeneracion()` determina qué agente debe regenerar según la sección:
  - Secciones 0, 1.x → `redactor_memoria`
  - Secciones 3.x → `redactor_pliego`
  - Sección 8 → `redactor_conclusiones`
- El agente recibe el motivo de la reescritura y la versión anterior como contexto
- Solo se regeneran las secciones marcadas, el resto se conserva

---

## 6. API REST (FastAPI)

Servidor en `http://localhost:8000`. Router montado en `/proyecto-tecnico`.

| Método | Endpoint | Descripción |
|---|---|---|
| `POST` | `/proyecto-tecnico/validar-crs` | Valida CRs antes de generar |
| `POST` | `/proyecto-tecnico/generar` | Inicia generación del proyecto |
| `POST` | `/proyecto-tecnico/{id}/revisar` | Registra aprobación o reescritura |
| `POST` | `/proyecto-tecnico/{id}/adjunto` | Sube fichero a una sección |
| `POST` | `/proyecto-tecnico/{id}/documento` | Genera el Word final |
| `GET`  | `/proyecto-tecnico/{id}/descargar` | Descarga el .docx generado |

```bash
# Arrancar backend
uvicorn backend.main:app --reload --port 8000
```

---

## 7. Frontend Streamlit

Interfaz de 4 pasos en `proyecto_tecnico/frontend/proyecto_tecnico_app.py`.

```bash
streamlit run proyecto_tecnico/frontend/proyecto_tecnico_app.py --server.port 8502
```

**Paso 1 — Formulario de entrada**
- Datos del vehículo (marca, modelo, VIN, matrícula, categoría, color, km)
- Datos del ingeniero (nombre, titulación, colegio, nº colegiado)
- Datos del taller ejecutor
- Descripción libre de la reforma
- CRs identificados (opcional; si se indican, se validan antes de generar)
- Componentes instalados (con marca, modelo, referencia, nº homologación)

**Paso 2 — Generación**
- Barra de progreso con estado en tiempo real
- El grafo LangGraph se ejecuta directamente (sin HTTP)

**Paso 3 — Revisión**
- Tab por sección con el texto generado
- Botones: Aprobar / Solicitar reescritura (con campo de motivo)
- Uploader de ficheros para secciones del ingeniero (2, 4, 5, 6, 7)
- Botón "Aprobar todas las pendientes" para agilizar
- Botón "Regenerar secciones marcadas" lanza solo los agentes necesarios

**Paso 4 — Descarga**
- Descarga del `.docx` generado

---

## 8. Generación del documento Word

El ensamblador escribe un script Node.js en `/tmp` y lo ejecuta con `subprocess`. La librería `docx` (npm) genera el `.docx`.

### 8.1 Estructura del documento

1. **Portada** (sin cabecera/pie): título, datos del vehículo, CRs, ingeniero, expediente, fecha
2. **Índice automático** (TOC con hipervínculos)
3. **Secciones del proyecto** con cabecera (vehículo + bastidor) y pie (ingeniero + nº página)

### 8.2 Tablas generadas automáticamente

| Tabla | Sección | Contenido |
|---|---|---|
| Tabla de CRs | 1.2 Antecedentes | Código · Denominación · Vía |
| Tabla de ARs | 1.2 Antecedentes | Sistema · Referencia · Nivel · Descripción |
| Ficha técnica del vehículo | 1.3.1 Identificación | Marca, Modelo, VIN, Matrícula, Categoría, Fecha, Color, Km |

### 8.3 Adjuntos incrustados

- **Imágenes** (JPG, JPEG, PNG): se incrustan inline en el documento Word con `ImageRun` (500×350 px)
- **Otros formatos** (PDF, DWG, XLSX): se muestra indicador `📎 Adjunto: nombre_fichero`
- **Sin adjunto**: marcador `[COMPLETAR POR EL INGENIERO]` en rojo con borde discontinuo

### 8.4 Payload al script JS

```json
{
  "proyecto_id": "...",
  "metadata": {
    "vehiculo": "VW Golf",
    "bastidor": "WVWZZZ...",
    "matricula": "1234 ABC",
    "categoria": "M1",
    "fecha_matriculacion": "15/03/2018",
    "color": "Blanco",
    "kilometraje": "85.000 km",
    "ingeniero": "Juan García",
    ...
  },
  "crs": [{"codigo": "2.1", "denominacion": "...", "via": "A"}],
  "ars": [{"sistema": "...", "referencia": "...", "nivel": "(1)", "descripcion": "..."}],
  "secciones": [{"id": "peticionario", "titulo": "0. Peticionario", "contenido": "..."}],
  "adjuntos": {
    "calculos": {"nombre": "calculos.pdf", "path": "/tmp/xxx.pdf", "es_imagen": false},
    "fotografias": {"nombre": "coche.jpg", "path": "/tmp/yyy.jpg", "es_imagen": true}
  }
}
```

---

## 9. Puesta en marcha

### 9.0 Prerrequisito: variables de entorno

Copia el fichero de ejemplo y rellena tu clave de OpenAI:

```bash
cp .env.example .env
```

Edita `.env` y añade al menos:

```
OPENAI_API_KEY=sk-...
```

Las variables de LangSmith son opcionales. Si no las necesitas, deja `LANGCHAIN_TRACING_V2=false` y el resto vacío.

Los modelos tienen defaults seguros y **no es necesario definirlos** para que el sistema funcione. Solo añádelos si quieres cambiar el modelo por defecto (ver [sección 10](#10-configuración-de-modelos)).

---

### 9.1 Preparación inicial de la base vectorial (una sola vez)

La ChromaDB debe indexarse antes de arrancar el sistema, independientemente de si se usa Docker o entorno local.

```bash
# 1. Parsear fichas CR de todas las secciones
python scripts_parser/parser_cr_seccion1.py              # Sección I — 76 fichas
python scripts_parser/parser_cr_secciones_ii_iii_iv.py  # Secciones II, III y IV — 144 fichas
python scripts_parser/parser_preambulo_updated.py        # Preámbulo (Rev. 7.2)
python scripts_parser/parser_reglamento_ue.py            # Reglamento (UE) 2018/858

# 2. Enriquecer con keywords del cliente (opcional)
python scripts_enrich/enriquecimiento.py
python scripts_enrich/enriquecimiento.py \
  --fichas json/fichas_cr_secciones_ii_iii_iv.json \
  --output json/fichas_cr_secciones_ii_iii_iv.json

# 3. Indexar en ChromaDB — 220 fichas en total
python scripts_index/indexado.py --reset

# 4. Construir el grafo KAG — genera graph.json y json/normativas_ar.json
python scripts_graph/build_graph.py

# 5. Descargar normativas AR desde EUR-Lex e indexarlas (opcional pero recomendado)
python scripts_parser/parser_directivas_ar.py        # descarga 103 normativas (~6 min)
python scripts_index/indexado.py --solo directivas   # indexa 3 442 chunks en ChromaDB
```

Verificación:

```bash
python scripts_index/inspect_chroma.py               # resumen de colecciones
python scripts_index/inspect_chroma.py --col fichas_cr  # detalle colección
```

---

### 9.2 Opción A — Docker (recomendado para ejecutar en cualquier máquina)

**Requisitos:** Docker Desktop instalado y corriendo.

```bash
# 1. Asegúrate de tener el .env y la chroma_db indexada (ver 9.0 y 9.1)

# 2. Construir y arrancar los contenedores
docker compose up --build

# Para arrancar en segundo plano
docker compose up --build -d

# Para parar
docker compose down
```

Una vez arrancado:
- Frontend: [http://localhost:8501](http://localhost:8501)
- Backend (API): [http://localhost:8000](http://localhost:8000)
- Documentación API: [http://localhost:8000/docs](http://localhost:8000/docs)

Los documentos Word generados se guardan en `outputs/proyectos/` en el host.

---

### 9.3 Opción B — Entorno virtual local (desarrollo)

**Requisitos:** Python 3.11, Node.js 20 LTS.

```bash
# 1. Crear el entorno virtual
python3.11 -m venv hm_venv

# 2. Activarlo
source hm_venv/bin/activate          # macOS / Linux
# hm_venv\Scripts\activate           # Windows

# 3. Instalar dependencias Python
pip install -r requirements.txt

# 4. Instalar dependencia Node.js para el ensamblador
npm install

# 5. Asegúrate de tener el .env y la chroma_db indexada (ver 9.0 y 9.1)

# 6. Arrancar
# Terminal 1 — Backend FastAPI
uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Frontend (hub con chatbot + generador)
streamlit run frontend/app.py --server.port 8501
```

---

### 9.4 Actualización de keywords (recurrente)

```bash
# Añadir filas en scripts_enrich/keywords_reformas.csv, luego:
python scripts_enrich/enriquecimiento.py
python scripts_enrich/enriquecimiento.py \
  --fichas json/fichas_cr_secciones_ii_iii_iv.json \
  --output json/fichas_cr_secciones_ii_iii_iv.json
python scripts_index/indexado.py --reset
```

---

## 10. Configuración de modelos

Los modelos de cada agente son configurables mediante variables de entorno sin necesidad de modificar código. La configuración vive en `proyecto_tecnico/config.py` (generador) y `backend/rag/config.py` (RAG).

### 10.1 Variables disponibles

| Variable | Default | Afecta a |
|---|---|---|
| `MODELO_RAZONAMIENTO` | `gpt-4o` | Identificador CR, Validador CRs |
| `MODELO_REDACCION` | `gpt-4o-mini` | Redactor Memoria, Pliego, Conclusiones, RAG chain |
| `MODELO_EMBEDDING` | `text-embedding-3-small` | ChromaDB (indexación y búsqueda) |

### 10.2 Cómo actualizar a un nuevo modelo

```bash
# En .env, añadir o modificar:
MODELO_RAZONAMIENTO=gpt-4.1
MODELO_REDACCION=gpt-4o-mini-2025-04-14
```

Reiniciar el backend y el frontend. No hace falta tocar ningún fichero de código.

> **⚠️ Cambio de `MODELO_EMBEDDING`:** si se cambia el modelo de embeddings hay que re-indexar la ChromaDB completa, ya que los vectores almacenados son incompatibles con un modelo diferente:
> ```bash
> python scripts_index/indexado.py --reset
> ```

### 10.3 Salidas estructuradas (tool calling)

El `identificador_cr.py` usa `ChatOpenAI.with_structured_output()` para obtener la respuesta del LLM directamente como un objeto Pydantic validado, en lugar de parsear JSON manualmente. El esquema de salida está definido en `_RespuestaCRs`:

```python
class _RespuestaCRs(BaseModel):
    crs_identificados: list[_CRIdentificado]
    crs_adicionales_detectados: list[_CRAdicional]
```

Esto elimina el riesgo de JSON malformado y aprovecha la API de function calling de OpenAI, que garantiza la estructura de la respuesta.

---

## 11. Tests

Suite de tests unitarios en `tests/`. No requieren conexión a OpenAI ni a ChromaDB — toda dependencia externa está mockeada.

```bash
# Ejecutar todos los tests
python -m pytest tests/ -v

# Ejecutar un fichero concreto
python -m pytest tests/test_rag_chain.py -v
```

### 11.1 Ficheros de test

| Fichero | Qué prueba | Tests |
|---|---|---|
| `test_models.py` | Validación de modelos Pydantic (DatosVehiculo, FichaCR, ARFiltrado…) | 16 |
| `test_rag_chain.py` | Helpers de la cadena RAG: filtrado ARs, formateo fichas, contexto, fuentes | 17 |
| `test_rag_retriever.py` | Lógica del retriever: `_necesita_preambulo`, `_necesita_reglamento`, `_filtro_fichas` | 25 |
| `test_identificador_cr.py` | Helpers del identificador: `_deduplicar_docs`, extracción de campos de fichas | 19 |
| `test_ensamblador.py` | `_construir_payload`: estructura y contenido del payload al script Node.js | 11 |
| `test_api.py` | Endpoints FastAPI con `TestClient` y mocks | 18 |
| `test_enriquecimiento.py` | `cargar_csv` y `enriquecer` con ficheros temporales (`tmp_path`) | 16 |

**Total: 128 tests · 0 llamadas reales a APIs externas**

---

## 12. Estructura del proyecto

```
Proyecto_homologaciones/
├── .env                          # OPENAI_API_KEY + modelos (no subir a git)
├── .env.example                  # Plantilla de variables de entorno
├── requirements.txt
├── package.json                  # Dependencia Node.js: docx
│
├── scripts_parser/               # Parsers de PDFs y descarga de normativa EU
│   ├── parser_cr_seccion1.py              # Sección I (M, N, O) — 76 fichas
│   ├── parser_cr_secciones_ii_iii_iv.py   # Secciones II, III, IV — 144 fichas
│   ├── parser_preambulo_updated.py        # Preámbulo (Rev. 7.2)
│   ├── parser_reglamento_ue.py
│   └── parser_directivas_ar.py            # Descarga 103 normativas desde EUR-Lex CELLAR
│
├── scripts_enrich/               # Enriquecimiento de keywords
│   ├── enriquecimiento.py
│   └── keywords_reformas.csv
│
├── scripts_index/                # Indexación ChromaDB
│   ├── indexado.py               # Indexa fichas de todas las secciones (220 docs)
│   ├── inspect_chroma.py
│   └── chroma_db/                # Base vectorial (no subir a git)
│
├── scripts_graph/                # Grafo KAG
│   ├── build_graph.py            # Construye graph.json (220 nodos, 4 secciones)
│   ├── graph.json                # Grafo serializado — sí va a git
│   ├── inspect_graph.py          # Inspección CLI: --cr [SEC:]X.Y --seccion
│   └── visualize_graph.py        # Visualización HTML interactiva
│
├── json/                         # JSONs parseados
│   ├── fichas_cr_seccion1_v3.json          # Sección I — 76 fichas
│   ├── fichas_cr_secciones_ii_iii_iv.json  # Secciones II, III, IV — 144 fichas
│   ├── preambulo_seccion1.json
│   ├── reglamento_ue_2018_858.json
│   ├── normativas_ar.json                  # 134 referencias normativas únicas del grafo
│   └── directivas_ar.json                  # 103 normativas descargadas de EUR-Lex
│
├── backend/                      # FastAPI + RAG chain
│   ├── main.py
│   └── rag/
│       ├── config.py             # Variables de entorno y paths (modelos configurables)
│       ├── chain.py              # Pipeline RAG completo + KAG + directivas AR
│       ├── retriever.py          # Retrieval condicional: fichas, preámbulo, reglamento, directivas
│       └── graph_retriever.py    # Traversal del grafo KAG (param seccion)
│
├── frontend/                     # Hub Streamlit (menú central)
│   └── app.py
│
├── proyecto_tecnico/             # Generador de Proyectos Técnicos
│   ├── config.py                 # Roles de modelos (MODELO_RAZONAMIENTO, etc.)
│   ├── models.py                 # Esquemas Pydantic
│   ├── graph.py                  # Grafo LangGraph
│   ├── validador_crs.py          # Validación previa de CRs
│   ├── router_proyecto_tecnico.py # Endpoints FastAPI
│   │
│   ├── agents/
│   │   ├── identificador_cr.py   # Agente 1: gpt-4o + tool calling
│   │   ├── redactor_memoria.py   # Agente 2: secciones 0, 1.x
│   │   ├── redactor_pliego.py    # Agente 3: secciones 3.x
│   │   ├── redactor_conclusiones.py # Agente 4: sección 8
│   │   └── ensamblador.py        # Agente 5: genera .docx vía Node.js
│   │
│   └── frontend/
│       └── proyecto_tecnico_app.py
│
├── tests/                        # Suite de tests unitarios (126 tests)
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_rag_chain.py
│   ├── test_rag_retriever.py
│   ├── test_identificador_cr.py
│   ├── test_ensamblador.py
│   ├── test_api.py
│   └── test_enriquecimiento.py
│
├── docs/
│   └── TFM_Memoria.md            # Memoria del Trabajo Fin de Máster
│
└── outputs/
    └── proyectos/                # .docx generados (no subir a git)
```

---

## 13. Pendiente / Roadmap

### Normativa AR

- [ ] **Verificar cobertura completa de normativas**: comprobar que las 103 directivas/reglamentos descargados de EUR-Lex son accesibles y que no faltan referencias (algunas normativas antiguas pueden no estar disponibles en CELLAR en formato HTML/XHTML)
- [ ] **Resolver normativas derogadas y no encontradas**: para las normativas marcadas como derogadas, identificar y descargar la vigente que las sustituye (campo `sustituida_por` de CELLAR SPARQL); para las no encontradas, buscar fuentes alternativas (EUR-Lex web, UNECE) e indexarlas

### Generador de Proyectos Técnicos

- [ ] **Corregir formatos de salida**: revisar y ajustar el maquetado del `.docx` generado (estilos de párrafo, márgenes, cabeceras, numeración de secciones) para que se ajuste al formato exigido por los colegios de ingenieros
- [ ] **Plantillas propias del cliente**: permitir que cada cliente aporte su propia plantilla Word (`.dotx`) con logo, fuentes y estilos corporativos; el ensamblador la usaría como base en lugar de la plantilla genérica
- [ ] Incrustación de PDFs en el Word (requiere conversión a imagen o adjunto como objeto OLE)
- [ ] Soporte para reformas Vía B (Informe de Conformidad) y Vía C (Certificado de Taller)
- [ ] Cálculo automático de sección 1.3.2 y 1.3.3 (características antes/después)
- [ ] Exportación a PDF además de Word

### Plataforma

- [ ] **Estudiar modelo de negocio**: definir la propuesta de valor, segmentos de cliente (ingeniero autónomo, taller, ITV, gestoría), precios y forma de monetización (suscripción, créditos por documento, licencia corporativa)
- [ ] **Estudiar formas de implementación**: evaluar despliegue en nube (AWS/GCP/Azure), en local (Docker on-premise), como SaaS web o como aplicación de escritorio; considerar costes, privacidad de datos y requisitos del cliente
- [ ] **Cambiar/evaluar modelos LLM**: comparar GPT-4o vs Claude vs Gemini en calidad de proyectos técnicos generados y coste por documento; evaluar modelos open-source (Llama, Mistral) con Ollama para eliminar dependencia de APIs externas
- [ ] **Testear vulnerabilidades**: auditoría de seguridad de la API FastAPI (inyección de prompts, autenticación de endpoints, exposición de datos sensibles, validación de ficheros subidos)
- [ ] **Volver a enlazar con LangSmith**: reconfigurar `LANGCHAIN_TRACING_V2=true` y revisar trazas de los agentes para detectar latencias, tokens consumidos y respuestas incorrectas
- [ ] **Pedir revisión a un experto en reformas de vehículos**: validar con un ingeniero o técnico de ITV que las fichas CR, ARs y el contenido de los proyectos técnicos generados son correctos y cumplen la normativa vigente
- [ ] Evaluación automática con RAGAS (faithfulness, answer relevancy, context precision)
- [ ] Modelos locales con Ollama (eliminar dependencia de la API de OpenAI)
- [ ] Multitenancy: namespacing por cliente en ChromaDB o migración a Qdrant
- [ ] Autenticación y billing (Supabase o Clerk)

### Completado

- [x] Secciones II, III y IV del Manual de Reformas (144 fichas indexadas en ChromaDB + grafo KAG)
- [x] Normativa AR indexada: 103 directivas/reglamentos EU descargados de EUR-Lex CELLAR (3 442 chunks)
- [x] Grafo KAG con relaciones entre CRs: 220 nodos, 362 edges, 4 secciones
- [x] Dockerización: `docker-compose` con backend y frontend
- [x] Tests automatizados: 128 tests unitarios sin dependencias externas
- [x] Configuración dinámica de modelos vía variables de entorno
- [x] Tool calling (structured outputs) en el Identificador CR
