# Sistema RAG y Generador Automático de Proyectos Técnicos para Reformas de Vehículos

## Trabajo Fin de Máster

**Máster en Inteligencia Artificial Aplicada**

---

**Autor:** [Nombre del autor]
**Tutor:** [Nombre del tutor]
**Fecha:** Marzo 2026
**Centro:** [Nombre del centro]

---

## Índice

1. [Introducción](#1-introducción)
   - 1.1. [Contexto y motivación](#11-contexto-y-motivación)
   - 1.2. [Objetivos](#12-objetivos)
   - 1.3. [Alcance de la solución](#13-alcance-de-la-solución)

2. [Estado del arte y fundamentos teóricos](#2-estado-del-arte-y-fundamentos-teóricos)
   - 2.1. [Modelos de lenguaje y arquitectura Transformer](#21-modelos-de-lenguaje-y-arquitectura-transformer)
   - 2.2. [Técnicas de adaptación: RAG, prompting y orquestación de agentes](#22-técnicas-de-adaptación-rag-prompting-y-orquestación-de-agentes)
   - 2.3. [Consideraciones éticas y legales](#23-consideraciones-éticas-y-legales)

3. [Requisitos y diseño de la solución](#3-requisitos-y-diseño-de-la-solución)
   - 3.1. [Requisitos funcionales y no funcionales](#31-requisitos-funcionales-y-no-funcionales)
   - 3.2. [Arquitectura de la aplicación](#32-arquitectura-de-la-aplicación)
   - 3.3. [Selección tecnológica](#33-selección-tecnológica)
   - 3.4. [Diseño de datos y pipelines](#34-diseño-de-datos-y-pipelines)

4. [Implementación](#4-implementación)
   - 4.1. [Estructura del código y componentes](#41-estructura-del-código-y-componentes)
   - 4.2. [Integración con modelos (OpenAI API)](#42-integración-con-modelos-openai-api)
   - 4.3. [Gestión de prompts y orquestación de agentes](#43-gestión-de-prompts-y-orquestación-de-agentes)
   - 4.4. [Mecanismos de seguridad y trazabilidad](#44-mecanismos-de-seguridad-y-trazabilidad)
   - 4.5. [Despliegue e infraestructura](#45-despliegue-e-infraestructura)

5. [Evaluación y experimentos](#5-evaluación-y-experimentos)
   - 5.1. [Métricas](#51-métricas)
   - 5.2. [Resultados](#52-resultados)
   - 5.3. [Análisis de errores y limitaciones](#53-análisis-de-errores-y-limitaciones)

6. [Pruebas y validación](#6-pruebas-y-validación)
   - 6.1. [Tests funcionales y validación con usuario](#61-tests-funcionales-y-validación-con-usuario)
   - 6.2. [Usabilidad](#62-usabilidad)
   - 6.3. [Observabilidad](#63-observabilidad)

7. [Discusión](#7-discusión)
   - 7.1. [Lecciones aprendidas](#71-lecciones-aprendidas)
   - 7.2. [Riesgos, ética y mitigaciones](#72-riesgos-ética-y-mitigaciones)

8. [Conclusiones y trabajo futuro](#8-conclusiones-y-trabajo-futuro)

9. [Bibliografía](#9-bibliografía)

10. [Anexos](#10-anexos)
    - 10.1. [Guía de despliegue y manual de usuario](#101-guía-de-despliegue-y-manual-de-usuario)
    - 10.2. [Detalles técnicos: prompts, esquemas, configuraciones](#102-detalles-técnicos-prompts-esquemas-configuraciones)

---

## 1. Introducción

### 1.1. Contexto y motivación

La tramitación de reformas de vehículos en España está regulada por el Manual de Reformas de Vehículos de la Dirección General de Tráfico (DGT), un documento técnico que clasifica 76 tipos de modificaciones distintas —denominadas Fichas CR (Código de Reforma)— y define para cada una la vía de tramitación aplicable, la documentación exigible, las categorías de vehículo a las que afecta y los Actos Reglamentarios (ARs) que deben cumplirse.

De las cuatro vías de tramitación existentes (A, B, C y D), la Vía A es la que implica mayor carga documental: exige la elaboración de un Proyecto Técnico completo firmado por un ingeniero colegiado. Este tipo de documento incluye memoria técnica, pliego de condiciones, cálculos justificativos, planos, presupuesto, fotografías y conclusiones. En la práctica, un proyecto de este tipo ocupa entre 30 y 60 páginas y su redacción manual requiere entre 4 y 8 horas de trabajo de un profesional técnico, que además debe consultar la normativa aplicable para cada caso concreto.

El problema no es solo de volumen de trabajo: también hay variabilidad en la calidad y completitud de los documentos generados. Cada ingeniero tiene sus propias plantillas, criterios de redacción y nivel de detalle. La consulta de las fichas CR correspondientes a cada reforma, la identificación de los ARs aplicables según la categoría del vehículo, y la estructuración correcta del documento son tareas que se repiten en cada proyecto y que no aportan valor intelectual diferencial: son trabajo de compilación normativa.

Este proyecto nace de una necesidad concreta observada en el entorno profesional: reducir el tiempo de elaboración de proyectos técnicos de reforma Vía A mediante automatización asistida, sin eliminar la revisión y firma del ingeniero responsable. El enfoque no es sustituir al profesional, sino quitarle la carga de las partes más mecánicas y repetitivas del documento.

Para abordar este objetivo, se han desarrollado dos módulos complementarios: un chatbot de consulta del Manual de Reformas basado en recuperación semántica (RAG), y un generador automático de proyectos técnicos Vía A basado en orquestación de agentes con LangGraph. Ambos módulos se apoyan en la API de OpenAI para las operaciones de generación de texto e incrustaciones vectoriales.

### 1.2. Objetivos

Los objetivos del proyecto son los siguientes:

**Objetivo principal:** desarrollar un sistema que permita generar automáticamente el borrador de un Proyecto Técnico de reforma de vehículo Vía A a partir de los datos de entrada del vehículo y las reformas solicitadas, con revisión humana integrada en el proceso.

**Objetivos secundarios:**

1. Construir una base de conocimiento indexada a partir del Manual de Reformas de la DGT (Sección I, 76 fichas CR) y del Reglamento (UE) 2018/858, accesible mediante búsqueda semántica.
2. Implementar un chatbot de consulta que permita a ingenieros y talleres resolver dudas sobre la normativa de reformas sin necesidad de navegar manualmente por el PDF.
3. Diseñar un pipeline de generación que, dado un conjunto de reformas y datos del vehículo, identifique automáticamente las fichas CR aplicables, filtre los ARs por categoría, y redacte las secciones del documento.
4. Integrar un mecanismo de revisión humana (human-in-the-loop) que permita al ingeniero aprobar o rechazar cada sección generada antes de producir el documento final en formato Word.
5. Producir un archivo `.docx` estructurado con portada, índice automático, tablas normativas y bloques de firma, directamente entregable como borrador de trabajo.

### 1.3. Alcance de la solución

El sistema cubre la generación automática de proyectos técnicos únicamente para reformas de Vía A (39 fichas CR). Las vías B, C y D no están implementadas, aunque el validador previo sí las identifica para informar al usuario.

La base vectorial indexa la Sección I del Manual de Reformas (76 fichas CR más el preámbulo), y ocho fragmentos del Reglamento (UE) 2018/858. Las secciones II, III y IV del Manual no están indexadas en esta versión.

El sistema no está integrado con los sistemas de tramitación de la DGT ni con los colegios de ingenieros. El documento generado es un borrador que requiere revisión, completado de las secciones marcadas como `[COMPLETAR]`, y firma del ingeniero responsable antes de cualquier uso oficial.

La infraestructura prevista es un entorno Docker en servidor local o VPS. No hay autenticación de usuarios implementada; el acceso está restringido a nivel de red.

---

## 2. Estado del arte y fundamentos teóricos

### 2.1. Modelos de lenguaje y arquitectura Transformer

Los modelos de lenguaje de gran escala (LLMs) que se usan en este proyecto —GPT-4o y GPT-4o-mini— se basan en la arquitectura Transformer introducida por Vaswani et al. (2017). La característica central de esta arquitectura es el mecanismo de atención multi-cabeza (multi-head attention), que permite al modelo ponderar la relevancia de cada token del contexto respecto a cada posición de la secuencia de salida, sin depender de la estructura secuencial de las RNNs previas.

Formalmente, la atención se calcula como:

$$\text{Attention}(Q, K, V) = \text{softmax}\left(\frac{QK^T}{\sqrt{d_k}}\right)V$$

donde $Q$ (queries), $K$ (keys) y $V$ (values) son proyecciones lineales de los vectores de entrada, y $d_k$ es la dimensión de las keys. La división por $\sqrt{d_k}$ estabiliza los gradientes evitando que el producto interno crezca demasiado con la dimensión.

Los modelos de la familia GPT son decodificadores causales: en cada paso de generación, el token producido se añade al contexto y se usa para predecir el siguiente. El entrenamiento se realiza sobre grandes corpus con objetivo de modelado de lenguaje causal (predecir el siguiente token), y posteriormente se aplica ajuste fino con RLHF (Reinforcement Learning from Human Feedback) para alinear el comportamiento del modelo con instrucciones y preferencias humanas (Ouyang et al., 2022). La capacidad de seguir instrucciones complejas que presentan modelos como GPT-4o se atribuye en gran medida a esta fase de ajuste (Brown et al., 2020).

Para este proyecto, la diferencia práctica entre GPT-4o y GPT-4o-mini es relevante desde dos ángulos: capacidad de razonamiento y coste. GPT-4o tiene mejor desempeño en tareas que requieren interpretar normativa, detectar dependencias entre reformas y filtrar condiciones por atributos del vehículo; por eso se asigna al agente Identificador CR. GPT-4o-mini tiene suficiente capacidad para redactar texto técnico estructurado siguiendo un prompt detallado, a una fracción del coste, y se usa para los agentes redactores.

El modelo de embeddings utilizado es `text-embedding-3-small` de OpenAI, que genera vectores de 1536 dimensiones. Este modelo aplica técnicas de entrenamiento contrastivo para que textos semánticamente similares queden cercanos en el espacio vectorial. La similitud entre embeddings se mide con similitud coseno, que es invariante a la escala de los vectores.

### 2.2. Técnicas de adaptación: RAG, prompting y orquestación de agentes

**Retrieval-Augmented Generation (RAG)**

RAG es una técnica que combina un sistema de recuperación de información con un modelo generativo. En lugar de intentar que el LLM "memorice" toda la normativa durante el entrenamiento (lo cual es imposible para documentos privados o actualizados), se indexa el corpus en una base vectorial y, en tiempo de inferencia, se recuperan los fragmentos más relevantes para la consulta y se inyectan en el contexto del modelo. Este enfoque fue formalizado por Lewis et al. (2020), que demostraron mejoras sustanciales sobre modelos puramente paramétricos en tareas de respuesta a preguntas sobre bases de conocimiento externas.

El pipeline RAG básico tiene tres pasos: (1) convertir la consulta a un vector de embedding, (2) buscar los k vectores más cercanos en la base de datos vectorial, y (3) construir un prompt que incluya los fragmentos recuperados más la pregunta original. La ventaja frente al fine-tuning es que el corpus puede actualizarse sin re-entrenar el modelo, y la fuente de cada respuesta es trazable. Para una revisión sistemática de las variantes de RAG y sus aplicaciones véase Gao et al. (2023).

En este proyecto se añade un paso de filtrado por metadatos: antes de la búsqueda semántica, se pueden aplicar filtros por categoría de vehículo o vía de tramitación, reduciendo el espacio de búsqueda y mejorando la precisión del retrieval.

**Prompting estructurado**

Un prompt bien diseñado es la principal palanca de control sobre el comportamiento del LLM. En este proyecto se distinguen dos tipos de prompts: los prompts de sistema (system prompts), que establecen el rol del agente y las restricciones generales, y los prompts de usuario, que contienen los datos específicos de cada llamada.

Las técnicas aplicadas incluyen few-shot prompting (incluir ejemplos del formato de salida esperado), instrucciones de formato explícitas (indicar exactamente qué secciones debe generar y en qué orden), y restricciones negativas (indicar qué no debe hacer el modelo, como inventar datos del vehículo no proporcionados).

**Orquestación de agentes con LangGraph**

LangGraph es un framework construido sobre LangChain (Chase, 2022) que permite definir grafos de estado dirigidos donde cada nodo es una función (agente) que lee el estado actual, realiza alguna operación —que puede incluir llamadas a LLMs, búsquedas en bases de datos o ejecución de código— y actualiza el estado (LangChain AI, 2024). Las aristas del grafo pueden ser condicionales, lo que permite bifurcar el flujo según el resultado de un nodo.

La diferencia principal respecto a cadenas lineales (como las LangChain chains) es que LangGraph mantiene un estado explícito y tipado a lo largo de toda la ejecución. Esto facilita las interrupciones (human-in-the-loop), el checkpointing y la regeneración parcial de resultados. En este proyecto, el grafo se detiene antes del nodo de revisión humana mediante `interrupt_before`, espera la aprobación del ingeniero, y puede reanudar la ejecución regenerando solo las secciones marcadas para reescritura.

### 2.3. Consideraciones éticas y legales

**Responsabilidad profesional:** un Proyecto Técnico de reforma Vía A es un documento con efectos legales. El ingeniero que lo firma asume responsabilidad profesional sobre su contenido. El sistema no elimina esa responsabilidad; genera un borrador que el profesional debe revisar y firmar. Este punto debe quedar claro en la interfaz de usuario y en la documentación.

**Alucinaciones del modelo:** los LLMs pueden generar texto incorrecto con apariencia de veracidad. En el contexto de documentación técnica normativa, esto es especialmente problemático. Las mitigaciones aplicadas son: temperatura 0 en todos los agentes, inyección explícita de los ARs y fichas CR en el prompt (el modelo no debe "recordar" normativa, sino redactar a partir de los datos proporcionados), y revisión humana obligatoria antes de la exportación del documento.

**Uso de la API de OpenAI:** los datos enviados a la API incluyen información del vehículo y posiblemente datos del propietario. OpenAI tiene políticas de privacidad que excluyen el uso de datos de API para entrenamiento por defecto, pero el operador del sistema debe informar a los usuarios de que sus datos se procesan en servidores externos. En un despliegue para uso profesional habitual, sería preferible evaluar alternativas con modelos desplegados localmente.

**Propiedad intelectual:** el Manual de Reformas de la DGT es un documento público. Su indexación y uso para consulta tiene cobertura bajo el derecho de cita y uso privado. No hay impedimento legal para construir un sistema de consulta basado en él, siempre que no se redistribuya el contenido original de forma que infrinja los términos de la DGT.

---

## 3. Requisitos y diseño de la solución

### 3.1. Requisitos funcionales y no funcionales

**Requisitos funcionales:**

| ID | Requisito |
|---|---|
| RF-01 | El sistema permite consultar las fichas CR del Manual de Reformas en lenguaje natural |
| RF-02 | El chatbot mantiene historial de conversación de hasta 4 turnos |
| RF-03 | El sistema acepta como entrada: datos del vehículo, reformas solicitadas, datos del ingeniero y del expediente |
| RF-04 | El sistema identifica automáticamente las fichas CR correspondientes a las reformas indicadas |
| RF-05 | El sistema filtra los ARs aplicables según la categoría del vehículo |
| RF-06 | El sistema detecta fichas CR adicionales a partir del campo `informacion_adicional` de las fichas identificadas |
| RF-07 | El sistema genera las secciones de texto del Proyecto Técnico mediante LLM |
| RF-08 | El sistema permite al ingeniero revisar cada sección y aprobarla o solicitar reescritura con motivo |
| RF-09 | Solo se regeneran las secciones marcadas para reescritura; el resto se mantiene |
| RF-10 | El sistema exporta el proyecto aprobado a formato `.docx` con portada, índice, tablas y bloques de firma |
| RF-11 | El endpoint `/validar-crs` clasifica un conjunto de reformas por vía y bloquea la generación si ninguna es Vía A |

**Requisitos no funcionales:**

| ID | Requisito |
|---|---|
| RNF-01 | Tiempo de generación del borrador completo inferior a 3 minutos para una reforma estándar |
| RNF-02 | Coste por proyecto generado inferior a $0.50 |
| RNF-03 | La base vectorial debe soportar búsqueda con latencia inferior a 500ms para las colecciones actuales |
| RNF-04 | El sistema debe ser desplegable con Docker sin dependencias adicionales en el host |
| RNF-05 | Las secciones generadas deben incluir marcadores `[COMPLETAR]` en los campos que el LLM no puede rellenar sin datos adicionales del ingeniero |
| RNF-06 | El documento Word generado debe seguir la estructura definida en el diseño, con estilos de cabecera y pie de página correctos |

### 3.2. Arquitectura de la aplicación

La aplicación tiene dos módulos independientes que comparten la misma base vectorial (ChromaDB) y la misma API de OpenAI.

```
┌─────────────────────────────────────────────────────────┐
│                    MÓDULO 1: CHATBOT RAG                │
│                                                         │
│  Streamlit Frontend  ──►  FastAPI Backend               │
│                               │                         │
│                    ┌──────────┴──────────┐              │
│                    │     ChromaDB        │              │
│                    │  fichas_cr          │              │
│                    │  preambulo          │              │
│                    │  reglamento_ue      │              │
│                    └──────────┬──────────┘              │
│                               │                         │
│                    text-embedding-3-small                │
│                    gpt-4o-mini (respuesta)               │
└─────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────┐
│            MÓDULO 2: GENERADOR VÍA A                    │
│                                                         │
│  Streamlit Frontend  ──►  FastAPI Backend               │
│                               │                         │
│                        LangGraph Grafo                  │
│                               │                         │
│         ┌─────────────────────┼──────────────┐          │
│         │                     │              │           │
│  Identificador CR    Redactores (paralelo)  Ensamblador │
│  (gpt-4o)           (gpt-4o-mini)          (Node.js)   │
│         │                                              │
│    ChromaDB                                            │
│    fichas_cr                                           │
└─────────────────────────────────────────────────────────┘
```

El flujo del Módulo 2 es el siguiente:

1. El frontend recibe los datos del vehículo y las reformas solicitadas
2. FastAPI valida la entrada mediante Pydantic v2 y lanza el grafo LangGraph
3. El nodo Identificador CR consulta ChromaDB, identifica las fichas, filtra los ARs y actualiza el estado
4. Los nodos Redactor Memoria, Redactor Pliego y Redactor Conclusiones se ejecutan (se pueden paralelizar con ramas del grafo)
5. El grafo se interrumpe antes del nodo `revision_humana`
6. El frontend muestra las secciones generadas; el ingeniero aprueba o solicita reescritura
7. Si hay secciones para regenerar, los redactores correspondientes se vuelven a ejecutar solo para esas secciones
8. Una vez aprobado todo, el nodo Ensamblador llama al script Node.js para generar el `.docx`
9. El archivo se sirve como descarga desde FastAPI

### 3.3. Selección tecnológica

**Python 3.11** es la versión de referencia por su rendimiento respecto a versiones anteriores y su compatibilidad con todas las librerías del stack.

**FastAPI 0.115** se usa como capa de API REST porque ofrece validación automática de esquemas con Pydantic, documentación OpenAPI generada automáticamente, y rendimiento adecuado para un servicio de baja concurrencia como este.

**Streamlit 1.45** se elige como frontend por su rapidez de desarrollo para interfaces de usuario orientadas a datos. No es la opción más flexible para interfaces complejas, pero es suficiente para un prototipo funcional de uso profesional.

**LangChain 0.3.25 + LangGraph 0.4.5** proporcionan las abstracciones para gestión de prompts, integración con embeddings y orquestación de agentes. LangGraph añade el control de flujo stateful que no está disponible en las cadenas estándar de LangChain.

**ChromaDB 1.0.9** es la base vectorial. Se eligió por su simplicidad de despliegue (no requiere servicio externo en modo embebido), su soporte nativo de filtros por metadatos y su integración directa con LangChain. Para volúmenes mayores de datos sería más adecuado un servicio como Pinecone o Qdrant, pero para 76 fichas CR más algunos cientos de chunks adicionales, ChromaDB es suficiente.

**Node.js 20 LTS + librería docx v9** se usa para la generación del archivo Word porque la librería `docx` de Node.js tiene un soporte más completo de las especificaciones OOXML (cabeceras, pies de página, índices con hipervínculos, estilos de tabla) que las alternativas en Python disponibles en el momento de desarrollo. El script Node.js se invoca desde Python mediante `subprocess`.

**Docker + docker-compose** simplifican el despliegue al encapsular Python, Node.js y ChromaDB en contenedores con sus dependencias. Esto elimina problemas de versiones y facilita replicar el entorno en distintas máquinas.

### 3.4. Diseño de datos y pipelines

**Estructura de una ficha CR en ChromaDB:**

Cada ficha CR se almacena como un documento en la colección `fichas_cr` con los siguientes metadatos:

```json
{
  "codigo_cr": "CR-01",
  "descripcion": "Instalación de equipo de alumbrado adicional",
  "via_tramitacion": "A",
  "categorias_vehiculo": ["M1", "M2", "N1"],
  "documentacion_exigible": ["Proyecto Técnico", "Certificado de Conformidad", ...],
  "ars": [{"codigo": "UNECE R48", "condicion": "M1, M2, M3"}, ...],
  "informacion_adicional": "...",
  "keywords": ["faro", "luz", "alumbrado", "LED", ...]
}
```

El campo `keywords` se enriquece con términos de taller extraídos de un CSV externo, para mejorar el retrieval cuando un usuario usa terminología de taller en lugar de terminología normativa.

**Pipeline de indexación:**

El pipeline de indexación (ejecutado una vez, offline) sigue estos pasos:

1. Extracción de texto y tablas del PDF del Manual de Reformas con `pdfplumber`
2. Arquitectura híbrida: `extract_tables()` para las tablas de campo de aplicación y ARs; `extract_text()` para los campos de texto libre (descripción, documentación, condiciones)
3. Construcción del chunk de embedding: texto concatenado que incluye descripción, categorías, vía, documentación y keywords, más la interpretación de los ARs inyectada desde el chunk del preámbulo correspondiente
4. Generación de embeddings con `text-embedding-3-small`
5. Inserción en ChromaDB con metadatos completos

**Estado del grafo LangGraph (TypedDict):**

```python
class EstadoGrafo(TypedDict):
    proyecto_id: str
    entrada: EntradaProyecto
    crs_identificados: list[FichaCR]
    ars_filtrados: list[ActoReglamentario]
    secciones: dict[str, SeccionGenerada]
    secciones_a_regenerar: list[str]
    docx_path: Optional[str]
```

`EntradaProyecto` contiene los datos del vehículo (matrícula, bastidor, categoría, marca, modelo, año), los datos del ingeniero (nombre, número de colegiado, colegio), los datos del expediente, y la lista de reformas solicitadas en texto libre.

---

## 4. Implementación

### 4.1. Estructura del código y componentes

La estructura de directorios del proyecto es la siguiente:

```
proyecto_tecnico/
├── agents/
│   ├── identificador_cr.py
│   ├── redactor_memoria.py
│   ├── redactor_pliego.py
│   ├── redactor_conclusiones.py
│   └── ensamblador.py          # Wrapper Python que llama al script Node.js
├── graph/
│   ├── grafo.py                # Definición del grafo LangGraph
│   └── estado.py               # TypedDict del estado y modelos Pydantic
├── rag/
│   ├── indexer.py              # Pipeline de indexación offline
│   ├── retriever.py            # Funciones de búsqueda en ChromaDB
│   └── embeddings.py           # Configuración del cliente de embeddings
├── api/
│   ├── main.py                 # FastAPI app, rutas
│   ├── schemas.py              # Esquemas de entrada/salida
│   └── dependencies.py         # Dependencias inyectadas (ChromaDB client, etc.)
├── frontend/
│   ├── chatbot.py              # Streamlit app chatbot RAG
│   └── generador.py            # Streamlit app generador Vía A
├── word_generator/
│   ├── generate.js             # Script Node.js con librería docx
│   ├── package.json
│   └── templates/
│       └── estilos.js          # Definición de estilos Word
├── parsers/
│   ├── parse_fichas.py         # Parser PDF fichas CR
│   └── parse_reglamento.py     # Parser PDF Reglamento UE
├── data/
│   ├── keywords_taller.csv
│   └── chroma_db/              # Directorio de la base vectorial
├── docker-compose.yml
├── Dockerfile.python
├── Dockerfile.node
└── .env.example
```

Los agentes son funciones Python que toman el estado del grafo como entrada y devuelven un diccionario con las actualizaciones al estado. El grafo en `grafo.py` conecta estos nodos y define las aristas condicionales.

### 4.2. Integración con modelos (OpenAI API)

Todos los accesos a la API de OpenAI se realizan a través de `langchain-openai 0.3.16`. Se usan dos clases principales:

- `ChatOpenAI`: para los agentes de generación de texto (GPT-4o y GPT-4o-mini)
- `OpenAIEmbeddings`: para la generación de embeddings con `text-embedding-3-small`

La configuración de los modelos es:

```python
# Identificador CR
llm_identificador = ChatOpenAI(
    model="gpt-4o",
    temperature=0,
    max_tokens=2048
)

# Redactores
llm_redactor = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    max_tokens=4096
)

# Embeddings
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-small",
    dimensions=1536
)
```

Temperatura 0 en todos los agentes es una decisión deliberada: en un contexto de documentación técnica con efectos legales, la reproducibilidad es más importante que la variedad. Se quiere que, dados los mismos inputs, el sistema produzca siempre el mismo output (dentro de la variabilidad inherente de los modelos de lenguaje, que no es completamente determinista incluso con temperatura 0).

El manejo de errores de la API incluye reintentos automáticos con backoff exponencial para errores de rate limit (429) y errores transitorios de red. Se usa el mecanismo de reintentos integrado en el cliente de OpenAI.

El modelo GPT-4o-mini tiene una ventana de contexto de 128k tokens, suficiente para incluir todas las fichas CR relevantes más el prompt de sistema en una sola llamada. GPT-4o tiene la misma ventana. En la práctica, las llamadas típicas usan entre 2.000 y 8.000 tokens de entrada, con salidas de 500 a 2.000 tokens por sección.

### 4.3. Gestión de prompts y orquestación de agentes

**Agente Identificador CR**

Este agente es el más crítico del pipeline. Su función es:

1. Recibir la lista de reformas solicitadas en texto libre
2. Para cada reforma, buscar en ChromaDB las fichas CR correspondientes (combinando búsqueda exacta por código CR si se indica y búsqueda semántica si solo hay descripción)
3. Filtrar los ARs de cada ficha según la categoría del vehículo
4. Leer el campo `informacion_adicional` de cada ficha identificada para detectar si se requieren fichas CR adicionales
5. Actualizar el estado con `crs_identificados` y `ars_filtrados`

El prompt del sistema de este agente especifica el formato de salida esperado en JSON estructurado (usando structured outputs de OpenAI), lo que garantiza que el modelo devuelva un objeto parseable sin texto adicional.

**Agentes Redactores**

Los tres agentes redactores (Memoria, Pliego, Conclusiones) siguen el mismo patrón: reciben las secciones que deben generar, los datos del vehículo, las fichas CR identificadas y los ARs filtrados, y producen las secciones de texto en Markdown con marcadores `[COMPLETAR]` donde faltan datos.

Las secciones generadas en paralelo dentro de cada agente redactor se implementan lanzando múltiples llamadas al LLM en paralelo (usando `asyncio.gather`), una por cada sección, y agregando los resultados. Esto reduce el tiempo de generación respecto a la ejecución secuencial.

El prompt de cada sección incluye:
- El rol del agente ("Eres un ingeniero técnico redactando la sección X de un Proyecto Técnico...")
- Los datos estructurados del vehículo y las fichas CR (en formato JSON embebido)
- Las instrucciones específicas de formato y contenido para esa sección
- Ejemplos de frases y estructuras típicas en proyectos de reforma Vía A

**Human-in-the-loop**

El mecanismo de interrupción se implementa con `interrupt_before=["revision_humana"]` en la configuración del grafo. Cuando el grafo llega a ese punto, LangGraph lanza una excepción `GraphInterrupt` que el servidor FastAPI captura y devuelve al cliente como una respuesta con estado `"pendiente_revision"`.

El frontend muestra entonces las secciones generadas. El ingeniero puede aprobar cada sección o marcarla para reescritura, opcionalmente añadiendo un motivo. Este motivo se incluye en el prompt de regeneración, lo que permite refinar el resultado de forma guiada.

Una vez enviada la decisión, FastAPI reanuda el grafo (usando `graph.invoke(Command(resume=decision))`) desde el punto de interrupción. Si hay secciones para regenerar, el grafo ejecuta de nuevo los nodos correspondientes antes de continuar al Ensamblador.

**Ensamblador**

El nodo Ensamblador es una función Python que construye el objeto JSON con todas las secciones aprobadas y los datos del proyecto, y llama al script `generate.js` mediante `subprocess.run`. El script Node.js recibe el JSON por stdin, construye el documento Word usando la librería `docx` v9, y escribe el archivo `.docx` en una ruta temporal que el servidor devuelve como descarga.

La librería `docx` v9 permite definir estilos personalizados, encabezados y pies de página diferenciados (la portada no lleva cabecera/pie), índices con hipervínculos y tablas con estilos específicos. La lógica de construcción del documento está separada de los datos en el script Node.js para facilitar la modificación del aspecto visual sin tocar el pipeline de generación.

### 4.4. Mecanismos de seguridad y trazabilidad

**Validación de entrada:** todos los datos de entrada pasan por modelos Pydantic v2 en FastAPI. Esto previene errores en tiempo de ejecución por datos malformados y proporciona mensajes de error claros al cliente.

**Validador previo de CRs:** el endpoint `/validar-crs` permite clasificar un conjunto de reformas antes de iniciar la generación. Si ninguna reforma es de Vía A, el sistema bloquea la generación e informa al usuario. Si hay reformas de otras vías mezcladas con Vía A, se genera una advertencia pero se permite continuar (el proyecto solo incluirá las reformas Vía A).

**Trazabilidad de secciones:** cada `SeccionGenerada` en el estado del grafo incluye metadatos de generación: timestamp, modelo usado, número de tokens consumidos (entrada y salida), y si fue regenerada y con qué motivo. Esto permite auditar el proceso de generación de cada proyecto.

**Variables de entorno:** las claves de API y configuraciones sensibles se gestionan mediante `python-dotenv`. El repositorio incluye un `.env.example` con todas las variables necesarias documentadas pero sin valores reales.

**Logging:** el sistema usa el módulo `logging` de Python con niveles configurables. En producción se recomienda nivel INFO; en desarrollo, DEBUG para ver los prompts completos enviados a la API.

### 4.5. Despliegue e infraestructura

El despliegue se realiza con `docker-compose` con tres servicios:

1. **python-backend:** FastAPI + LangGraph + ChromaDB (modo embebido). El volumen de ChromaDB se monta en el host para persistir la base vectorial entre reinicios.
2. **node-generator:** servicio Node.js que escucha en un socket Unix llamadas de generación de documentos Word. (Alternativa: el script se lanza como proceso hijo desde Python.)
3. **streamlit-frontend:** los dos frontends de Streamlit, uno en el puerto 8501 (chatbot) y otro en el 8502 (generador).

El backend FastAPI escucha en el puerto 8000. En producción se recomienda poner un proxy inverso (Nginx) delante para gestionar TLS y limitar el acceso por IP.

El checkpointing con `MemorySaver` mantiene el estado de los grafos en memoria del proceso Python. Si el servidor se reinicia, los proyectos en curso se pierden. Para producción con sesiones largas, habría que migrar a `SqliteSaver` o `PostgresSaver` de LangGraph.

---

## 5. Evaluación y experimentos

### 5.1. Métricas

Se definen tres grupos de métricas:

**Calidad del retrieval RAG:**
- Precisión@k: fracción de los k chunks recuperados que son relevantes para la consulta
- Recall@k: fracción de los chunks relevantes que aparecen entre los k recuperados
- MRR (Mean Reciprocal Rank): posición media del primer chunk relevante

**Calidad del texto generado:**
- Completitud de secciones: fracción de secciones obligatorias generadas sin marcar como `[COMPLETAR]` (solo aplicable a las secciones que el LLM puede rellenar con los datos disponibles)
- Tasa de aceptación en primera revisión: fracción de secciones aprobadas por el ingeniero sin solicitar reescritura
- Número medio de ciclos de revisión por proyecto

**Eficiencia:**
- Tiempo total de generación (desde entrada hasta archivo `.docx` listo para revisión)
- Coste en tokens por proyecto
- Reducción de tiempo de trabajo del ingeniero respecto al proceso manual

### 5.2. Resultados

Las evaluaciones se realizaron sobre un conjunto de 12 proyectos técnicos de prueba, cubriendo reformas de distintos tipos (instalación de sistemas de alumbrado adicional, modificación de suspensión, instalación de equipos de transporte de personas con movilidad reducida, entre otros). Los proyectos fueron revisados por un ingeniero técnico industrial con experiencia en proyectos de reforma.

**Retrieval RAG:**

| Métrica | Valor |
|---|---|
| Precisión@3 | 0.89 |
| Precisión@5 | 0.82 |
| Recall@5 | 0.94 |
| MRR | 0.91 |

El retrieval falla principalmente en consultas con terminología muy informal o acrónimos no incluidos en el CSV de keywords de taller. La adición del CSV de keywords mejoró la precisión@3 desde 0.74 hasta 0.89 respecto a la indexación sin enriquecimiento.

**Calidad de texto generado:**

| Métrica | Valor |
|---|---|
| Completitud de secciones generables | 96% |
| Tasa de aceptación en primera revisión | 71% |
| Ciclos de revisión medio por proyecto | 1.4 |
| Secciones más rechazadas | 1.4 (Descripción reforma), 3.2 (Pliego materiales) |

La sección de Descripción de la reforma (1.4) es la más rechazada porque su corrección depende de detalles específicos de la instalación que el usuario no siempre proporciona en la entrada. Cuando el ingeniero añade una descripción detallada de la reforma en el formulario de entrada, la tasa de aceptación de esa sección sube al 88%.

**Eficiencia:**

| Métrica | Valor |
|---|---|
| Tiempo medio de generación | 87 segundos |
| Tiempo mínimo | 54 segundos |
| Tiempo máximo | 143 segundos |
| Coste medio por proyecto (tokens) | $0.22 |
| Rango de coste | $0.15 – $0.38 |

La variabilidad en el tiempo de generación se debe principalmente a la latencia de la API de OpenAI, que depende de la carga de los servidores en el momento de la llamada. El tiempo de generación del `.docx` por el script Node.js es constante y se sitúa entre 1 y 3 segundos.

**Reducción de tiempo de trabajo:**

En los 12 proyectos evaluados, el ingeniero reportó una reducción del tiempo de trabajo de entre el 60% y el 75% respecto a la elaboración manual completa. El tiempo que sigue siendo necesario incluye: completar las secciones `[COMPLETAR]` (características antes/después de la reforma, cálculos justificativos, planos), revisar las secciones generadas, añadir fotografías, y firmar el documento. La estimación del ingeniero es que el sistema reduce el trabajo de 4-8 horas a 1-2 horas por proyecto.

### 5.3. Análisis de errores y limitaciones

**Errores de identificación de CRs:** en 2 de los 12 proyectos, el agente Identificador CR no detectó una ficha CR adicional mencionada en el campo `informacion_adicional`. En ambos casos se trataba de referencias cruzadas con redacción ambigua en el PDF original. Este es el tipo de error más grave porque afecta a la completitud normativa del proyecto.

**Errores de filtrado de ARs:** no se observaron errores de filtrado de ARs en los proyectos evaluados. El filtrado por categoría de vehículo funciona correctamente cuando la categoría está bien definida en los metadatos de la ficha.

**Alucinaciones en texto:** se detectaron 3 casos de texto generado que contenía afirmaciones técnicas no respaldadas por los datos de entrada (p. ej., valores numéricos de resistencia de materiales no especificados). En todos los casos, el ingeniero los detectó en la revisión. Esto subraya que la revisión humana no es un paso opcional.

**Secciones `[COMPLETAR]`:** las secciones 2 (Cálculos justificativos), 4 (Planos), 5 (Presupuesto), 6 (Fotografías) y 7 (Normativa aplicable adicional) siempre se generan con marcador `[COMPLETAR]` porque requieren trabajo específico del ingeniero que no puede automatizarse con los datos de entrada disponibles. Esta es una limitación del sistema que se documenta explícitamente.

---

## 6. Pruebas y validación

### 6.1. Tests funcionales y validación con usuario

**Tests unitarios y de integración:**

Se implementaron tests unitarios con `pytest` para los siguientes componentes:

- Parser de fichas CR: verificación de que la extracción de texto y tablas produce los metadatos correctos para un subconjunto de 10 fichas representativas
- Retriever: verificación de que las búsquedas semánticas devuelven las fichas esperadas para un conjunto de queries conocidas
- Filtro de ARs: verificación del filtrado por categoría de vehículo para cada combinación de categoría y ficha CR
- Validador de CRs: verificación de la clasificación por vía y detección de bloqueos
- Ensamblador: verificación de que el `.docx` generado contiene el número esperado de secciones y que los metadatos del documento son correctos

**Validación con usuario:**

Se realizó una sesión de validación con un ingeniero técnico industrial que realiza habitualmente proyectos de reforma Vía A. El protocolo de validación incluyó:

1. Generación de 3 proyectos técnicos completos usando el sistema, cubriendo reformas de distintas fichas CR
2. Comparación de los borradores generados con proyectos reales elaborados manualmente por el mismo ingeniero para las mismas reformas
3. Evaluación cualitativa de cada sección según: completitud, corrección técnica, adecuación al lenguaje de este tipo de documentos, y utilidad como punto de partida

Los resultados de la evaluación cualitativa fueron positivos en general. El ingeniero valoró especialmente la generación automática de las tablas de fichas CR y ARs (que normalmente elabora manualmente consultando el manual), y la estructura consistente del documento. La principal crítica fue que algunas secciones de descripción de la reforma son demasiado genéricas cuando no se proporciona suficiente contexto en la entrada.

### 6.2. Usabilidad

La interfaz de Streamlit para el generador de proyectos se estructura en cuatro pasos:

1. **Formulario de entrada:** datos del vehículo, datos del ingeniero, datos del expediente, descripción de las reformas solicitadas
2. **Validación y confirmación:** muestra las fichas CR identificadas y los ARs filtrados; el ingeniero puede confirmar o corregir antes de lanzar la generación
3. **Revisión de secciones:** muestra cada sección generada con un selector de aprobación/rechazo y un campo de texto para el motivo del rechazo
4. **Descarga:** botón de descarga del `.docx` una vez aprobadas todas las secciones

Esta estructura lineal reduce la posibilidad de errores de uso. El paso de validación previa (paso 2) es especialmente importante porque permite al ingeniero corregir identificaciones erróneas de fichas CR antes de invertir tiempo en revisar el texto generado.

Una limitación de usabilidad es que la interfaz no guarda el estado entre sesiones (por el MemorySaver en memoria). Si el ingeniero cierra el navegador durante la revisión, el proceso se pierde y hay que empezar desde el principio. Esta es la consecuencia directa de no tener checkpointing persistido.

### 6.3. Observabilidad

El sistema expone las siguientes métricas operacionales:

- Endpoint `/health` en FastAPI: devuelve estado del servidor, estado de conexión con ChromaDB y número de documentos en cada colección
- Logs estructurados en JSON: cada llamada a la API de OpenAI produce un registro con timestamp, modelo, tokens de entrada, tokens de salida, latencia y coste estimado
- `proyecto_id` único por generación: permite rastrear todos los logs y eventos de un proyecto específico

No se ha implementado monitorización de métricas en tiempo real (Prometheus, Grafana) en esta versión. Para un despliegue con múltiples usuarios concurrentes, añadir métricas de latencia y tasa de errores sería el primer paso de observabilidad adicional.

---

## 7. Discusión

### 7.1. Lecciones aprendidas

**La calidad del retrieval depende más del procesamiento del corpus que del modelo de embeddings.** El mayor salto de calidad en el chatbot RAG no vino de cambiar el modelo de embeddings sino de mejorar el pipeline de extracción de texto del PDF. La extracción inicial con solo `extract_text()` producía chunks de baja calidad para las tablas de ARs (el texto de las tablas se extraía de forma desestructurada). El cambio a arquitectura híbrida con `extract_tables()` para las tablas y `extract_text()` para el texto libre mejoró significativamente la calidad de los metadatos almacenados y, con ello, la precisión del retrieval.

**El enriquecimiento de keywords es más efectivo de lo esperado.** La incorporación de un CSV de términos de taller (jerga técnica, nombres comerciales, acrónimos usados en el sector) mejoró la precisión@3 en 15 puntos porcentuales. El esfuerzo de construir ese CSV (aproximadamente 4 horas de trabajo con un mecánico de taller) tiene un retorno alto.

**LangGraph añade complejidad pero el control de flujo stateful lo justifica.** La curva de aprendizaje de LangGraph es notable: el modelo de grafo con estado, las aristas condicionales y el mecanismo de interrupción requieren entender bien la documentación antes de implementar algo no trivial. Sin embargo, una vez implementado, el human-in-the-loop y la regeneración selectiva de secciones habrían sido mucho más difíciles de implementar con una cadena lineal estándar.

**La generación paralela de secciones no siempre es más rápida en la práctica.** Aunque `asyncio.gather` lanza las llamadas al LLM en paralelo, los rate limits de la API de OpenAI (especialmente en cuentas con límites de TPM bajos) pueden causar que algunas llamadas paralelas esperen antes de ejecutarse. En entornos con límites de API ajustados, la diferencia entre ejecución paralela y secuencial es menor de lo esperado.

**La generación de documentos Word es una tarea no trivial.** La librería `docx` de Node.js es potente pero verbosa. Implementar correctamente un índice con hipervínculos, cabeceras diferenciadas para la portada, y estilos de tabla consistentes requirió más tiempo de desarrollo del previsto. El uso de Node.js para esta tarea (en lugar de una librería Python) se justifica por el mejor soporte OOXML, pero introduce heterogeneidad en el stack que complica el mantenimiento.

**Los prompts de los agentes redactores necesitan iteración.** La calidad del texto generado mejora sustancialmente con prompts que incluyen ejemplos concretos del lenguaje esperado. Los primeros prompts producían texto correcto pero con un registro demasiado formal y genérico; añadir frases de ejemplo extraídas de proyectos reales mejoró la adecuación del registro. Esta iteración requirió revisar el output de cada sección con el ingeniero colaborador.

### 7.2. Riesgos, ética y mitigaciones

**Riesgo: el sistema genera texto incorrecto que pasa la revisión humana.**

Este es el riesgo más relevante. Un ingeniero bajo presión de tiempo podría aprobar secciones sin leerlas en detalle. Si el documento llega a la DGT con errores técnicos o normativos, la responsabilidad recae sobre el ingeniero firmante.

Mitigaciones aplicadas: temperatura 0 (máxima reproducibilidad), inyección explícita de datos normativos en el prompt (el modelo no infiere normativa de su preentrenamiento), marcadores `[COMPLETAR]` explícitos para las secciones incompletas, y advertencias en la interfaz de usuario sobre la necesidad de revisión. Lo que no se puede mitigar tecnológicamente es la presión de tiempo: la formación del usuario en el uso responsable del sistema es tan importante como las salvaguardas técnicas.

**Riesgo: cambio en la normativa que no se refleja en la base vectorial.**

El Manual de Reformas de la DGT se actualiza periódicamente. Si la base vectorial no se actualiza, el sistema generará proyectos basados en fichas CR obsoletas.

Mitigaciones: el pipeline de indexación está diseñado para ejecutarse sobre una nueva versión del PDF del Manual sin cambios en el código. Se recomienda establecer un proceso de revisión trimestral de la normativa y re-indexación si hay cambios.

**Riesgo: dependencia de la API de OpenAI.**

Si la API de OpenAI no está disponible o cambia sus modelos, el sistema deja de funcionar.

Mitigaciones parciales: los timeouts y reintentos están implementados. Para independencia total de un proveedor externo, habría que migrar a modelos locales, lo que implica requisitos de hardware significativos y posiblemente reducción de calidad en la generación.

**Consideraciones sobre privacidad:**

Los datos del vehículo, el propietario y el ingeniero se envían a la API de OpenAI durante la generación. En el ámbito profesional, esto requiere que el operador del sistema informe a los usuarios y, dependiendo del contexto, pueda necesitar un acuerdo de procesamiento de datos con OpenAI. Se recomienda revisar los términos de la API y la política de privacidad aplicable antes del despliegue en un entorno con usuarios reales.

---

## 8. Conclusiones y trabajo futuro

El proyecto demuestra que es técnicamente viable automatizar la generación del borrador de un Proyecto Técnico de reforma de vehículo Vía A mediante una combinación de recuperación semántica y orquestación de agentes LLM. Los resultados obtenidos en la validación con usuario —reducción de tiempo de trabajo del 60-75%, tasa de aceptación de secciones del 71% en primera revisión, coste medio de $0.22 por proyecto— son suficientemente positivos para considerar el sistema útil en un entorno profesional real, con las limitaciones documentadas.

El chatbot RAG cumple su función de consulta normativa. La precisión@3 del 89% significa que, en la mayoría de las consultas, el primer o segundo resultado recuperado contiene la información buscada. Las consultas donde el sistema falla son principalmente aquellas con terminología muy informal, y este problema es parcialmente mitigable con el enriquecimiento de keywords.

Las limitaciones actuales más significativas son tres: el checkpointing en memoria (que hace el sistema frágil ante reinicios), la cobertura parcial del Manual de Reformas (solo Sección I), y la ausencia de autenticación de usuarios. Estas tres limitaciones son abordables en versiones siguientes sin cambios arquitecturales profundos.

**Trabajo futuro:**

El orden de prioridad propuesto para trabajo futuro es el siguiente:

1. **Checkpointing persistente:** migrar de `MemorySaver` a `SqliteSaver` o `PostgresSaver` para mantener el estado de los proyectos entre reinicios del servidor. Es un cambio relativamente pequeño con un impacto grande en la fiabilidad.

2. **Implementación de Vía B:** las 34 fichas de Vía B requieren un documento más simple (Informe de Conformidad + Certificado de Taller). Implementar este módulo ampliaría significativamente el ámbito de uso del sistema.

3. **Indexación de Secciones II, III y IV del Manual:** ampliar la base vectorial para cubrir el Manual completo permitiría responder consultas sobre categorías de vehículos y procedimientos que actualmente quedan fuera del ámbito del chatbot.

4. **Autenticación de usuarios:** añadir autenticación básica (JWT) para controlar el acceso y asociar proyectos a usuarios específicos.

5. **Evaluación con modelos locales:** explorar la sustitución de GPT-4o-mini por un modelo de código abierto desplegado localmente (Mistral, LLaMA) para las tareas de redacción, reduciendo la dependencia de la API externa y los problemas de privacidad. El agente Identificador CR probablemente requeriría GPT-4o o equivalente para mantener la calidad de identificación.

6. **Integración de PDFs adjuntos:** implementar la incrustación real de documentos PDF en el archivo Word generado, o alternativamente generar el documento en formato PDF directamente para facilitar la incorporación de cálculos y planos.

7. **Panel de administración:** interfaz para gestionar la base vectorial, actualizar fichas CR, revisar logs de uso y monitorizar costes de API.

---

## 9. Bibliografía

Las referencias se presentan en formato APA 7.ª edición, ordenadas alfabéticamente por el primer apellido del autor o por el nombre de la organización cuando no se indica autor personal.

---

Brown, T. B., Mann, B., Ryder, N., Subbiah, M., Kaplan, J., Dhariwal, P., Neelakantan, A., Shyam, P., Sastry, G., Askell, A., Agarwal, S., Herbert-Voss, A., Krueger, G., Henighan, T., Child, R., Ramesh, A., Ziegler, D. M., Wu, J., Winter, C., … Amodei, D. (2020). Language models are few-shot learners. *Advances in Neural Information Processing Systems*, *33*, 1877–1901. https://arxiv.org/abs/2005.14165

Chase, H. (2022). *LangChain* (Versión 0.3) [Software]. LangChain AI. https://github.com/langchain-ai/langchain

Chroma. (2023). *ChromaDB: The AI-native open-source embedding database* (Versión 1.0) [Software]. https://github.com/chroma-core/chroma

Dirección General de Tráfico. (2021). *Manual de Reformas de Vehículos* (7.ª ed.). Ministerio del Interior, Gobierno de España. https://sede.dgt.gob.es/es/tramites-y-multas/vehiculos/reformas-de-vehiculos/

Docker Inc. (2024). *Docker documentation* [Documentación de software]. https://docs.docker.com/ (Recuperado el 15 de marzo de 2026)

Gao, Y., Xiong, Y., Gao, X., Jia, K., Pan, J., Bi, Y., Dai, Y., Sun, J., & Wang, H. (2023). Retrieval-augmented generation for large language models: A survey. *arXiv preprint arXiv:2312.10997*. https://arxiv.org/abs/2312.10997

LangChain AI. (2024). *LangGraph: Building stateful, multi-actor applications with LLMs* (Versión 0.4) [Software]. https://github.com/langchain-ai/langgraph

Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems*, *33*, 9459–9474. https://arxiv.org/abs/2005.11401

Miu, D. (2024). *docx: Easily generate .docx files with JS/TS* (Versión 9) [Paquete de software]. npm. https://www.npmjs.com/package/docx

OpenAI. (2024a). *GPT-4o system card*. https://openai.com/index/gpt-4o-system-card/ (Recuperado el 15 de marzo de 2026)

OpenAI. (2024b). *Text embeddings: text-embedding-3-small*. OpenAI Platform Documentation. https://platform.openai.com/docs/guides/embeddings (Recuperado el 15 de marzo de 2026)

Ouyang, L., Wu, J., Jiang, X., Almeida, D., Wainwright, C. L., Mishkin, P., Zhang, C., Agarwal, S., Slama, K., Ray, A., Schulman, J., Hilton, J., Kelton, F., Miller, L., Simens, M., Askell, A., Welinder, P., Christiano, P., Leike, J., & Lowe, R. (2022). Training language models to follow instructions with human feedback. *Advances in Neural Information Processing Systems*, *35*, 27730–27744. https://arxiv.org/abs/2203.02155

Parlamento Europeo y Consejo de la Unión Europea. (2018). Reglamento (UE) 2018/858 del Parlamento Europeo y del Consejo, de 30 de mayo de 2018, sobre la homologación de los vehículos de motor y sus remolques y los sistemas, componentes y unidades técnicas independientes destinados a dichos vehículos. *Diario Oficial de la Unión Europea*, L 151, 1–218. https://eur-lex.europa.eu/legal-content/ES/TXT/?uri=CELEX:32018R0858

Pydantic. (2024). *Pydantic V2: Data validation using Python type hints* [Documentación de software]. https://docs.pydantic.dev/ (Recuperado el 15 de marzo de 2026)

Ramírez, S. (2018). *FastAPI* (Versión 0.115) [Software]. Tiangolo. https://fastapi.tiangolo.com/

Streamlit Inc. (2024). *Streamlit: A faster way to build and share data apps* (Versión 1.45) [Software]. https://streamlit.io/

Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all you need. *Advances in Neural Information Processing Systems*, *30*, 5998–6008. https://arxiv.org/abs/1706.03762

---

## 10. Anexos

### 10.1. Guía de despliegue y manual de usuario

#### Requisitos del sistema

- Docker Engine 24.0 o superior
- Docker Compose v2
- 4 GB de RAM mínimo (8 GB recomendados)
- 10 GB de espacio en disco
- Acceso a internet para la API de OpenAI
- Clave de API de OpenAI con acceso a `gpt-4o`, `gpt-4o-mini` y `text-embedding-3-small`

#### Pasos de despliegue

**1. Clonar el repositorio y configurar variables de entorno:**

```bash
git clone <url-repositorio>
cd proyecto_tecnico
cp .env.example .env
# Editar .env y añadir OPENAI_API_KEY
```

El archivo `.env` contiene las siguientes variables:

```
OPENAI_API_KEY=sk-...
CHROMA_PERSIST_DIRECTORY=./data/chroma_db
LOG_LEVEL=INFO
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
```

**2. Indexar la base de conocimiento (solo la primera vez):**

```bash
docker-compose run --rm python-backend python parsers/parse_fichas.py
docker-compose run --rm python-backend python parsers/parse_reglamento.py
docker-compose run --rm python-backend python rag/indexer.py
```

Este paso descarga el PDF del Manual de Reformas (o usa la copia local en `data/`), extrae las fichas CR, genera los embeddings y los almacena en ChromaDB. El proceso tarda aproximadamente 5-10 minutos y consume aproximadamente $0.02 en la API de embeddings.

**3. Arrancar los servicios:**

```bash
docker-compose up -d
```

Los servicios quedan disponibles en:
- Chatbot RAG: `http://localhost:8501`
- Generador Vía A: `http://localhost:8502`
- API FastAPI (documentación): `http://localhost:8000/docs`

**4. Verificar el estado:**

```bash
curl http://localhost:8000/health
```

Respuesta esperada:

```json
{
  "status": "ok",
  "chroma": {
    "fichas_cr": 76,
    "preambulo": 9,
    "reglamento_ue": 8
  }
}
```

#### Manual de usuario: Chatbot RAG

El chatbot permite consultas en lenguaje natural sobre el Manual de Reformas. Ejemplos de consultas:

- "¿Qué documentación necesito para cambiar el motor de un turismo?"
- "¿La ficha CR-07 aplica a vehículos de categoría N1?"
- "¿Cuáles son los ARs que debe cumplir la instalación de un equipo de GLP?"

El historial se mantiene durante 4 turnos. Para una nueva consulta sin contexto anterior, usar el botón "Nueva conversación".

#### Manual de usuario: Generador Vía A

**Paso 1 — Formulario de entrada:**

Rellenar todos los campos obligatorios:
- Matrícula, número de bastidor, categoría del vehículo (M1, M2, M3, N1, N2, N3, O1, O2, O3, O4, L...)
- Marca, modelo, año de fabricación
- Número de expediente, fecha del proyecto
- Nombre del ingeniero, número de colegiado, colegio
- Descripción de las reformas solicitadas (texto libre; cuanto más detallada, mejor será la sección de descripción)

Campos opcionales pero recomendados:
- Características actuales del vehículo (potencia, peso, dimensiones)
- Detalles técnicos de la reforma (materiales, fabricante del equipo a instalar, etc.)

**Paso 2 — Validación:**

El sistema muestra las fichas CR identificadas y los ARs filtrados. Verificar que son correctos antes de continuar. Si falta alguna ficha CR o hay una incorrecta, se puede cancelar y reformular la descripción de la reforma.

**Paso 3 — Generación y revisión:**

Pulsar "Generar proyecto". El proceso tarda entre 1 y 3 minutos. Una vez completado, se muestran todas las secciones generadas. Para cada sección:
- Pulsar "Aprobar" si el contenido es correcto
- Pulsar "Solicitar reescritura" y añadir el motivo si hay que mejorarla

Las secciones marcadas con `[COMPLETAR]` (cálculos, planos, presupuesto, fotografías) requieren que el ingeniero las complete manualmente en el Word.

**Paso 4 — Descarga:**

Una vez aprobadas todas las secciones, pulsar "Generar documento Word". El archivo `.docx` se descarga automáticamente.

---

### 10.2. Detalles técnicos: prompts, esquemas, configuraciones

#### Prompt del sistema — Agente Identificador CR

```
Eres un asistente técnico especializado en el Manual de Reformas de 
Vehículos de la DGT. Tu función es identificar las Fichas CR aplicables 
a una reforma descrita en lenguaje natural, y filtrar los Actos 
Reglamentarios (ARs) según la categoría del vehículo indicada.

Reglas:
1. Identifica todas las fichas CR relevantes para las reformas descritas.
2. Para cada ficha CR identificada, filtra los ARs: incluye solo los ARs 
   cuya condición de aplicación incluya la categoría del vehículo indicada.
3. Lee el campo informacion_adicional de cada ficha. Si menciona otras 
   fichas CR que deben aplicarse en combinación, añádelas a la lista.
4. Si una reforma no corresponde a ninguna ficha CR conocida, indícalo 
   explícitamente en el campo observaciones.
5. Devuelve únicamente JSON válido con el esquema indicado. 
   Sin texto adicional.

Categoría del vehículo: {categoria}
Reformas solicitadas: {reformas}

Fichas CR disponibles (recuperadas por búsqueda semántica):
{fichas_recuperadas}
```

#### Prompt del sistema — Agente Redactor Memoria (sección 1.4)

```
Eres un ingeniero técnico industrial redactando la sección 1.4 
"Descripción de la reforma" de un Proyecto Técnico de reforma de 
vehículo, conforme a la normativa española de la DGT.

El texto debe ser técnico, preciso y en tercera persona. 
No uses adjetivos valorativos. No inventes datos que no estén 
en los inputs. Si un dato no está disponible, escribe [COMPLETAR].

La sección 1.4 debe tener cuatro subsecciones:
- 1.4.1 Descripción general de la reforma
- 1.4.2 Componentes y materiales empleados  
- 1.4.3 Proceso de instalación
- 1.4.4 Verificaciones y ensayos

Datos del vehículo: {datos_vehiculo}
Fichas CR aplicables: {crs_identificados}
ARs filtrados: {ars_filtrados}
Descripción proporcionada por el ingeniero: {descripcion_reforma}

Ejemplo de tono y formato esperado:
"La reforma consiste en la instalación de [componente] sobre el 
vehículo [marca modelo], con número de bastidor [bastidor]. 
El equipo instalado cumple con los requisitos establecidos en 
[AR correspondiente]..."
```

#### Esquema Pydantic — EntradaProyecto

```python
from pydantic import BaseModel, Field
from typing import Optional
from datetime import date

class DatosVehiculo(BaseModel):
    matricula: str
    bastidor: str
    categoria: str  # M1, M2, N1, etc.
    marca: str
    modelo: str
    anio_fabricacion: int
    potencia_kw: Optional[float] = None
    masa_max_kg: Optional[float] = None

class DatosIngeniero(BaseModel):
    nombre: str
    numero_colegiado: str
    colegio: str
    especialidad: Optional[str] = None

class DatosExpediente(BaseModel):
    numero_expediente: str
    fecha_proyecto: date
    objeto_encargo: Optional[str] = None

class EntradaProyecto(BaseModel):
    vehiculo: DatosVehiculo
    ingeniero: DatosIngeniero
    expediente: DatosExpediente
    reformas_solicitadas: str = Field(
        ..., 
        min_length=20,
        description="Descripción en texto libre de las reformas a realizar"
    )
    descripcion_detallada: Optional[str] = None
```

#### Configuración ChromaDB — Colecciones y parámetros de búsqueda

```python
# Configuración de colecciones
COLECCIONES = {
    "fichas_cr": {
        "n_results_default": 5,
        "metadata_filters": ["via_tramitacion", "categorias_vehiculo"]
    },
    "preambulo": {
        "n_results_default": 3,
        "metadata_filters": []
    },
    "reglamento_ue": {
        "n_results_default": 3,
        "metadata_filters": ["articulo"]
    }
}

# Función de búsqueda con filtro por vía
def buscar_fichas_via_a(query: str, categoria: Optional[str] = None):
    filtro = {"via_tramitacion": {"$eq": "A"}}
    if categoria:
        filtro["categorias_vehiculo"] = {"$contains": categoria}
    
    return collection.query(
        query_texts=[query],
        n_results=5,
        where=filtro
    )
```

#### Configuración del grafo LangGraph

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

builder = StateGraph(EstadoGrafo)

# Añadir nodos
builder.add_node("identificador_cr", nodo_identificador_cr)
builder.add_node("redactor_memoria", nodo_redactor_memoria)
builder.add_node("redactor_pliego", nodo_redactor_pliego)
builder.add_node("redactor_conclusiones", nodo_redactor_conclusiones)
builder.add_node("revision_humana", nodo_revision_humana)
builder.add_node("ensamblador", nodo_ensamblador)

# Aristas
builder.set_entry_point("identificador_cr")
builder.add_edge("identificador_cr", "redactor_memoria")
builder.add_edge("redactor_memoria", "redactor_pliego")
builder.add_edge("redactor_pliego", "redactor_conclusiones")
builder.add_edge("redactor_conclusiones", "revision_humana")
builder.add_conditional_edges(
    "revision_humana",
    decidir_siguiente_paso,  # Función que evalúa secciones_a_regenerar
    {
        "regenerar": "redactor_memoria",  # Volver a redactar
        "aprobar": "ensamblador"
    }
)
builder.add_edge("ensamblador", END)

# Compilar con interrupción antes de revision_humana
checkpointer = MemorySaver()
grafo = builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["revision_humana"]
)
```

#### Estructura del JSON enviado al script Node.js

```json
{
  "proyecto_id": "proj_20260315_abc123",
  "metadata": {
    "vehiculo": {
      "matricula": "1234ABC",
      "bastidor": "VF1...",
      "categoria": "M1",
      "marca": "Renault",
      "modelo": "Kangoo",
      "anio": 2019
    },
    "ingeniero": {
      "nombre": "Nombre Apellido",
      "colegiado": "IC-12345",
      "colegio": "COIIM"
    },
    "expediente": {
      "numero": "EXP-2026-001",
      "fecha": "2026-03-15"
    }
  },
  "crs_identificados": [
    {"codigo": "CR-07", "descripcion": "...", "via": "A"}
  ],
  "ars_filtrados": [
    {"codigo": "UNECE R48", "condicion": "M1"}
  ],
  "secciones": {
    "0_peticionario": "Texto de la sección 0...",
    "1_1_objeto": "Texto de la sección 1.1...",
    "1_2_antecedentes": "Texto de la sección 1.2...",
    "1_3_1_identificacion": "Texto de la sección 1.3.1...",
    "1_4_descripcion": "Texto de la sección 1.4...",
    "3_1_pliego_generalidades": "Texto de la sección 3.1...",
    "3_2_pliego_materiales": "Texto de la sección 3.2...",
    "3_3_pliego_ejecucion": "Texto de la sección 3.3...",
    "3_4_pliego_control": "Texto de la sección 3.4...",
    "8_conclusiones": "Texto de la sección 8..."
  },
  "output_path": "/tmp/proyectos/proj_20260315_abc123.docx"
}
```

---

*Fin del documento.*

---

**Nota sobre la versión actual del sistema:** la versión documentada en esta memoria corresponde al estado del proyecto a marzo de 2026. El sistema está operativo para proyectos de reforma Vía A sobre vehículos de categorías M y N. Las limitaciones indicadas a lo largo del documento —especialmente el checkpointing en memoria, la ausencia de autenticación y la cobertura parcial del Manual— son conocidas y se espera abordarlas en iteraciones siguientes.
