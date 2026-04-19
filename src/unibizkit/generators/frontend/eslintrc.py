import json


def generate() -> str:
    config = {
        "env": {"browser": True, "es2020": True},
        "extends": ["eslint:recommended", "plugin:react/recommended"],
        "plugins": ["react"],
        "settings": {"react": {"version": "detect"}},
        "parserOptions": {
            "ecmaVersion": 2020,
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
