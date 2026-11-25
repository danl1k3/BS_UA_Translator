# Training, Conversion & Evaluation

This directory is intentionally kept outside the `backend/` and `frontend/` Docker build contexts so heavy ML dependencies (`torch`, `transformers`, `ctranslate2`, `datasets`) are never shipped to the Heroku gateway image.

## Hugging Face Artifacts

- **Converted Model + Tokenizer:** `<HUGGINGFACE_MODEL_URL>`
- **Parallel Dataset:** `<HUGGINGFACE_DATASET_URL>`

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r training/requirements.txt
```

## Scripts

### 1. Fine-tune NLLB-200

```bash
python training/finetune.py \
  --base-model facebook/nllb-200-distilled-600M \
  --dataset <HUGGINGFACE_DATASET_URL> \
  --src-lang bos_Latn \
  --tgt-lang ukr_Cyrl \
  --output-dir ./checkpoints/nllb-bs-ua
```

### 2. Convert to CTranslate2 (`int8`) + Bundle Tokenizer

`convert_ct2.py` places the tokenizer files alongside the converted CTranslate2 model so the inference service can load both from a single Hugging Face repository:

```bash
python training/convert_ct2.py \
  --model ./checkpoints/nllb-bs-ua \
  --output-dir ./nllb-bs-ua-ct2-int8 \
  --quantization int8
```

### 3. Evaluate (BLEU & chrF++)

```bash
python training/evaluate.py \
  --model-dir ./nllb-bs-ua-ct2-int8 \
  --dataset <HUGGINGFACE_DATASET_URL> \
  --split test
```

## License & Credits

- **Base Model:** Meta AI — [NLLB-200-distilled-600M](https://huggingface.co/facebook/nllb-200-distilled-600M).
- **License:** **CC-BY-NC 4.0** (non-commercial use only). Fine-tuned checkpoints and converted CTranslate2 weights derived from NLLB-200 remain subject to CC-BY-NC 4.0.
