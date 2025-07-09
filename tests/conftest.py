"""
Pytest configuration and shared fixtures for image-builder-mcp tests.
"""

import pytest


@pytest.fixture
def default_response_size():
    """Default response size for pagination tests."""
    return 7


@pytest.fixture
def test_client_credentials():
    """Test client credentials."""
    return {
        'client_id': 'test-client-id',
        'client_secret': 'test-client-secret'
    }


@pytest.fixture
def mock_http_headers(client_creds):
    """Mock HTTP headers with test credentials."""
    return {
        'image-builder-client-id': client_creds['client_id'],
        'image-builder-client-secret': client_creds['client_secret']
    }
