import json


def generate() -> str:
    # The linter must not be stricter than the bundler: Vite/esbuild compiles
    # current JS, so pinning an older ecmaVersion would reject valid model code
    # (a '??=' in a presentation page is a parse error under es2020).
    config = {
        "env": {"browser": True, "es2022": True},
        "extends": ["eslint:recommended", "plugin:react/recommended"],
        "plugins": ["react"],
        "settings": {"react": {"version": "detect"}},
        "parserOptions": {
            "ecmaVersion": "latest",
            "sourceType": "module",
            "ecmaFeatures": {"jsx": True}
        },
        "rules": {
            "no-unused-vars": "off",
            "react/prop-types": "off",
            "react/react-in-jsx-scope": "off",
            "react/display-name": "off",
            "react/jsx-key": "off",
            "no-undef": "off"
        }
    }
    return json.dumps(config, indent=2)
