import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import tseslint from 'typescript-eslint'

// Correctness only: no formatting rules. The hooks rules are errors because a
// missing effect dependency is a stale closure, not a matter of style.
export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  {
    files: ['src/**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    linterOptions: {
      reportUnusedDisableDirectives: 'error',
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'error',
      // Off: files here keep their hooks and helpers beside the component, and
      // this rule is about hot-reload speed, not correctness.
      'react-refresh/only-export-components': 'off',
      // A name the component forgot to define resolves to the browser's own
      // global (close, open, name, status …) and type-checks: the note's
      // close button called window.close() and did nothing.
      'no-restricted-globals': ['error',
        'close', 'open', 'name', 'status', 'event', 'origin', 'parent', 'self', 'top',
        'print', 'stop', 'find', 'blur', 'focus', 'scroll', 'length', 'closed', 'opener',
        'confirm', 'alert', 'prompt', 'history', 'location', 'screen', 'external', 'frames'],
      'no-unused-vars': 'off',
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrors: 'none',
        ignoreRestSiblings: true,
      }],
    },
  },
)
