#!/usr/bin/env python3
"""
ANVEL Authentication & Authorization Service
Provides JWT, OAuth2 (PKCE), and TOTP 2FA authentication.
Production-ready with fail-closed security.
"""

import hashlib
import logging
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import jwt
import pyotp
import requests
from passlib.hash import bcrypt

log = logging.getLogger(__name__)


class AuthenticationError(Exception):
    """Base exception for authentication failures."""
    pass


class AuthorizationError(Exception):
    """Base exception for authorization failures."""
    pass


class OAuth2Config:
    """OAuth2 provider configuration."""

    GOOGLE = {
        "auth_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scopes": ["openid", "email", "profile"],
    }

    GITHUB = {
        "auth_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "userinfo_url": "https://api.github.com/user",
        "scopes": ["user:email"],
    }


class AuthService:
    """
    Production-grade authentication service.
    Implements JWT, OAuth2 with PKCE, and TOTP 2FA.
    """

    def __init__(
        self,
        jwt_secret: str,
        jwt_algorithm: str = "HS256",
        jwt_expiry_seconds: int = 3600,
        oauth_client_ids: Optional[Dict[str, str]] = None,
        oauth_client_secrets: Optional[Dict[str, str]] = None,
        oauth_redirect_uri: Optional[str] = None,
    ):
        """
        Initialize authentication service.
        
        Args:
            jwt_secret: Secret key for JWT signing (must be cryptographically secure)
            jwt_algorithm: JWT signing algorithm (default: HS256)
            jwt_expiry_seconds: JWT token expiry time in seconds
            oauth_client_ids: Dict with 'google' and 'github' client IDs
            oauth_client_secrets: Dict with 'google' and 'github' client secrets
            oauth_redirect_uri: OAuth callback redirect URI
        """
        if not jwt_secret or len(jwt_secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")

        self.jwt_secret = jwt_secret
        self.jwt_algorithm = jwt_algorithm
        self.jwt_expiry_seconds = jwt_expiry_seconds
        self.oauth_client_ids = oauth_client_ids or {}
        self.oauth_client_secrets = oauth_client_secrets or {}
        self.oauth_redirect_uri = oauth_redirect_uri

        # PKCE state storage (in production, use Redis/database)
        self._pkce_states: Dict[str, Dict] = {}

    def hash_password(self, password: str) -> str:
        """
        Hash password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Bcrypt hash
        """
        if not password or len(password) < 8:
            raise ValueError("Password must be at least 8 characters")

        return bcrypt.hash(password)

    def verify_password(self, password: str, password_hash: str) -> bool:
        """
        Verify password against bcrypt hash.
        
        Args:
            password: Plain text password
            password_hash: Bcrypt hash to verify against
            
        Returns:
            True if password matches, False otherwise
        """
        if not password or not password_hash:
            return False

        try:
            return bcrypt.verify(password, password_hash)
        except Exception as e:
            log.error(f"Password verification error: {e}")
            return False

    def generate_jwt(
        self,
        user_id: str,
        username: str,
        email: str,
        tenant_id: Optional[str] = None,
        roles: Optional[list] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Generate JWT access token.
        
        Args:
            user_id: User UUID
            username: Username
            email: User email
            tenant_id: Tenant ID for multi-tenant isolation
            roles: User roles/permissions
            metadata: Additional claims
            
        Returns:
            Signed JWT token
        """
        now = datetime.utcnow()
        exp = now + timedelta(seconds=self.jwt_expiry_seconds)

        payload = {
            "sub": user_id,
            "username": username,
            "email": email,
            "tenant_id": tenant_id,
            "roles": roles or [],
            "iat": int(now.timestamp()),
            "exp": int(exp.timestamp()),
            "jti": secrets.token_urlsafe(16),  # JWT ID for revocation
        }

        if metadata:
            payload["metadata"] = metadata

        try:
            token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
            return token
        except Exception as e:
            log.error(f"JWT generation failed: {e}")
            raise AuthenticationError("Failed to generate access token")

    def verify_jwt(self, token: str) -> Dict:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token to verify
            
        Returns:
            Decoded token payload
            
        Raises:
            AuthenticationError: If token is invalid or expired
        """
        if not token:
            raise AuthenticationError("No token provided")

        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_iat": True,
                    "require": ["sub", "exp", "iat"],
                }
            )

            # Additional validation
            if not payload.get("sub"):
                raise AuthenticationError("Invalid token: missing user ID")

            return payload

        except jwt.ExpiredSignatureError:
            raise AuthenticationError("Token expired")
        except jwt.InvalidTokenError as e:
            log.warning(f"Invalid JWT: {e}")
            raise AuthenticationError("Invalid token")
        except Exception as e:
            log.error(f"JWT verification error: {e}")
            raise AuthenticationError("Token verification failed")

    def generate_totp_secret(self) -> str:
        """
        Generate TOTP secret for 2FA.
        
        Returns:
            Base32-encoded secret
        """
        return pyotp.random_base32()

    def get_totp_uri(self, secret: str, username: str, issuer: str = "ANVEL") -> str:
        """
        Generate TOTP provisioning URI for QR code.
        
        Args:
            secret: TOTP secret
            username: User's username or email
            issuer: Application name
            
        Returns:
            otpauth:// URI for QR code generation
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(name=username, issuer_name=issuer)

    def verify_totp(self, secret: str, token: str, window: int = 1) -> bool:
        """
        Verify TOTP token for 2FA.
        
        Args:
            secret: User's TOTP secret
            token: 6-digit TOTP token
            window: Time window tolerance (±30 seconds per window)
            
        Returns:
            True if token is valid, False otherwise
        """
        if not secret or not token:
            return False

        # Remove whitespace and validate format
        token = token.strip().replace(" ", "")
        if not token.isdigit() or len(token) != 6:
            return False

        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(token, valid_window=window)
        except Exception as e:
            log.error(f"TOTP verification error: {e}")
            return False

    def generate_pkce_challenge(self) -> Tuple[str, str]:
        """
        Generate PKCE code verifier and challenge for OAuth2.
        
        Returns:
            Tuple of (code_verifier, code_challenge)
        """
        # Generate random verifier (43-128 chars per RFC 7636)
        code_verifier = secrets.token_urlsafe(64)

        # Create SHA256 challenge with base64url encoding per RFC 7636
        import base64
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).decode('utf-8').rstrip('=')

        return code_verifier, code_challenge

    def initiate_oauth2_flow(
        self,
        provider: str,
        state: Optional[str] = None,
    ) -> Tuple[str, str]:
        """
        Initiate OAuth2 authorization flow with PKCE.
        
        Args:
            provider: 'google' or 'github'
            state: Optional state parameter for CSRF protection
            
        Returns:
            Tuple of (authorization_url, state)
            
        Raises:
            ValueError: If provider not configured
        """
        if provider not in ['google', 'github']:
            raise ValueError(f"Unsupported provider: {provider}")

        if provider == 'google':
            config = OAuth2Config.GOOGLE
        else:
            config = OAuth2Config.GITHUB

        client_id = self.oauth_client_ids.get(provider)
        if not client_id:
            raise ValueError(f"{provider} OAuth not configured")

        # Generate PKCE challenge
        code_verifier, code_challenge = self.generate_pkce_challenge()

        # Generate state for CSRF protection
        if not state:
            state = secrets.token_urlsafe(32)

        # Store PKCE state (in production, use Redis with expiry)
        self._pkce_states[state] = {
            "provider": provider,
            "code_verifier": code_verifier,
            "timestamp": time.time(),
        }

        # Build authorization URL
        params = {
            "client_id": client_id,
            "redirect_uri": self.oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(config["scopes"]),
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }

        auth_url = f"{config['auth_url']}?{urllib.parse.urlencode(params)}"
        return auth_url, state

    def complete_oauth2_flow(
        self,
        provider: str,
        code: str,
        state: str,
    ) -> Dict:
        """
        Complete OAuth2 authorization flow and exchange code for tokens.
        
        Args:
            provider: 'google' or 'github'
            code: Authorization code from provider
            state: State parameter for CSRF validation
            
        Returns:
            Dict with user info: {email, name, provider_id}
            
        Raises:
            AuthenticationError: If OAuth flow fails
        """
        # Validate state
        pkce_state = self._pkce_states.get(state)
        if not pkce_state:
            raise AuthenticationError("Invalid or expired OAuth state")

        if pkce_state["provider"] != provider:
            raise AuthenticationError("Provider mismatch")

        # Check state expiry (10 minutes)
        if time.time() - pkce_state["timestamp"] > 600:
            del self._pkce_states[state]
            raise AuthenticationError("OAuth state expired")

        code_verifier = pkce_state["code_verifier"]
        del self._pkce_states[state]

        # Get config
        if provider == 'google':
            config = OAuth2Config.GOOGLE
        else:
            config = OAuth2Config.GITHUB

        # Exchange code for token
        token_data = {
            "client_id": self.oauth_client_ids[provider],
            "client_secret": self.oauth_client_secrets[provider],
            "code": code,
            "redirect_uri": self.oauth_redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }

        try:
            headers = {"Accept": "application/json"}
            resp = requests.post(
                config["token_url"],
                data=token_data,
                headers=headers,
                timeout=10,
            )
            resp.raise_for_status()
            tokens = resp.json()

            if "access_token" not in tokens:
                raise AuthenticationError("No access token received")

            # Get user info
            access_token = tokens["access_token"]
            userinfo_headers = {"Authorization": f"Bearer {access_token}"}

            user_resp = requests.get(
                config["userinfo_url"],
                headers=userinfo_headers,
                timeout=10,
            )
            user_resp.raise_for_status()
            user_info = user_resp.json()

            # Extract user data
            if provider == 'google':
                return {
                    "email": user_info.get("email"),
                    "name": user_info.get("name"),
                    "provider_id": user_info.get("sub"),
                    "provider": "google",
                    "email_verified": user_info.get("email_verified", False),
                }
            else:  # GitHub
                # GitHub may need separate API call for email
                email = user_info.get("email")
                if not email:
                    email_resp = requests.get(
                        "https://api.github.com/user/emails",
                        headers=userinfo_headers,
                        timeout=10,
                    )
                    if email_resp.status_code == 200:
                        emails = email_resp.json()
                        primary_email = next(
                            (e for e in emails if e.get("primary")),
                            None
                        )
                        if primary_email:
                            email = primary_email["email"]

                return {
                    "email": email,
                    "name": user_info.get("name") or user_info.get("login"),
                    "provider_id": str(user_info.get("id")),
                    "provider": "github",
                    "email_verified": True,  # GitHub verifies emails
                }

        except requests.RequestException as e:
            log.error(f"OAuth2 token exchange failed: {e}")
            raise AuthenticationError(f"OAuth authentication failed: {str(e)}")

    def validate_permissions(
        self,
        user_roles: list,
        required_permissions: list,
    ) -> bool:
        """
        Validate user has required permissions.
        
        Args:
            user_roles: List of user's roles
            required_permissions: List of required permissions
            
        Returns:
            True if user has all required permissions
        """
        if not required_permissions:
            return True

        if not user_roles:
            return False

        # Admin role has all permissions
        if "admin" in user_roles:
            return True

        # Check specific permissions
        return all(perm in user_roles for perm in required_permissions)
