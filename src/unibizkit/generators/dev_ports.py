import os

ENV_NUM = int(os.environ.get('UBK_DEV_ENV_NUM', '0'))

# Two parallel dev environments share one UBK_DEV_ENV_NUM block of 100 ports: the
# primary model at offset 0 (base+0..49) and the UBK_DEV_MODEL at offset 50
# (base+50..99). The CLI calls set_secondary(True) when it detects it is generating
# the UBK_DEV_MODEL, so every generated artifact for that model lands on the +50 slot.
_OFFSET = 0


def _recompute():
    base = 3000 + 100 * ENV_NUM + _OFFSET
    g = globals()
    g['BASE'] = base

    # Frontend / tooling  (base + 0..9)
    g['FRONTEND']       = base + 0
    g['VITE_PREVIEW']   = base + 1
    g['CHROME_DEBUG']   = base + 2
    g['EDGE_INSPECTOR'] = base + 3

    # External services  (base + 10..19)
    g['SMTP'] = base + 10

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


def set_secondary(is_secondary: bool):
    """Shift all ports by +50 when generating the secondary model (UBK_DEV_MODEL)."""
    global _OFFSET
    _OFFSET = 50 if is_secondary else 0
    _recompute()


_recompute()
