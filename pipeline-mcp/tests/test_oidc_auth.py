from pipeline_mcp.oidc import OIDCSettings
from pipeline_mcp.oidc import _claims_match_expected_client
from pipeline_mcp.oidc import account_console_url
from pipeline_mcp.oidc import claims_to_user


def test_claims_to_user_maps_pipeline_roles_and_identity():
    claims = {
        "sub": "user-123",
        "email": "tester@kribb.re.kr",
        "preferred_username": "tester@kribb.re.kr",
        "resource_access": {
            "protein-pipeline": {"roles": ["pipeline-user"]},
        },
    }

    user = claims_to_user(claims)

    assert user["username"] == "tester@kribb.re.kr"
    assert user["role"] == "user"
    assert user["run_prefix"] == "tester_kribb.re.kr"


def test_account_console_url_uses_realm_issuer():
    settings = OIDCSettings(
        issuer="https://sso.k-biofoundrycopilot.duckdns.org/realms/kbf",
        client_id="protein-pipeline",
        audience="protein-pipeline",
        scopes="openid profile email",
        provider_name="KBF SSO",
        jwks_url=None,
        algorithms=("RS256",),
    )

    assert account_console_url(settings) == "https://sso.k-biofoundrycopilot.duckdns.org/realms/kbf/account/"


def test_claims_match_expected_client_accepts_keycloak_azp_fallback():
    settings = OIDCSettings(
        issuer="https://sso.k-biofoundrycopilot.duckdns.org/realms/kbf",
        client_id="protein-pipeline",
        audience="protein-pipeline",
        scopes="openid profile email",
        provider_name="KBF SSO",
        jwks_url=None,
        algorithms=("RS256",),
    )

    claims = {
        "iss": settings.issuer,
        "sub": "user-123",
        "aud": "account",
        "azp": "protein-pipeline",
    }

    assert _claims_match_expected_client(claims, settings) is True


def test_claims_match_expected_client_rejects_other_client():
    settings = OIDCSettings(
        issuer="https://sso.k-biofoundrycopilot.duckdns.org/realms/kbf",
        client_id="protein-pipeline",
        audience="protein-pipeline",
        scopes="openid profile email",
        provider_name="KBF SSO",
        jwks_url=None,
        algorithms=("RS256",),
    )

    claims = {
        "iss": settings.issuer,
        "sub": "user-123",
        "aud": "account",
        "azp": "unrelated-client",
    }

    assert _claims_match_expected_client(claims, settings) is False
