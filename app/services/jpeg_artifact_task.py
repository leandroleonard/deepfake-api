import cv2
import numpy as np
import os
import uuid
from datetime import datetime

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.analysis import Analysis
from app.models.result import Result

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "app/uploads")
HEATMAPS_DIR = os.path.join(UPLOADS_DIR, "heatmaps")
os.makedirs(HEATMAPS_DIR, exist_ok=True)


def _save_image(img_array: np.ndarray, suffix: str) -> str:
    filename = f"{uuid.uuid4().hex}_{suffix}.jpg"
    full_path = os.path.join(HEATMAPS_DIR, filename)
    cv2.imwrite(full_path, img_array)
    return f"/uploads/heatmaps/{filename}"


def analyze_jpeg_artifacts(image_path: str) -> dict:
    """
    Detecta artefatos de compressão JPEG inconsistentes que indicam manipulação.

    Deepfakes frequentemente introduzem regiões com qualidade JPEG diferente
    do resto da imagem — especialmente na região facial após o blending.

    Pipeline:
      1. DCT por blocos 8x8 (padrão JPEG) → mapa de energia de alta frequência
      2. Error Level Analysis (ELA) → diferença entre original e re-comprimido
      3. Detecção de bordas de bloco (block boundary artifacts)
      4. Score final ponderado dos 3 métodos
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Não foi possível abrir a imagem: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape

    # ── 1. DCT por blocos 8x8 ─────────────────────────────────────────────────
    # Energia nas altas frequências de cada bloco indica artefatos de compressão
    block_size = 8
    dct_map = np.zeros_like(gray)

    for y in range(0, h - block_size + 1, block_size):
        for x in range(0, w - block_size + 1, block_size):
            block = gray[y:y + block_size, x:x + block_size]
            dct_block = cv2.dct(block)
            # Alta frequência = canto inferior direito do bloco DCT
            high_freq = np.abs(dct_block[4:, 4:])
            energy = float(np.mean(high_freq))
            dct_map[y:y + block_size, x:x + block_size] = energy

    dct_map_norm = cv2.normalize(dct_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    dct_score = float(np.mean(dct_map) / 255.0)
    dct_score = min(max(dct_score, 0.0), 1.0)

    # ── 2. Error Level Analysis (ELA) ─────────────────────────────────────────
    # Re-comprime a imagem com qualidade conhecida e mede a diferença.
    # Regiões manipuladas têm nível de erro diferente do original.
    tmp_path = os.path.join(HEATMAPS_DIR, f"{uuid.uuid4().hex}_tmp_ela.jpg")
    cv2.imwrite(tmp_path, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    recompressed = cv2.imread(tmp_path).astype(np.float32)
    os.remove(tmp_path)

    original_f = img.astype(np.float32)
    ela_diff = np.abs(original_f - recompressed)
    ela_gray = np.mean(ela_diff, axis=2)  # média dos 3 canais
    ela_amplified = np.clip(ela_gray * 10, 0, 255).astype(np.uint8)  # amplifica para visualização
    ela_score = float(np.mean(ela_gray) / 255.0)
    ela_score = min(max(ela_score, 0.0), 1.0)

    # ── 3. Block Boundary Artifacts ───────────────────────────────────────────
    # Detecta descontinuidades nas bordas dos blocos 8x8 (grid JPEG)
    # Manipulações criam inconsistências nessa grade
    boundary_map = np.zeros_like(gray)

    # Bordas horizontais (a cada 8 linhas)
    for y in range(block_size, h, block_size):
        if y < h:
            diff = np.abs(gray[y, :] - gray[y - 1, :])
            boundary_map[y, :] = diff

    # Bordas verticais (a cada 8 colunas)
    for x in range(block_size, w, block_size):
        if x < w:
            diff = np.abs(gray[:, x] - gray[:, x - 1])
            boundary_map[:, x] = np.maximum(boundary_map[:, x], diff)

    boundary_norm = cv2.normalize(boundary_map, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    boundary_score = float(np.mean(boundary_map) / 255.0)
    boundary_score = min(max(boundary_score, 0.0), 1.0)

    # ── 4. Score final ponderado ──────────────────────────────────────────────
    confidence = round(
        dct_score      * 0.35 +
        ela_score      * 0.45 +  # ELA é o método mais confiável
        boundary_score * 0.20,
        4
    )
    confidence = min(confidence, 1.0)

    # ── 5. Gerar jpeg_evidence ────────────────────────────────────────────────
    # Combina os 3 mapas num único mapa de evidência colorido
    combined = cv2.addWeighted(
        dct_map_norm, 0.35,
        ela_amplified, 0.45,
        0
    )
    combined = cv2.addWeighted(combined, 0.80, boundary_norm, 0.20, 0)
    evidence_colored = cv2.applyColorMap(combined, cv2.COLORMAP_HOT)
    evidence_path = _save_image(evidence_colored, "jpeg_evidence")

    # ── 6. Gerar jpeg_overlay ─────────────────────────────────────────────────
    # Heatmap sobreposto na imagem original
    overlay = cv2.addWeighted(img, 0.50, evidence_colored, 0.50, 0)
    overlay_path = _save_image(overlay, "jpeg_overlay")

    return {
        "prediction": "FAKE" if confidence >= 0.5 else "REAL",
        "confidence": confidence,
        "method": "jpeg_artifact_analysis",
        "version": "1.0",
        "metadata": {
            "dct_score":       round(dct_score, 4),
            "ela_score":       round(ela_score, 4),
            "boundary_score":  round(boundary_score, 4),
            "image_size":      f"{w}x{h}",
            "blocks_analyzed": (h // block_size) * (w // block_size),
        },
        "jpeg_evidence": evidence_path,
        "jpeg_overlay":  overlay_path,
    }


@celery_app.task(name="process_jpeg_artifact_analysis")
def process_jpeg_artifact_analysis(analysis_id: str):
    db = SessionLocal()
    started_at = datetime.utcnow()

    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            return {"error": "Analysis not found"}

        media = analysis.media
        image_path = os.path.join(UPLOADS_DIR, media.location)

        result_data = analyze_jpeg_artifacts(image_path)

        result = Result(
            analysis_id=analysis_id,
            type="jpeg",
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
            type="jpeg",
            result={"error": str(e), "prediction": None, "confidence": None},
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
        db.add(result)
        db.commit()
        return {"error": str(e)}

    finally:
        db.close()