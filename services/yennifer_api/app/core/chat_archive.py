"""
S3 Archive Layer for Cold Chat Messages.

Archives old chat messages (> 365 days) to S3 with:
- Per-user encryption using user's DEK
- Lifecycle rules for Glacier transition
- Organized by user/year/month for efficient retrieval

Object key format: chat-archive/{user_id}/{year}/{month}/session-{session_id}.json.enc
"""

import gzip
import json
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID

import boto3
from botocore.exceptions import ClientError

from .config import get_settings
from .encryption import encrypt_for_user, decrypt_for_user, decrypt_user_dek

logger = logging.getLogger(__name__)


class ChatArchive:
    """S3 archive for cold chat storage."""
    
    def __init__(
        self,
        bucket_name: Optional[str] = None,
        region: Optional[str] = None,
    ):
        """
        Initialize the archive.
        
        Args:
            bucket_name: S3 bucket name. If None, uses settings.
            region: AWS region. If None, uses settings.
        """
        settings = get_settings()
        self._bucket = bucket_name or getattr(settings, 'chat_archive_bucket', None)
        self._region = region or settings.aws_region
        self._enabled = bool(self._bucket)
        self._client: Optional[boto3.client] = None
        
        if not self._enabled:
            logger.info("S3 chat archive disabled (no bucket configured)")
    
    def _get_client(self) -> Optional[boto3.client]:
        """Get or create S3 client."""
        if not self._enabled:
            return None
            
        if self._client is None:
            try:
                self._client = boto3.client('s3', region_name=self._region)
            except Exception as e:
                logger.error(f"Failed to create S3 client: {e}")
                self._enabled = False
                
        return self._client
    
    def _archive_key(
        self,
        user_id: UUID,
        session_id: UUID,
        year: int,
        month: int,
    ) -> str:
        """Generate S3 object key."""
        return f"chat-archive/{user_id}/{year}/{month:02d}/session-{session_id}.json.enc.gz"
    
    async def archive_session(
        self,
        user_id: UUID,
        session_id: UUID,
        messages: List[Dict[str, Any]],
        user_dek: bytes,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Archive a chat session to S3.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            messages: List of message dicts (content should be decrypted).
            user_dek: User's DEK for encryption.
            session_metadata: Optional session metadata.
            
        Returns:
            True if archived successfully.
        """
        client = self._get_client()
        if not client:
            return False
            
        try:
            # Determine archive date from messages
            if messages:
                first_msg_date = messages[0].get("created_at", "")
                if isinstance(first_msg_date, str):
                    dt = datetime.fromisoformat(first_msg_date.replace("Z", "+00:00"))
                else:
                    dt = datetime.now()
            else:
                dt = datetime.now()
            
            year = dt.year
            month = dt.month
            
            # Build archive payload
            archive_data = {
                "session_id": str(session_id),
                "user_id": str(user_id),
                "archived_at": datetime.utcnow().isoformat() + "Z",
                "message_count": len(messages),
                "metadata": session_metadata or {},
                "messages": messages,
            }
            
            # Serialize
            json_data = json.dumps(archive_data, default=str)
            
            # Encrypt with user's DEK
            encrypted_data = encrypt_for_user(user_dek, json_data)
            
            # Compress
            compressed_data = gzip.compress(encrypted_data)
            
            # Upload to S3
            key = self._archive_key(user_id, session_id, year, month)
            
            client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=compressed_data,
                ContentType='application/octet-stream',
                Metadata={
                    'user-id': str(user_id),
                    'session-id': str(session_id),
                    'message-count': str(len(messages)),
                    'archived-at': datetime.utcnow().isoformat(),
                },
                # SSE-S3 for additional layer (our data is already encrypted)
                ServerSideEncryption='AES256',
            )
            
            logger.info(f"Archived session {session_id} to S3: {key}")
            return True
            
        except ClientError as e:
            logger.error(f"S3 error archiving session {session_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to archive session {session_id}: {e}")
            return False
    
    async def retrieve_session(
        self,
        user_id: UUID,
        session_id: UUID,
        year: int,
        month: int,
        user_dek: bytes,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve an archived session from S3.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            year: Archive year.
            month: Archive month.
            user_dek: User's DEK for decryption.
            
        Returns:
            Archive data dict or None.
        """
        client = self._get_client()
        if not client:
            return None
            
        try:
            key = self._archive_key(user_id, session_id, year, month)
            
            response = client.get_object(
                Bucket=self._bucket,
                Key=key,
            )
            
            # Read and decompress
            compressed_data = response['Body'].read()
            encrypted_data = gzip.decompress(compressed_data)
            
            # Decrypt with user's DEK
            json_data = decrypt_for_user(user_dek, encrypted_data)
            
            # Parse
            archive_data = json.loads(json_data)
            
            logger.info(f"Retrieved archived session {session_id} from S3")
            return archive_data
            
        except client.exceptions.NoSuchKey:
            logger.debug(f"Archive not found: {session_id}")
            return None
        except ClientError as e:
            # Check for Glacier restore needed
            if e.response['Error']['Code'] == 'InvalidObjectState':
                logger.info(f"Session {session_id} is in Glacier, restore needed")
                return {"error": "glacier_restore_needed", "session_id": str(session_id)}
            logger.error(f"S3 error retrieving session {session_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve session {session_id}: {e}")
            return None
    
    async def list_user_archives(
        self,
        user_id: UUID,
        year: Optional[int] = None,
        month: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        List archived sessions for a user.
        
        Args:
            user_id: User's UUID.
            year: Optional year filter.
            month: Optional month filter.
            
        Returns:
            List of archive metadata dicts.
        """
        client = self._get_client()
        if not client:
            return []
            
        try:
            # Build prefix
            if year and month:
                prefix = f"chat-archive/{user_id}/{year}/{month:02d}/"
            elif year:
                prefix = f"chat-archive/{user_id}/{year}/"
            else:
                prefix = f"chat-archive/{user_id}/"
            
            # List objects
            paginator = client.get_paginator('list_objects_v2')
            archives = []
            
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Parse key to extract session info
                    parts = key.split('/')
                    if len(parts) >= 4 and parts[-1].startswith('session-'):
                        session_id = parts[-1].replace('session-', '').replace('.json.enc.gz', '')
                        archives.append({
                            'key': key,
                            'session_id': session_id,
                            'year': int(parts[2]),
                            'month': int(parts[3]),
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'storage_class': obj.get('StorageClass', 'STANDARD'),
                        })
            
            return archives
            
        except ClientError as e:
            logger.error(f"Failed to list archives for user {user_id}: {e}")
            return []
    
    async def initiate_glacier_restore(
        self,
        user_id: UUID,
        session_id: UUID,
        year: int,
        month: int,
        days: int = 7,
    ) -> bool:
        """
        Initiate restore of a Glacier-archived session.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            year: Archive year.
            month: Archive month.
            days: Number of days to keep restored copy.
            
        Returns:
            True if restore initiated.
        """
        client = self._get_client()
        if not client:
            return False
            
        try:
            key = self._archive_key(user_id, session_id, year, month)
            
            client.restore_object(
                Bucket=self._bucket,
                Key=key,
                RestoreRequest={
                    'Days': days,
                    'GlacierJobParameters': {
                        'Tier': 'Standard',  # 3-5 hours
                    },
                },
            )
            
            logger.info(f"Initiated Glacier restore for session {session_id}")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'RestoreAlreadyInProgress':
                logger.info(f"Restore already in progress for session {session_id}")
                return True
            logger.error(f"Failed to initiate restore for session {session_id}: {e}")
            return False
    
    async def delete_archive(
        self,
        user_id: UUID,
        session_id: UUID,
        year: int,
        month: int,
    ) -> bool:
        """
        Delete an archived session.
        
        Args:
            user_id: User's UUID.
            session_id: Session UUID.
            year: Archive year.
            month: Archive month.
            
        Returns:
            True if deleted.
        """
        client = self._get_client()
        if not client:
            return False
            
        try:
            key = self._archive_key(user_id, session_id, year, month)
            
            client.delete_object(
                Bucket=self._bucket,
                Key=key,
            )
            
            logger.info(f"Deleted archive for session {session_id}")
            return True
            
        except ClientError as e:
            logger.error(f"Failed to delete archive for session {session_id}: {e}")
            return False
    
    @property
    def is_enabled(self) -> bool:
        """Check if archive is enabled."""
        return self._enabled


# Global archive instance
_archive: Optional[ChatArchive] = None


def get_chat_archive() -> ChatArchive:
    """Get the global chat archive instance."""
    global _archive
    if _archive is None:
        _archive = ChatArchive()
    return _archive


