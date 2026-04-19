from ..context import Context


def generate(ctx: Context, has_custom_layout: bool = False, has_auth_provider: bool = False) -> str:
    import_statements = []
    resource_components = []

    for concept in ctx.concepts:
        resource_name = concept["name"]
        import_statements.append(
            f"import {{ {resource_name.upper()}_LIST, {resource_name.upper()}_CREATE, "
            f"{resource_name.upper()}_EDIT, {resource_name.upper()}_SHOW }} "
            f"from './resources/{resource_name}/{resource_name}.jsx';"
        )
        resource_components.append(
            f"""          {{(permissions?.['{resource_name}']?.includes('read') || permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('read') || permissions?.['*']?.includes('write')) ? (
              <Resource name="{resource_name}"
                  list={{ {resource_name.upper()}_LIST }}
                  create={{(permissions?.['{resource_name}']?.includes('write') || permissions?.['*']?.includes('write')) ? {resource_name.upper()}_CREATE : null}}
                  edit={{ {resource_name.upper()}_EDIT }}
                  show={{ {resource_name.upper()}_SHOW }}
              />
          ) : null}}"""
        )

    layout_import = ""
    layout_prop = ""
    if has_custom_layout:
        layout_import = "import { MyLayout } from './layout/MyLayout';"
        layout_prop = " layout={MyLayout}"

    auth_import = ""
    auth_prop = ""
    require_auth = ""
    ra_extra_imports = "Admin, Resource"
    extra_imports = ""
    custom_routes_block = ""
    i18n_provider_def = ""
    i18n_prop = ""
    if has_auth_provider:
        allow_registration = ctx.security_config["registration"]["allow"]
        if allow_registration:
            login_import = "import { MyLoginPage } from './layout/MyLoginPage';"
            login_prop = "MyLoginPage"
        else:
            login_import = ""
            login_prop = "LoginPage"
        ra_supabase_imports = f"{login_prop + ', ' if login_prop == 'LoginPage' else ''}ForgotPasswordPage, defaultI18nProvider"
        auth_import = f"import {{ authProvider }} from './authProvider';\n{login_import}\nimport {{ MySetPasswordPage }} from './layout/MySetPasswordPage';\nimport {{ {ra_supabase_imports} }} from 'ra-supabase';"
        auth_prop = f" authProvider={{authProvider}} loginPage={{{login_prop}}}"
        require_auth = " requireAuth"
        ra_extra_imports = "Admin, Resource, CustomRoutes"
        extra_imports = "import { Route } from 'react-router-dom';"
        custom_routes_block = """    <CustomRoutes noLayout>
        <Route path="/set-password" element={<MySetPasswordPage />} />
        <Route path="/forgot-password" element={<ForgotPasswordPage />} />
    </CustomRoutes>
"""
        i18n_provider_def = "\nconst i18nProvider = defaultI18nProvider;"
        i18n_prop = " i18nProvider={i18nProvider}"

    return f"""import * as React from 'react';
import {{ {ra_extra_imports} }} from 'react-admin';
import {{ dataProvider }} from './dataProvider';
{layout_import}
{auth_import}
{extra_imports}
{chr(10).join(import_statements)}
{i18n_provider_def}
const App = () => (
  <Admin dataProvider={{dataProvider}}{layout_prop}{auth_prop}{i18n_prop} mutationMode="pessimistic">
{custom_routes_block}      {{permissions => (
          <>
{chr(10).join(resource_components)}
          </>
      )}}
  </Admin>
);

export default App;"""
