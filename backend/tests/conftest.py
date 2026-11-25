import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

for mod_name in ("ctranslate2", "sentencepiece", "pynvml"):
    if mod_name not in sys.modules:
        stub = ModuleType(mod_name)
        if mod_name == "ctranslate2":
            stub.Translator = MagicMock()
        elif mod_name == "sentencepiece":
            stub.SentencePieceProcessor = MagicMock()
        elif mod_name == "pynvml":
            stub.nvmlInit = MagicMock(side_effect=RuntimeError("No GPU in test"))
            stub.nvmlShutdown = MagicMock()
        sys.modules[mod_name] = stub
