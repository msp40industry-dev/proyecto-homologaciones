# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What this project does

Sistema de dos módulos para la tramitación de reformas de vehículos en España:

1. **Chatbot RAG** (`/backend`, `/frontend`): responde preguntas sobre el Manual de Reformas DGT (Sección I) y el Reglamento (UE) 2018/858, usando ChromaDB como base vectorial.
2. **Generador de Proyectos Técnicos Vía A** (`/proyecto_tecnico`): genera el proyecto técnico completo para una reforma a partir de los datos del ingeniero, con revisión humana por secciones y exportación a `.docx`.

---

## Commands

```bash
# Backend FastAPI (puerto 8000)
uvicorn backend.main:app --reload --port 8000

# Frontend Streamlit — hub con chatbot + generador (puerto 8501)
streamlit run frontend/app.py --server.port 8501

# Generador solo (sin hub, puerto 8502)
streamlit run proyecto_tecnico/frontend/proyecto_tecnico_app.py --server.port 8502

# Tests — todos (sin llamadas reales a APIs)
python -m pytest tests/ -v

# Tests — fichero concreto
python -m pytest tests/test_identificador_cr.py -v

# Docker (opción recomendada para despliegue)
docker compose up --build
```

### Preparación inicial de la base vectorial (una sola vez)

```bash
python scripts_parser/parser_cr_seccion1.py
python scripts_parser/parser_preambulo.py
python scripts_parser/parser_reglamento_ue.py
python scripts_enrich/enriquecimiento.py   # opcional
python scripts_index/indexado.py --reset   # crea scripts_index/chroma_db/

# Verificar
python scripts_index/inspect_chroma.py
```

### Actualizar keywords del cliente

```bash
# Editar scripts_enrich/keywords_reformas.csv, luego:
python scripts_enrich/enriquecimiento.py
python scripts_index/indexado.py --reset
```

### Construir el grafo KAG (una sola vez, o al actualizar el Manual)

```bash
python scripts_graph/build_graph.py              # procesa las 76 fichas
python scripts_graph/build_graph.py --cr 2.1 5.1 # solo estas CRs (debug)
python scripts_graph/build_graph.py --dry-run    # sin llamadas al LLM
```

`graph.json` **sí va a git** (a diferencia de `chroma_db/`). Cada nodo incluye `revision_fuente` para actualizaciones incrementales cuando salga una nueva versión del Manual.

---

## Architecture

### Grafo LangGraph (`proyecto_tecnico/graph.py`)

El corazón del generador. Estado: `EstadoProyecto` (TypedDict). Flujo:

```
identificador_cr
    ↓
[redactor_memoria | redactor_pliego | redactor_conclusiones]  ← paralelo
    ↓
revision_humana  ← interrupt_before (el ingeniero aprueba/rechaza por tabs)
    ↓ (si reescrituras → agente correspondiente; si todo aprobado → ensamblador)
ensamblador
    ↓
.docx
```

- El grafo se compila con `MemorySaver` como checkpointer; el `proyecto_id` actúa como `thread_id`.
- `interrupt_before=["revision_humana"]`: el grafo se pausa antes de este nodo; Streamlit lo reanuda con `graph.update_state(as_node="revision_humana")`.
- La función `enrutar_regeneracion()` mapea cada `id_seccion` al agente propietario (memoria / pliego / conclusiones).

### Agentes (`proyecto_tecnico/agents/`)

| Agente | Modelo | Responsabilidad |
|---|---|---|
| `identificador_cr.py` | `MODELO_RAZONAMIENTO` | Recupera fichas CR de ChromaDB (exacto por metadato si el ingeniero indica CRs, semántico si no). Usa `with_structured_output()` sobre el esquema `_RespuestaCRs` (Pydantic). Filtra ARs por categoría del vehículo. |
| `redactor_memoria.py` | `MODELO_REDACCION` | Secciones 0, 1.1, 1.2, 1.3.1, 1.4. Importante: 1.2 solo texto introductorio (las tablas de CRs/ARs las añade el ensamblador). 1.3.1 solo 1-2 frases (la ficha técnica la añade el ensamblador). |
| `redactor_pliego.py` | `MODELO_REDACCION` | Secciones 3.1, 3.2, 3.3, 3.4. |
| `redactor_conclusiones.py` | `MODELO_REDACCION` | Sección 8 con declaración de viabilidad, CRs, ARs para ITV y bloque de firma. |
| `ensamblador.py` | Node.js (`docx` npm) | Genera el `.docx` final. Escribe un script JS en `/tmp` y lo ejecuta con `subprocess`. Añade portada, TOC, tablas de CRs/ARs/ficha técnica, incrusta imágenes, muestra indicadores para PDFs/DWG. |

### Grafo KAG (`scripts_graph/`)

- `build_graph.py`: recorre las 76 fichas CR del JSON, extrae relaciones del campo `informacion_adicional` con LLM + `with_structured_output()`, y serializa a `graph.json`.
- `graph.json`: grafo completo. Estructura: `nodos` (dict por `CR-X.Y`) + `edges` (lista). Cada nodo incluye `revision_fuente`, `ars_por_categoria` (dict por categoría), `via`, `categorias_aplicables`.
- Tipos de edges: `implica_cr` | `obliga_incorporar` | `restriccion`. El campo `condicion` es texto libre que el LLM evalúa en tiempo de consulta contra los datos del vehículo.

### RAG (`backend/rag/`)

- `chain.py`: pipeline RAG completo. Temperatura 0.0 (dominio técnico-legal).
- `retriever.py`: recuperación condicional en ChromaDB. Decide si incluir chunks del preámbulo o del reglamento UE según la pregunta.
- ChromaDB en `scripts_index/chroma_db/`. Tres colecciones: `fichas_cr` (76 docs), `preambulo` (9 docs), `reglamento_ue` (8 docs).

### Modelos Pydantic (`proyecto_tecnico/models.py`)

Jerarquía de entrada: `EntradaProyecto` → `DatosVehiculo`, `Componente[]`, `Taller`, `Ingeniero`.  
Intermedios: `FichaCR`, `ARFiltrado`.  
Secciones: `SeccionGenerada` (contiene `EstadoRevision` con estados `pendiente` / `aprobado` / `reescribir`).

### Configuración de modelos

Toda la configuración de modelos vive en variables de entorno (`.env`), sin tocar código:

| Variable | Default |
|---|---|
| `MODELO_RAZONAMIENTO` | `gpt-4o` |
| `MODELO_REDACCION` | `gpt-4o-mini` |
| `MODELO_EMBEDDING` | `text-embedding-3-small` |

`proyecto_tecnico/config.py` y `backend/rag/config.py` leen estas variables.  
**Si se cambia `MODELO_EMBEDDING` hay que re-indexar ChromaDB completa** (`python scripts_index/indexado.py --reset`).

---

## Tests

126 tests unitarios en `tests/`. **Ninguno hace llamadas reales a OpenAI ni ChromaDB** — todo está mockeado.

`conftest.py` inyecta `OPENAI_API_KEY=sk-test-placeholder` para que `config.py` no lance `EnvironmentError` al importarse.

| Fichero | Qué cubre |
|---|---|
| `test_models.py` | Validación Pydantic de todos los modelos |
| `test_rag_chain.py` | Helpers de la cadena RAG |
| `test_rag_retriever.py` | Lógica del retriever condicional |
| `test_identificador_cr.py` | Helpers del identificador: deduplicación, extracción de campos |
| `test_ensamblador.py` | `_construir_payload`: estructura del JSON al script Node.js |
| `test_api.py` | Endpoints FastAPI con `TestClient` |
| `test_enriquecimiento.py` | `cargar_csv` y `enriquecer` con ficheros temporales |

---

## Key constraints

- El frontend del generador (`proyecto_tecnico_app.py`) llama al grafo **directamente** (sin HTTP), no a través del backend FastAPI. El backend FastAPI existe para integraciones externas.
- La ChromaDB **no se incluye en git** (`scripts_index/chroma_db/`). Hay que indexar antes de arrancar.
- El ensamblador requiere **Node.js 20 LTS** instalado en el sistema (`npm install` instala `docx`).
- Las secciones 1.3.2, 1.3.3, 2, 4, 5, 6 y 7 las completa el ingeniero manualmente o subiendo ficheros; el sistema inserta `[COMPLETAR POR EL INGENIERO]` en rojo si quedan vacías.
