
# ai_services.py
# This file serves as a compatibility layer for existing imports
# All functionality has been moved to services/ai_service.py

import logging
from .services.ai_service import AIService

logger = logging.getLogger(__name__)

# Log a deprecation warning for monitoring purposes
logger.warning(
    "Importing AIService from ai_services.py is deprecated. "
    "Import from services.ai_service instead."
)

# Re-export the class for backward compatibility
__all__ = ['AIService']
