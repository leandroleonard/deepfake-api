import cv2
import numpy as np
import os
import uuid
from datetime import datetime
from app.core.celery_app import celery_app
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.analysis import Analysis
from app.models.result import Result

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "app/uploads")
HEATMAPS_DIR = os.path.join(UPLOADS_DIR, "heatmaps")
os.makedirs(HEATMAPS_DIR, exist_ok=True)

MIN_FRAMES = 5  


def _save_heatmap(img_array: np.ndarray, suffix: str) -> str:
    filename = f"{uuid.uuid4().hex}_{suffix}.jpg"
    full_path = os.path.join(HEATMAPS_DIR, filename)
    cv2.imwrite(full_path, img_array)
    return f"/uploads/heatmaps/{filename}"


def _extract_frames(video_path: str, num_frames: int = MIN_FRAMES) -> list[np.ndarray]:
    """
    Extrai `num_frames` frames distribuídos uniformemente ao longo do vídeo.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total_frames <= 0:
        raise ValueError("Vídeo sem frames detectados.")

    indices = np.linspace(0, total_frames - 1, num=num_frames, dtype=int)

    frames = []
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret and frame is not None:
            frames.append((int(idx), frame))

    cap.release()

    if not frames:
        raise ValueError("Nenhum frame pôde ser lido do vídeo.")

    return frames  


def _analyze_single_frame(img: np.ndarray) -> dict:
    """
    Analisa iluminação de um único frame/imagem.
    Retorna scores e os arrays das imagens de evidência (sem salvar em disco).
    """
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    L, A, B = cv2.split(lab)

    grad_x = cv2.Sobel(L.astype(np.float32), cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(L.astype(np.float32), cv2.CV_32F, 0, 1, ksize=3)
    gradient_magnitude = np.sqrt(grad_x ** 2 + grad_y ** 2)
    gradient_norm = cv2.normalize(gradient_magnitude, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    shadow_mask    = (L < 80).astype(np.uint8) * 255
    highlight_mask = (L > 200).astype(np.uint8) * 255
    shadow_anomaly    = cv2.bitwise_and(gradient_norm, gradient_norm, mask=shadow_mask)
    highlight_anomaly = cv2.bitwise_and(gradient_norm, gradient_norm, mask=highlight_mask)

    ambient_score   = min(max(float(np.std(L) / 128.0), 0.0), 1.0)
    shadow_score    = min(max(float(np.mean(shadow_anomaly) / 255.0), 0.0), 1.0)
    highlight_score = min(max(float(np.mean(highlight_anomaly) / 255.0), 0.0), 1.0)
    gradient_score  = min(max(float(np.mean(gradient_norm) / 255.0), 0.0), 1.0)

    confidence = round(
        ambient_score   * 0.25 +
        shadow_score    * 0.25 +
        highlight_score * 0.25 +
        gradient_score  * 0.25,
        4
    )
    confidence = min(confidence, 1.0)

    heatmap_colored = cv2.applyColorMap(gradient_norm, cv2.COLORMAP_JET)

    return {
        "confidence": confidence,
        "ambient_score":    round(ambient_score, 4),
        "shadow_score":     round(shadow_score, 4),
        "highlight_score":  round(highlight_score, 4),
        "gradient_score":   round(gradient_score, 4),
        "regions_analyzed": int(np.sum(shadow_mask > 0) + np.sum(highlight_mask > 0)),
        "_heatmap":  heatmap_colored,
        "_original": img,
    }


def analyze_illumination_image(image_path: str) -> dict:
    """Análise de iluminação para imagem estática."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Não foi possível abrir a imagem: {image_path}")

    r = _analyze_single_frame(img)

    evidence_path = _save_heatmap(r["_heatmap"], "lighting_evidence")
    overlay       = cv2.addWeighted(img, 0.55, r["_heatmap"], 0.45, 0)
    overlay_path  = _save_heatmap(overlay, "lighting_overlay")

    return {
        "prediction": "FAKE" if r["confidence"] >= 0.5 else "REAL",
        "confidence": r["confidence"],
        "method": "illumination_consistency",
        "version": "1.0",
        "metadata": {
            "ambient_score":    r["ambient_score"],
            "shadow_score":     r["shadow_score"],
            "highlight_score":  r["highlight_score"],
            "gradient_score":   r["gradient_score"],
            "regions_analyzed": r["regions_analyzed"],
        },
        "lighting_evidence": evidence_path,
        "lighting_overlay":  overlay_path,
    }


def analyze_illumination_video(video_path: str, num_frames: int = MIN_FRAMES) -> dict:
    frames = _extract_frames(video_path, num_frames)

    frame_results = []
    confidences   = []

    for frame_idx, img in frames:
        r = _analyze_single_frame(img)

        evidence_path = _save_heatmap(r["_heatmap"], f"lighting_evidence_f{frame_idx}")

        frame_results.append({
            "frame_index":   frame_idx,
            "confidence":    r["confidence"],
            "prediction":    "FAKE" if r["confidence"] >= 0.5 else "REAL",
            "ambient_score":    r["ambient_score"],
            "shadow_score":     r["shadow_score"],
            "highlight_score":  r["highlight_score"],
            "gradient_score":   r["gradient_score"],
            "lighting_evidence": evidence_path, 
        })
        confidences.append(r["confidence"])

    avg_confidence = round(float(np.mean(confidences)), 4)
    max_confidence = round(float(np.max(confidences)), 4)
    fake_frames    = sum(1 for c in confidences if c >= 0.5)

    return {
        "prediction": "FAKE" if avg_confidence >= 0.5 else "REAL",
        "confidence": avg_confidence,
        "method": "illumination_consistency_video",
        "version": "1.0",
        "metadata": {
            "frames_analyzed": len(frame_results),
            "fake_frames":     fake_frames,
            "real_frames":     len(frame_results) - fake_frames,
            "max_confidence":  max_confidence,
            "avg_confidence":  avg_confidence,
        },
        "frames": frame_results,
    }


@celery_app.task(name="process_illumination_analysis")
def process_illumination_analysis(analysis_id: str, media_type: str):
    db: Session = SessionLocal()
    started_at = datetime.utcnow()

    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            return {"error": "Analysis not found"}

        media      = analysis.media
        file_path  = os.path.join(UPLOADS_DIR, media.location)

        if media_type == MediaTypeEnum.image:
            result_data = analyze_illumination_image(file_path)
        else:
            result_data = analyze_illumination_video(file_path)

        db.add(Result(
            analysis_id=analysis_id,
            type="lum",
            result=result_data,
            started_at=started_at,
            finished_at=datetime.utcnow(),
        ))
        db.commit()

        return {"status": "ok", "confidence": result_data["confidence"]}

    except Exception as e:
        db.rollback()
        db.add(Result(
            analysis_id=analysis_id,
            type="lum",
            result={"error": str(e), "prediction": None, "confidence": None},
            started_at=started_at,
            finished_at=datetime.utcnow(),
        ))
        db.commit()
        return {"error": str(e)}

    finally:
        db.close()