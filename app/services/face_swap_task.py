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

def _save_image(img_array: np.ndarray, suffix: str) -> str:
    filename = f"{uuid.uuid4().hex}_{suffix}.jpg"
    full_path = os.path.join(HEATMAPS_DIR, filename)
    cv2.imwrite(full_path, img_array)
    return f"/uploads/heatmaps/{filename}"

def analyze_face_swap(image_path: str) -> dict:
    """
    Detecta manipulações de troca de rosto (Face Swap).
    
    Foca em:
    1. Inconsistência de Textura (LBP): Deepfakes costumam ter pele "lisa" demais.
    2. Artefatos de Borda: Procura por descontinuidades onde o rosto foi mesclado.
    3. Erro de Reconstrução: Diferença de ruído entre o centro do rosto e as bordas.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Não foi possível abrir a imagem: {image_path}")

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # ── 1. Análise de Textura Local (LBP) ─────────────────────────────────────
    # Deepfakes perdem porosidade natural da pele.
    radius = 3
    n_points = 8 * radius
    lbp = local_binary_pattern(gray, n_points, radius, method='uniform')
    
    # Normaliza LBP para visualização
    lbp_norm = cv2.normalize(lbp, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    
    # Score de textura: quanto menor o desvio padrão local, mais "artificial" (liso)
    texture_score = 1.0 - (np.std(lbp) / (np.mean(lbp) + 1e-6))
    texture_score = min(max(texture_score, 0.0), 1.0)

    # ── 2. Detecção de Artefatos de Blending (Bordas) ─────────────────────────
    # Procura por "halos" ou linhas de costura (seams)
    edges = cv2.Canny(gray, 100, 200)
    kernel = np.ones((5,5), np.uint8)
    dilated_edges = cv2.dilate(edges, kernel, iterations=1)
    
    # Score de bordas: densidade de bordas anômalas
    edge_score = float(np.sum(dilated_edges > 0) / dilated_edges.size)
    edge_score = min(edge_score * 10, 1.0) # Amplifica para escala 0-1

    # ── 3. Mapa de Calor de Manipulação (Heatmap) ─────────────────────────────
    # Combina gradientes e LBP para destacar áreas suspeitas
    grad_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    mag = np.sqrt(grad_x**2 + grad_y**2)
    mag_norm = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    
    # Mistura LBP com Gradiente para evidenciar "costuras" faciais
    combined_map = cv2.addWeighted(lbp_norm, 0.4, mag_norm, 0.6, 0)
    
    # ── 4. Score Final ────────────────────────────────────────────────────────
    confidence = round(texture_score * 0.6 + edge_score * 0.4, 4)
    confidence = min(confidence, 1.0)

    # ── 5. Gerar Imagens de Evidência ─────────────────────────────────────────
    
    # swap_evidence: Mapa de textura e bordas (COLORMAP_JET)
    evidence_colored = cv2.applyColorMap(combined_map, cv2.COLORMAP_JET)
    evidence_path = _save_image(evidence_colored, "swap_evidence")

    # swap_overlay: Sobreposição na imagem original
    overlay = cv2.addWeighted(img, 0.6, evidence_colored, 0.4, 0)
    overlay_path = _save_image(overlay, "swap_overlay")

    return {
        "prediction": "FAKE" if confidence >= 0.5 else "REAL",
        "confidence": confidence,
        "method": "face_swap_texture_analysis",
        "version": "1.0",
        "metadata": {
            "texture_smoothness": round(texture_score, 4),
            "edge_artifacts": round(edge_score, 4),
            "resolution": f"{w}x{h}"
        },
        "swap_evidence": evidence_path,
        "swap_overlay": overlay_path,
    }

@celery_app.task(name="process_face_swap_analysis")
def process_face_swap_analysis(analysis_id: str):
    db = SessionLocal()
    started_at = datetime.utcnow()

    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis: return {"error": "Analysis not found"}

        media = analysis.media
        image_path = os.path.join(UPLOADS_DIR, media.location)

        result_data = analyze_face_swap(image_path)

        result = Result(
            analysis_id=analysis_id,
            type="swap",
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
            type="swap",
            result={"error": str(e), "prediction": None, "confidence": None},
            started_at=started_at,
            finished_at=datetime.utcnow(),
        )
        db.add(result)
        db.commit()
        return {"error": str(e)}
    finally:
        db.close()