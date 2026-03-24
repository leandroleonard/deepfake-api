import json
import os
import re
import subprocess
from datetime import datetime
from typing import Any, Dict, List, Tuple

from app.core.celery_app import celery_app
from app.db.session import SessionLocal
from app.models.analysis import Analysis
from app.models.result import Result

UPLOADS_DIR = os.getenv("UPLOADS_DIR", "app/uploads")

AI_KEYWORDS = [
    "openai",
    "OpenAI-API"
    "open-ai",
    "chatgpt",
    "dall-e",
    "dalle",
    "midjourney",
    "stable diffusion",
    "stablediffusion",
    "automatic1111",
    "comfyui",
    "invokeai",
    "generative",
    "ai generated",
    "aigc",
    "diffusion",
    "prompt",
    "negative prompt",
    "sampler",
    "seed",
    "steps",
    "cfg scale",
    "clip skip",
    "lora",
    "text encoder",
    "GPT-4o",
    "gpt",
    "claude",
    "nano banana",
]

SUSPICIOUS_TAG_HINTS = [
    "Software",
    "CreatorTool",
    "ProcessingSoftware",
    "Comment",
    "UserComment",
    "Description",
    "ImageDescription",
    "XPComment",
    "XPSubject",
    "XPKeywords",
    "Keywords",
    "Subject",
    "Title",
    "CreateDate",
    "ModifyDate",
    "Producer",
    "Creator",
    "AuthorsPosition",
    "XMP",
]


def _run_exiftool_json(file_path: str) -> Dict[str, Any]:
    """
    Retorna um dict com os metadados via exiftool JSON.
    -G1: inclui grupo (EXIF, XMP, IPTC...) no nome do campo
    -j: json
    -n: numérico onde aplicável
    """
    try:
        proc = subprocess.run(
            ["exiftool", "-G1", "-j", "-n", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as e:
        raise RuntimeError("exiftool não está instalado ou não está no PATH") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"exiftool falhou: {e.stderr or e.stdout}") from e

    data = json.loads(proc.stdout or "[]")
    if not data:
        return {}
    return data[0]


def _flatten_metadata(meta: Dict[str, Any]) -> List[Tuple[str, str]]:
    """
    Flata valores para pares (key, value_as_string), ignorando binários.
    """
    items: List[Tuple[str, str]] = []
    for k, v in meta.items():
        if v is None:
            continue
        if isinstance(v, (int, float, bool)):
            items.append((k, str(v)))
        elif isinstance(v, str):
            items.append((k, v))
        elif isinstance(v, list):
            try:
                items.append((k, " | ".join([str(x) for x in v[:50]])))
            except Exception:
                continue
        elif isinstance(v, dict):
            items.append((k, json.dumps(v)[:5000]))
        else:
            continue
    return items


def _find_ai_signatures(meta: Dict[str, Any]) -> Dict[str, Any]:
    """
    Procura palavras-chave em tags suspeitas e também em todo o metadata.
    Retorna:
      {
        "hit": bool,
        "matches": [{"tag": "...", "value_excerpt": "...", "keyword": "..."}],
        "searched_tags": int
      }
    """
    flat = _flatten_metadata(meta)
    matches = []

    # regex de keywords (case-insensitive, com tolerância a espaços)
    kw_patterns = []
    for kw in AI_KEYWORDS:
        # transforma "stable diffusion" em regex com espaços flexíveis
        escaped = re.escape(kw).replace(r"\ ", r"\s+")
        kw_patterns.append((kw, re.compile(escaped, re.IGNORECASE)))

    for tag, value in flat:
        tag_short = tag.split(":")[-1]  # "XMP:Software" -> "Software"
        tag_is_suspicious = any(h.lower() in tag_short.lower() for h in SUSPICIOUS_TAG_HINTS)

        for kw, rx in kw_patterns:
            if rx.search(value):
                excerpt = value.strip()
                if len(excerpt) > 280:
                    excerpt = excerpt[:280] + "…"
                matches.append(
                    {
                        "tag": tag,
                        "tag_suspicious": tag_is_suspicious,
                        "keyword": kw,
                        "value_excerpt": excerpt,
                    }
                )

    # de-dup
    uniq = []
    seen = set()
    for m in matches:
        key = (m["tag"], m["keyword"], m["value_excerpt"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(m)

    return {
        "hit": len(uniq) > 0,
        "matches": uniq[:30],
        "searched_tags": len(flat),
    }


@celery_app.task(name="process_metadata_ai_analysis")
def process_metadata_ai_analysis(analysis_id: str):
    db = SessionLocal()
    started_at = datetime.utcnow()

    try:
        analysis = db.query(Analysis).filter(Analysis.id == analysis_id).first()
        if not analysis:
            return {"error": "Analysis not found"}

        media = analysis.media
        file_path = os.path.join(UPLOADS_DIR, media.location)

        meta = _run_exiftool_json(file_path)
        findings = _find_ai_signatures(meta)

        if findings["hit"]:
            result_data = {
                "prediction": "FAKE",
                "confidence": 1.0,
                "method": "metadata_ai_signature",
                "version": "1.0",
                "metadata": {
                    "reason": "Encontradas assinaturas/keywords associadas a conteúdo gerado por IA nos metadados.",
                    "matches": findings["matches"],
                    "searched_tags": findings["searched_tags"],
                },
            }
        else:
            result_data = {
                "prediction": "UNKNOWN",
                "confidence": 0.0,
                "method": "metadata_ai_signature",
                "version": "1.0",
                "metadata": {
                    "reason": "Nenhuma assinatura evidente de IA encontrada nos metadados (não é prova de autenticidade).",
                    "searched_tags": findings["searched_tags"],
                },
            }

        db.add(
            Result(
                analysis_id=analysis_id,
                type="meta_ai",
                result=result_data,
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )
        )
        db.commit()
        return {"status": "ok", "hit": findings["hit"]}

    except Exception as e:
        db.rollback()
        db.add(
            Result(
                analysis_id=analysis_id,
                type="meta_ai",
                result={"error": str(e), "prediction": None, "confidence": None},
                started_at=started_at,
                finished_at=datetime.utcnow(),
            )
        )
        db.commit()
        return {"error": str(e)}

    finally:
        db.close()