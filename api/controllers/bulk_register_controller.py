"""
Bulk Smart Registration Controller
===================================
Implements the 5-step user-controlled bulk face registration pipeline:

Step 2: crop_images()       — detect & crop all faces from uploaded 4K photos
Step 3: cluster_faces()     — group same person across multiple photos
Step 5: push_person()       — register ONE person's cluster to AWS
Step 5: push_all()          — register ALL labeled clusters to AWS

SAFETY: This controller ONLY calls index_faces() (append).
        It NEVER calls delete_collection(), delete_faces(), or any destructive AWS API.
        Existing registered students are completely untouched.
"""

import base64
import asyncio
import uuid
import re
import sqlite3
from typing import List, Dict, Any

import cv2
import numpy as np

from services.aws_client import rekognition, register_face_to_aws, COLLECTION_ID
from services.face_detector import detect_faces_4k_ultra
from core.state import DB_PATH

# ─────────────────────────────────────────────────────────────────────────────
# In-memory session store: keyed by session_id
# Holds crops + clusters between HTTP calls (lives in HF container RAM)
# ─────────────────────────────────────────────────────────────────────────────
_sessions: Dict[str, Dict] = {}

CLUSTER_SIMILARITY_THRESHOLD = 85.0   # % — AWS compare_faces similarity
MAX_CROPS_PER_CLUSTER_FOR_AWS = 3     # push top-3 best quality crops per person


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Crop all faces from all uploaded images
# ─────────────────────────────────────────────────────────────────────────────
async def crop_images(file_payloads: List[Dict]) -> Dict:
    """
    Receives list of {"filename": str, "bytes": bytes} dicts.
    Runs SCRFD 4K ultra detector on each image.
    Returns session_id + list of all detected face crops as base64.
    """
    session_id = str(uuid.uuid4())[:12]
    all_crops = []
    total_images = len(file_payloads)

    for img_idx, payload in enumerate(file_payloads):
        img_bytes = payload["bytes"]
        filename = payload["filename"]

        # Run SCRFD ultra detector (same engine used by 4K event scanner)
        faces = await asyncio.to_thread(detect_faces_4k_ultra, img_bytes)

        for face_idx, face in enumerate(faces):
            # display_bytes = natural padded crop at native 4K resolution (quality 100)
            disp_bytes = face.get("display_bytes") or face.get("bytes")
            aws_bytes = face.get("bytes")

            if not disp_bytes or not aws_bytes:
                continue

            disp_b64 = base64.b64encode(disp_bytes).decode("utf-8")

            all_crops.append({
                "crop_id": f"img{img_idx}_face{face_idx}",
                "source_image": filename,
                "image_index": img_idx,
                "face_index": face_idx,
                "crop_b64": f"data:image/jpeg;base64,{disp_b64}",
                # raw bytes kept in memory for clustering (NOT sent to client)
                "_aws_bytes": aws_bytes,
                "_disp_bytes": disp_bytes,
                "confidence": round(face.get("confidence", 0.0), 3),
                "blur": round(face.get("blur", 0.0), 1),
                "pixel_w": face.get("pixel_w", 0),
                "pixel_h": face.get("pixel_h", 0),
                "clustered": False,
            })

    # Store in session
    _sessions[session_id] = {
        "crops": all_crops,
        "clusters": [],
        "total_images": total_images,
    }

    # Return crops without raw bytes (those stay server-side)
    client_crops = [
        {k: v for k, v in c.items() if not k.startswith("_")}
        for c in all_crops
    ]

    print(f"[BULK] Session {session_id}: {len(all_crops)} crops from {total_images} images.")
    return {
        "success": True,
        "session_id": session_id,
        "total_crops": len(all_crops),
        "total_images": total_images,
        "crops": client_crops,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — Cluster faces (group same person from multiple images)
# ─────────────────────────────────────────────────────────────────────────────
def _compare_faces_aws(source_bytes: bytes, target_bytes: bytes) -> float:
    """
    Returns similarity % (0–100) between two face images using AWS Rekognition.
    Uses compare_faces() — does NOT write to any collection.
    """
    if not rekognition:
        return 0.0
    try:
        resp = rekognition.compare_faces(
            SourceImage={"Bytes": source_bytes},
            TargetImage={"Bytes": target_bytes},
            SimilarityThreshold=50.0,   # low threshold here, we filter ourselves
        )
        matches = resp.get("FaceMatches", [])
        if matches:
            return float(matches[0].get("Similarity", 0.0))
        return 0.0
    except Exception as e:
        print(f"[BULK CLUSTER] compare_faces error: {e}")
        return 0.0


async def cluster_faces(session_id: str) -> Dict:
    """
    Groups all crops from the session into person clusters using
    AWS Rekognition compare_faces() as the similarity engine.

    Algorithm:
    1. First crop → seed of Cluster #1
    2. Each subsequent crop compared against ONE representative from each cluster
    3. If similarity >= 85% → added to that cluster
    4. If no match → starts a new cluster
    """
    session = _sessions.get(session_id)
    if not session:
        return {"success": False, "error": "Session not found. Re-upload images."}

    crops = session["crops"]
    if not crops:
        return {"success": False, "error": "No crops found in this session."}

    clusters: List[Dict] = []   # [{cluster_id, label, representative_bytes, crop_ids: []}]
    crop_to_cluster: Dict[str, int] = {}   # crop_id → cluster_index

    print(f"[BULK CLUSTER] Clustering {len(crops)} crops with threshold={CLUSTER_SIMILARITY_THRESHOLD}%...")

    for crop in crops:
        crop_id = crop["crop_id"]
        aws_bytes = crop["_aws_bytes"]
        matched_cluster = None

        # Compare against representative of each existing cluster
        for cidx, cluster in enumerate(clusters):
            rep_bytes = cluster["_representative_bytes"]
            similarity = await asyncio.to_thread(_compare_faces_aws, aws_bytes, rep_bytes)
            print(f"[BULK CLUSTER]   {crop_id} vs Cluster#{cidx+1} → {similarity:.1f}%")
            if similarity >= CLUSTER_SIMILARITY_THRESHOLD:
                matched_cluster = cidx
                break

        if matched_cluster is not None:
            # Add to existing cluster
            clusters[matched_cluster]["crop_ids"].append(crop_id)
            crop_to_cluster[crop_id] = matched_cluster
            crop["clustered"] = True
        else:
            # Start new cluster — this crop becomes the representative
            cluster_num = len(clusters) + 1
            clusters.append({
                "cluster_id": f"cluster_{cluster_num}",
                "label": f"Unknown #{cluster_num}",
                "person_name": "",
                "person_roll": "",
                "crop_ids": [crop_id],
                "_representative_bytes": aws_bytes,  # server-side only
                "pushed_to_aws": False,
                "vector_generated": False,
            })
            crop_to_cluster[crop_id] = len(clusters) - 1
            crop["clustered"] = True

    # Store clusters in session
    session["clusters"] = clusters
    session["crop_to_cluster"] = crop_to_cluster

    # Build client-safe cluster response (no raw bytes)
    client_clusters = []
    crop_index = {c["crop_id"]: c for c in crops}

    for cidx, cluster in enumerate(clusters):
        member_crops = []
        for cid in cluster["crop_ids"]:
            crop = crop_index.get(cid, {})
            member_crops.append({
                "crop_id": cid,
                "crop_b64": crop.get("crop_b64", ""),
                "source_image": crop.get("source_image", ""),
                "confidence": crop.get("confidence", 0.0),
                "blur": crop.get("blur", 0.0),
            })

        client_clusters.append({
            "cluster_id": cluster["cluster_id"],
            "label": cluster["label"],
            "person_name": cluster["person_name"],
            "person_roll": cluster["person_roll"],
            "crop_count": len(cluster["crop_ids"]),
            "crops": member_crops,
            "pushed_to_aws": cluster["pushed_to_aws"],
            "vector_generated": cluster["vector_generated"],
        })

    print(f"[BULK CLUSTER] Found {len(clusters)} unique persons from {len(crops)} crops.")
    return {
        "success": True,
        "session_id": session_id,
        "total_persons": len(clusters),
        "clusters": client_clusters,
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3b — Remove a specific crop from a cluster (user correction)
# ─────────────────────────────────────────────────────────────────────────────
def remove_crop_from_cluster(session_id: str, cluster_id: str, crop_id: str) -> Dict:
    session = _sessions.get(session_id)
    if not session:
        return {"success": False, "error": "Session not found"}

    for cluster in session["clusters"]:
        if cluster["cluster_id"] == cluster_id:
            if crop_id in cluster["crop_ids"]:
                cluster["crop_ids"].remove(crop_id)
                # If cluster is now empty, mark it as removed
                if not cluster["crop_ids"]:
                    cluster["removed"] = True
                return {"success": True, "remaining": len(cluster["crop_ids"])}

    return {"success": False, "error": "Cluster or crop not found"}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Generate vectors + push to AWS for ONE person cluster
# ─────────────────────────────────────────────────────────────────────────────
def _quality_score(crop: Dict) -> float:
    """Higher is better: combines sharpness (blur) and confidence."""
    return crop.get("blur", 0.0) * 0.7 + crop.get("confidence", 0.0) * 100 * 0.3


async def push_person_to_aws(
    session_id: str,
    cluster_id: str,
    person_name: str,
    person_roll: str,
) -> Dict:
    """
    Registers TOP-3 best quality crops from the cluster to AWS Rekognition.
    Saves to local SQLite DB.
    Does NOT touch any existing records.
    """
    session = _sessions.get(session_id)
    if not session:
        return {"success": False, "error": "Session not found. Re-upload images."}

    cluster = next((c for c in session["clusters"] if c["cluster_id"] == cluster_id), None)
    if not cluster:
        return {"success": False, "error": f"Cluster {cluster_id} not found"}

    if cluster.get("pushed_to_aws"):
        return {"success": False, "error": f"{person_name} already pushed to AWS."}

    if not person_name.strip():
        return {"success": False, "error": "Person name cannot be empty"}

    # Build AWS-safe identity key (same format as existing registration)
    safe_name = re.sub(r'[^a-zA-Z0-9_]', '_', person_name.strip().replace(" ", "_"))
    safe_roll = re.sub(r'[^a-zA-Z0-9_]', '_', person_roll.strip() or "BULK")
    identity_key = f"{safe_roll}__{safe_name}"

    # Get crop objects and sort by quality (best first)
    crop_index = {c["crop_id"]: c for c in session["crops"]}
    cluster_crops = [crop_index[cid] for cid in cluster["crop_ids"] if cid in crop_index]
    cluster_crops.sort(key=_quality_score, reverse=True)

    # Push top-N crops to AWS
    crops_to_push = cluster_crops[:MAX_CROPS_PER_CLUSTER_FOR_AWS]
    success_count = 0
    errors = []

    for crop in crops_to_push:
        aws_bytes = crop.get("_aws_bytes")
        if not aws_bytes:
            continue
        ok, msg = await asyncio.to_thread(register_face_to_aws, aws_bytes, identity_key)
        if ok:
            success_count += 1
        else:
            errors.append(msg)

    if success_count == 0:
        return {
            "success": False,
            "error": f"AWS rejected all crops for {person_name}: {'; '.join(errors)}"
        }

    # Save to local SQLite (same table as existing registration)
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO registered_faces (roll_number, name) VALUES (?, ?)",
            (person_roll.strip() or "BULK", person_name.strip())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[BULK] SQLite save error: {e}")

    # Mark cluster as pushed
    cluster["pushed_to_aws"] = True
    cluster["vector_generated"] = True
    cluster["person_name"] = person_name
    cluster["person_roll"] = person_roll

    print(f"[BULK] Pushed {success_count}/{len(crops_to_push)} crops for '{person_name}' [{person_roll}] → AWS key: {identity_key}")
    return {
        "success": True,
        "person_name": person_name,
        "person_roll": person_roll,
        "identity_key": identity_key,
        "crops_pushed": success_count,
        "errors": errors,
        "message": f"✅ {person_name} registered ({success_count} angle vectors) in AWS."
    }


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5b — Push ALL labeled clusters at once
# ─────────────────────────────────────────────────────────────────────────────
async def push_all_to_aws(session_id: str, labels: List[Dict]) -> Dict:
    """
    labels = [{"cluster_id": "cluster_1", "person_name": "Alice", "person_roll": "22BCE001"}, ...]
    Pushes all at once. Skips any already pushed or with empty names.
    """
    results = []
    for label in labels:
        cluster_id = label.get("cluster_id", "")
        name = label.get("person_name", "").strip()
        roll = label.get("person_roll", "").strip()

        if not name:
            results.append({"cluster_id": cluster_id, "skipped": True, "reason": "Empty name"})
            continue

        result = await push_person_to_aws(session_id, cluster_id, name, roll)
        results.append({"cluster_id": cluster_id, **result})

    pushed = sum(1 for r in results if r.get("success"))
    skipped = sum(1 for r in results if r.get("skipped"))
    failed = len(results) - pushed - skipped

    return {
        "success": True,
        "pushed": pushed,
        "skipped": skipped,
        "failed": failed,
        "results": results,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Session cleanup
# ─────────────────────────────────────────────────────────────────────────────
def clear_session(session_id: str):
    _sessions.pop(session_id, None)
