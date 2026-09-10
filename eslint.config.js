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
  {
    // Playwright specs run under Node, not the browser: Buffer/process are globals there.
    files: ['tests/**/*.spec.js'],
    languageOptions: {
      globals: globals.node,
    },
  },
  {
    // Standalone Node scripts (dev bootstrap, browser verification) run under Node.
    files: ['scripts/**/*.{js,mjs,cjs}'],
    languageOptions: {
      globals: globals.node,
    },
  },
]
