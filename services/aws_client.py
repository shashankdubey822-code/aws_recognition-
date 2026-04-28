import boto3
from botocore.exceptions import ClientError
from core.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, COLLECTION_ID, MATCH_THRESHOLD

# Initialize Boto3 Client
if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
    rekognition = boto3.client(
        'rekognition',
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )
else:
    rekognition = None
    print("⚠️ WARNING: AWS Credentials not found. AWS features will not work.")

def ensure_collection_exists():
    """Checks if the Rekognition Collection exists, creates it if not."""
    if not rekognition: return
    try:
        rekognition.describe_collection(CollectionId=COLLECTION_ID)
        print(f"☁️ AWS Collection '{COLLECTION_ID}' found.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"☁️ Creating new AWS Collection '{COLLECTION_ID}'...")
            rekognition.create_collection(CollectionId=COLLECTION_ID)
        else:
            print(f"AWS Error: {e}")

def register_face_to_aws(image_bytes, name):
    """Sends an image to AWS to be indexed under the given name."""
    if not rekognition: return False, "AWS not configured"
    
    # AWS ExternalImageId does not allow spaces. 
    # Regex allowed: [a-zA-Z0-9_.\-:]+
    safe_name = name.replace(" ", "_")
    
    try:
        response = rekognition.index_faces(
            CollectionId=COLLECTION_ID,
            Image={'Bytes': image_bytes},
            ExternalImageId=safe_name,
            MaxFaces=1,
            QualityFilter="AUTO",
            DetectionAttributes=['DEFAULT']
        )
        
        if len(response['FaceRecords']) > 0:
            return True, f"Indexed 1 face for {name}"
        else:
            return False, "No face found by AWS."
            
    except Exception as e:
        return False, str(e)

def search_face_on_aws(image_bytes):
    """Searches AWS for the faces in the image."""
    if not rekognition: return []
    
    try:
        response = rekognition.search_faces_by_image(
            CollectionId=COLLECTION_ID,
            Image={'Bytes': image_bytes},
            MaxFaces=1, 
            FaceMatchThreshold=MATCH_THRESHOLD
        )
        
        results = []
        if len(response['FaceMatches']) > 0:
            match = response['FaceMatches'][0]
            confidence = match['Similarity']
            name = match['Face']['ExternalImageId']
            bbox = response['SearchedFaceBoundingBox']
            
            results.append({
                "status": "match",
                "name": name,
                "score": round(confidence, 1),
                "aws_box": bbox
            })
        else:
            if 'SearchedFaceBoundingBox' in response:
                results.append({
                    "status": "unknown",
                    "name": "Unknown",
                    "score": 0,
                    "aws_box": response['SearchedFaceBoundingBox']
                })
                
        return results
    except Exception as e:
        return []

def delete_all_faces():
    """Deletes the entire collection and recreates it to wipe all face embeddings."""
    if not rekognition: return False, "AWS not configured"
    try:
        print(f"🔥 Deleting collection '{COLLECTION_ID}'...")
        try:
            rekognition.delete_collection(CollectionId=COLLECTION_ID)
        except rekognition.exceptions.ResourceNotFoundException:
            pass
        rekognition.create_collection(CollectionId=COLLECTION_ID)
        print(f"✨ Collection '{COLLECTION_ID}' recreated (clean start).")
        return True, "All faces deleted successfully."
    except Exception as e:
        return False, str(e)
