"""
Common services module for the Jobraker application.
Provides utility services and imports for shared functionality.
"""

from .vector_service import VectorDBService

# Export commonly used services
__all__ = [
    'VectorDBService',
]


# Utility functions for common operations
def get_vector_db_service():
    """
    Get an instance of the VectorDBService.
    
    Returns:
        VectorDBService: Configured instance for vector operations
    """
    return VectorDBService()


def format_search_results(results, limit=None):
    """
    Format search results for consistent API responses.
    
    Args:
        results: List of search results
        limit: Optional limit on number of results
    
    Returns:
        dict: Formatted results with metadata
    """
    if limit:
        results = results[:limit]
    
    return {
        'count': len(results),
        'results': results
    }


def validate_embedding_vector(embedding):
    """
    Validate that an embedding vector is properly formatted.
    
    Args:
        embedding: Vector to validate
    
    Returns:
        bool: True if valid, False otherwise
    """
    if not isinstance(embedding, list):
        return False
    
    if len(embedding) == 0:
        return False
    
    # Check if all elements are numbers
    try:
        [float(x) for x in embedding]
        return True
    except (ValueError, TypeError):
        return False
