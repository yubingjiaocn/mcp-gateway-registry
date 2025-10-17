"""
Unit tests for Anthropic MCP Registry API endpoints.
"""

import pytest
from typing import Any, Dict
from unittest.mock import Mock, patch
from fastapi import status
from fastapi.testclient import TestClient

from registry.main import app
from registry.services.server_service import server_service
from registry.health.service import health_service
from registry.constants import REGISTRY_CONSTANTS


@pytest.fixture
def mock_enhanced_auth_admin():
    """Mock enhanced_auth for admin user."""

    def _mock_auth(session=None):
        return {
            "username": "testadmin",
            "groups": ["mcp-registry-admin"],
            "scopes": [
                "mcp-registry-admin",
                "mcp-servers-unrestricted/read",
                "mcp-servers-unrestricted/execute",
            ],
            "auth_method": "traditional",
            "provider": "local",
            "accessible_servers": [],
            "accessible_services": ["all"],
            "ui_permissions": {
                "list_service": ["all"],
                "register_service": ["all"],
                "toggle_service": ["all"],
            },
            "can_modify_servers": True,
            "is_admin": True,
        }

    return _mock_auth


@pytest.fixture
def mock_enhanced_auth_user():
    """Mock enhanced_auth for regular user with limited access."""

    def _mock_auth(session=None):
        return {
            "username": "testuser",
            "groups": ["mcp-registry-user"],
            "scopes": ["mcp-servers-restricted/read"],
            "auth_method": "oauth2",
            "provider": "cognito",
            "accessible_servers": ["mcpgw"],
            "accessible_services": ["MCP Gateway Tools"],
            "ui_permissions": {"list_service": ["MCP Gateway Tools"]},
            "can_modify_servers": False,
            "is_admin": False,
        }

    return _mock_auth


@pytest.fixture
def sample_servers_data():
    """Create sample server data for testing."""
    return {
        "/server-a": {
            "server_name": "Server A",
            "description": "First test server",
            "path": "/server-a",
            "proxy_pass_url": "http://localhost:8001",
            "tags": ["test", "example"],
            "num_tools": 3,
            "num_stars": 10,
            "is_python": True,
            "license": "MIT",
            "tool_list": [],
        },
        "/server-b": {
            "server_name": "Server B",
            "description": "Second test server",
            "path": "/server-b",
            "proxy_pass_url": "http://localhost:8002",
            "tags": ["production"],
            "num_tools": 5,
            "num_stars": 20,
            "is_python": False,
            "license": "Apache-2.0",
            "tool_list": [],
        },
        "/mcpgw": {
            "server_name": "MCP Gateway Tools",
            "description": "Gateway management tools",
            "path": "/mcpgw",
            "proxy_pass_url": "http://localhost:8003",
            "tags": ["management"],
            "num_tools": 11,
            "num_stars": 0,
            "is_python": True,
            "license": "N/A",
            "tool_list": [],
        },
    }


@pytest.mark.unit
class TestV0ListServers:
    """Test suite for GET /{api_version}/servers endpoint."""

    def test_list_servers_admin_sees_all(
        self, mock_enhanced_auth_admin, sample_servers_data
    ):
        """Test that admin users see all servers."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service, "get_all_servers", return_value=sample_servers_data
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 0,
            },
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert "servers" in data
            assert "metadata" in data
            assert len(data["servers"]) == 3
            assert data["metadata"]["count"] == 3

        app.dependency_overrides.clear()

    def test_list_servers_user_filtered_by_permissions(
        self, mock_enhanced_auth_user, sample_servers_data
    ):
        """Test that regular users see only authorized servers."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        # User should only see servers they have permission for
        filtered_servers = {"/mcpgw": sample_servers_data["/mcpgw"]}

        with patch.object(
            server_service,
            "get_all_servers_with_permissions",
            return_value=filtered_servers,
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 11,
            },
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert len(data["servers"]) == 1
            assert data["servers"][0]["server"]["name"] == "io.mcpgateway/mcpgw"

        app.dependency_overrides.clear()

    def test_list_servers_pagination(self, mock_enhanced_auth_admin, sample_servers_data):
        """Test server list pagination with limit."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service, "get_all_servers", return_value=sample_servers_data
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 0,
            },
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers?limit=2")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert len(data["servers"]) == 2
            assert data["metadata"]["count"] == 2
            assert data["metadata"]["nextCursor"] is not None

        app.dependency_overrides.clear()

    def test_list_servers_response_format(
        self, mock_enhanced_auth_admin, sample_servers_data
    ):
        """Test that response follows Anthropic schema."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service, "get_all_servers", return_value=sample_servers_data
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 3,
            },
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Validate structure
            assert "servers" in data
            assert "metadata" in data
            assert isinstance(data["servers"], list)

            # Validate first server
            if len(data["servers"]) > 0:
                server = data["servers"][0]
                assert "server" in server
                assert "_meta" in server

                server_detail = server["server"]
                assert "name" in server_detail
                assert "description" in server_detail
                assert "version" in server_detail
                assert "packages" in server_detail
                assert server_detail["name"].startswith("io.mcpgateway/")

                # Validate packages
                assert len(server_detail["packages"]) > 0
                package = server_detail["packages"][0]
                assert "registryType" in package
                assert "identifier" in package
                assert "version" in package
                assert "transport" in package
                assert package["transport"]["type"] == "streamable-http"

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestV0ListServerVersions:
    """Test suite for GET /{api_version}/servers/{serverName}/versions endpoint."""

    def test_list_versions_success(self, mock_enhanced_auth_admin, sample_servers_data):
        """Test listing versions for a server."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service,
            "get_server_info",
            return_value=sample_servers_data["/server-a"],
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 3,
            },
        ):
            client = TestClient(app)
            # URL-encode the server name
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fserver-a/versions")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert "servers" in data
            assert len(data["servers"]) == 1
            assert data["servers"][0]["server"]["name"] == "io.mcpgateway/server-a"

        app.dependency_overrides.clear()

    def test_list_versions_server_not_found(self, mock_enhanced_auth_admin):
        """Test listing versions for non-existent server."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(server_service, "get_server_info", return_value=None):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fnonexistent/versions")

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_list_versions_invalid_name_format(self, mock_enhanced_auth_admin):
        """Test listing versions with invalid server name format."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        client = TestClient(app)
        response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/invalid-format/versions")

        assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_list_versions_unauthorized_user(
        self, mock_enhanced_auth_user, sample_servers_data
    ):
        """Test that users cannot access servers they don't have permission for."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_user

        with patch.object(
            server_service,
            "get_server_info",
            return_value=sample_servers_data["/server-a"],
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fserver-a/versions")

            # User doesn't have permission to Server A
            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()


@pytest.mark.unit
class TestV0GetServerVersion:
    """Test suite for GET /{api_version}/servers/{serverName}/versions/{version} endpoint."""

    def test_get_version_latest(self, mock_enhanced_auth_admin, sample_servers_data):
        """Test getting server details with 'latest' version."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service,
            "get_server_info",
            return_value=sample_servers_data["/server-a"],
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 3,
            },
        ):
            client = TestClient(app)
            response = client.get(
                f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fserver-a/versions/latest"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert "server" in data
            assert "_meta" in data
            assert data["server"]["name"] == "io.mcpgateway/server-a"
            assert data["server"]["version"] == "1.0.0"

        app.dependency_overrides.clear()

    def test_get_version_specific(self, mock_enhanced_auth_admin, sample_servers_data):
        """Test getting server details with specific version."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service,
            "get_server_info",
            return_value=sample_servers_data["/server-a"],
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 3,
            },
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fserver-a/versions/1.0.0")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["server"]["version"] == "1.0.0"

        app.dependency_overrides.clear()

    def test_get_version_unsupported(self, mock_enhanced_auth_admin, sample_servers_data):
        """Test getting unsupported version returns 404."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service,
            "get_server_info",
            return_value=sample_servers_data["/server-a"],
        ):
            client = TestClient(app)
            response = client.get(f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fserver-a/versions/2.0.0")

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_get_version_server_not_found(self, mock_enhanced_auth_admin):
        """Test getting version for non-existent server."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(server_service, "get_server_info", return_value=None):
            client = TestClient(app)
            response = client.get(
                f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fnonexistent/versions/latest"
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

        app.dependency_overrides.clear()

    def test_get_version_response_format(
        self, mock_enhanced_auth_admin, sample_servers_data
    ):
        """Test that response follows Anthropic ServerResponse schema."""
        from registry.auth.dependencies import enhanced_auth

        app.dependency_overrides[enhanced_auth] = mock_enhanced_auth_admin

        with patch.object(
            server_service,
            "get_server_info",
            return_value=sample_servers_data["/server-a"],
        ), patch.object(
            server_service, "is_service_enabled", return_value=True
        ), patch.object(
            health_service,
            "_get_service_health_data",
            return_value={
                "status": "healthy",
                "last_checked_iso": "2025-10-12T10:00:00Z",
                "num_tools": 3,
            },
        ):
            client = TestClient(app)
            response = client.get(
                f"/{REGISTRY_CONSTANTS.ANTHROPIC_API_VERSION}/servers/io.mcpgateway%2Fserver-a/versions/latest"
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            # Validate ServerResponse structure
            assert "server" in data
            assert "_meta" in data

            # Validate ServerDetail
            server = data["server"]
            assert "name" in server
            assert "description" in server
            assert "version" in server
            assert "title" in server
            assert "packages" in server
            assert "_meta" in server

            # Validate internal metadata
            internal_meta = server["_meta"]["io.mcpgateway/internal"]
            assert "path" in internal_meta
            assert "is_enabled" in internal_meta
            assert "health_status" in internal_meta
            assert "num_tools" in internal_meta

            # Validate registry metadata
            registry_meta = data["_meta"]["io.mcpgateway/registry"]
            assert "last_checked" in registry_meta
            assert "health_status" in registry_meta

        app.dependency_overrides.clear()
