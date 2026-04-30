import os

ENV_NUM = int(os.environ.get('UBK_DEV_ENV_NUM', '0'))
BASE = 3000 + 100 * ENV_NUM

# Frontend / tooling  (base + 0..9)
FRONTEND       = BASE + 0
VITE_PREVIEW   = BASE + 1
CHROME_DEBUG   = BASE + 2
EDGE_INSPECTOR = BASE + 3

# External services  (base + 10..19)
SMTP = BASE + 10

# SSO / Keycloak  (base + 30..39)
KC_PORT      = BASE + 30
KC_MGMT_PORT = BASE + 31
KDC_PORT     = BASE + 32
KADMIN_PORT  = BASE + 33

# Supabase  (base + 40..49)
SUPABASE_API       = BASE + 40
SUPABASE_DB        = BASE + 41
SUPABASE_SHADOW    = BASE + 42
SUPABASE_STUDIO    = BASE + 43
SUPABASE_INBUCKET  = BASE + 44
SUPABASE_ANALYTICS = BASE + 45
SUPABASE_POOLER    = BASE + 46
