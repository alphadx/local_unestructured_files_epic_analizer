# Estado del arte — NER (Named Entity Recognition) y extracción de contactos

**Fecha**: Abril 2026  
**Status**: 🔬 Investigación completada (basada en conocimiento 2024)  
**Objetivo**: Fundamentar la decisión arquitectónica para agregar extracción generalizada de entidades nombradas (NER) y base de datos de contactos en Epic Analyzer

---

## 1. Panorama general

### Historia de NER
- **Pre-2010**: Regex + diccionarios (frágil, bajo recall)
- **2010-2015**: Modelos gráficos probabilísticos (CRF, HMM)
- **2015-2018**: Deep learning (BiLSTM-CRF, primeras redes neuronales)
- **2018-2022**: Transformers pre-entrenados (BERT, RoBERTa, mBERT)
- **2022-2024**: LLMs generativos (GPT, Gemini) + token classification mejorado

### Definición de NER
Identificación automática de entidades nombradas (personas, organizaciones, ubicaciones, etc.) en texto no estructurado.

**Ejemplo**:
```
"La factura fue emitida por Acme Corp. a Juan Pérez (juan@acme.cl) 
el 2024-05-15 por un monto de $50,000 CLP."

Entidades identificadas:
- ORGANIZATION: Acme Corp.
- PERSON: Juan Pérez
- EMAIL: juan@acme.cl
- DATE: 2024-05-15
- MONEY: $50,000 CLP
```

---

## 2. Técnicas modernas de NER

### 2.1 CRF (Conditional Random Field) — Baseline clásico

**Concepto**: Modelo probabilístico que etiqueta secuencias de tokens considerando contexto bilateral.

**Fórmula**:
$$P(y | x) = \frac{\exp(\sum_i w_j f_j(x_i, y_i, y_{i-1}))}{\sum_{y'} \exp(\sum_i w_j f_j(x_i, y'_i, y'_{i-1}))}$$

**Características**:
- ✅ Explicable, predecible
- ✅ Bajo overhead computacional
- ✅ Bueno para tareas con etiquetado clara
- ❌ Requiere features manuales (PoS tags, gazetteer lookups)
- ❌ Bajo recall en entidades no vistas

**Bibliotecas**:
- `sklearn-crfsuite` (Python)
- `CRF++` (C++, investigación)

**Cuándo usarlo**:
- Corpus pequeño + etiquetado disponible
- Entidades muy específicas (RUTs, códigos internos)
- Casos donde interpretabilidad es crítica

---

### 2.2 BiLSTM-CRF — Deep learning clásico

**Arquitectura**:
```
  [Texto]
    |
 [Embedding layer]
    |
 [BiLSTM forward]  +  [BiLSTM backward]
    |                       |
    └───────►[Concatenate]◄─┘
            |
       [CRF layer] (constraints de secuencia)
            |
          [Tag probabilities]
```

**Ventajas**:
- ✅ Captura contexto largo-plazo (bidireccional)
- ✅ No requiere features manuales
- ✅ Estado del arte ~2016-2018
- ⚠️ Requiere entrenamiento en corpus etiquetado

**Desventajas**:
- ❌ Menos preciso que BERT
- ❌ Latencia media en inferencia
- ⚠️ Overfitting en corpus pequeños

**Bibliotecas**:
- `keras/tensorflow`
- `pytorch` + `pytorch-crf`

---

### 2.3 BERT-based Token Classification — Estado del arte 2018-2024

**Concepto**: Fine-tune modelo BERT pre-entrenado en tarea de token classification (tagging).

**Modelos populares**:
- `bert-base-multilingual-cased` — 104 idiomas, BERT base
- `dslim/bert-base-multilingual-cased-ner` — Fine-tuned para NER multiidioma
- `xlm-roberta-base` — RoBERTa multiidioma optimizado
- `dbmdz/bert-base-spanish-wwm-cased` — BERT especializado en español

**Proceso**:
```
1. Tokenizar con WordPiece tokenizer del modelo
2. Pasar por BERT pre-entrenado (768-dim hidden states)
3. Agregar capa linear de clasificación (token-level)
4. Fine-tune en corpus etiquetado con loss de cross-entropy
5. Aplicar CRF para constraints de secuencia (opcional)
```

**Ventajas**:
- ✅ Alta precisión (F1 > 0.85 en idiomas con datasets grandes)
- ✅ Transferencia cero-shot a nuevas entidades (semántica pre-entrenada)
- ✅ Multiidioma nativo
- ✅ Librerías maduras (HuggingFace Transformers)

**Desventajas**:
- ❌ Requiere fine-tuning en corpus específico para accuracy máxima
- ⚠️ Latencia ~100-500ms por documento
- ⚠️ Necesita GPU para producción (CPU es lento)
- ❌ Sesgo del modelo pre-entrenado

**Bibliotecas**:
```python
from transformers import pipeline
ner_pipeline = pipeline("ner", model="dslim/bert-base-multilingual-cased-ner")
results = ner_pipeline("Juan Pérez trabaja en la empresa Acme Corp.")
```

**Tags estándar (CoNLL-2002/2003)**:
- `PER` — Persona
- `ORG` — Organización
- `LOC` — Localización
- `MISC` — Miscelánea

---

### 2.4 LLM-based NER — Gemini, GPT-4, prompting

**Concepto**: Usar LLMs generativos con prompting para extraer entidades.

**Ejemplo de prompt**:
```
Extrae las siguientes entidades del texto:
- Personas (PER): nombres de individuos
- Organizaciones (ORG): empresas, instituciones
- Emails (EMAIL): direcciones de correo
- Teléfonos (PHONE): números de teléfono
- Datesfull (DATE): fechas en cualquier formato
- Monedas (MONEY): montos y divisas

Devuelve formato JSON:
{
  "PER": [...],
  "ORG": [...],
  "EMAIL": [...],
  "PHONE": [...],
  "DATE": [...],
  "MONEY": [...]
}

Texto:
{documento}
```

**Ventajas**:
- ✅ Fleksible — fácil agregar tipos de entidades nuevas
- ✅ Zero-shot — no necesita entrenamiento
- ✅ Entiende contexto complejo
- ✅ USA en Epic Analyzer (Gemini Flash ya está integrado)
- ✅ Multilingual nativo

**Desventajas**:
- ❌ Costo (tokens) — $0.075-0.30 por 1M tokens dependiendo del modelo
- ❌ Latencia ~1-3 segundos por documento
- ❌ Hallucinations posibles (inventa entidades)
- ❌ Dependencia de API remota

**Modelos recomendados**:
- `gemini-2.5-flash` — Rápido, barato, bueno para volumen alto (~usado actualmente)
- `gemini-1.5-pro` — Más preciso, más caro
- `gpt-4-turbo` — OpenAI, excelente calidad pero muy caro
- `claude-3.5-sonnet` — Anthropic, buen balance costo/calidad

**Estrategia de prompting mejorada** (Chain-of-Thought):
```
1. Primer paso: Identificar tipos de entidades relevantes en el documento
2. Segundo paso: Extraer cada tipo con contexto
3. Tercer paso: Validar no hay duplicados o contradicciones
4. Devolver JSON estructurado
```

---

### 2.5 Entidades personalizadas — Domain-specific NER

Combinación de técnicas para tipos de entidades relevantes a Epic Analyzer:

| Tipo | Técnica | Ejemplo |
|------|---------|---------|
| **RUT/Tax ID** | Regex + validación checksum | `12.345.678-9` |
| **Email** | Regex + DNS lookup (opcional) | `user@domain.com` |
| **Teléfono** | Regex con formatos locales | `+56 2 2123 4567` |
| **Fecha** | DateParser + normalización | `2024-05-15`, `15 de mayo de 2024` |
| **Monto** | Regex + moneda + normalización | `$50,000 CLP`, `€1.200,50` |
| **Relaciones** | Patrón mencionado (x asociado a y) | `factura #INV-2024-001 para Acme Corp` |

---

### 2.6 Técnicas avanzadas de NER

#### **Few-Shot Learning con LLMs**
Agregar ejemplos al prompt para mejorar resultados sin fine-tuning:

```
Ejemplos:
- "Acme Corp LLC" → ORG
- "Juan Pérez Silva" → PER
- "Av. Libertador 500" → LOC

Ahora extrae del siguiente texto...
```

**Beneficio**: Mejora recall/precision ~10-20% vs zero-shot.

---

#### **Entity Linking (Desambiguación)**
Una vez identificadas entidades, vincularlas a bases de conocimiento:

```
NER output: [PER: "Apple"]
Entity Linking: ¿Es la persona o la empresa Apple Inc?
→ Consultar contexto, Google Knowledge Graph
→ Devolver: ORGANIZATION (Apple Inc)
```

**Herramientas**:
- `spaCy` + `spacy-transformers` (acceso a Wikipedia)
- Google Knowledge Graph API
- DBpedia Lookup

---

#### **Relational NER (Information Extraction)**
Extraer no solo entidades, sino relaciones entre ellas:

```
Texto: "Juan Pérez (CEO de Acme Corp) emitió una factura"

Entidades: PER: Juan Pérez, ORG: Acme Corp
Relaciones: 
  - juan_perez --[works_for]--> acme_corp
  - juan_perez --[role:CEO]--> acme_corp
  - juan_perez --[issued]--> factura
```

**Técnicas**:
- Dependency parsing + reglas
- Joint NER + RE (tareas simultáneas)
- Semantic role labeling (SRL)

---

## 3. Soluciones del mercado

### 3.1 spaCy — Librería Python estándar

**Características**:
- Pipelines pre-entrenadas para múltiples idiomas
- Modelos `sm` (pequeño, rápido), `md` (mediano), `lg` (grande, preciso)
- Integración con `transformers` de HuggingFace
- Entidad linking integrado

**Modelos disponibles** (español):
- `es_core_news_sm` — 11.5 MB, F1 ~0.74
- `es_core_news_md` — 37 MB, F1 ~0.81
- `es_core_news_lg` — 46 MB, F1 ~0.84

```python
import spacy
nlp = spacy.load("es_core_news_lg")
doc = nlp("Juan Pérez trabaja en Acme Corp.")
for ent in doc.ents:
    print(ent.text, ent.label_)
```

**Ventajas**:
- ✅ Documentación excelente
- ✅ Comunidad grande
- ✅ Rápido en CPU
- ✅ Bajo overhead (sin API remota)

**Desventajas**:
- ⚠️ Modelos pre-entrenados generales (bajo recall en dominios específicos)
- ❌ Entidades limitadas (PER, ORG, LOC, MISC)
- ⚠️ Requiere fine-tuning para mejora significativa

**Costo**: Libre y open source

---

### 3.2 Hugging Face Transformers + Token Classification

**Modelos pre-entrenados para NER**:
- `dslim/bert-base-multilingual-cased-ner` — Multiidioma
- `flair/ner-english-ontonotes` — Inglés, alta calidad
- `xlm-roberta-large-finetuned-conllxx-english` — XLM-RoBERTa fine-tuned

```python
from transformers import AutoTokenizer, AutoModelForTokenClassification, pipeline

model_name = "dslim/bert-base-multilingual-cased-ner"
nlp = pipeline("ner", model=model_name)

results = nlp("Juan Pérez trabaja en Acme Corp.")
for entity in results:
    print(entity)
```

**Ventajas**:
- ✅ Precisión muy alta (~F1 0.85+)
- ✅ Fácil fine-tuning en corpus específico
- ✅ Comunidad enorme, modelos nuevos constantemente

**Desventajas**:
- ❌ Latencia 100-500ms en CPU, 10-50ms en GPU
- ❌ Requiere GPU para producción
- ⚠️ Overhead de memoria (modelos grandes)

**Costo**: Libre y open source; solo requiere GPU (costo infra)

---

### 3.3 Azure Text Analytics / AWS Comprehend

**Características** (Azure):
- API REST para NER
- Modelos pre-entrenados en 12+ idiomas
- Análisis de sentimiento, entidades, PII integrados
- Enterprise SLA

```bash
curl -X POST "https://{region}.tagger.cognitiveservices.azure.com/text/analytics/v3.1/entities/recognition/general" \
  -H "Ocp-Apim-Subscription-Key: {key}" \
  -d "{\"documents\": [{\"language\": \"es\", \"id\": \"1\", \"text\": \"Juan Pérez\"}]}"
```

**Ventajas**:
- ✅ Managed service — sin infraestructura
- ✅ Alta disponibilidad, escalabilidad probada
- ✅ Múltiples analíticas integradas (PII, sentimiento, etc.)

**Desventajas**:
- ❌ Costo: $1-2 por 1000 registros
- ❌ Vendor lock-in
- ⚠️ Latencia ~500ms-1s (API remota)

**Costo aproximado**: $500-2000/mes para corpus mediano (100k docs/mes)

---

### 3.4 Google Cloud Natural Language API

**Características**:
- API REST con entity recognition
- Entidades pre-definidas: PER, ORG, LOC, EVENT, PRODUCT, etc.
- Análisis de sentimiento, syntax

```bash
curl -X POST https://language.googleapis.com/v2/analyzeEntities \
  -H "Content-Type: application/json" \
  -d '{
    "document": {"content": "Juan trabaja en Acme", "language": "ES"},
    "encodingType": "UTF8"
  }' \
  -H "Authorization: Bearer {access_token}"
```

**Ventajas**:
- ✅ Calidad muy alta (BERT based back-end)
- ✅ Integración con Google Cloud ecosystem

**Desventajas**:
- ❌ Costo: $1 por 1000 requests
- ❌ Latencia 200-500ms

---

### 3.5 OpenAI GPT / Anthropic Claude (LLM prompting)

**API**:
```python
import openai

response = openai.ChatCompletion.create(
    model="gpt-4-turbo",
    messages=[{
        "role": "user",
        "content": f"Extract entities from: {text}"
    }]
)
```

**Ventajas**:
- ✅ Máxima flexibilidad (custom entity types)
- ✅ Zero-shot, no necesita entrenamiento
- ✅ Excelente para casos complejos

**Desventajas**:
- ❌ Muy caro: $0.01-0.15 por 1000 tokens
- ❌ Latencia 1-3s
- ❌ Rate limiting

**Estimado de costos**:
- 100k documentos × 500 tokens promedio = 50M tokens
- GPT-4: $50M × $0.015 / 1M = **$750**
- Claude 3.5: $50M × $0.003 / 1M = **$150**

---

### 3.6 Fusión: Gemini (estado actual de Epic Analyzer)

**Ya implementado**: Gemini Flash para clasificación y extracción de `emisor`, `receptor`, `monto_total`.

**Opción**: Extender el prompt de Gemini para también extraer NER generalizada.

**Ventajas adicionales**:
- ✅ Ya integrado en Epic Analyzer
- ✅ Barato comparado con GPT-4 (~$0.0375 por 1M input tokens)
- ✅ Multiidioma
- ✅ Rápido (Flash)

**Desventajas**:
- ⚠️ Requiere agregar lógica al prompt
- ⚠️ Costo acumulativo si se usan embeddings + clasificación + NER

---

## 4. Comparativa arquitectónica para Epic Analyzer

| Aspecto | spaCy (local) | BERT fine-tune | Gemini (LLM) | Azure API |
|--------|---------------|---------------|------------|-----------|
| **Precision (F1)** | ⭐⭐⭐ (0.74-0.84) | ⭐⭐⭐⭐⭐ (0.85-0.92) | ⭐⭐⭐⭐ (0.80-0.90) | ⭐⭐⭐⭐ (0.82-0.88) |
| **Latencia** (ms/doc) | 10-50 | 100-500 | 1000-3000 | 500-1000 |
| **Tipos entidades** | 4 (PER,ORG,LOC,MISC) | Configurable | Ilimitadas (custom) | 10+ pre-definidas |
| **Costo infra** | 💚 Bajo (~200/mes GPU) | 💚 Bajo (~200/mes GPU) | 💰 Medio (~0.50-1.00$50-500/mes) | 🔴 Alto ($500-2000+/mes) |
| **Implementación** | ✅ Trivial | ⚠️ Media (fine-tune) | ✅ Fácil (prompt) | ⚠️ Media (API setup) |
| **Mantenimiento** | ✅ Bajo | ⚠️ Medio (reentrenamiento) | ✅ Bajo | ✅ Bajo |
| **Customización** | ⚠️ Limitada | ✅ Alta | ✅ Alta | ⚠️ Media |
| **Sin GPU** | ❌ Lento (50-100ms/doc) | ❌ Muy lento (1-5s/doc) | ✅ Funciona | ✅ Funciona |

---

## 5. Casos de uso específicos en Epic Analyzer

### 5.1 Extracción de contactos

**Tipos de entidades requeridas**:
- `PERSON`: Nombres de personas
- `ORGANIZATION`: Empresas, instituciones
- `EMAIL`: Direcciones de correo
- `PHONE`: Números telefónicos
- `ADDRESS`: Direcciones postales
- `TAX_ID` / `RUT`: Identificadores fiscales

**Entidades personalizadas para documentos contables**:
```
"La factura #INV-2024-0001 fue emitida por ACME Corp. 
(RUT: 12.345.678-9, contacto: Juan Pérez, juan@acme.cl, +56 22123 4567)"

Output esperado:
{
  "document_id": "INV-2024-0001",
  "organization": "ACME Corp.",
  "rut": "12345678-9",
  "contact_person": "Juan Pérez",
  "email": "juan@acme.cl",
  "phone": "+56 22 1234567"
}
```

**Recomendación arquitectónica**:
- Layer 1: Regex para RUT, email, teléfono (alta precisión, bajo costo)
- Layer 2: spaCy para PER/ORG previos (rápido, sin GPU)
- Layer 3: Complementar con Gemini para contexto complejo

---

### 5.2 Base de datos de contactos

**Estructura propuesta**:
```python
# backend/app/models/schemas.py

class ContactRecord(BaseModel):
    """Entidad de contacto extraída del corpus"""
    contact_id: str  # UUID
    name: str  # Nombre de persona u organización
    type: Literal["PERSON", "ORGANIZATION", "LOCATION"]
    email: Optional[str]
    phone: Optional[str]
    address: Optional[str]
    rut: Optional[str]
    frequency: int  # Cuántos documentos mencionan este contacto
    first_seen: datetime
    last_seen: datetime
    documents: List[str]  # Job IDs donde aparece
    metadata: Dict[str, Any]  # Información adicional
    confidence: float  # 0-1, confianza de la extracción
```

**Endpoint propuesto**:
```
GET /api/reports/{job_id}/contacts
GET /api/reports/{job_id}/contacts?type=PERSON&limit=50
GET /api/contacts/search?email=juan@acme.cl
POST /api/contacts/bulk-export
```

---

### 5.3 Entity Linking a base de conocimiento interna

Vincular contactos extraídos a CRM o base de conocimiento:

```
Juan Pérez (encontrado en 5 facturas) → Posible cliente/proveedor
→ Buscar en CRM interno
→ Si existe en CRM: actualizar frecuencia
→ Si no existe: sugerir crear registro
```

---

## 6. Roadmap de implementación para Epic Analyzer

### Fase 1 — Corto plazo (2-3 semanas) ⚡

**Opción recomendada**: **Combinación de regex + Gemini extendido**

```
1. Agregar tipos de entidades al esquema DocumentMetadata:
   - named_entities: List[Entity]
   - contact_records: List[ContactRecord]

2. Extender prompt de Gemini para incluir NER:
   - Mantener campos actuales (emisor, receptor, etc.)
   - Agregar extracción de: PERSON, ORG, EMAIL, PHONE, DATE, MONEY
   - Devolver JSON estructurado

3. Parser simple para procesar respuesta de Gemini:
   - Mapear entidades a DocumentMetadata
   - Normalizar formatos (teléfono, email)

4. Endpoint GET /api/reports/{job_id}/contacts (lectura simple)
```

**Esfuerzo**: ~4-6 horas  
**Costo**: Marginal (tokens Gemini ya usados)  
**ROI**: Acceso a contactos sin infraestructura adicional

---

### Fase 2 — Mediano plazo (4-8 semanas) 🔄

**Upgrade opcional**: **spaCy local + Gemini complementario**

```
1. Instalar modelo spaCy para español:
   python -m spacy download es_core_news_lg

2. Pipeline dual:
   - spaCy para extracción rápida (PER, ORG, LOC)
   - Gemini solo para contexto complejo / desambiguación
   - Fusionar resultados

3. Crear tabla en base de datos (si se implementa PostgreSQL):
   - contacts (id, name, type, email, phone, etc.)
   - contact_mentions (contact_id, job_id, document_id, context)
   - Indexar para búsqueda rápida

4. Endpoint GET /api/contacts/search?email=...
5. Tabla en frontend: "Contactos encontrados"
```

**Esfuerzo**: 1-2 sprints  
**Costo infra**: ~200/mes GPU (si se quiere acelerar)  
**Beneficio**: 20-50% más rápido, mejor recall local

---

### Fase 3 — Largo plazo (3+ meses) 🚀

**Full NER + Entity Linking avanzado**

```
1. Fine-tune BERT/RoBERTa en corpus específico (si hay datos etiquetados)
2. Implementar entity linking a:
   - CRM interno
   - Google Knowledge Graph
   - DBpedia
3. Grafo de relaciones: entidad → entidad
4. Búsqueda por grafo: "¿Con qué empresas trabajó Juan Pérez?"
```

---

## 7. Técnicas emergentes (2024)

### 7.1 RAG-based NER
Usar Retrieval-Augmented Generation para mejorar NER:

```
1. Recuperar documentos similares del corpus que mencionen la misma entidad
2. Usar como contexto para desambiguación
3. Refinar extracción basada en patrón histórico

Ejemplo: Si "Apple" aparece en contexto de "IT", más probable que sea: ORGANIZATION
vs en contexto de "frutas", probable: PRODUCT
```

---

### 7.2 Active Learning para NER
Modelo que aprende de las correcciones del usuario:

```
1. Gemini extrae entidades iniciales (baja confianza en nuevos tipos)
2. Usuario revisa y etiqueta en frontend
3. Acumular feedback
4. Re-entrenar modelo (fine-tune) con nueva data etiquetada
5. Mejorar recall/precision progresivamente
```

---

## 8. Limitaciones y desafíos identificados

### 8.1 Multiidioma
Documentos en español, inglés, portugués.
- **spaCy**: Modelos separados por idioma
- **BERT multiidioma**: Un modelo para todos
- **Gemini**: Multiidioma nativo (recomendado)

### 8.2 Entidades ambiguas
```
"Banco Central" — ¿Organización o Ubicación?
"Apple" — ¿Empresa o fruta?
"Libertad, SA" — ¿Ubicación o nombre empresa?
```

**Solución**: Usar contexto (embeddings del doc), entity linking a KB.

### 8.3 Dominios específicos
RUT, códigos internos, nomenclatura de empresas chilenas.
- Requiere custom entidades + entrenamiento

### 8.4 Normalización de formatos
```
Teléfono: "+56-2-2123-4567", "56 22123 4567", "2 2123 4567"
→ Necesita parser localizado
Email: "juan.perez@acme.cl", "jperez@acme.cl"
→ Deduplicar (posible la misma persona)
RUT: "12.345.678-9", "12345678-9", "12345678"
→ Normalizar y validar checksum
```

---

## 9. Referencias y recursos

### Papers clave
- Devlin et al. (2018) — "BERT: Pre-training of Deep Bidirectional Transformers" (Google)
- Ma & Hovy (2016) — "End-to-end Sequence Labeling via Bi-directional LSTM-CNNs-CRF" (CMU)
- Lample et al. (2016) — "Neural Architectures for Named Entity Recognition"

### Librerías recomendadas
- **spaCy**: `pip install spacy` — https://spacy.io
- **Hugging Face Transformers**: `pip install transformers` — https://huggingface.co
- **PyTorch**: `pip install torch` — https://pytorch.org
- **Named Entity Recognition libraries**:
  - `flair` — https://github.com/flairNLP/flair
  - `stanza` (Stanford NLP) — https://stanfordnlp.github.io/stanza/
  - `textacy` — wrapper sobre spaCy

### Datasets públicos para entrenamiento
- CoNLL-2002/2003 (inglés, español, holandés, alemán)
- SQuAD 2.0 (para preguntas)
- WikiNER (Wikipedia NER, multiidioma)
- SEC Filings (corpus financiero, inglés)

### Tutoriales online (2024)
- HuggingFace Course — "Named Entity Recognition" (https://huggingface.co/course)
- spaCy 101 — Advanced NER
- Kaggle NER competitions (datos anotados, benchmarks)

---

## 10. Decisión recomendada para Epic Analyzer

### ✅ Estrategia propuesta: **Gramínea híbrida de 3 capas**

```
                    ┌─────────────────────────────┐
                    │  Gemini Flash (LLM)         │
                    │  • Contexto complejo        │
                    │  • Entidades ambiguas       │
                    │  • Custom types             │
                    └────────────┬────────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │   spaCy (local)        │
                    │   • PER, ORG, LOC      │
                    │   • Rápido (~10ms)     │
                    │   • CPU-friendly       │
                    └────────────┬────────────┘
                                 │
                    ┌────────────┴────────────┐
                    │   Regex Patterns       │
                    │   • Email, Phone       │
                    │   • RUT, Fechas        │
                    │   • 100% precisión     │
                    └────────────┬────────────┘
                                 │
                          ┌──────┴──────┐
                          │  Deduplicar │
                          │  Normalizar │
                          │  Vincular   │
                          └──────┬──────┘
                                 │
                    ┌────────────┴────────────┐
                    │ ContactRecords DB       │
                    │ (frecuencia, docs)      │
                    └────────────────────────┘
```

**Implementación**:

**Fase 1 (inmediato)**:
- [ ] Extender schema DocumentMetadata con `named_entities` y `contact_records`
- [ ] Agregar regex para: email, teléfono, RUT, fechas
- [ ] Extender prompt de Gemini con tipos NER (PERSON, ORG, EMAIL, PHONE, DATE)
- [ ] Parser para normalizar y estructurar respuesta de Gemini
- [ ] Endpoint GET `/api/reports/{job_id}/contacts`

**Esfuerzo**: 4-6 horas  
**Costo**: Negligible (tokens Gemini ya usados)

**Fase 2 (opcional, si corpus crece)**:
- [ ] Integrar spaCy para extracción local rápida
- [ ] Fusionar resultados (spaCy + Gemini)
- [ ] Tabla de contactos en base de datos

**Esfuerzo**: 1-2 sprints  
**ROI**: +30-50% en recall, -60% en latencia

---

## Conclusión

**NER en Epic Analyzer hoy**:
1. ✅ **Leverage Gemini** — ya está integrado, agregar tipos de entidades al prompt
2. ✅ **Regex para precisión** — email, RUT, teléfono (100% recall en formatos conocidos)
3. ⏳ **Opcional: spaCy** — cuando corpus crezca o latencia sea crítica
4. 🔮 **Futuro: Entity Linking** — vincular a CRM o knowledge graph

**Stack recomendado**:
```
Backend: Gemini (extracción) + Python regex (normalización) + spaCy (complementario)
Frontend: Tabla de contactos + búsqueda + deduplicación visual
DB: Si PostgreSQL se implementa, tabla `contacts` + índices
```

**Prioridad**: Baja-media. Puede hacerse post-ranking y filtrado de binarios, no bloquea funcionalidad principal.

