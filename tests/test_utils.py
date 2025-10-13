"""
Shared test utilities for FolioClient tests.

This module provides robust, Pythonic test utilities that avoid cross-test 
contamination while maintaining compatibility across Python versions.
"""

from unittest.mock import Mock, patch
from contextlib import contextmanager


@contextmanager
def folio_auth_patcher():
    """
    Context manager for patching FolioAuth in a robust, cross-version way.
    
    This uses standard unittest.mock.patch which works reliably in all Python versions
    when properly scoped to individual tests.
    
    Usage:
        with folio_auth_patcher() as mock_auth_class:
            mock_auth_class.configure_mock(...)
            # Test code here
    """
    # Instead of trying to mock the whole class, patch the problematic methods
    # This is more reliable as it doesn't deal with import timing issues
    from datetime import datetime, timezone, timedelta
    
    mock_token = Mock()
    mock_token.auth_token = "test-token"
    mock_token.refresh_token = "test-refresh-token"
    # Set expires_at to a future datetime to avoid expiration issues
    mock_token.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    
    with patch('folioclient._httpx.FolioAuth._do_sync_auth', return_value=mock_token), \
         patch('folioclient._httpx.FolioAuth._token_is_expiring', return_value=False):
        yield mock_token


@contextmanager  
def httpx_client_patcher(sync_factory, async_factory=None):
    """
    Context manager for patching httpx.Client and AsyncClient.
    
    Args:
        sync_factory: A callable that returns a mock sync client
        async_factory: Optional callable that returns a mock async client
    
    Usage:
        def my_sync_client(*args, **kwargs):
            return MyDummyClient()
        
        with httpx_client_patcher(my_sync_client):
            # Test code here
    """
    patches = [patch('httpx.Client', sync_factory)]
    if async_factory:
        patches.append(patch('httpx.AsyncClient', async_factory))
    
    # Stack the patches
    for p in patches:
        p.__enter__()
    
    try:
        yield
    finally:
        # Ensure proper cleanup in reverse order
        for p in reversed(patches):
            p.__exit__(None, None, None)