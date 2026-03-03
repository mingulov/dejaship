# Embedding Model Comparison (fastembed 768-dim)

Date: 2026-03-02

## Current Model

**BAAI/bge-base-en-v1.5** — 768-dim, 512 tokens, MIT, 0.21 GB
- MTEB retrieval NDCG@10: ~53.25
- No prefix required (though asymmetric prefix exists)
- Tested extensively on DejaShip coverage-max corpus
- Produces unit-norm vectors (required for pgvector cosine ops)

## Candidates (768-dim, fastembed-supported)

### Tier 1: Worth Testing

| Model | Tokens | Size | License | Key Feature |
|-------|--------|------|---------|-------------|
| `snowflake/snowflake-arctic-embed-m` | 512 | 0.43 GB | Apache-2.0 | Best retrieval NDCG in fastembed (55.14) |
| `nomic-ai/nomic-embed-text-v1.5` | 8192 | 0.52 GB | Apache-2.0 | Matryoshka dimensions, instruction prefixes |
| `thenlper/gte-base` | 512 | 0.44 GB | MIT | Strong general-purpose, no prefix needed |

### Tier 2: Unlikely to Help

| Model | Tokens | Size | License | Why Skip |
|-------|--------|------|---------|----------|
| `jinaai/jina-embeddings-v2-base-en` | 8192 | 0.52 GB | Apache-2.0 | Worse MTEB than BGE; long context not needed |
| `BAAI/bge-base-en` | 512 | 0.42 GB | MIT | Older version of current model |
| `snowflake/snowflake-arctic-embed-m-long` | 2048 | 0.54 GB | Apache-2.0 | Long context not needed for our inputs |
| `jinaai/jina-clip-v1` | — | 0.55 GB | Apache-2.0 | Multimodal, not relevant |
| `jinaai/jina-embeddings-v2-base-code` | 8192 | 0.64 GB | Apache-2.0 | Code-focused, wrong domain |
| Multilingual models | — | — | — | English-only corpus |

## Model Feature Notes

### snowflake-arctic-embed-m
- **Requires query prefix**: `"Represent this sentence for searching relevant passages: "`
- Best retrieval benchmark in fastembed (NDCG@10: 55.14 vs BGE's 53.25)
- Trained specifically for retrieval tasks
- Risk: asymmetric prefix requirement may not suit DejaShip's symmetric comparison use case

### nomic-embed-text-v1.5
- **Requires task prefix**: `search_query:`, `search_document:`, `clustering:`, `classification:`
- `clustering:` prefix is most relevant for DejaShip (grouping similar products)
- Matryoshka representation: can truncate to 256/384/512 dims with minor quality loss
- 8192 token context (but our inputs are short, so no benefit)
- Risk: prefix requirement adds complexity; wrong prefix can degrade quality

### thenlper/gte-base
- No prefix required
- Good general-purpose embeddings
- Less retrieval-specialized than snowflake

## Why Model Swap Alone Won't Fix FPR

The maximum retrieval benchmark improvement from BGE to snowflake is ~3.5% relative NDCG improvement. Our FPR problem requires a ~50% relative reduction (0.72 → ~0.35). The gap between what a model swap provides and what we need is an order of magnitude.

The models all correctly identify that SaaS subscription vocabulary is semantically similar — because it is. The discrimination problem requires structural changes (reranking, filtering), not a better embedding function.

## Experiment Results (2026-03-02, coverage-max corpus)

Ran `evaluate_cross_model_retrieval --model-set coverage-max` with each model:

| Model | exact_top1 | overlap_hit | recall_at_k | false_positive_rate |
|-------|-----------|-------------|-------------|---------------------|
| BAAI/bge-base-en-v1.5 (baseline) | 1.0000 | 0.9890 | 0.7348 | 0.7224 |
| snowflake/snowflake-arctic-embed-m | 0.9983 | 0.9085 | 0.5246 | 0.7620 |
| nomic-ai/nomic-embed-text-v1.5 | 1.0000 | 0.9972 | 0.7208 | 0.7475 |

**Findings:**
- Snowflake **significantly worse**: recall drops 21% (0.73 → 0.52), FPR increases. The query prefix requirement (`"Represent this sentence for searching relevant passages: "`) was not applied (we embed claim text symmetrically). Adding the prefix might help, but symmetric comparison is DejaShip's use case.
- Nomic is **marginally worse**: FPR slightly higher (+2.5%), recall slightly lower (-2%). The task prefix was not applied either, which likely explains the small regression.
- **BGE wins on all metrics.** Model swap does not improve FPR as predicted.

## Recommendation

1. **Keep BGE as default** — best on all coverage-max metrics, smallest footprint (0.21 GB), no prefix complexity
2. **EMBEDDING_MODEL config flag** already exists for runtime switching if needed
3. **Model swap is not a strategy for FPR reduction** — structural fixes (Jaccard, two-stage, hybrid FTS) are the right approach
