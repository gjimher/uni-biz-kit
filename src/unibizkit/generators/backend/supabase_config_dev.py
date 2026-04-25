import re
from .context import Context
from ..dev_sso.constants import KC_PORT, REALM_NAME


def _sso_sections(kc_port: int, realm_name: str) -> str:
    return f"""
[auth.external.keycloak]
enabled = true
client_id = "supabase"
secret = "REPLACE_WITH_DEV_SSO_SECRET"
url = "http://keycloak.dev.local:{kc_port}/realms/{realm_name}"

[auth.hook.custom_access_token]
enabled = true
uri = "pg-functions://postgres/public/custom_access_token_hook"
"""


def generate(ctx: Context) -> str:
    system_config = ctx.system_config
    smtp = system_config.get('smtp', {})
    smtp_host = smtp.get('host', '127.0.0.1')
    if smtp_host in ('127.0.0.1', 'localhost'):
        smtp_host = '172.17.0.1'
    smtp_port = smtp.get('port', 25)
    smtp_from = smtp.get('from_email', 'noreply@localhost')
    smtp_user = smtp.get('user') or 'mock'
    smtp_pass = smtp.get('password') or 'mock'
    base_url = system_config.get('base_url', 'http://localhost:3000')

    registration = ctx.security_config['registration']
    allow_registration = registration['allow']
    enable_signup = 'true' if allow_registration else 'false'

    sso_config = ctx.security_config["sso"]
    sso_enabled = sso_config["enabled"]

    app_name = ctx.business_schema.get('name', 'app')
    project_id = re.sub(r'[^a-z0-9]+', '_', app_name.lower()).strip('_')

    return f"""# For detailed configuration reference documentation, visit:
# https://supabase.com/docs/guides/local-development/cli/config
project_id = "{project_id}"

[api]
enabled = true
port = 55321
external_url = "http://localhost:55321"
schemas = ["public", "graphql_public"]
extra_search_path = ["public", "extensions"]
max_rows = 1000

[api.tls]
enabled = false

[db]
port = 55322
shadow_port = 55320
health_timeout = "2m"
major_version = 17

[db.pooler]
enabled = false
port = 55329
pool_mode = "transaction"
default_pool_size = 20
max_client_conn = 100

[db.migrations]
enabled = true
schema_paths = []

[db.seed]
enabled = true
sql_paths = ["./seed.sql"]

[db.network_restrictions]
enabled = false
allowed_cidrs = ["0.0.0.0/0"]
allowed_cidrs_v6 = ["::/0"]

[realtime]
enabled = true

[studio]
enabled = true
port = 55323
api_url = "http://127.0.0.1"
openai_api_key = "env(OPENAI_API_KEY)"

[inbucket]
enabled = false
port = 55324

[storage]
enabled = true
file_size_limit = "50MiB"

[storage.s3_protocol]
enabled = true

[storage.analytics]
enabled = false
max_namespaces = 5
max_tables = 10
max_catalogs = 2

[storage.vector]
enabled = false
max_buckets = 10
max_indexes = 5

[auth]
enabled = true
site_url = "{base_url}"
additional_redirect_urls = ["{base_url}", "{base_url}/**"]
jwt_expiry = 3600
enable_refresh_token_rotation = true
refresh_token_reuse_interval = 10
enable_signup = {enable_signup}
enable_anonymous_sign_ins = false
enable_manual_linking = false
minimum_password_length = 6
password_requirements = ""

[auth.rate_limit]
email_sent = 100
sms_sent = 30
anonymous_users = 30
token_refresh = 150
sign_in_sign_ups = 30
token_verifications = 30
web3 = 30

[auth.email]
enable_signup = {enable_signup}
double_confirm_changes = false
enable_confirmations = true
secure_password_change = false
max_frequency = "1s"
otp_length = 6
otp_expiry = 3600

[auth.sms]
enable_signup = true
enable_confirmations = true
template = "Your code is {{{{ .Code }}}}"
max_frequency = "5s"

[auth.sms.twilio]
enabled = false
account_sid = ""
message_service_sid = ""
auth_token = "env(SUPABASE_AUTH_SMS_TWILIO_AUTH_TOKEN)"

[auth.mfa]
max_enrolled_factors = 10

[auth.mfa.totp]
enroll_enabled = false
verify_enabled = false

[auth.mfa.phone]
enroll_enabled = false
verify_enabled = false
otp_length = 6
template = "Your code is {{{{ .Code }}}}"
max_frequency = "5s"

[auth.external.apple]
enabled = false
client_id = ""
secret = "env(SUPABASE_AUTH_EXTERNAL_APPLE_SECRET)"
redirect_uri = ""
url = ""
skip_nonce_check = false
email_optional = false

[auth.web3.solana]
enabled = false

[auth.third_party.firebase]
enabled = false

[auth.third_party.auth0]
enabled = false

[auth.third_party.aws_cognito]
enabled = false

[auth.third_party.clerk]
enabled = false

[auth.oauth_server]
enabled = false
authorization_url_path = "/oauth/consent"
allow_dynamic_registration = false

[edge_runtime]
enabled = true
policy = "per_worker"
inspector_port = 8083
deno_version = 2

[analytics]
enabled = true
port = 55327
backend = "postgres"

[experimental]
orioledb_version = ""
s3_host = "env(S3_HOST)"
s3_region = "env(S3_REGION)"
s3_access_key = "env(S3_ACCESS_KEY)"
s3_secret_key = "env(S3_SECRET_KEY)"

[auth.email.smtp]
enabled = true
host = "{smtp_host}"
port = {smtp_port}
admin_email = "{smtp_from}"
sender_name = "App"
user = "{smtp_user}"
pass = "{smtp_pass}"
""" + (_sso_sections(KC_PORT, REALM_NAME) if sso_enabled else "")
