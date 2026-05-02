from pathlib import Path
from .. import dev_ports
from ..dev_sso.constants import REALM, REALM_NAME


def generate(bin_dir: Path):
    script = bin_dir / 'dev-sso-start.py'
    script.write_text(_content(), encoding='utf-8')
    script.chmod(0o755)


def _content() -> str:
    header = (
        '#!/usr/bin/python3\n'
        '"""Start the SSO dev environment (MIT Kerberos + Keycloak) and configure it automatically."""\n'
        '\n'
        f'REALM = "{REALM}"\n'
        f'KC_PORT = {dev_ports.KC_PORT}\n'
        f'KC_MGMT_PORT = {dev_ports.KC_MGMT_PORT}\n'
        f'REALM_NAME = "{REALM_NAME}"\n'
        f'SUPABASE_PORT = {dev_ports.SUPABASE_API}\n'
        f'FRONTEND_PORT = {dev_ports.FRONTEND}\n'
        f'COMPOSE_PROJECT = "unibizkit-sso-{dev_ports.ENV_NUM:02d}"\n'
    )
    return header + _body()


def _body() -> str:
    # Plain string — no f-string, so {KC_PORT} etc pass through as literals
    # that become variable references in the generated script.
    return """
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

root_dir = Path(__file__).parent.parent
sso_dir = root_dir / 'dev-sso'
krb5_host_conf = sso_dir / 'krb5-host.conf'

_sec_file = root_dir / 'security_extended.json'
if not _sec_file.exists():
    sys.exit(f"Not found: {_sec_file}\\nRun the generator first.")
_sec = json.loads(_sec_file.read_text())
USERS = [{"email": u["email"], "password": u["password"], "roles": u.get("roles", [])} for u in _sec.get("users", [])]
ROLES = sorted({r for u in USERS for r in u["roles"]})

KC_BASE = f"http://localhost:{KC_PORT}"
KC_MGMT_BASE = f"http://localhost:{KC_MGMT_PORT}"


# --- Keycloak API helpers ---

def _kc_token():
    data = "client_id=admin-cli&username=admin&password=admin&grant_type=password"
    req = urllib.request.Request(
        f"{KC_BASE}/realms/master/protocol/openid-connect/token",
        data=data.encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def _kc(method, path, data=None, token=None, ok=(200, 201, 204, 409)):
    url = f"{KC_BASE}{path}"
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as r:
            content = r.read()
            return json.loads(content) if content else None
    except urllib.error.HTTPError as e:
        if e.code in ok:
            return None
        body_text = e.read().decode("utf-8", errors="replace")
        sys.exit(f"Keycloak API error {e.code} {method} {path}:\\n{body_text}")


def _kc_get(token, path):
    return _kc("GET", path, token=token)


def _kc_post(token, path, data):
    return _kc("POST", path, data=data, token=token)


def _kc_put(token, path, data):
    return _kc("PUT", path, data=data, token=token)


# --- Keycloak configuration ---

def configure_keycloak():
    print("Configuring Keycloak...")
    token = _kc_token()

    # Realm
    print("  Creating realm...")
    realm_config = {
        "realm": REALM_NAME,
        "enabled": True,
        "displayName": "Dev Local",
        "sslRequired": "none",
        "registrationAllowed": False,
        "duplicateEmailsAllowed": True,
        "loginWithEmailAllowed": False,
        "bruteForceProtected": False,
    }
    _kc_post(token, "/admin/realms", realm_config)
    _kc_put(token, f"/admin/realms/{REALM_NAME}", realm_config)

    # Realm user profile — configure BEFORE creating users/federation.
    # KC 26 Declarative User Profile (enabled by default) requires firstName/lastName
    # and rejects unknown attributes like KERBEROS_PRINCIPAL (set by the Kerberos
    # federation provider). Fix both by:
    #   1. Allowing unmanaged attributes (ENABLED policy)
    #   2. Making firstName and lastName optional (required: {})
    print("  Configuring realm user profile...")
    profile = _kc_get(token, f"/admin/realms/{REALM_NAME}/users/profile") or {"attributes": []}
    profile["unmanagedAttributePolicy"] = "ENABLED"
    for attr in profile.get("attributes", []):
        if attr.get("name") in ("firstName", "lastName"):
            attr.pop("required", None)
    _kc_put(token, f"/admin/realms/{REALM_NAME}/users/profile", profile)

    # Realm roles — before users so assignments work
    print("  Creating roles...")
    for role in ROLES:
        _kc_post(token, f"/admin/realms/{REALM_NAME}/roles", {"name": role})

    # Kerberos federation — add FIRST so that the ROPC step below creates users
    # through the provider, giving them the correct federationLink automatically.
    # Pre-creating users via admin API and then patching federationLink does NOT work
    # in Keycloak 26: getUserByUsername still returns null and causes a duplicate INSERT.
    print("  Adding Kerberos user federation...")
    existing_fed = _kc_get(token, f"/admin/realms/{REALM_NAME}/components?name=kerberos&type=org.keycloak.storage.UserStorageProvider")
    if not existing_fed:
        _kc_post(token, f"/admin/realms/{REALM_NAME}/components", {
            "name": "kerberos",
            "providerId": "kerberos",
            "providerType": "org.keycloak.storage.UserStorageProvider",
            "config": {
                "kerberosRealm": [REALM],
                "serverPrincipal": [f"HTTP/keycloak.dev.local@{REALM}"],
                "keyTab": ["/keytabs/keycloak.keytab"],
                "debug": ["false"],
                "allowPasswordAuthentication": ["true"],
                "updateProfileFirstLogin": ["off"],
                "priority": ["0"],
                "cachePolicy": ["DEFAULT"],
                "editMode": ["UNSYNCED"],
            },
        })

    # Bootstrap public client — required to do ROPC without a client secret.
    # GET-before-POST to stay idempotent on re-run.
    print("  Creating bootstrap client for federation user init...")
    existing_bootstrap = _kc_get(token, f"/admin/realms/{REALM_NAME}/clients?clientId=bootstrap")
    if not existing_bootstrap:
        _kc_post(token, f"/admin/realms/{REALM_NAME}/clients", {
            "clientId": "bootstrap",
            "protocol": "openid-connect",
            "enabled": True,
            "publicClient": True,
            "directAccessGrantsEnabled": True,
            "standardFlowEnabled": False,
            "implicitFlowEnabled": False,
            "serviceAccountsEnabled": False,
        })

    # Disable any realm-level default required actions (e.g. UPDATE_PROFILE,
    # VERIFY_EMAIL) so that users created via ROPC don't get them applied
    # automatically — otherwise ROPC returns "Account is not fully set up".
    print("  Disabling realm default required actions...")
    required_actions = _kc_get(token, f"/admin/realms/{REALM_NAME}/authentication/required-actions") or []
    for ra in required_actions:
        if ra.get("defaultAction"):
            _kc_put(token, f"/admin/realms/{REALM_NAME}/authentication/required-actions/{ra['alias']}",
                    {**ra, "defaultAction": False})

    # Trigger user creation through the Kerberos federation via ROPC.
    # Keycloak validates the password against the KDC and calls
    # KerberosFederationProvider.findOrCreateAuthenticatedUser, which creates
    # the user with the correct federationLink set internally — no manual patching needed.
    print("  Bootstrapping users through Kerberos ROPC...")
    for user in USERS:
        username = user["email"].split("@")[0]
        password = user["password"]
        found = _kc_get(token, f"/admin/realms/{REALM_NAME}/users?username={username}&exact=true")
        if found:
            print(f"    {username}: already exists, skipping ROPC")
            continue
        data = (
            "client_id=bootstrap"
            f"&username={username}"
            f"&password={password}"
            "&grant_type=password"
        )
        req = urllib.request.Request(
            f"{KC_BASE}/realms/{REALM_NAME}/protocol/openid-connect/token",
            data=data.encode(),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        try:
            with urllib.request.urlopen(req):
                print(f"    {username}: created via Kerberos ROPC")
        except urllib.error.HTTPError as e:
            body_text = e.read().decode("utf-8", errors="replace")
            print(f"    {username}: ROPC failed ({e.code}): {body_text[:300]}")

    # Update user profiles and assign roles (users now exist via federation).
    # Use GET-then-PUT with the full representation so Keycloak does not reject
    # the update due to missing internal fields on federated users.
    # Also clear any pending required actions (e.g. UPDATE_PROFILE) so that
    # the account becomes fully usable.
    print("  Updating user profiles and assigning roles...")
    for user in USERS:
        username = user["email"].split("@")[0]
        found = _kc_get(token, f"/admin/realms/{REALM_NAME}/users?username={username}&exact=true")
        if not found:
            print(f"    Warning: {username} not found — ROPC may have failed")
            continue
        user_id = found[0]["id"]
        current = _kc_get(token, f"/admin/realms/{REALM_NAME}/users/{user_id}") or {}
        # KC 26 Declarative User Profile rejects attributes not in the realm
        # profile schema (e.g. KERBEROS_PRINCIPAL added by the Kerberos provider).
        # Omit attributes, access, and disableableCredentialTypes from the PUT —
        # KC ignores absent optional fields but rejects unknown attribute keys.
        for _f in ("attributes", "access", "disableableCredentialTypes", "notBefore"):
            current.pop(_f, None)
        current.update({
            "email": user["email"],
            "emailVerified": True,
            "firstName": username.capitalize(),
            "lastName": "Dev",
            "enabled": True,
            "requiredActions": [],
        })
        try:
            _kc_put(token, f"/admin/realms/{REALM_NAME}/users/{user_id}", current)
        except SystemExit as e:
            print(f"    Warning: profile update for {username} failed ({e}), continuing")
        role_reps = []
        for role_name in user.get("roles", []):
            role_data = _kc_get(token, f"/admin/realms/{REALM_NAME}/roles/{role_name}")
            if role_data:
                role_reps.append({"id": role_data["id"], "name": role_data["name"]})
        if role_reps:
            _kc_post(token, f"/admin/realms/{REALM_NAME}/users/{user_id}/role-mappings/realm", role_reps)

    # Enable Kerberos (SPNEGO) in browser flow — PUT is idempotent
    print("  Enabling SPNEGO in browser flow...")
    executions = _kc_get(token, f"/admin/realms/{REALM_NAME}/authentication/flows/browser/executions")
    if executions:
        for ex in executions:
            if ex.get("providerId") == "auth-spnego" and ex.get("requirement") != "ALTERNATIVE":
                ex["requirement"] = "ALTERNATIVE"
                _kc_put(token, f"/admin/realms/{REALM_NAME}/authentication/flows/browser/executions", ex)
                break

    # OIDC client for Supabase
    print("  Creating OIDC client for Supabase...")
    _kc_post(token, f"/admin/realms/{REALM_NAME}/clients", {
        "clientId": "supabase",
        "protocol": "openid-connect",
        "enabled": True,
        "publicClient": False,
        "standardFlowEnabled": True,
        "directAccessGrantsEnabled": True,
        "redirectUris": [
            f"http://localhost:{SUPABASE_PORT}/auth/v1/callback",
            f"http://localhost:{FRONTEND_PORT}/*",
        ],
        "webOrigins": [
            f"http://localhost:{SUPABASE_PORT}",
            f"http://localhost:{FRONTEND_PORT}",
        ],
    })

    clients = _kc_get(token, f"/admin/realms/{REALM_NAME}/clients?clientId=supabase")
    client_uuid = clients[0]["id"] if clients else None

    # Protocol mapper: roles → JWT claim — GET-before-POST to avoid duplicates
    if client_uuid:
        print("  Adding roles claim mapper...")
        existing_mappers = _kc_get(token, f"/admin/realms/{REALM_NAME}/clients/{client_uuid}/protocol-mappers/models") or []
        if not any(m.get("name") == "realm-roles" for m in existing_mappers):
            _kc_post(token, f"/admin/realms/{REALM_NAME}/clients/{client_uuid}/protocol-mappers/models", {
                "name": "realm-roles",
                "protocol": "openid-connect",
                "protocolMapper": "oidc-usermodel-realm-role-mapper",
                "consentRequired": False,
                "config": {
                    "multivalued": "true",
                    "user.attribute": "roles",
                    "id.token.claim": "true",
                    "access.token.claim": "true",
                    "claim.name": "roles",
                    "jsonType.label": "String",
                    "userinfo.token.claim": "true",
                },
            })
        secret_data = _kc_get(token, f"/admin/realms/{REALM_NAME}/clients/{client_uuid}/client-secret")
        client_secret = (secret_data or {}).get("value", "(unavailable)")
    else:
        client_secret = "(unavailable)"

    print("  Done.")
    return client_secret


# --- infrastructure helpers ---

def _get_compose_cmd():
    if subprocess.run(['docker', 'compose', 'version'], capture_output=True).returncode == 0:
        return ['docker', 'compose']
    if subprocess.run(['docker-compose', 'version'], capture_output=True).returncode == 0:
        return ['docker-compose']
    sys.exit(
        "Error: Docker Compose not found. Install one of:\\n"
        "  sudo apt install docker-compose          (Ubuntu repo)\\n"
        "  sudo apt install docker-compose-plugin   (Docker official repo)\\n"
        "  pip install docker-compose"
    )


COMPOSE = _get_compose_cmd()


def check_hosts():
    # keycloak.dev.local needs its own IP (127.0.0.2) so reverse DNS returns the
    # right hostname for Kerberos service principal lookup (HTTP/keycloak.dev.local)
    required = {"kdc.dev.local": "127.0.0.1", "keycloak.dev.local": "127.0.0.2"}
    try:
        hosts = Path('/etc/hosts').read_text()
    except Exception:
        hosts = ""
    missing = {h: ip for h, ip in required.items() if h not in hosts}
    if missing:
        print("WARNING: add to /etc/hosts:")
        for host, ip in missing.items():
            print(f"  sudo bash -c 'echo \\"{ip}  {host}\\" >> /etc/hosts'")
        print()


def run(cmd, **kwargs):
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd)}")


def wait_for_keycloak():
    url = f"{KC_MGMT_BASE}/health/ready"
    print("Waiting for Keycloak to be ready", end="", flush=True)
    for _ in range(60):
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    print(" ready.")
                    return
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(3)
    print()
    sys.exit("Keycloak did not become ready. Check: docker compose -f dev-sso/docker-compose.yml logs keycloak")


def write_sso_delta(client_secret):
    sso_delta_path = root_dir / 'backend' / 'supabase_sso_config_dev.toml'
    content = (
        "# SSO configuration — generated by bin/dev-sso-start.py, do not edit manually.\\n"
        "\\n"
        "[auth.external.keycloak]\\n"
        "enabled = true\\n"
        'client_id = "supabase"\\n'
        f'secret = "{client_secret}"\\n'
        f'url = "http://keycloak.dev.local:{KC_PORT}/realms/{REALM_NAME}"\\n'
        "\\n"
        "[auth.hook.custom_access_token]\\n"
        "enabled = true\\n"
        'uri = "pg-functions://postgres/public/custom_access_token_hook"\\n'
    )
    if sso_delta_path.exists() and sso_delta_path.read_text() == content:
        print(f"  Unchanged: {sso_delta_path}")
        return False
    sso_delta_path.write_text(content)
    print(f"  Written: {sso_delta_path}")
    return True


def print_instructions(client_secret):
    sep = "=" * 60
    users_str = ", ".join(u["email"].split("@")[0] for u in USERS)
    print()
    print(sep)
    print("SSO DEV ENVIRONMENT READY")
    print(sep)
    print()
    print(f"  Keycloak admin:  http://localhost:{KC_PORT}/admin  (admin / admin)")
    print(f"  OIDC secret:     {client_secret}")
    print()
    print(f"  Users: {users_str}")
    print()
    print("  Scripts:")
    print("    python bin/dev-sso-chrome.py [user]")
    print("    python bin/dev-sso-stop.py")
    print("    python bin/dev-sso-remove.py [-f]")
    print()


# --- main ---

check_hosts()

print("Building SSO containers...")
run([*COMPOSE, '-p', COMPOSE_PROJECT, 'build'], cwd=sso_dir, stdout=sys.stdout, stderr=sys.stderr)

print("Starting SSO containers...")
run([*COMPOSE, '-p', COMPOSE_PROJECT, 'up', '-d'], cwd=sso_dir, stdout=sys.stdout, stderr=sys.stderr)

wait_for_keycloak()
client_secret = configure_keycloak()
print("Writing SSO config delta...")
write_sso_delta(client_secret)
print("Starting/updating Supabase...")
result = subprocess.run([sys.executable, str(root_dir / 'bin' / 'dev-supabase-start.py')],
                        stdout=sys.stdout, stderr=sys.stderr)
if result.returncode != 0:
    sys.exit(f"dev-supabase-start.py failed with code {result.returncode}")
print_instructions(client_secret)
"""
