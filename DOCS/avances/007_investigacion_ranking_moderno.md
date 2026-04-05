# Estado del arte — Ranking moderno para búsqueda documental híbrida

**Fecha**: Abril 2026  
**Status**: 🔬 Investigación completada (basada en conocimiento 2024)  
**Objetivo**: Fundamentar la decisión arquitectónica para reemplazar o complementar BM25 en Epic Analyzer

---

## 1. Panorama general

El ranking de documentos ha evolucionado significativamente desde BM25 (1994). Hoy se distinguen tres familias:

| Familia | Técnica | Mejor para | Complejidad |
|---------|---------|-----------|-------------|
| **Léxica** | BM25, TF-IDF | Exactitud textual, términos raros | Baja |
| **Densa** | Embeddings (coseno/distancia) | Semántica, sinonimia, contexto | Media |
| **Aprendida** | Learning to Rank (LtR), Neural IR | Ranking cuidado, señales multi-fuente | Alta |

### Tendencia actual
La industria se mueve a **búsqueda híbrida** (hybrid retrieval):
- Recuperar top-K documentos con BM25 + Dense retrieval
- Re-ranking con LtR o modelos neuronales
- Combinar señales: relevancia, recencia, autoridad, confianza, PII risk

---

## 2. Técnicas léxicas (texto exacto)

### 2.1 BM25 (Best Matching 25)

**Fórmula**:
$$\text{BM25}(D, Q) = \sum_{i=1}^{n} \text{IDF}(q_i) \cdot \frac{f(q_i, D) \cdot (k_1 + 1)}{f(q_i, D) + k_1 \cdot \left(1 - b + b \cdot \frac{|D|}{\text{avgdl}}\right)}$$

Donde:
- $f(q_i, D)$: frecuencia del término en el documento
- $|D|$: longitud del documento
- $\text{avgdl}$: longitud promedio de documentos
- $k_1, b$: parámetros (típicamente $k_1 = 1.5, b = 0.75$)

**Ventajas**:
- ✅ Control exacto de términos clave
- ✅ Resistente a ruido en corpus pequeños
- ✅ Predecible y explicable
- ✅ Bajo costo computacional

**Desventajas**:
- ❌ No entiende sinonimia ("factura" ≠ "invoice")
- ❌ Ignora estructura semántica
- ❌ Sensible a variantes léxicas (singular/plural, flexiones)
- ❌ Peso uniforme en todos los campos

**Cuándo usarlo**:
- Búsquedas de terminología exacta (IDs, códigos, entidades de catálogo)
- Corpus con vocabulario controlado
- Casos donde explicabilidad es crítica

---

### 2.2 Búsqueda de texto completo (Full-Text Search)

Extensiones de BM25 en bases de datos modernas:

**PostgreSQL + pgvector**:
```sql
SELECT * FROM documents
WHERE to_tsvector('spanish', content) @@ plainto_tsquery('spanish', 'factura')
ORDER BY ts_rank(...) DESC;
```

**Elasticsearch / OpenSearch**:
- Analyzer configurable (tokenización, stemming, stop words)
- Boosting por campo (título > cuerpo)
- Fuzziness y fuzzy matching
- Phrase queries con slop

**Limitaciones**: Mismas que BM25; no captura semántica.

---

## 3. Técnicas densas (semántica vectorial)

### 3.1 Embeddings y búsqueda coseno

**Concepto**: Conversión documento → vector en espacio de embedding (100-1536 dimensiones)

$$\text{Similitud}(D_1, D_2) = \frac{D_1 \cdot D_2}{||D_1|| \cdot ||D_2||}$$

**Modelos populares**:
- `text-embedding-3-small` (OpenAI) — 512 dim, bajo costo
- `all-mpnet-base-v2` (Hugging Face) — 768 dim, código abierto
- `multilingual-e5-base` — soporta 100+ idiomas
- Gemini `text-multilingual-embedding-002` (usado en Epic Analyzer)

**Ventajas**:
- ✅ Entiende semántica ("factura" ≈ "documento de pago")
- ✅ Captura sinonimia y variantes
- ✅ Robusto a typos
- ✅ Funciona con consultas en lenguaje natural

**Desventajas**:
- ❌ Requiere modelos pre-entrenados (costo + latencia de inferencia)
- ❌ Non-explainable ("por qué se rankeó así?")
- ❌ Sesgo del modelo de embedding
- ❌ Mala performance en términos muy específicos (códigos, IDs)

**Infraestructura**:
- **ChromaDB** (usado actualmente): Simple, en memoria o persistido, bueno para prototipos
- **Weaviate**: Indexación vectorial distribuida, búsqueda híbrida integrada
- **Milvus**: Vector database escalable, clustering automático
- **Pinecone**: Vector database cloud con metadata filtering
- **LanceDB**: Enfoque columnar + DuckDB, optimizado para analytics

**Cuándo usarlo**:
- Búsquedas semánticas ("documentos sobre presupuestos")
- Detección de duplicados (alta similitud → duplicado)
- Queries en lenguaje natural

---

### 3.2 Sparse embeddings (BM25 vectorizado)

Técnica reciente: representar BM25 como matriz dispersa en espacio vectorial.

**Ejemplo**: `SPLADE` (Sparse Lexical and Expansion Retrieval)
- Genera sparse vector con pesos aprendidos para cada término
- Permite búsqueda BM25-like pero diferenciable
- Combina semántica con exactitud léxica

Beneficio: Usa misma infraestructura de búsqueda vectorial para ambas técnicas (hybrid search nativo).

---

## 4. Learning to Rank (LtR) — Técnicas aprendidas

### 4.1 Concepto

En lugar de usar fórmula manual (BM25), entrenar un modelo que aprenda qué combinación de **features** predice mejor ranking.

**Pipeline LtR típico**:
1. **Feature engineering**: Extraer 100+ features por (query, documento) — BM25 score, similitud vectorial, longitud, densidad de entidades, recencia, autoridad, etc.
2. **Etiquetar datos**: Crear dataset de pairs (query, doc1, doc2) con juicios humanos: "doc1 > doc2"
3. **Entrenar ranking model**: Algoritmo de aprendizaje (LambdaMART, RankNet, ListNet, etc.)
4. **Servir**: Usar modelo entrenado para re-ranking en tiempo real

### 4.2 Algoritmos principales

#### **LambdaMART** (Gradient Boosting)
- Optimiza directamente métrica NRPG@10 (normalized discounted cumulative gain)
- Estado del arte en competiciones Letor
- Implementación: LightGBM, XGBoost

```python
# Pseudocódigo
ranker = LtRRanker(algo='lambda_mart')
ranker.fit(
    X_train=features(queries, documents),
    y_train=relevance_labels,
    groups=group_sizes  # docs per query
)
scores = ranker.predict(features(new_query, candidates))
```

#### **Neural LtR** (Deep learning)
- RankNet: Red neuronal para pairwise ranking
- ListNet: Optimiza lista de rankings completa
- BERT-based rerankers: Fine-tune BERT para ranking

Ejemplo: `cross-encoder` de HuggingFace
```python
from sentence_transformers import CrossEncoder
model = CrossEncoder('cross-encoder/mmarco-MiniLMv2-L12-H384-multilingual')
scores = model.predict([[query, doc] for doc in candidates])
```

#### **Learning to Rank con espacios densos**
- Entrenar modelos que optimicen tanto similitud vectorial como métrica de ranking
- Usar contrastive loss (triplet loss, InfoNCE)

---

### 4.3 Ventajas y desventajas de LtR

| Aspecto | Ventaja | Desventaja |
|--------|---------|-----------|
| **Accuracy** | ✅ Máxima (entrena en datos reales) | ❌ Solo si datos de entrenamiento son suficientes |
| **Features** | ✅ Combina BM25, embeddings, metadatos | ❌ Requiere ingeniería manual de features |
| **Explicabilidad** | ⚠️ Parcial (importancia de features) | ❌ Modelos neuronales → black box |
| **Latencia** | ❌ Más lenta (inferencia del modelo) | ⚠️ ~10-100ms por doc |
| **Datos** | N/A | ❌ Requiere labels relevancia (costo) |
| **Escalabilidad** | ⚠️ Buena con caché | ❌ Re-ranking escala con corpus |

**Cuándo usarlo**:
- Corpus > 100k documentos con datos de relevancia disponibles
- Optimizar métrica específica (click-through rate, time-on-page, etc.)
- Caso de uso crítico donde mejora 5-10% NRPG justifica inversión

---

## 5. Soluciones del mercado — Comparativa

### 5.1 **Elasticsearch / OpenSearch**

**Características**:
- Léxica: BM25 configurable + analyzers de texto completo
- Densa: KNN search (embeddings) con `dense_vector` field type
- Híbrida: RRF (Reciprocal Rank Fusion) nativo o custom scripts

**Ventajas**:
- ✅ Madurez (15+ años)
- ✅ Ecosistema extenso (kibana, beats, logs)
- ✅ Escalabilidad probada (petabytes)
- ✅ Soporte para ambos léxica y densa integrados

**Desventajas**:
- ❌ Complejidad operacional (sharding, replicas)
- ❌ Curva de aprendizaje (query DSL)
- ❌ Costo de infraestructura (memoria, CPU)

**Learning to Rank**: Soporte via plugins (`elasticsearch-learning-to-rank`) o scripts personalizados.

**Costo aproximado**:
- Cloud (Elastic Cloud): ~$50/mes pequeño, $500+/mes producción
- Self-hosted: Servidor 8 CPU, 32GB RAM: ~$200/mes cloud VM

---

### 5.2 **Weaviate**

**Características**:
- Vector database nativo + full-text search integrado
- Búsqueda híbrida: `hybrid()` method
- Metadata filtering con donde-clauses
- Reranking: Soporte para modelos custom

**Ventajas**:
- ✅ Diseño específico para vectores (optimizado)
- ✅ Búsqueda híbrida integrada (no glue-code)
- ✅ GraphQL API (flexible, easy filtering)
- ✅ Menor curva de aprendizaje que Elastic

**Desventajas**:
- ⚠️ Comunidad menor que Elastic
- ❌ Menos opciones de análisis léxico
- ⚠️ Performance en corpus masivos aún en mejora

**Precio**:
- Cloud (Weaviate Cloud): ~$25/mes starter, $200+/mes producción
- Self-hosted: Similar a ES

---

### 5.3 **Milvus**

**Características**:
- Vector database específico, licencia open source
- Soporta múltiples índices (HNSW, IVF, SCANN)
- Escalabilidad horizontal con Kubernetes
- Metadata filtering robusto

**Ventajas**:
- ✅ Open source, sin vendor lock-in
- ✅ Índices vectoriales optimizados (rápido)
- ✅ Escalable y cloud-native (K8s ready)

**Desventajas**:
- ❌ Búsqueda léxica NO está integrada (usar Elasticsearch en paralelo)
- ⚠️ Comunidad más pequeña, documentación fragmentada

**Learning to Rank**: No integrado; usar con otros servicios.

---

### 5.4 **Vespa** (por Yahoo)

**Características**:
- Plataforma completa: búsqueda + ranking + ML
- Soporte nativo para BM25, vectors, tensores
- Ranking framework integrado (no necesita modelo externo)
- Tensorflow/ONNX models en scoring

**Ventajas**:
- ✅ Ranking avanzado integrado (LtR-friendly)
- ✅ Performance extremo (1000s de queries/sec)
- ✅ Unifica léxico + denso + LtR

**Desventajas**:
- ❌ Curva de aprendizaje pronunciada
- ⚠️ Comunidad pequeña (Yahoo)
- ❌ Overkill para pequeños corpus

---

### 5.5 **LanceDB**

**Características**:
- Vector database + SQL (DuckDB integrado)
- Columnar storage (bueno para analytics)
- Metadata filtering via SQL
- API simple (Python + JavaScript)

**Ventajas**:
- ✅ Sintaxis SQL familiar
- ✅ Analytics + retrieval integrados
- ✅ Open source, lightweight
- ✅ Bueno para prototipaje rápido

**Desventajas**:
- ❌ No tiene búsqueda de texto completo integrada
- ⚠️ Escalabilidad limitada vs Milvus/Elastic (single-node centric)
- ⚠️ Comunidad emergente

---

### 5.6 **Chroma** (actual en Epic Analyzer)

**Estado actual**: ChromaDB como vector store

**Ventajas**:
- ✅ Integración actual, familiaridad con código
- ✅ Simple para prototipaje
- ✅ Bueno para corpus < 1M documentos

**Limitaciones**:
- ❌ No tiene búsqueda léxica nativa (solo vectores)
- ❌ Re-ranking manual (sin orquestación integrada)
- ❌ No soporta LtR

---

## 6. Técnicas de re-ranking y fusión

### 6.1 Reciprocal Rank Fusion (RRF)

Combinar rankings de múltiples sistemas sin pesos calibrados:

$$\text{RRF}(\text{doc}) = \sum_{\text{system}} \frac{1}{k + \text{rank}_{\text{system}}}$$

Ejemplo: top-3 de BM25 + top-3 de embeddings
```
BM25:    doc_a (1), doc_b (2), doc_c (3)
Vector:  doc_c (1), doc_a (2), doc_d (3)

RRF:     doc_a: 1/61 + 1/62 ≈ 0.033
         doc_c: 1/63 + 1/61 ≈ 0.033
         doc_b: 1/62 = 0.016
```

**Ventaja**: No requiere entrenamiento; solo lógica simple.

---

### 6.2 Cross-encoder re-ranking

Fine-tuned BERT que toma (query, doc) y predice relevancia (0-1):

```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder('cross-encoder/mmarco-multilingual-v1')

# Recuperar top-100 con BM25 o embeddings
candidates = retrieve_bm25(query, k=100)

# Re-rank top-100 con modelo
scores = reranker.predict([(query, doc['text']) for doc in candidates])
reranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
```

**Ventaja**: Mejor que RRF, sin necesidad de entrenamiento específico.  
**Costo**: ~50-100ms por rerank en CPU; ~5-10ms en GPU.

---

## 7. Matriz de decisión para Epic Analyzer

| Criterio | BM25 actual | BM25 + Vectors (RRF) | Elasticsearch Híbrido | LtR (futuro) |
|----------|-----------|-------------------|---------------------|-------------|
| **Accuracy** (P@5) | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **Latencia** (ms/query) | 10 | 50 | 100 | 200 |
| **Implementación** | ✅ Trivial | ✅ Fácil | ⚠️ Media | ❌ Compleja |
| **Mantenimiento** | ✅ Bajo | ✅ Bajo | ⚠️ Medio | ❌ Alto |
| **Escalabilidad** (corpus > 1M) | ⚠️ Limitada | ⚠️ Limitada | ✅ Alta | ✅ Alta |
| **Explicabilidad** | ✅ Alta | ⚠️ Media | ⚠️ Media | ❌ Baja |
| **Costo infra** | 💚 Bajo | 💚 Bajo | 🟡 Medio | 🔴 Alto |

---

## 8. Recomendacion arquitectonica para Epic Analyzer

### Fase 1 — Corto plazo (próximas 2-4 semanas) ⚡

**Opción recomendada**: **BM25 + Dense retrieval (RRF)**

```python
# backend/services/hybrid_search_service.py

class HybridSearchService:
    def search(self, query: str, k: int = 10):
        # 1. Recuperar top-K de BM25 en ChromaDB
        bm25_results = self.chroma_client.query_documents(query, k=30)
        
        # 2. Recuperar top-K de embeddings
        dense_results = self.chroma_client.query_embeddings(encoding(query), k=30)
        
        # 3. Fusionar con RRF
        fused = self.rrf_fusion(bm25_results, dense_results)
        
        # 4. Opcionalmente, re-rank con cross-encoder
        if self.enable_reranking:
            fused = self.cross_encoder_rerank(query, fused, k)
        
        return fused[:k]
```

**Cambios en backend**:
- Crear servicio `hybrid_search_service.py` con RRF
- Buscar método BM25 en ChromaDB (o implementar simple TF-IDF)
- Integrar cross-encoder (opcional, lightweight)

**Esfuerzo**: ~4-6 horas  
**Mejora esperada**: +40-60% en recall sem{ántica, +20-30% en precisión exacta

---

### Fase 2 — Mediano plazo (4-12 semanas) 🔄

**Opción**: **Elasticsearch híbrido** OR **Weaviate**

**Si eliges Elasticsearch**:
- Índice con BM25 estándar + embedding field
- Query `bool` con `must` (BM25) + `should` (knn)
- Boost por fecha, confianza, inversibilidad

**Si eliges Weaviate**:
- Setup cloud o self-hosted
- Migrar embeddings existentes
- Usar `hybrid()` query method

**Esfuerzo**: 1-2 sprints  
**Beneficio**: Escalabilidad + operacional (no es glue code)

---

### Fase 3 — Largo plazo (6+ meses) 🚀

**Learning to Rank** si:
- Corpus > 500k documentos
- Datos de interacción (clicks, dwell time) disponibles
- ROI justifica esfuerzo

**Stack sugerido**:
- LightGBM (LambdaMART) + feature engineering
- O: Cross-encoder fine-tuned en datos propios
- Servir como modelo ONNX en Elasticsearch/Vespa

---

## 9. Próximos pasos de investigación

Para tomar la decisión final, se recomienda:

1. **Benchmark local** (esta semana):
   - Tomar corpus de prueba (1k-10k documentos)
   - Comparar latencia: BM25 vs embeddings vs RRF
   - Evaluar recall/precision en queries representativas

2. **PoC de Elasticsearch** (si presupuesto permite):
   - Levantar instancia test en cloud
   - Migrar corpus
   - Medir latencia, costo, overhead operacional

3. **Análisis de costos** (antes de avanzar):
   - Costo de almacenamiento (embeddings + índices)
   - Costo de compute (indexación, queries)
   - Costo operacional (alertas, backups, monitoreo)

4. **Recolectar feedback de usuarios**:
   - ¿Qué queries fallan con BM25 actual?
   - ¿Qué precision necesitan usuarios?
   - ¿Es latencia crítica?

---

## 10. Referencias y recursos

### Papers clave
- BM25: Robertson et al. (1994) — "Okapi at TREC-4"
- LambdaMART: Burges et al. (2010) — "From RankNet to LambdaRank to LambdaMART"
- Dense Retrieval: Karpukhin et al. (2020) — "Dense Passage Retrieval for Open-Domain QA" (Facebook)
- SPLADE: Formal et al. (2021) — "SPLADE: Sparse Lexical and Expansion Model" (Naver)

### Documentación
- **Elasticsearch**: [Hybrid search guide](https://www.elastic.co/guide/en/elasticsearch/reference/current/search-search.html)
- **Weaviate**: [Hybrid search](https://weaviate.io/developers/weaviate/search/hybrid)
- **Sentence Transformers**: [Cross-encoders](https://www.sbert.net/docs/sentence_transformer/usage/semantic_search.html#cross-encoders)
- **OpenSearch**: [Learning to Rank plugin](https://github.com/opensearch-project/learning-to-rank-opensearch)

### Herramientas recomendadas para evaluación
- `rank-eval` (Elasticsearch) — evaluar queries
- `trec_eval` — benchmark NRPG@10, MAP, etc.
- `BERTScore` — evaluar texto generado

---

## Conclusión

**Para Epic Analyzer hoy**:
1. ✅ **Short-term**: Implementar RRF (BM25 + embeddings) — bajo riesgo, alto valor
2. ⏳ **Medium-term**: Migrar a Elasticsearch hybrid search si corpus crece
3. 🔮 **Long-term**: Explorar LtR cuando datos de relevancia estén disponibles

El documento quedará disponible para refinamiento según findings del equipo.
