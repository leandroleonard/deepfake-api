import cv2
import numpy as np
import os
import uuid
from datetime import datetime
from app.core.celery_app import celery_app
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.analysis import Analysis, StatusEnum
from app.models.result import Result

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "app/uploads")
HEATMAPS_DIR = os.path.join(UPLOADS_DIR, "heatmaps")
os.makedirs(HEATMAPS_DIR, exist_ok=True)


def _save_heatmap(img_array: np.ndarray, suffix: str) -> str:
    """Salva uma imagem numpy e retorna o path relativo para a DB."""
    filename = f"{uuid.uuid4().hex}_{suffix}.jpg"
    full_path = os.path.join(HEATMAPS_DIR, filename)
    cv2.imwrite(full_path, img_array)
    return f"/uploads/heatmaps/{filename}"


def analyze_illumination(image_path: str) -> dict:
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Não foi possível abrir a imagem: {image_path}")

    # ── 1. Converter para LAB (L = luminosidade, A/B = cor) ──────────────────
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    # ── 2. Gradiente de luminosidade (detecta bordas de luz inconsistentes) ──
    grad_x = cv2.Sobel(L.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(L.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(grad_x ** 2 + grad_y ** 2)
    gradient_norm = cv2.normalize(gradient_magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    # ── 3. Mapa de anomalias de sombra (regiões escuras com gradiente alto) ──
    shadow_mask = (L < 80).astype(np.uint8) * 255
    shadow_anomaly = cv2.bitwise_and(gradient_norm, gradient_norm, mask=shadow_mask)

    # ── 4. Mapa de anomalias de highlight (regiões muito brilhantes) ─────────
    highlight_mask = (L > 200).astype(np.uint8) * 255
    highlight_anomaly = cv2.bitwise_and(gradient_norm, gradient_norm, mask=highlight_mask)

    # ── 5. Sub-scores (0.0 – 1.0) ────────────────────────────────────────────
    ambient_score = float(np.std(L) / 128.0)                                    # desvio padrão da luminosidade
    shadow_score = float(np.mean(shadow_anomaly) / 255.0)                       # anomalia nas sombras
    highlight_score = float(np.mean(highlight_anomaly) / 255.0)                 # anomalia nos highlights
    gradient_score = float(np.mean(gradient_norm) / 255.0)                      # gradiente médio

    # Clamp 0-1
    ambient_score   = min(max(ambient_score, 0.0), 1.0)
    shadow_score    = min(max(shadow_score, 0.0), 1.0)
    highlight_score = min(max(highlight_score, 0.0), 1.0)
    gradient_score  = min(max(gradient_score, 0.0), 1.0)

    # Score final ponderado
    confidence = round(
        ambient_score   * 0.25 +
        shadow_score    * 0.25 +
        highlight_score * 0.25 +
        gradient_score  * 0.25,
        4
    )
    confidence = min(confidence, 1.0)

    # ── 6. Gerar imagens de evidência ─────────────────────────────────────────

    # lighting_evidence: heatmap colorido do gradiente de luminosidade
    heatmap_colored = cv2.applyColorMap(gradient_norm, cv2.COLORMAP_JET)
    evidence_path = _save_heatmap(heatmap_colored, "lighting_evidence")

    # lighting_overlay: heatmap sobreposto na imagem original (alpha blend)
    overlay = cv2.addWeighted(img, 0.55, heatmap_colored, 0.45, 0)
    overlay_path = _save_heatmap(overlay, "lighting_overlay")

    return {
        "prediction": "FAKE" if confidence >= 0.5 else "REAL",
        "confidence": confidence,
        "method": "illumination_consistency",
        "version": "1.0",
        "metadata": {
            "ambient_score":    round(ambient_score, 4),
            "shadow_score":     round(shadow_score, 4),
            "highlight_score":  round(highlight_score, 4),
            "gradient_score":   round(gradient_score, 4),
            "regions_analyzed": int(np.sum(shadow_mask > 0) + np.sum(highlight_mask > 0)),
        },
        "lighting_evidence": evidence_path,
        "lighting_overlay":  overlay_path,
    }


@celery_app.task(name="process_illumination_analysis")
def process_illumination_analysis(analysis_id: str):
    db: Session = SessionLocal()
    started_at = datetime.utcnow()

    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            return {"error": "Analysis not found"}

        media = analysis.media
        image_path = os.path.join(UPLOADS_DIR, media.location)

        result_data = analyze_illumination(image_path)

        result = Result(
            analysis_id=analysis_id,
            type="lum",
            result=result_data,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
        db.add(result)
        db.commit()

        return {"status": "ok", "confidence": result_data["confidence"]}

    except Exception as e:
        db.rollback()
        result = Result(
            analysis_id=analysis_id,
            type="lum",
            result={"error": str(e), "prediction": None, "confidence": None},
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
        db.add(result)
        db.commit()
        return {"error": str(e)}

    finally:
        db.close()