# Evaluation Results

Generated at: 2026-11-07T08:49:50.649777+00:00
Python: 3.13.8  
Platform: Windows-10-10.0.19045-SP0  
Random seed: 42

All scores are computed from live algorithm/model output over the labelled
datasets in `evaluation/datasets`. See `docs/EVALUATION.md` for methodology,
dataset provenance and limitations.

## Keyword extraction

Dataset: 8 documents, top-10 keywords.

| Algorithm | Strict P | Strict R | Strict F1 | Soft P | Soft R | Soft F1 | Latency (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TF-IDF | 0.150 | 0.150 | 0.150 | 0.475 | 0.362 | 0.411 | 0.016 |
| RAKE | 0.062 | 0.062 | 0.062 | 0.388 | 0.388 | 0.388 | 0.001 |
| YAKE | 0.163 | 0.163 | 0.163 | 0.400 | 0.300 | 0.343 | 0.145 |

Strict matching requires the normalised predicted term to equal a gold term.
Soft matching gives partial credit at a token-set Jaccard similarity of at least 0.5.

## Sentiment analysis

Dataset: 30 labelled English sentences. Model: VADER (NLTK lexicon + rule-based).

| Metric | Value |
| --- | ---: |
| Accuracy | 0.867 |
| Macro precision | 0.890 |
| Macro recall | 0.867 |
| Macro F1 | 0.864 |
| Mean confidence | 0.450 |
| Mean latency (s) | 0.013 |

| Class | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Positive | 0.769 | 1.000 | 0.870 | 10 |
| Negative | 0.900 | 0.900 | 0.900 | 10 |
| Neutral | 1.000 | 0.700 | 0.824 | 10 |

## Language detection

Dataset: 18 multilingual samples. Model: langdetect Naive Bayes character n-gram classifier.

| Metric | Value |
| --- | ---: |
| Accuracy | 1.000 |
| Mean confidence | 1.000 |
| Reliable-rate | 1.000 |
| Mean latency (s) | 0.002 |

| Language | Accuracy | Support |
| --- | ---: | ---: |
| de | 1.000 | 3 |
| en | 1.000 | 3 |
| es | 1.000 | 3 |
| fr | 1.000 | 3 |
| it | 1.000 | 3 |
| pt | 1.000 | 3 |

## Summarisation

ROUGE uses stemming; BLEU-4 uses NLTK smoothing method 1. Scores are means over documents.

| Method | Length | ROUGE-1 | ROUGE-2 | ROUGE-L | BLEU-1 | BLEU-4 | Compression | Latency (s) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| extractive | short | 0.172 | 0.018 | 0.118 | 0.084 | 0.008 | 83.5% | 0.01 |
| extractive | medium | 0.238 | 0.033 | 0.182 | 0.184 | 0.013 | 66.5% | 0.00 |

## Reproducing

```bash
python scripts/evaluate.py --full
```

Heavy modules (abstractive summarisation, local explanation) and the
network translation provider are opt-in flags; see the script's `--help`.
