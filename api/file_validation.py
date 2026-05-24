"""
File Upload Validation and Security

Comprehensive file upload validation including:
- MIME type verification
- File size limits
- Magic number validation
- Filename sanitization
- Malware scanning integration
"""

import os
import mimetypes
import magic
import re
from typing import Optional, List, Tuple
from fastapi import UploadFile, HTTPException, status
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Configuration
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "100"))
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

# Allowed MIME types for different file categories
ALLOWED_MIMETYPES = {
    'image': [
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'image/tiff',
    ],
    'document': [
        'application/pdf',
        'text/plain',
        'text/csv',
        'application/json',
    ],
    'data': [
        'application/x-netcdf',
        'application/x-hdf',
        'application/octet-stream',  # Generic binary
        'text/csv',
        'application/json',
    ],
    'archive': [
        'application/zip',
        'application/x-tar',
        'application/gzip',
        'application/x-7z-compressed',
    ]
}

# Dangerous file extensions to block
BLOCKED_EXTENSIONS = {
    '.exe', '.dll', '.bat', '.cmd', '.com', '.pif', '.scr',
    '.vbs', '.js', '.jar', '.sh', '.app', '.deb', '.rpm',
    '.msi', '.ps1', '.wsf', '.cpl', '.inf', '.reg'
}

# Magic number signatures for common file types (first bytes)
MAGIC_NUMBERS = {
    'image/jpeg': [b'\xFF\xD8\xFF'],
    'image/png': [b'\x89PNG\r\n\x1a\n'],
    'image/gif': [b'GIF87a', b'GIF89a'],
    'application/pdf': [b'%PDF-'],
    'application/zip': [b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08'],
    'application/gzip': [b'\x1f\x8b'],
}


class FileValidator:
    """Comprehensive file upload validator"""

    def __init__(
        self,
        max_size_bytes: int = MAX_FILE_SIZE_BYTES,
        allowed_categories: Optional[List[str]] = None,
        allowed_mimetypes: Optional[List[str]] = None,
        enable_magic_check: bool = True,
        enable_virus_scan: bool = False,
    ):
        """
        Initialize file validator.

        Args:
            max_size_bytes: Maximum file size in bytes
            allowed_categories: Allowed file categories (image, document, data, archive)
            allowed_mimetypes: Specific allowed MIME types (overrides categories)
            enable_magic_check: Verify file content matches declared type
            enable_virus_scan: Enable ClamAV virus scanning
        """
        self.max_size_bytes = max_size_bytes
        self.enable_magic_check = enable_magic_check
        self.enable_virus_scan = enable_virus_scan

        # Build allowed MIME types list
        if allowed_mimetypes:
            self.allowed_mimetypes = set(allowed_mimetypes)
        elif allowed_categories:
            self.allowed_mimetypes = set()
            for category in allowed_categories:
                self.allowed_mimetypes.update(ALLOWED_MIMETYPES.get(category, []))
        else:
            # Default: allow all defined types
            self.allowed_mimetypes = set()
            for mimes in ALLOWED_MIMETYPES.values():
                self.allowed_mimetypes.update(mimes)

    def sanitize_filename(self, filename: str) -> str:
        """
        Sanitize uploaded filename to prevent path traversal and other attacks.

        Args:
            filename: Original filename

        Returns:
            Sanitized filename
        """
        # Remove path components
        filename = os.path.basename(filename)

        # Remove any null bytes
        filename = filename.replace('\x00', '')

        # Replace dangerous characters
        filename = re.sub(r'[^\w\s.-]', '_', filename)

        # Remove leading dots and spaces
        filename = filename.lstrip('. ')

        # Limit length
        if len(filename) > 255:
            name, ext = os.path.splitext(filename)
            filename = name[:255 - len(ext)] + ext

        # Ensure filename is not empty
        if not filename:
            filename = 'unnamed_file'

        return filename

    def check_extension(self, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Check if file extension is allowed.

        Args:
            filename: File name

        Returns:
            (is_valid, error_message)
        """
        ext = os.path.splitext(filename.lower())[1]

        if ext in BLOCKED_EXTENSIONS:
            return False, f"File extension '{ext}' is not allowed for security reasons"

        return True, None

    def check_size(self, file_size: int) -> Tuple[bool, Optional[str]]:
        """
        Check if file size is within limits.

        Args:
            file_size: File size in bytes

        Returns:
            (is_valid, error_message)
        """
        if file_size > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            return False, f"File size exceeds maximum allowed size of {max_mb:.1f} MB"

        if file_size == 0:
            return False, "File is empty"

        return True, None

    def check_mimetype(self, mimetype: str) -> Tuple[bool, Optional[str]]:
        """
        Check if MIME type is allowed.

        Args:
            mimetype: MIME type string

        Returns:
            (is_valid, error_message)
        """
        if mimetype not in self.allowed_mimetypes:
            return False, f"File type '{mimetype}' is not allowed"

        return True, None

    def verify_magic_number(self, content: bytes, declared_mimetype: str) -> Tuple[bool, Optional[str]]:
        """
        Verify file content matches declared MIME type using magic numbers.

        Args:
            content: First bytes of file
            declared_mimetype: MIME type from file extension/header

        Returns:
            (is_valid, error_message)
        """
        if not self.enable_magic_check:
            return True, None

        # Get expected magic numbers
        expected_magics = MAGIC_NUMBERS.get(declared_mimetype, [])
        if not expected_magics:
            # No magic number defined, use libmagic
            try:
                detected_mime = magic.from_buffer(content, mime=True)
                if detected_mime != declared_mimetype:
                    logger.warning(
                        f"MIME type mismatch: declared={declared_mimetype}, "
                        f"detected={detected_mime}"
                    )
                    # Be lenient with octet-stream
                    if declared_mimetype != 'application/octet-stream':
                        return False, f"File content does not match declared type"
            except Exception as e:
                logger.error(f"Magic number check failed: {e}")

            return True, None

        # Check against known magic numbers
        for magic_bytes in expected_magics:
            if content.startswith(magic_bytes):
                return True, None

        return False, "File content does not match declared file type"

    async def scan_for_malware(self, file_path: str) -> Tuple[bool, Optional[str]]:
        """
        Scan file for malware using ClamAV.

        Args:
            file_path: Path to file to scan

        Returns:
            (is_clean, error_message)
        """
        if not self.enable_virus_scan:
            return True, None

        try:
            import pyclamd

            # Connect to ClamAV daemon
            cd = pyclamd.ClamdUnixSocket()

            # Scan file
            result = cd.scan_file(file_path)

            if result is None:
                # No virus found
                return True, None
            else:
                # Virus detected
                virus_name = result[file_path][1]
                logger.warning(f"Malware detected in uploaded file: {virus_name}")
                return False, f"Malware detected: {virus_name}"

        except ImportError:
            logger.warning("pyclamd not installed, skipping virus scan")
            return True, None
        except Exception as e:
            logger.error(f"Virus scan failed: {e}")
            # Fail-safe: allow file if scan fails (could be made stricter)
            return True, None

    async def validate_upload(self, file: UploadFile) -> Tuple[bool, Optional[str], str]:
        """
        Comprehensive validation of uploaded file.

        Args:
            file: FastAPI UploadFile object

        Returns:
            (is_valid, error_message, sanitized_filename)

        Raises:
            HTTPException: If validation fails
        """
        # Sanitize filename
        safe_filename = self.sanitize_filename(file.filename)

        # Check extension
        is_valid, error = self.check_extension(safe_filename)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

        # Check MIME type
        content_type = file.content_type or mimetypes.guess_type(safe_filename)[0] or 'application/octet-stream'
        is_valid, error = self.check_mimetype(content_type)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

        # Read file content for size and magic number check
        content = await file.read()
        file_size = len(content)

        # Reset file pointer
        await file.seek(0)

        # Check size
        is_valid, error = self.check_size(file_size)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=error)

        # Verify magic number
        is_valid, error = self.verify_magic_number(content[:512], content_type)
        if not is_valid:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)

        logger.info(
            f"File upload validated: {safe_filename} "
            f"({file_size / 1024:.1f} KB, {content_type})"
        )

        return True, None, safe_filename


# Pre-configured validators for common use cases
image_validator = FileValidator(
    max_size_bytes=10 * 1024 * 1024,  # 10 MB
    allowed_categories=['image'],
    enable_magic_check=True,
)

document_validator = FileValidator(
    max_size_bytes=50 * 1024 * 1024,  # 50 MB
    allowed_categories=['document'],
    enable_magic_check=True,
)

data_validator = FileValidator(
    max_size_bytes=500 * 1024 * 1024,  # 500 MB
    allowed_categories=['data', 'archive'],
    enable_magic_check=False,  # Data files vary too much
)


async def validate_file_upload(
    file: UploadFile,
    category: str = 'data'
) -> str:
    """
    Dependency to validate file uploads in FastAPI endpoints.

    Args:
        file: Uploaded file
        category: File category (image, document, data)

    Returns:
        Sanitized filename

    Example:
        @app.post("/upload")
        async def upload_file(
            file: UploadFile = File(...),
            filename: str = Depends(lambda f=file: validate_file_upload(f, 'image'))
        ):
            ...
    """
    validators = {
        'image': image_validator,
        'document': document_validator,
        'data': data_validator,
    }

    validator = validators.get(category, data_validator)
    _, _, safe_filename = await validator.validate_upload(file)

    return safe_filename
