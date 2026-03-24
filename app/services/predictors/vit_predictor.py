import logging
import torch
from PIL import Image

logger  = logging.getLogger(__name__)
_model  = None
_processor = None
_device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

VIT_MODEL_ID = "haywoodsloan/ai-image-detector-deploy"


def _get_model():
    global _model, _processor
    if _model is None:
        from transformers import AutoImageProcessor, AutoModelForImageClassification  # lazy import
        logger.info("[ViT] Carregando modelo...")
        _processor = AutoImageProcessor.from_pretrained(VIT_MODEL_ID)
        _model     = AutoModelForImageClassification.from_pretrained(VIT_MODEL_ID).to(_device)
        _model.eval()
        logger.info("[ViT] Modelo carregado.")
    return _model, _processor


def predict(file_path: str) -> dict:
    model, processor = _get_model()
    image  = Image.open(file_path).convert("RGB")
    inputs = processor(images=image, return_tensors="pt").to(_device)

    with torch.no_grad():
        outputs = model(**inputs)
        probs   = torch.softmax(outputs.logits, dim=1)[0].cpu()

    # Verifica os labels do modelo para mapear corretamente
    id2label   = model.config.id2label  # ex: {0: "real", 1: "artificial"}
    fake_idx   = next(
        (i for i, l in id2label.items() if "art" in l.lower() or "fake" in l.lower() or "ai" in l.lower()),
        1
    )
    confidence = round(float(probs[fake_idx].item()), 4)

    return {
        "prediction": "FAKE" if confidence >= 0.5 else "REAL",
        "confidence": confidence,
        "method":     "vit_ai_detector",
        "version":    "1.0",
        "metadata": {
            "labels": {l: round(float(probs[i].item()), 4) for i, l in id2label.items()},
        },
    }