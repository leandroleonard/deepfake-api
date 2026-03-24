import cv2
import numpy as np
import os

MODEL_DIR    = os.getenv("FACE_MODEL_DIR", "app/services/models/face")
PROTOTXT     = os.path.join(MODEL_DIR, "deploy.prototxt")
CAFFEMODEL   = os.path.join(MODEL_DIR, "res10_300x300_ssd_iter_140000.caffemodel")

_net = None 


def _get_net():
    global _net
    if _net is None:
        if not os.path.exists(PROTOTXT) or not os.path.exists(CAFFEMODEL):
            raise RuntimeError(
                f"Modelos DNN não encontrados em {MODEL_DIR}.\n"
            )
        _net = cv2.dnn.readNetFromCaffe(PROTOTXT, CAFFEMODEL)
    return _net


def detect_face(frame: np.ndarray) -> np.ndarray | None:
    """
    Detecta o melhor rosto no frame.
    Retorna o crop do rosto (com margem) ou None se não encontrar.
    """
    net = _get_net()
    h, w = frame.shape[:2]

    blob = cv2.dnn.blobFromImage(frame, 1.0, (300, 300), (104.0, 177.0, 123.0))
    net.setInput(blob)
    detections = net.forward()

    best_face = None
    best_conf = 0.0

    for i in range(detections.shape[2]):
        confidence = float(detections[0, 0, i, 2])

        if confidence > 0.6 and confidence > best_conf:
            box = detections[0, 0, i, 3:7] * np.array([w, h, w, h])
            x1, y1, x2, y2 = box.astype("int")

            margin = int((x2 - x1) * 0.2)
            x1 = max(0, x1 - margin)
            y1 = max(0, y1 - margin)
            x2 = min(w, x2 + margin)
            y2 = min(h, y2 + margin)

            face = frame[y1:y2, x1:x2]
            if face.size > 0:
                best_face = face
                best_conf = confidence

    return best_face


def _is_video(file_path: str) -> bool:
    return os.path.splitext(file_path)[1].lower() in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".flv"}


def media_has_face(file_path: str) -> bool:
    if _is_video(file_path):
        return _video_has_face(file_path)
    else:
        return _image_has_face(file_path)


def _image_has_face(image_path: str) -> bool:
    img = cv2.imread(image_path)
    if img is None:
        return False
    return detect_face(img) is not None


def _video_has_face(video_path: str, sample_frames: int = 5) -> bool:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return False

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if total <= 0:
        cap.release()
        return False

    indices = np.linspace(0, total - 1, num=sample_frames, dtype=int)

    found = False
    for idx in indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, int(idx))
        ret, frame = cap.read()
        if ret and frame is not None:
            if detect_face(frame) is not None:
                found = True
                break 

    cap.release()
    return found