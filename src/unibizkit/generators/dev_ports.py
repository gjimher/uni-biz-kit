BASE = 3000
ENV_NUM = 0


def _recompute():
    g = globals()
    base = g['BASE']
    # Compatibility suffix for generated Docker names. It is derived from the
    # selected base port, not configured independently.
    g['ENV_NUM'] = max(0, (base - 3000) // 100)

    # Frontend / tooling  (base + 0..9)
    g['FRONTEND']       = base + 0
    g['VITE_PREVIEW']   = base + 1
    g['CHROME_DEBUG']   = base + 2
    g['EDGE_INSPECTOR'] = base + 3

    # External services  (base + 10..19)
    g['SMTP'] = base + 10
    g['INTEGRATION_MOCK'] = base + 11

    # SSO / Keycloak  (base + 30..39)
    g['KC_PORT']      = base + 30
    g['KC_MGMT_PORT'] = base + 31
    g['KDC_PORT']     = base + 32
    g['KADMIN_PORT']  = base + 33

    # Supabase  (base + 40..49)
    g['SUPABASE_API']       = base + 40
    g['SUPABASE_DB']        = base + 41
    g['SUPABASE_SHADOW']    = base + 42
    g['SUPABASE_STUDIO']    = base + 43
    g['SUPABASE_INBUCKET']  = base + 44
    g['SUPABASE_ANALYTICS'] = base + 45
    g['SUPABASE_POOLER']    = base + 46


def configure(base_port: int = 3000):
    """Configure generated development ports from a single base port."""
    global BASE
    BASE = int(base_port)
    _recompute()


_recompute()
