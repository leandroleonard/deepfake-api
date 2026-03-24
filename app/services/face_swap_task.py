import cv2
import numpy as np
import os
import uuid
from datetime import datetime
from skimage.feature import local_binary_pattern

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.analysis import Analysis
from app.models.result import Result

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "app/uploads")
HEATMAPS_DIR = os.path.join(UPLOADS_DIR, "heatmaps")
os.makedirs(HEATMAPS_DIR, exist_ok=True)

MIN_FRAMES = 5


def _save_image(img_array: np.ndarray, suffix: str) -> str:
    filename = f"{uuid.uuid4().hex}_{suffix}.jpg"
    full_path = os.path.join(HEATMAPS_DIR, filename)
    cv2.imwrite(full_path, img_array)
    return f"/uploads/heatmaps/{filename}"

def _extract_frames(video_path: str, num_frames: int = MIN_FRAMES) -> list:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Não foi possível abrir o vídeo: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        raise ValueError("Vídeo sem frames detectados.")

    indices = np.linspace(0, total - 1, num=num_frames, dtype=int)
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
    Analisa um único frame/imagem para face swap.
    Retorna scores + arrays de evidência (não salva em disco).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    radius   = 3
    n_points = 8 * radius
    lbp      = local_binary_pattern(gray, n_points, radius, method='uniform')
    lbp_norm = cv2.normalize(lbp, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    texture_score = 1.0 - (np.std(lbp) / (np.mean(lbp) + 1e-6))
    texture_score = min(max(float(texture_score), 0.0), 1.0)

    edges         = cv2.Canny(gray, 100, 200)
    kernel        = np.ones((5, 5), np.uint8)
    dilated_edges = cv2.dilate(edges, kernel, iterations=1)

    edge_score = float(np.sum(dilated_edges > 0) / dilated_edges.size)
    edge_score = min(edge_score * 10, 1.0)

    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag      = np.sqrt(grad_x ** 2 + grad_y ** 2)
    mag_norm = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    combined_map     = cv2.addWeighted(lbp_norm, 0.4, mag_norm, 0.6, 0)
    evidence_colored = cv2.applyColorMap(combined_map, cv2.COLORMAP_JET)

    confidence = round(texture_score * 0.6 + edge_score * 0.4, 4)
    confidence = min(confidence, 1.0)

    return {
        "confidence":     confidence,
        "texture_score":  round(texture_score, 4),
        "edge_score":     round(edge_score, 4),
        "resolution":     f"{w}x{h}",
        "_evidence": evidence_colored,
        "_original": img,
    }


def analyze_face_swap_image(image_path: str) -> dict:
    """Análise de face swap para imagem estática."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Não foi possível abrir a imagem: {image_path}")

    r = _analyze_single_frame(img)

    evidence_path = _save_image(r["_evidence"], "swap_evidence")
    overlay       = cv2.addWeighted(img, 0.6, r["_evidence"], 0.4, 0)
    overlay_path  = _save_image(overlay, "swap_overlay")

    return {
        "prediction": "FAKE" if r["confidence"] >= 0.5 else "REAL",
        "confidence": r["confidence"],
        "method":     "face_swap_texture_analysis",
        "version":    "1.0",
        "metadata": {
            "texture_smoothness": r["texture_score"],
            "edge_artifacts":     r["edge_score"],
            "resolution":         r["resolution"],
        },
        "swap_evidence": evidence_path,
        "swap_overlay":  overlay_path,
    }


def analyze_face_swap_video(video_path: str, num_frames: int = MIN_FRAMES) -> dict:
    """
    Análise de face swap para vídeo.
    Extrai frames, analisa cada um e retorna média + swap_evidence por frame.
    """
    frames = _extract_frames(video_path, num_frames)

    frame_results = []
    confidences   = []

    for frame_idx, img in frames:
        r = _analyze_single_frame(img)

        evidence_path = _save_image(r["_evidence"], f"swap_evidence_f{frame_idx}")

        frame_results.append({
            "frame_index":   frame_idx,
            "confidence":    r["confidence"],
            "prediction":    "FAKE" if r["confidence"] >= 0.5 else "REAL",
            "texture_smoothness": r["texture_score"],
            "edge_artifacts":     r["edge_score"],
            "resolution":         r["resolution"],
            "swap_evidence": evidence_path,
        })
        confidences.append(r["confidence"])

    avg_confidence = round(float(np.mean(confidences)), 4)
    max_confidence = round(float(np.max(confidences)), 4)
    fake_frames    = sum(1 for c in confidences if c >= 0.5)

    return {
        "prediction": "FAKE" if avg_confidence >= 0.5 else "REAL",
        "confidence": avg_confidence,
        "method":     "face_swap_texture_analysis_video",
        "version":    "1.0",
        "metadata": {
            "frames_analyzed": len(frame_results),
            "fake_frames":     fake_frames,
            "real_frames":     len(frame_results) - fake_frames,
            "avg_confidence":  avg_confidence,
            "max_confidence":  max_confidence,
        },
        "frames": frame_results,
    }


@celery_app.task(name="process_face_swap_analysis")
def process_face_swap_analysis(analysis_id: str, media_type: str):
    db = SessionLocal()
    started_at = datetime.utcnow()

    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            return {"error": "Analysis not found"}

        media     = analysis.media
        file_path = os.path.join(UPLOADS_DIR, media.location)

        if media_type == 'image':
            result_data = analyze_face_swap_image(file_path)
        else:
            result_data = analyze_face_swap_video(file_path)

        db.add(Result(
            analysis_id=analysis_id,
            type="swap",
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
            type="swap",
            result={"error": str(e), "prediction": None, "confidence": None},
            started_at=started_at,
            finished_at=datetime.utcnow(),
        ))
        db.commit()
        return {"error": str(e)}

    finally:
        db.close()