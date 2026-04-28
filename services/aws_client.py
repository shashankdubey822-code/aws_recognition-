import boto3
from botocore.exceptions import ClientError
from core.config import AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, COLLECTION_ID, MATCH_THRESHOLD

# Initialize Boto3 Client
# We must check if keys exist to prevent crashing on startup without an .env file
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
    
    try:
        response = rekognition.index_faces(
            CollectionId=COLLECTION_ID,
            Image={'Bytes': image_bytes},
            ExternalImageId=name, # We use the name as the AWS External ID
            MaxFaces=1,
            QualityFilter="AUTO", # AWS automatically rejects blurry faces
            DetectionAttributes=['DEFAULT']
        )
        
        if len(response['FaceRecords']) > 0:
            return True, f"Indexed 1 face for {name}"
        else:
            return False, "No face found by AWS."
            
    except Exception as e:
        return False, str(e)

def delete_all_faces():
    """Deletes the entire collection and recreates it to wipe all face embeddings."""
    if not rekognition: return False, "AWS not configured"
    try:
        print(f"🔥 Deleting collection '{COLLECTION_ID}'...")
        rekognition.delete_collection(CollectionId=COLLECTION_ID)
        rekognition.create_collection(CollectionId=COLLECTION_ID)
        print(f"✨ Collection '{COLLECTION_ID}' recreated (clean start).")
        return True, "All faces deleted successfully."
    except rekognition.exceptions.ResourceNotFoundException:
        rekognition.create_collection(CollectionId=COLLECTION_ID)
        return True, "Collection was already empty."
    except Exception as e:
        return False, str(e)