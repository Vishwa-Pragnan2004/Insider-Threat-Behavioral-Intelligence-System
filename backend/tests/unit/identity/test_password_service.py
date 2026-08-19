import pytest
from app.modules.identity.application.services.password_service import password_service
from app.modules.identity.domain.exceptions import WeakPasswordError

def test_password_hashing():
    plaintext = "StrongPass123!"
    hashed = password_service.hash(plaintext)
    
    assert hashed != plaintext
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert password_service.verify(plaintext, hashed)
    assert not password_service.verify("WrongPass123!", hashed)

def test_password_strength_validation():
    with pytest.raises(WeakPasswordError):
        password_service.hash("short")
        
    with pytest.raises(WeakPasswordError):
        password_service.hash("nouppercase123")
        
    with pytest.raises(WeakPasswordError):
        password_service.hash("NOLOWERCASE123")
        
    with pytest.raises(WeakPasswordError):
        password_service.hash("NoDigitsHere")
