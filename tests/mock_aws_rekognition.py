"""
tests/mock_aws_rekognition.py - High-Fidelity In-Memory Deterministic Mock of AWS Rekognition.

Provides complete offline simulation of boto3 Rekognition client for Milestone M4 testing,
supporting collection management, face indexing, vector search, fault injection, latency simulation,
and seamless monkeypatching of services.aws_client.
"""

import io
import time
import uuid
import hashlib
from typing import Dict, List, Any, Optional, Tuple, Union
from contextlib import contextmanager
from botocore.exceptions import ClientError


class MockFaceRecord:
    """Represents an indexed facial biometric vector in the mock Rekognition collection."""

    def __init__(
        self,
        face_id: str,
        external_image_id: str,
        image_bytes: bytes,
        confidence: float = 99.8,
        bounding_box: Optional[Dict[str, float]] = None
    ):
        self.face_id = face_id
        self.external_image_id = external_image_id
        self.image_bytes = image_bytes
        self.image_hash = self._compute_hash(image_bytes)
        self.confidence = confidence
        self.created_at = time.time()
        self.bounding_box = bounding_box or {
            "Width": 0.35,
            "Height": 0.45,
            "Left": 0.32,
            "Top": 0.28
        }

    @staticmethod
    def _compute_hash(data: bytes) -> str:
        if not data:
            return "0" * 64
        return hashlib.sha256(data).hexdigest()

    def to_boto3_face(self) -> Dict[str, Any]:
        """Formats the record into the standard Boto3 Rekognition Face dictionary."""
        return {
            "FaceId": self.face_id,
            "BoundingBox": self.bounding_box,
            "ImageId": str(uuid.uuid4()),
            "ExternalImageId": self.external_image_id,
            "Confidence": self.confidence,
            "IndexFacesModelVersion": "6.0"
        }

    def to_boto3_face_detail(self) -> Dict[str, Any]:
        """Formats the record into the standard Boto3 Rekognition FaceDetail dictionary."""
        return {
            "BoundingBox": self.bounding_box,
            "Confidence": self.confidence,
            "Landmarks": [
                {"Type": "eyeLeft", "X": self.bounding_box["Left"] + 0.08, "Y": self.bounding_box["Top"] + 0.12},
                {"Type": "eyeRight", "X": self.bounding_box["Left"] + 0.22, "Y": self.bounding_box["Top"] + 0.12},
                {"Type": "nose", "X": self.bounding_box["Left"] + 0.15, "Y": self.bounding_box["Top"] + 0.22},
                {"Type": "mouthLeft", "X": self.bounding_box["Left"] + 0.09, "Y": self.bounding_box["Top"] + 0.32},
                {"Type": "mouthRight", "X": self.bounding_box["Left"] + 0.21, "Y": self.bounding_box["Top"] + 0.32}
            ],
            "Pose": {"Roll": 0.0, "Yaw": 0.0, "Pitch": 0.0},
            "Quality": {"Brightness": 85.0, "Sharpness": 90.0}
        }


class MockRekognitionClient:
    """
    Drop-in replacement for boto3.client('rekognition').
    Maintains collections and face records completely in-memory with deterministic matching.
    """

    def __init__(self):
        self.collections: Dict[str, Dict[str, Any]] = {}
        self.call_history: List[Dict[str, Any]] = []
        self.simulated_latency_sec: float = 0.0
        self.fault_injections: Dict[str, Dict[str, str]] = {}
        self.exceptions = self._create_exceptions_namespace()

    def _create_exceptions_namespace(self):
        class ExceptionsNamespace:
            ResourceNotFoundException = type('ResourceNotFoundException', (ClientError,), {})
            ResourceAlreadyExistsException = type('ResourceAlreadyExistsException', (ClientError,), {})
            InvalidParameterException = type('InvalidParameterException', (ClientError,), {})
            ProvisionedThroughputExceededException = type('ProvisionedThroughputExceededException', (ClientError,), {})
            AccessDeniedException = type('AccessDeniedException', (ClientError,), {})
            InternalServerError = type('InternalServerError', (ClientError,), {})
        return ExceptionsNamespace()

    def _log_call(self, op_name: str, params: Dict[str, Any]):
        self.call_history.append({
            "operation": op_name,
            "params": params,
            "timestamp": time.time()
        })

    def _check_fault(self, op_name: str):
        if op_name in self.fault_injections:
            fault = self.fault_injections[op_name]
            raise ClientError(
                {"Error": {"Code": fault["code"], "Message": fault["message"]}},
                op_name
            )

    def _apply_latency(self):
        if self.simulated_latency_sec > 0:
            time.sleep(self.simulated_latency_sec)

    # -------------------------------------------------------------
    # BOTO3 SDK COMPATIBILITY METHODS
    # -------------------------------------------------------------

    def describe_collection(self, CollectionId: str) -> Dict[str, Any]:
        """Describes the specified collection."""
        self._log_call("describe_collection", {"CollectionId": CollectionId})
        self._check_fault("describe_collection")
        self._apply_latency()

        if CollectionId not in self.collections:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": f"The collection id: {CollectionId} does not exist"}},
                "DescribeCollection"
            )

        col = self.collections[CollectionId]
        return {
            "CollectionARN": f"arn:aws:rekognition:us-east-1:123456789012:collection/{CollectionId}",
            "FaceCount": len(col["faces"]),
            "FaceModelVersion": "6.0",
            "CreationTimestamp": col["created_at"],
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def create_collection(self, CollectionId: str) -> Dict[str, Any]:
        """Creates an in-memory collection."""
        self._log_call("create_collection", {"CollectionId": CollectionId})
        self._check_fault("create_collection")
        self._apply_latency()

        if CollectionId in self.collections:
            raise ClientError(
                {"Error": {"Code": "ResourceAlreadyExistsException", "Message": f"The collection {CollectionId} already exists"}},
                "CreateCollection"
            )

        self.collections[CollectionId] = {
            "faces": {},
            "created_at": time.time()
        }
        return {
            "StatusCode": 200,
            "CollectionArn": f"arn:aws:rekognition:us-east-1:123456789012:collection/{CollectionId}",
            "FaceModelVersion": "6.0",
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def delete_collection(self, CollectionId: str) -> Dict[str, Any]:
        """Deletes the specified collection and all contained faces."""
        self._log_call("delete_collection", {"CollectionId": CollectionId})
        self._check_fault("delete_collection")
        self._apply_latency()

        if CollectionId not in self.collections:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": f"The collection id: {CollectionId} does not exist"}},
                "DeleteCollection"
            )

        del self.collections[CollectionId]
        return {
            "StatusCode": 200,
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def list_collections(self, MaxResults: int = 100, NextToken: str = "") -> Dict[str, Any]:
        """Lists all existing collection IDs."""
        self._log_call("list_collections", {"MaxResults": MaxResults})
        self._check_fault("list_collections")
        self._apply_latency()

        col_ids = list(self.collections.keys())[:MaxResults]
        return {
            "CollectionIds": col_ids,
            "FaceModelVersions": {c: "6.0" for c in col_ids},
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def index_faces(
        self,
        CollectionId: str,
        Image: Dict[str, Any],
        ExternalImageId: str,
        MaxFaces: int = 1,
        QualityFilter: str = "AUTO",
        DetectionAttributes: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Indexes a face into the specified collection."""
        self._log_call("index_faces", {"CollectionId": CollectionId, "ExternalImageId": ExternalImageId})
        self._check_fault("index_faces")
        self._apply_latency()

        if CollectionId not in self.collections:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": f"Collection {CollectionId} not found."}},
                "IndexFaces"
            )

        image_bytes = Image.get("Bytes", b"")
        if not image_bytes:
            return {"FaceRecords": [], "UnindexedFaces": [], "ResponseMetadata": {"HTTPStatusCode": 200}}

        face_id = str(uuid.uuid4())
        record = MockFaceRecord(face_id, ExternalImageId, image_bytes)
        self.collections[CollectionId]["faces"][face_id] = record

        face_dict = record.to_boto3_face()
        face_detail = record.to_boto3_face_detail()

        return {
            "FaceRecords": [{
                "Face": face_dict,
                "FaceDetail": face_detail
            }],
            "UnindexedFaces": [],
            "FaceModelVersion": "6.0",
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def search_faces_by_image(
        self,
        CollectionId: str,
        Image: Dict[str, Any],
        MaxFaces: int = 1,
        FaceMatchThreshold: float = 95.0
    ) -> Dict[str, Any]:
        """
        Searches the collection for matching face records based on image bytes.
        Calculates similarity deterministically.
        """
        self._log_call("search_faces_by_image", {"CollectionId": CollectionId, "FaceMatchThreshold": FaceMatchThreshold})
        self._check_fault("search_faces_by_image")
        self._apply_latency()

        if CollectionId not in self.collections:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": f"Collection {CollectionId} not found."}},
                "SearchFacesByImage"
            )

        query_bytes = Image.get("Bytes", b"")
        if not query_bytes:
            return {"FaceMatches": [], "SearchedFaceConfidence": 0.0, "ResponseMetadata": {"HTTPStatusCode": 200}}

        query_hash = MockFaceRecord._compute_hash(query_bytes)
        matches = []

        for face_id, record in self.collections[CollectionId]["faces"].items():
            # Calculate match similarity:
            # 1. Exact byte hash match -> 99.5%
            # 2. Tagged test match or prefix match -> 97.5%
            # 3. Partial hash character match -> scaled similarity
            if record.image_hash == query_hash:
                sim = 99.5
            elif record.external_image_id in query_bytes.decode('latin-1', errors='ignore'):
                sim = 98.2
            elif query_bytes in record.image_bytes or record.image_bytes in query_bytes:
                sim = 96.8
            else:
                matching_chars = sum(1 for c1, c2 in zip(record.image_hash, query_hash) if c1 == c2)
                sim = round(float(matching_chars) / len(record.image_hash) * 100.0, 1)

            if sim >= FaceMatchThreshold:
                matches.append({
                    "Similarity": sim,
                    "Face": record.to_boto3_face()
                })

        matches.sort(key=lambda m: m["Similarity"], reverse=True)
        top_matches = matches[:MaxFaces]

        return {
            "SearchedFaceBoundingBox": {"Width": 0.35, "Height": 0.45, "Left": 0.32, "Top": 0.28},
            "SearchedFaceConfidence": 99.9 if top_matches else 0.0,
            "FaceMatches": top_matches,
            "FaceModelVersion": "6.0",
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def detect_faces(self, Image: Dict[str, Any], Attributes: Optional[List[str]] = None) -> Dict[str, Any]:
        """Detects faces and generates facial details."""
        self._log_call("detect_faces", {})
        self._check_fault("detect_faces")
        self._apply_latency()

        image_bytes = Image.get("Bytes", b"")
        if not image_bytes or len(image_bytes) < 32:
            return {"FaceDetails": [], "ResponseMetadata": {"HTTPStatusCode": 200}}

        record = MockFaceRecord(str(uuid.uuid4()), "detected_face", image_bytes)
        return {
            "FaceDetails": [record.to_boto3_face_detail()],
            "ResponseMetadata": {"HTTPStatusCode": 200}
        }

    def delete_faces(self, CollectionId: str, FaceIds: List[str]) -> Dict[str, Any]:
        """Deletes specified faces from the collection."""
        self._log_call("delete_faces", {"CollectionId": CollectionId, "FaceIds": FaceIds})
        self._check_fault("delete_faces")
        self._apply_latency()

        if CollectionId not in self.collections:
            raise ClientError(
                {"Error": {"Code": "ResourceNotFoundException", "Message": f"Collection {CollectionId} not found."}},
                "DeleteFaces"
            )

        deleted = []
        for fid in FaceIds:
            if fid in self.collections[CollectionId]["faces"]:
                del self.collections[CollectionId]["faces"][fid]
                deleted.append(fid)

        return {"DeletedFaces": deleted, "ResponseMetadata": {"HTTPStatusCode": 200}}

    # -------------------------------------------------------------
    # TEST HARNESS CONTROLS & UTILITIES
    # -------------------------------------------------------------

    def seed_face(self, collection_id: str, external_image_id: str, image_bytes: bytes) -> str:
        """Helper to quickly seed a face in a collection without manual setup."""
        if collection_id not in self.collections:
            self.create_collection(collection_id)
        res = self.index_faces(collection_id, {"Bytes": image_bytes}, external_image_id)
        return res["FaceRecords"][0]["Face"]["FaceId"]

    def set_latency(self, seconds: float):
        """Sets simulated API call latency in seconds."""
        self.simulated_latency_sec = max(0.0, float(seconds))

    def set_fail_mode(self, operation: str, error_code: str = "InternalServerError", error_message: str = "Simulated AWS failure"):
        """Configures simulated fault injection for an operation."""
        self.fault_injections[operation] = {"code": error_code, "message": error_message}

    def set_fault(self, operation: str, error_code: str, error_message: str):
        """Alias for set_fail_mode."""
        self.set_fail_mode(operation, error_code, error_message)

    def clear_fault(self, operation: str):
        """Clears fault injection for the specified operation."""
        self.fault_injections.pop(operation, None)

    def get_call_log(self, operation: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves call history, optionally filtered by operation name."""
        if operation is None:
            return list(self.call_history)
        return [c for c in self.call_history if c["operation"] == operation]

    def reset(self):
        """Resets all in-memory collections, history, and fault injections."""
        self.collections.clear()
        self.call_history.clear()
        self.fault_injections.clear()
        self.simulated_latency_sec = 0.0


# Global singleton mock client
_global_mock_client = MockRekognitionClient()


def get_mock_rekognition_client() -> MockRekognitionClient:
    """Returns the singleton mock Rekognition client."""
    return _global_mock_client


@contextmanager
def patch_boto3_rekognition(mock_client: Optional[MockRekognitionClient] = None):
    """
    Context manager to safely patch services.aws_client.rekognition with the mock client.
    Restores original client upon exit.
    """
    import services.aws_client as aws_mod
    original_client = aws_mod.rekognition
    active_mock = mock_client or _global_mock_client

    aws_mod.rekognition = active_mock
    try:
        yield active_mock
    finally:
        aws_mod.rekognition = original_client
