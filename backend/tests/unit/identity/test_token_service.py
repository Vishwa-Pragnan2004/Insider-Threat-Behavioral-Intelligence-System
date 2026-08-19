import time
import pytest
from app.modules.identity.application.services.token_service import token_service
from app.modules.identity.domain.exceptions import TokenExpiredError, TokenInvalidError

def test_create_and_decode_access_token():
    subject = "user123"
    claims = {"roles": ["admin"]}
    
    token = token_service.create_access_token(subject, claims)
    assert isinstance(token, str)
    
    payload = token_service.decode_token(token, expected_type="access")
    assert payload["sub"] == subject
    assert payload["type"] == "access"
    assert payload["roles"] == ["admin"]
    assert "exp" in payload
    assert "iat" in payload

def test_create_and_decode_refresh_token():
    subject = "user123"
    jti = "unique-jti"
    
    token = token_service.create_refresh_token(subject, jti)
    payload = token_service.decode_token(token, expected_type="refresh")
    
    assert payload["sub"] == subject
    assert payload["type"] == "refresh"
    assert payload["jti"] == jti

def test_invalid_token_type():
    token = token_service.create_access_token("user123", {})
    with pytest.raises(TokenInvalidError, match="Expected refresh token"):
        token_service.decode_token(token, expected_type="refresh")

def test_tampered_token():
    token = token_service.create_access_token("user123", {})
    tampered = token[:-5] + "aaaaa"
    with pytest.raises(TokenInvalidError):
        token_service.decode_token(tampered, expected_type="access")
