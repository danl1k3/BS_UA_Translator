"""Convert a fine-tuned NLLB-200 Hugging Face model to CTranslate2 format.

Also saves the tokenizer files into the same output directory so the converted
model and tokenizer can be uploaded together to Hugging Face Hub.
"""

import argparse
from pathlib import Path

import ctranslate2
from transformers import AutoTokenizer


def convert_model(
    model_name_or_path: str,
    output_dir: str,
    quantization: str = "int8",
) -> None:
    """Convert Hugging Face NLLB model to CTranslate2 and bundle tokenizer."""
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    converter = ctranslate2.converters.TransformersConverter(model_name_or_path)
    converter.convert(str(out_path), quantization=quantization, force=True)

    # Save tokenizer alongside the converted CTranslate2 model
    tokenizer = AutoTokenizer.from_pretrained(model_name_or_path)
    tokenizer.save_pretrained(str(out_path))
    print(f"Converted model ({quantization}) and tokenizer saved to {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert NLLB-200 to CTranslate2")
    parser.add_argument(
        "--model",
        default="facebook/nllb-200-distilled-600M",
        help="Hugging Face model ID or local checkpoint path",
    )
    parser.add_argument(
        "--output-dir",
        default="./nllb-bs-ua-ct2-int8",
        help="Output directory for CTranslate2 model + tokenizer",
    )
    parser.add_argument(
        "--quantization",
        default="int8",
        choices=["int8", "int8_float16", "float16", "float32"],
        help="CTranslate2 quantization type",
    )
    args = parser.parse_args()
    convert_model(args.model, args.output_dir, args.quantization)


if __name__ == "__main__":
    main()
