"""Evaluate a CTranslate2 NLLB model on a parallel test set (BLEU and chrF++)."""

import argparse

import ctranslate2
import sacrebleu
from datasets import load_dataset
from transformers import AutoTokenizer


def evaluate(
    ct2_model_dir: str,
    dataset_name: str,
    split: str = "test",
    src_lang: str = "bos_Latn",
    tgt_lang: str = "ukr_Cyrl",
    beam_size: int = 4,
) -> None:
    """Compute corpus BLEU and chrF++ for a CTranslate2 model directory."""
    translator = ctranslate2.Translator(ct2_model_dir, device="auto")
    tokenizer = AutoTokenizer.from_pretrained(ct2_model_dir, src_lang=src_lang)
    dataset = load_dataset(dataset_name, split=split)

    sources = list(dataset[src_lang])
    references = list(dataset[tgt_lang])

    tokenized_sources = [
        tokenizer.convert_ids_to_tokens(tokenizer.encode(text)) for text in sources
    ]
    results = translator.translate_batch(
        tokenized_sources,
        target_prefix=[[tgt_lang]] * len(tokenized_sources),
        beam_size=beam_size,
    )

    hypotheses = []
    for res in results:
        tokens = res.hypotheses[0]
        if tokens and tokens[0] == tgt_lang:
            tokens = tokens[1:]
        hypotheses.append(tokenizer.decode(tokenizer.convert_tokens_to_ids(tokens)))

    bleu = sacrebleu.corpus_bleu(hypotheses, [references])
    chrf = sacrebleu.corpus_chrf(hypotheses, [references], word_order=2)
    print(f"BLEU: {bleu.score:.2f}")
    print(f"chrF++: {chrf.score:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CTranslate2 NLLB model")
    parser.add_argument("--model-dir", required=True, help="Path to CTranslate2 model + tokenizer")
    parser.add_argument("--dataset", required=True, help="Hugging Face dataset ID or local path")
    parser.add_argument("--split", default="test")
    parser.add_argument("--src-lang", default="bos_Latn")
    parser.add_argument("--tgt-lang", default="ukr_Cyrl")
    parser.add_argument("--beam-size", type=int, default=4)
    args = parser.parse_args()
    evaluate(
        args.model_dir,
        args.dataset,
        split=args.split,
        src_lang=args.src_lang,
        tgt_lang=args.tgt_lang,
        beam_size=args.beam_size,
    )


if __name__ == "__main__":
    main()
