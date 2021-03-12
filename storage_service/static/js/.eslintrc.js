module.exports = {
    "env": {
        "browser": true,
        "es2021": true,
        "jquery": true
    },
    "extends": ["eslint:recommended", "plugin:prettier/recommended"],
    "parserOptions": {
        "ecmaVersion": 12
    },
    "globals": {
        "Backbone": "readonly",
        "Base64": "readonly",
        "DirectoryPickerView": "readonly",
        "_": "readonly",
        "exports": "readonly",
        "gettext": "readonly"
    },
};
