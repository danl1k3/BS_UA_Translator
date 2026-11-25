"""Fine-tune NLLB-200-distilled-600M on Bosnian <-> Ukrainian parallel data."""

import argparse

from datasets import load_dataset
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    DataCollatorForSeq2Seq,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fine-tune NLLB-200 for BS <-> UK")
    parser.add_argument("--base-model", default="facebook/nllb-200-distilled-600M")
    parser.add_argument("--dataset", required=True, help="Hugging Face dataset ID or local path")
    parser.add_argument("--src-lang", default="bos_Latn")
    parser.add_argument("--tgt-lang", default="ukr_Cyrl")
    parser.add_argument("--output-dir", default="./checkpoints/nllb-bs-ua")
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--max-length", type=int, default=256)
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.base_model, src_lang=args.src_lang)
    model = AutoModelForSeq2SeqLM.from_pretrained(args.base_model)
    raw_datasets = load_dataset(args.dataset)

    def preprocess(examples):
        inputs = examples[args.src_lang]
        targets = examples[args.tgt_lang]
        model_inputs = tokenizer(inputs, max_length=args.max_length, truncation=True)
        labels = tokenizer(text_target=targets, max_length=args.max_length, truncation=True)
        model_inputs["labels"] = labels["input_ids"]
        return model_inputs

    tokenized = raw_datasets.map(preprocess, batched=True)
    collator = DataCollatorForSeq2Seq(tokenizer, model=model)

    training_args = Seq2SeqTrainingArguments(
        output_dir=args.output_dir,
        eval_strategy="epoch" if "validation" in tokenized else "no",
        save_strategy="epoch",
        learning_rate=args.lr,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        num_train_epochs=args.epochs,
        predict_with_generate=True,
        fp16=True,
        logging_steps=50,
    )

    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=tokenized["train"],
        eval_dataset=tokenized.get("validation"),
        processing_class=tokenizer,
        data_collator=collator,
    )
    trainer.train()
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)


if __name__ == "__main__":
    main()
