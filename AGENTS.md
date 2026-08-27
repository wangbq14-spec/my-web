# Project Agent Rules

## Development workflow

For every code change:

1. Inspect existing code before editing.
2. Preserve existing working functionality unless the task explicitly requires changing it.
3. Implement the requested feature.
4. Run:

npm run quality

5. If any step fails:
   - inspect the real error
   - fix the root cause
   - run npm run quality again
   - repeat until all checks pass

6. Never report a task as complete until npm run quality passes.

## Quality Gate

The following must all pass:

- Vitest unit tests
- ESLint
- Vite production build
- Playwright E2E tests

## Testing

When adding or changing functionality:

- Add/update Vitest tests for component or logic behavior when appropriate.
- Add/update Playwright tests for important user interactions.
- Tests must reflect real product behavior.
- Never change production behavior only to make a bad test pass.

## UI

For UI changes:

- Keep responsive behavior.
- Preserve accessibility.
- Include hover/focus/active states where appropriate.
- Avoid unnecessary animation.
- Do not break mobile layouts.

## Safety

- Never expose secrets or API keys in frontend code.
- Do not delete unrelated working code.
- Prefer minimal, targeted changes.