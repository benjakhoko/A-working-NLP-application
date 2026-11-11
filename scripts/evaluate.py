"""Reproducible evaluation harness for the Intelligent Text Analysis System.

The script runs the project's real NLP services over the labelled datasets in
``evaluation/datasets`` and writes machine-readable and human-readable results
to ``evaluation/results``. No predictions are hard-coded: every metric is
computed from model/algorithm output produced during the run.

Typical usage (from the project root)::

    python scripts/evaluate.py
    python scripts/evaluate.py --abstractive --explanation
    python scripts/evaluate.py --full          # also calls the translation API

Heavy or network-dependent modules are opt-in so the default run finishes in a
couple of minutes on a CPU-only laptop.
"""
from __future__ import annotations

import argparse
import json
import platform
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from backend import create_app  # noqa: E402
from backend.services.nlp.explainer import explain_text  # noqa: E402
from backend.services.nlp.keywords import ALGORITHMS, extract_keywords  # noqa: E402
from backend.services.nlp.language_detector import detect_language  # noqa: E402
from backend.services.nlp.preprocessing import (  # noqa: E402
    sentence_tokenize,
    word_tokenize_simple,
)
from backend.services.nlp.sentiment import analyze_sentiment  # noqa: E402
from backend.services.nlp.summarizer import summarize_abstractive, summarize_extractive  # noqa: E402
from backend.services.nlp.translator import translate_text  # noqa: E402

DATASETS = ROOT / "evaluation" / "datasets"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------
def load_dataset(name: str) -> list[dict]:
    path = DATASETS / f"{name}.json"
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not data:
        raise SystemExit(f"Dataset {path} must contain a non-empty JSON array.")
    return data


def normalise_term(term: str) -> str:
    term = unicodedata.normalize("NFKC", str(term)).lower().strip()
    term = re.sub(r"^[^\w]+|[^\w]+$", "", term)
    return re.sub(r"\s+", " ", term)


def soft_match(prediction: str, gold: str) -> bool:
    """Token-overlap match used as a secondary, explicitly-labelled metric.

    Exact matching is deliberately strict: a unigram prediction such as
    ``"artificial"`` does not receive credit for the gold phrase
    ``"artificial intelligence"``. The soft metric gives partial credit when
    the token sets have a Jaccard similarity of at least 0.5.
    """
    left, right = set(prediction.split()), set(gold.split())
    if not left or not right:
        return False
    return len(left & right) / len(left | right) >= 0.5


def safe_div(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator else 0.0


def f1_score(precision: float, recall: float) -> float:
    return safe_div(2 * precision * recall, precision + recall)


def rounded(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


def timed(function, *args, **kwargs):
    started = time.perf_counter()
    value = function(*args, **kwargs)
    return value, time.perf_counter() - started


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def environment() -> dict:
    packages = [
        "Flask", "nltk", "spacy", "scikit-learn", "transformers", "torch",
        "langdetect", "yake", "rake-nltk", "rouge-score", "numpy",
    ]
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "packages": {name: package_version(name) for name in packages},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "seed": 42,
    }


# ---------------------------------------------------------------------------
# Keyword evaluation
# ---------------------------------------------------------------------------
def evaluate_keywords(top_n: int = 10) -> dict:
    dataset = load_dataset("keywords")
    report = {"dataset_size": len(dataset), "top_n": top_n, "algorithms": {}}
    for algorithm in ALGORITHMS:
        rows = []
        latencies = []
        for item in dataset:
            result, elapsed = timed(extract_keywords, item["text"], algorithm=algorithm, top_n=top_n)
            latencies.append(elapsed)
            predictions = [normalise_term(entry["keyword"]) for entry in result["keywords"]]
            gold = [normalise_term(term) for term in item["gold_keywords"]]

            strict_hits = sum(1 for prediction in predictions if prediction in set(gold))
            soft_hits = sum(
                1 for prediction in predictions
                if any(soft_match(prediction, term) for term in gold)
            )
            strict_recalled = sum(
                1 for term in gold if any(prediction == term for prediction in predictions)
            )
            soft_recalled = sum(
                1 for term in gold if any(soft_match(prediction, term) for prediction in predictions)
            )
            rows.append(
                {
                    "id": item["id"],
                    "predictions": [entry["keyword"] for entry in result["keywords"]],
                    "gold": item["gold_keywords"],
                    "strict": {
                        "precision": safe_div(strict_hits, len(predictions)),
                        "recall": safe_div(strict_recalled, len(gold)),
                        "hits": strict_hits,
                        "recalled_gold": strict_recalled,
                    },
                    "soft": {
                        "precision": safe_div(soft_hits, len(predictions)),
                        "recall": safe_div(soft_recalled, len(gold)),
                        "hits": soft_hits,
                        "recalled_gold": soft_recalled,
                    },
                }
            )

        def aggregate(key: str) -> dict:
            precision = statistics.mean(row[key]["precision"] for row in rows)
            recall = statistics.mean(row[key]["recall"] for row in rows)
            micro_precision = safe_div(
                sum(row[key]["hits"] for row in rows),
                sum(len(row["predictions"]) for row in rows),
            )
            micro_recall = safe_div(
                sum(row[key]["recalled_gold"] for row in rows),
                sum(len(row["gold"]) for row in rows),
            )
            return {
                "macro_precision": rounded(precision),
                "macro_recall": rounded(recall),
                "macro_f1": rounded(f1_score(precision, recall)),
                "micro_precision": rounded(micro_precision),
                "micro_recall": rounded(micro_recall),
                "micro_f1": rounded(f1_score(micro_precision, micro_recall)),
            }

        report["algorithms"][algorithm] = {
            "label": ALGORITHMS[algorithm]["label"],
            "strict": aggregate("strict"),
            "soft": aggregate("soft"),
            "mean_latency_seconds": rounded(statistics.mean(latencies)),
            "documents": rows,
        }
    return report


# ---------------------------------------------------------------------------
# Sentiment evaluation
# ---------------------------------------------------------------------------
def evaluate_sentiment() -> dict:
    dataset = load_dataset("sentiment")
    labels = ["positive", "negative", "neutral"]
    rows = []
    confusion = {gold: {predicted: 0 for predicted in labels} for gold in labels}
    latencies = []
    for item in dataset:
        result, elapsed = timed(analyze_sentiment, item["text"])
        latencies.append(elapsed)
        predicted = result["label"]
        confusion[item["label"]][predicted] += 1
        rows.append(
            {
                "id": item["id"],
                "gold": item["label"],
                "predicted": predicted,
                "compound": result["compound_score"],
                "confidence": result["confidence"],
            }
        )

    per_class = {}
    for label in labels:
        true_positive = confusion[label][label]
        false_positive = sum(confusion[gold][label] for gold in labels if gold != label)
        false_negative = sum(confusion[label][predicted] for predicted in labels if predicted != label)
        precision = safe_div(true_positive, true_positive + false_positive)
        recall = safe_div(true_positive, true_positive + false_negative)
        per_class[label] = {
            "precision": rounded(precision),
            "recall": rounded(recall),
            "f1": rounded(f1_score(precision, recall)),
            "support": sum(confusion[label].values()),
        }

    correct = sum(confusion[label][label] for label in labels)
    return {
        "dataset_size": len(dataset),
        "model": "VADER (NLTK lexicon + rule-based)",
        "accuracy": rounded(safe_div(correct, len(dataset))),
        "macro_precision": rounded(statistics.mean(item["precision"] for item in per_class.values())),
        "macro_recall": rounded(statistics.mean(item["recall"] for item in per_class.values())),
        "macro_f1": rounded(statistics.mean(item["f1"] for item in per_class.values())),
        "per_class": per_class,
        "confusion_matrix": confusion,
        "mean_confidence": rounded(statistics.mean(row["confidence"] for row in rows)),
        "mean_latency_seconds": rounded(statistics.mean(latencies)),
        "items": rows,
    }


# ---------------------------------------------------------------------------
# Language identification evaluation
# ---------------------------------------------------------------------------
def evaluate_language() -> dict:
    dataset = load_dataset("language")
    rows = []
    latencies = []
    confusion: dict[str, Counter] = {}
    for item in dataset:
        result, elapsed = timed(detect_language, item["text"])
        latencies.append(elapsed)
        predicted = result["code"]
        confusion.setdefault(item["label"], Counter())[predicted] += 1
        rows.append(
            {
                "id": item["id"],
                "gold": item["label"],
                "predicted": predicted,
                "confidence": result["confidence"],
                "reliable": result["reliable"],
            }
        )
    correct = sum(1 for row in rows if row["gold"] == row["predicted"])
    per_language = {}
    for label in sorted({row["gold"] for row in rows}):
        subset = [row for row in rows if row["gold"] == label]
        per_language[label] = {
            "accuracy": rounded(safe_div(sum(row["gold"] == row["predicted"] for row in subset), len(subset))),
            "support": len(subset),
        }
    return {
        "dataset_size": len(dataset),
        "model": "langdetect Naive Bayes character n-gram classifier",
        "accuracy": rounded(safe_div(correct, len(rows))),
        "mean_confidence": rounded(statistics.mean(row["confidence"] for row in rows)),
        "reliable_rate": rounded(safe_div(sum(row["reliable"] for row in rows), len(rows))),
        "per_language": per_language,
        "confusion": {gold: dict(counter) for gold, counter in confusion.items()},
        "mean_latency_seconds": rounded(statistics.mean(latencies)),
        "items": rows,
    }


# ---------------------------------------------------------------------------
# Summarisation evaluation
# ---------------------------------------------------------------------------
def _rouge_scores(reference: str, hypothesis: str) -> dict:
    from rouge_score import rouge_scorer

    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)
    scores = scorer.score(reference, hypothesis)
    return {name: scores[name].fmeasure for name in scores}


def _bleu_scores(reference: str, hypothesis: str) -> dict:
    from nltk.translate.bleu_score import SmoothingFunction, sentence_bleu

    reference_tokens = word_tokenize_simple(reference.lower())
    hypothesis_tokens = word_tokenize_simple(hypothesis.lower())
    smoothing = SmoothingFunction().method1
    return {
        "bleu1": sentence_bleu([reference_tokens], hypothesis_tokens, weights=(1, 0, 0, 0), smoothing_function=smoothing),
        "bleu4": sentence_bleu([reference_tokens], hypothesis_tokens, weights=(0.25, 0.25, 0.25, 0.25), smoothing_function=smoothing),
    }


def _summarisation_rows(dataset: list[dict], method: str, length: str) -> dict:
    rows = []
    latencies = []
    for item in dataset:
        if method == "extractive":
            result, elapsed = timed(summarize_extractive, item["text"], length=length)
        else:
            result, elapsed = timed(summarize_abstractive, item["text"], length=length)
        latencies.append(elapsed)
        summary = result["summary"]
        rouge = _rouge_scores(item["reference_summary"], summary)
        bleu = _bleu_scores(item["reference_summary"], summary)
        rows.append(
            {
                "id": item["id"],
                "summary": summary,
                "reference": item["reference_summary"],
                "rouge1": rounded(rouge["rouge1"]),
                "rouge2": rounded(rouge["rouge2"]),
                "rougeL": rounded(rouge["rougeL"]),
                "bleu1": rounded(bleu["bleu1"]),
                "bleu4": rounded(bleu["bleu4"]),
                "compression_percentage": result.get("compression_percentage"),
                "latency_seconds": rounded(elapsed),
            }
        )
    return {
        "method": method,
        "length": length,
        "dataset_size": len(rows),
        "rouge1": rounded(statistics.mean(row["rouge1"] for row in rows)),
        "rouge2": rounded(statistics.mean(row["rouge2"] for row in rows)),
        "rougeL": rounded(statistics.mean(row["rougeL"] for row in rows)),
        "bleu1": rounded(statistics.mean(row["bleu1"] for row in rows)),
        "bleu4": rounded(statistics.mean(row["bleu4"] for row in rows)),
        "mean_compression_percentage": rounded(
            statistics.mean(float(row["compression_percentage"] or 0) for row in rows)
        ),
        "mean_latency_seconds": rounded(statistics.mean(latencies)),
        "documents": rows,
    }


def evaluate_summarisation(*, abstractive: bool, abstractive_limit: int = 3) -> dict:
    dataset = load_dataset("summarization")
    report = {
        "dataset_size": len(dataset),
        "extractive_short": _summarisation_rows(dataset, "extractive", "short"),
        "extractive_medium": _summarisation_rows(dataset, "extractive", "medium"),
    }
    if abstractive:
        report["abstractive_short"] = _summarisation_rows(
            dataset[:abstractive_limit], "abstractive", "short"
        )
    return report


# ---------------------------------------------------------------------------
# Translation evaluation (network provider, opt-in)
# ---------------------------------------------------------------------------
def evaluate_translation(provider: str | None = None) -> dict:
    dataset = load_dataset("translation")
    from nltk.translate.bleu_score import SmoothingFunction, corpus_bleu, sentence_bleu
    from nltk.translate.chrf_score import sentence_chrf

    references = []
    hypotheses = []
    rows = []
    latencies = []
    for item in dataset:
        try:
            result, elapsed = timed(
                translate_text,
                item["text"],
                target=item["target"],
                source=item["source"],
                provider=provider,
            )
            hypothesis = result["translated_text"]
            reference_tokens = word_tokenize_simple(item["reference"].lower())
            hypothesis_tokens = word_tokenize_simple(hypothesis.lower())
            references.append([reference_tokens])
            hypotheses.append(hypothesis_tokens)
            rows.append(
                {
                    "id": item["id"],
                    "source": item["text"],
                    "reference": item["reference"],
                    "hypothesis": hypothesis,
                    "bleu4": rounded(
                        sentence_bleu(
                            [reference_tokens],
                            hypothesis_tokens,
                            weights=(0.25, 0.25, 0.25, 0.25),
                            smoothing_function=SmoothingFunction().method1,
                        )
                    ),
                    "chrf": rounded(sentence_chrf(item["reference"], hypothesis)),
                    "latency_seconds": rounded(elapsed),
                }
            )
            latencies.append(elapsed)
        except Exception as exc:  # network/quota/provider errors must not abort the run
            rows.append({"id": item["id"], "error": str(exc)})

    successful = [row for row in rows if "error" not in row]
    corpus = None
    if hypotheses:
        corpus = {
            "bleu4": rounded(
                corpus_bleu(
                    references,
                    hypotheses,
                    weights=(0.25, 0.25, 0.25, 0.25),
                    smoothing_function=SmoothingFunction().method1,
                )
            ),
            "chrf": rounded(statistics.mean(row["chrf"] for row in successful)),
        }
    return {
        "dataset_size": len(dataset),
        "provider": provider or "configured default",
        "successful": len(successful),
        "failed": len(rows) - len(successful),
        "corpus": corpus,
        "mean_latency_seconds": rounded(statistics.mean(latencies)) if latencies else None,
        "items": rows,
    }


# ---------------------------------------------------------------------------
# Explanation / readability evaluation (local model, opt-in)
# ---------------------------------------------------------------------------
_VOWELS = "aeiouy"


def _syllables(word: str) -> int:
    word = re.sub(r"[^a-z]", "", word.lower())
    if not word:
        return 0
    count = 0
    previous_vowel = False
    for char in word:
        is_vowel = char in _VOWELS
        if is_vowel and not previous_vowel:
            count += 1
        previous_vowel = is_vowel
    if word.endswith("e") and count > 1 and not word.endswith(("le", "ee")):
        count -= 1
    return max(1, count)


def flesch_reading_ease(text: str) -> float:
    words = word_tokenize_simple(text)
    sentences = sentence_tokenize(text) or [text]
    if not words:
        return 0.0
    syllables = sum(_syllables(word) for word in words)
    score = 206.835 - 1.015 * (len(words) / max(len(sentences), 1)) - 84.6 * (syllables / len(words))
    return round(score, 2)


def evaluate_explanation(complexity: str = "simple") -> dict:
    dataset = load_dataset("explanation")
    rows = []
    latencies = []
    for item in dataset:
        result, elapsed = timed(explain_text, item["text"], complexity=complexity)
        latencies.append(elapsed)
        explanation = result["explanation"]
        before = flesch_reading_ease(item["text"])
        after = flesch_reading_ease(explanation)
        gold = [normalise_term(term) for term in item["gold_terms"]]
        covered = [
            term for term in gold
            if term in normalise_term(explanation)
            or any(soft_match(normalise_term(key), term) for key in result["key_terms"])
        ]
        rows.append(
            {
                "id": item["id"],
                "explanation": explanation,
                "provider": result["provider_label"],
                "key_terms": result["key_terms"],
                "readability_before": before,
                "readability_after": after,
                "readability_delta": round(after - before, 2),
                "compression_percentage": rounded(
                    100 * (1 - len(word_tokenize_simple(explanation)) / max(len(word_tokenize_simple(item["text"])), 1))
                ),
                "gold_term_coverage": rounded(safe_div(len(covered), len(gold))),
                "latency_seconds": rounded(elapsed),
            }
        )
    return {
        "dataset_size": len(rows),
        "complexity": complexity,
        "provider": rows[0]["provider"] if rows else None,
        "mean_readability_before": rounded(statistics.mean(row["readability_before"] for row in rows)),
        "mean_readability_after": rounded(statistics.mean(row["readability_after"] for row in rows)),
        "mean_readability_delta": rounded(statistics.mean(row["readability_delta"] for row in rows)),
        "mean_gold_term_coverage": rounded(statistics.mean(row["gold_term_coverage"] for row in rows)),
        "mean_compression_percentage": rounded(statistics.mean(row["compression_percentage"] for row in rows)),
        "mean_latency_seconds": rounded(statistics.mean(latencies)),
        "items": rows,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def write_markdown(results: dict, path: Path) -> None:
    lines = [
        "# Evaluation Results",
        "",
        f"Generated at: {results['environment']['generated_at']}",
        f"Python: {results['environment']['python']}  ",
        f"Platform: {results['environment']['platform']}  ",
        f"Random seed: {results['environment']['seed']}",
        "",
        "All scores are computed from live algorithm/model output over the labelled",
        "datasets in `evaluation/datasets`. See `docs/EVALUATION.md` for methodology,",
        "dataset provenance and limitations.",
        "",
    ]

    keywords = results.get("keywords")
    if keywords:
        lines += [
            "## Keyword extraction",
            "",
            f"Dataset: {keywords['dataset_size']} documents, top-{keywords['top_n']} keywords.",
            "",
            "| Algorithm | Strict P | Strict R | Strict F1 | Soft P | Soft R | Soft F1 | Latency (s) |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for name, data in keywords["algorithms"].items():
            strict, soft = data["strict"], data["soft"]
            lines.append(
                f"| {data['label']} | {strict['macro_precision']:.3f} | {strict['macro_recall']:.3f} | "
                f"{strict['macro_f1']:.3f} | {soft['macro_precision']:.3f} | {soft['macro_recall']:.3f} | "
                f"{soft['macro_f1']:.3f} | {data['mean_latency_seconds']:.3f} |"
            )
        lines += [
            "",
            "Strict matching requires the normalised predicted term to equal a gold term.",
            "Soft matching gives partial credit at a token-set Jaccard similarity of at least 0.5.",
            "",
        ]

    sentiment = results.get("sentiment")
    if sentiment:
        lines += [
            "## Sentiment analysis",
            "",
            f"Dataset: {sentiment['dataset_size']} labelled English sentences. Model: {sentiment['model']}.",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Accuracy | {sentiment['accuracy']:.3f} |",
            f"| Macro precision | {sentiment['macro_precision']:.3f} |",
            f"| Macro recall | {sentiment['macro_recall']:.3f} |",
            f"| Macro F1 | {sentiment['macro_f1']:.3f} |",
            f"| Mean confidence | {sentiment['mean_confidence']:.3f} |",
            f"| Mean latency (s) | {sentiment['mean_latency_seconds']:.3f} |",
            "",
            "| Class | Precision | Recall | F1 | Support |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
        for label, data in sentiment["per_class"].items():
            lines.append(
                f"| {label.capitalize()} | {data['precision']:.3f} | {data['recall']:.3f} | "
                f"{data['f1']:.3f} | {data['support']} |"
            )
        lines.append("")

    language = results.get("language")
    if language:
        lines += [
            "## Language detection",
            "",
            f"Dataset: {language['dataset_size']} multilingual samples. Model: {language['model']}.",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Accuracy | {language['accuracy']:.3f} |",
            f"| Mean confidence | {language['mean_confidence']:.3f} |",
            f"| Reliable-rate | {language['reliable_rate']:.3f} |",
            f"| Mean latency (s) | {language['mean_latency_seconds']:.3f} |",
            "",
            "| Language | Accuracy | Support |",
            "| --- | ---: | ---: |",
        ]
        for label, data in language["per_language"].items():
            lines.append(f"| {label} | {data['accuracy']:.3f} | {data['support']} |")
        lines.append("")

    summaries = results.get("summarisation")
    if summaries:
        lines += [
            "## Summarisation",
            "",
            "ROUGE uses stemming; BLEU-4 uses NLTK smoothing method 1. Scores are means over documents.",
            "",
            "| Method | Length | ROUGE-1 | ROUGE-2 | ROUGE-L | BLEU-1 | BLEU-4 | Compression | Latency (s) |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
        for key, data in summaries.items():
            if not isinstance(data, dict) or "rouge1" not in data:
                continue
            lines.append(
                f"| {data['method']} | {data['length']} | {data['rouge1']:.3f} | {data['rouge2']:.3f} | "
                f"{data['rougeL']:.3f} | {data['bleu1']:.3f} | {data['bleu4']:.3f} | "
                f"{data['mean_compression_percentage']:.1f}% | {data['mean_latency_seconds']:.2f} |"
            )
        lines.append("")

    translation = results.get("translation")
    if translation:
        lines += [
            "## Translation",
            "",
            f"Dataset: {translation['dataset_size']} English-to-French sentences. Provider: {translation['provider']}.",
            f"Successful requests: {translation['successful']}; failed: {translation['failed']}.",
            "",
        ]
        if translation.get("corpus"):
            lines += [
                "| Metric | Value |",
                "| --- | ---: |",
                f"| Corpus BLEU-4 | {translation['corpus']['bleu4']:.3f} |",
                f"| Mean chrF | {translation['corpus']['chrf']:.3f} |",
                "",
            ]

    explanation = results.get("explanation")
    if explanation:
        lines += [
            "## Explanation and readability",
            "",
            f"Dataset: {explanation['dataset_size']} technical passages. Provider: {explanation['provider']}.",
            "Readability is Flesch Reading Ease (higher is easier).",
            "",
            "| Metric | Value |",
            "| --- | ---: |",
            f"| Readability before | {explanation['mean_readability_before']:.2f} |",
            f"| Readability after | {explanation['mean_readability_after']:.2f} |",
            f"| Readability delta | {explanation['mean_readability_delta']:+.2f} |",
            f"| Gold term coverage | {explanation['mean_gold_term_coverage']:.3f} |",
            f"| Compression | {explanation['mean_compression_percentage']:.1f}% |",
            f"| Mean latency (s) | {explanation['mean_latency_seconds']:.2f} |",
            "",
        ]

    lines += [
        "## Reproducing",
        "",
        "```bash",
        "python scripts/evaluate.py --full",
        "```",
        "",
        "Heavy modules (abstractive summarisation, local explanation) and the",
        "network translation provider are opt-in flags; see the script's `--help`.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output directory")
    parser.add_argument("--top-n", type=int, default=10, help="Keywords evaluated per document")
    parser.add_argument("--abstractive", action="store_true", help="Evaluate DistilBART summarisation (slow)")
    parser.add_argument("--abstractive-limit", type=int, default=3, help="Documents for abstractive evaluation")
    parser.add_argument("--explanation", action="store_true", help="Evaluate the local explanation model")
    parser.add_argument("--translation", action="store_true", help="Call the configured translation provider")
    parser.add_argument("--translation-provider", default=None, help="Override translation provider for evaluation")
    parser.add_argument("--full", action="store_true", help="Run every module, including network and heavy models")
    parser.add_argument("--skip-summarisation", action="store_true", help="Skip summarisation metrics")
    args = parser.parse_args()

    random.seed(42)
    np.random.seed(42)

    output = args.output
    output.mkdir(parents=True, exist_ok=True)

    app = create_app("testing")
    results: dict = {"environment": environment()}

    with app.app_context():
        print("Evaluating keyword extraction ...", flush=True)
        results["keywords"] = evaluate_keywords(top_n=args.top_n)

        print("Evaluating sentiment ...", flush=True)
        results["sentiment"] = evaluate_sentiment()

        print("Evaluating language detection ...", flush=True)
        results["language"] = evaluate_language()

        if not args.skip_summarisation:
            print("Evaluating extractive summarisation ...", flush=True)
            results["summarisation"] = evaluate_summarisation(
                abstractive=args.abstractive or args.full,
                abstractive_limit=args.abstractive_limit,
            )

        if args.translation or args.full:
            print("Evaluating translation ...", flush=True)
            results["translation"] = evaluate_translation(
                provider=args.translation_provider
            )

        if args.explanation or args.full:
            print("Evaluating explanation and readability (local model) ...", flush=True)
            results["explanation"] = evaluate_explanation()

    json_path = output / "results.json"
    json_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = output / "RESULTS.md"
    write_markdown(results, markdown_path)

    print(f"\nWrote {json_path}")
    print(f"Wrote {markdown_path}")
    print("\nSummary")
    if "keywords" in results:
        for name, data in results["keywords"]["algorithms"].items():
            print(
                f"  keywords/{name}: strict F1={data['strict']['macro_f1']:.3f} "
                f"soft F1={data['soft']['macro_f1']:.3f}"
            )
    if "sentiment" in results:
        print(
            f"  sentiment: accuracy={results['sentiment']['accuracy']:.3f} "
            f"macro-F1={results['sentiment']['macro_f1']:.3f}"
        )
    if "language" in results:
        print(f"  language: accuracy={results['language']['accuracy']:.3f}")
    if "summarisation" in results:
        for key, data in results["summarisation"].items():
            if isinstance(data, dict) and "rougeL" in data:
                print(f"  summary/{key}: ROUGE-L={data['rougeL']:.3f} BLEU-4={data['bleu4']:.3f}")
    if "translation" in results and results["translation"].get("corpus"):
        print(f"  translation: BLEU-4={results['translation']['corpus']['bleu4']:.3f}")
    if "explanation" in results:
        print(
            f"  explanation: readability delta={results['explanation']['mean_readability_delta']:+.2f} "
            f"term coverage={results['explanation']['mean_gold_term_coverage']:.3f}"
        )


if __name__ == "__main__":
    main()
