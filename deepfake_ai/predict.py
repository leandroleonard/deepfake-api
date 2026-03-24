import os
import json
import numpy as np
import argparse
import cv2

from tensorflow import keras
from PIL import Image

os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"

# ---------------- CONFIG ----------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

MODEL_PATH = os.path.join(
    BASE_DIR,
    "models/patience-10/deepfake_detector_model.keras"
)

THRESHOLD_PATH = os.path.join(
    BASE_DIR,
    "models/patience-10/best_threshold.json"
)

IMAGE_SIZE = (256, 256)
FRAME_INTERVAL = 30  # pegar 1 frame a cada 30 frames

# ---------------- ARGUMENTS ----------------

parser = argparse.ArgumentParser()
parser.add_argument("--image", help="Path da imagem")
parser.add_argument("--video", help="Path do video")

args = parser.parse_args()

file_path = args.image or args.video

if not file_path:
    print(json.dumps({
        "status": "error",
        "message": "Image or video required"
    }))
    exit(1)

# ---------------- LOAD MODEL ----------------

model = keras.models.load_model(MODEL_PATH)

if os.path.exists(THRESHOLD_PATH):
    with open(THRESHOLD_PATH, "r") as f:
        best_threshold = json.load(f)["best_threshold"]
else:
    best_threshold = 0.5

# ---------------- IMAGE PREPROCESS ----------------

def preprocess_image(image_path, target_size=(256, 256)):

    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Image not found: {image_path}")

    img = Image.open(image_path).convert("RGB")
    img = img.resize(target_size)

    img_array = np.array(img, dtype=np.float32) / 255.0
    img_array = np.expand_dims(img_array, axis=0)

    return img_array


# ---------------- VIDEO PROCESS ----------------

def extract_frames(video_path):

    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(video_path)

    frames = []
    count = 0
    saved_count = 0

    # pasta da mídia
    media_dir = os.path.dirname(video_path)

    # nome do vídeo sem extensão
    video_name = os.path.splitext(os.path.basename(video_path))[0]

    # pasta frames
    frames_root = os.path.join(media_dir, "frames")
    video_frames_dir = os.path.join(frames_root, video_name)

    os.makedirs(video_frames_dir, exist_ok=True)

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        if count % FRAME_INTERVAL == 0:

            # salvar frame original
            frame_filename = f"frame_{count:05d}.jpg"
            frame_path = os.path.join(video_frames_dir, frame_filename)

            cv2.imwrite(frame_path, frame)

            # preparar para o modelo
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb = cv2.resize(frame_rgb, IMAGE_SIZE)
            frame_rgb = frame_rgb.astype(np.float32) / 255.0

            frames.append(frame_rgb)

            saved_count += 1

        count += 1

    cap.release()

    if not frames:
        raise Exception("No frames extracted")

    return np.array(frames), saved_count, video_frames_dir


def predict_video(video_path):

    frames, saved_count, frames_dir = extract_frames(video_path)

    preds = model.predict(frames, verbose=0)

    scores = preds.flatten().tolist()

    avg_score = float(np.mean(scores))

    label = "Deepfake" if avg_score < best_threshold else "Real"

    confidence = (
        (1 - avg_score) * 100 if label == "Deepfake"
        else avg_score * 100
    )

    return {
        "file": video_path,
        "frames_analyzed": len(scores),
        "frames_saved": saved_count,
        "frames_directory": frames_dir,
        "avg_score": round(avg_score, 4),
        "threshold": round(best_threshold, 4),
        "label": label,
        "confidence": round(confidence, 2),
        "media_type": "video",
        "status": "success"
    }


# ---------------- MAIN ----------------

try:

    if args.image:

        img = preprocess_image(args.image, IMAGE_SIZE)
        pred = model.predict(img, verbose=0)

        score = float(pred[0][0])

        label = "Deepfake" if score < best_threshold else "Real"

        confidence = (
            (1 - score) * 100 if label == "Deepfake"
            else score * 100
        )

        result = {
            "file": args.image,
            "score": round(score, 4),
            "threshold": round(best_threshold, 4),
            "label": label,
            "confidence": round(confidence, 2),
            "media_type": "image",
            "status": "success"
        }

    elif args.video:

        result = predict_video(args.video)

    print(json.dumps(result))

except Exception as e:

    print(json.dumps({
        "status": "error",
        "message": str(e),
        "file": file_path
    }))