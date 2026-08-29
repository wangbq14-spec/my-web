import globals from 'globals'
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'

export default [
  {
    ignores: ['dist/**', 'backend/**'],
  },
  js.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
  files: ['**/*.{js,mjs,cjs,vue}'],
  languageOptions: {
    globals: globals.browser,
  },
  rules: {
    'vue/multi-word-component-names': 'off',
  },
},
]
