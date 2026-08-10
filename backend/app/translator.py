import os
import re
import ctranslate2
import sentencepiece as spm
from typing import Generator

class NLLBTranslator:
    """
    Клас двигуна перекладу NLLB-200 з використанням CTranslate2.
    Керує токенізацією, очищенням тексту та стрімінговою генерацією.
    """

    def __init__(self, model_path: str, tokenizer_path: str):
        self.model_path = model_path
        
        if not os.path.exists(tokenizer_path):
            raise FileNotFoundError(f"Файл токенізатора не знайдено: {tokenizer_path}")
        
        self.sp = spm.SentencePieceProcessor()
        self.sp.load(tokenizer_path)

        self.translators = {}
        self._init_models()
        
        # Регулярний вираз для розбиття на речення зі збереженням контексту
        self.sentence_regex = re.compile(r'(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?|\!)\s')

    def _init_models(self):
        """Ініціалізація моделі на доступних пристроях (GPU/CPU)."""
        try:
            self.translators["cuda"] = ctranslate2.Translator(
                self.model_path,
                device="cuda",
                compute_type="int8",
                inter_threads=2
            )
        except Exception as e:
            print(f"Помилка ініціалізації CUDA: {e}")

        try:
            self.translators["cpu"] = ctranslate2.Translator(
                self.model_path,
                device="cpu",
                compute_type="int8",
                inter_threads=4 
            )
        except Exception as e:
            print(f"Помилка ініціалізації CPU: {e}")

    def _split_into_sentences(self, text: str) -> list[str]:
        """Розбиває вхідний текст на окремі речення."""
        text = text.strip()
        if not text:
            return []
        sentences = self.sentence_regex.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def translate_stream(
        self, 
        text: str, 
        source_lang: str,
        target_lang: str, 
        device: str = "cpu"
    ) -> Generator[str, None, None]:
        """
        Генерація перекладу в режимі стрімінгу.
        ВАЖЛИВО: Додає токен мови-джерела та штраф за повторення для усунення циклів.
        """
        active_device = device if device in self.translators else list(self.translators.keys())[0]
        translator = self.translators[active_device]

        sentences = self._split_into_sentences(text)
        
        for sentence in sentences:
            # Формуємо вхідні токени: [мова_джерела, текст, </s>]
            source_tokens = [source_lang] + self.sp.encode_as_pieces(sentence) + ["</s>"]
            
            # Виконуємо переклад із параметрами для запобігання повторів
            results = translator.translate_batch(
                [source_tokens],
                target_prefix=[[target_lang]],
                beam_size=4,
                max_decoding_length=256,
                repetition_penalty=1.2, # Забороняє безкінечні повтори слів
                replace_unknowns=True
            )

            translated_tokens = results[0].hypotheses[0]
            
            # Очищуємо технічні токени з результату
            if translated_tokens and (translated_tokens[0] == target_lang or translated_tokens[0].startswith("__")):
                translated_tokens = translated_tokens[1:]
                
            translated_text = self.sp.decode_pieces(translated_tokens)
            yield translated_text + " "