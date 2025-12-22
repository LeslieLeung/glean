# Frontend Development Guide

This file provides frontend-specific development guidance for the Glean project.

For general project information, see [../CLAUDE.md](../CLAUDE.md).

## Frontend Structure

```
frontend/
├── apps/
│   ├── web/           # Main React app (port 3000)
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   └── stores/    # Zustand state stores
│   └── admin/         # Admin dashboard (port 3001)
├── packages/
│   ├── ui/            # Shared components (COSS UI based)
│   ├── api-client/    # TypeScript API client SDK
│   ├── types/         # Shared TypeScript types
│   └── logger/        # Unified logging (loglevel based)
```

## Technology Stack

- **Language**: TypeScript (strict)
- **Framework**: React 18 + Vite
- **State/Cache**: Zustand + TanStack Query
- **Styling**: Tailwind CSS
- **Package Manager**: pnpm + Turborepo
- **Linting**: ESLint + Prettier

## UI Components (COSS UI)

This project uses [COSS UI](https://coss.com/ui/) for components.

To add a new component:

1. Visit `https://coss.com/ui/r/{component-name}.json`
2. Copy to `frontend/packages/ui/src/components/`
3. Export from `frontend/packages/ui/src/components/index.ts`

**IMPORTANT**: DO NOT modify anything within `frontend/packages/ui/src/components/` unless explicitly asked.

### Dialog/AlertDialog Close Buttons

When using `AlertDialogClose` or `DialogClose` from base-ui, **do not use the `render` prop with `<Button />`** as it requires ref forwarding which the Button component doesn't support. Instead, use `buttonVariants` to apply button styling directly:

```tsx
// ❌ Bad - causes "Function components cannot be given refs" warning
import { AlertDialogClose, Button } from '@glean/ui'

<AlertDialogClose render={<Button variant="ghost" />}>
  Cancel
</AlertDialogClose>

// ✅ Good - use buttonVariants for styling
import { AlertDialogClose, buttonVariants } from '@glean/ui'

<AlertDialogClose className={buttonVariants({ variant: 'ghost' })}>
  Cancel
</AlertDialogClose>

// For default button style
<AlertDialogClose className={buttonVariants()}>
  OK
</AlertDialogClose>

// For destructive actions
<AlertDialogClose className={buttonVariants({ variant: 'destructive' })}>
  Delete
</AlertDialogClose>
```

The same pattern applies to `DialogClose`.

## Code Style

- Prettier with Tailwind plugin
- Import order: React → third-party → workspace packages → relative

**ESLint + Prettier** (configured in `frontend/eslint.config.js` and `.prettierrc`):

- No semicolons
- Single quotes
- 2-space indentation
- 100 character print width
- Trailing commas (ES5 style)
- Tailwind class sorting (via prettier-plugin-tailwindcss)

**TypeScript**:

- Strict mode enabled
- Unused variables: error (prefix with `_` to ignore)
- All exports should be typed

**React-specific Rules**:

- Use `react-refresh/only-export-components` for HMR compatibility
- React hooks rules enforced

## Logging

```typescript
import { logger, createNamedLogger } from '@glean/logger'
logger.info('Message', { context: 'data' })
```

- Configure via `VITE_LOG_LEVEL` (debug in dev, error in prod)

## i18n (Internationalization)

This project uses **react-i18next** for internationalization. Always use translation keys instead of hardcoded text.

### Using i18n in Components

```tsx
// ❌ Bad - hardcoded text
<button>Save</button>
<h1>Settings</h1>

// ✅ Good - using i18n
import { useTranslation } from '@glean/i18n'

function MyComponent() {
  const { t } = useTranslation('common') // or 'auth', 'settings', etc.
  return (
    <>
      <button>{t('actions.save')}</button>
      <h1>{t('settings:title')}</h1>
    </>
  )
}
```

### Available Namespaces

- `common`: Shared UI text (buttons, states, actions)
- `auth`: Authentication pages (login, register)
- `settings`: Settings page
- `reader`: Reading interface
- `bookmarks`: Bookmark management
- `feeds`: Feed management, folders, OPML
- `ui`: UI component-level text

### Adding New Translations

1. Add key-value pairs to the appropriate namespace JSON files:
   - `frontend/packages/i18n/src/locales/en/{namespace}.json`
   - `frontend/packages/i18n/src/locales/zh-CN/{namespace}.json`

2. Use the translation in your component:
   ```tsx
   const { t } = useTranslation('namespace')
   t('your.new.key')
   ```

### Variable Interpolation

```json
// feeds.json
{
  "count": "{{count}} feeds"
}
```

```tsx
t('feeds:count', { count: 5 }) // Output: "5 feeds"
```

### Date Formatting

```tsx
import { formatRelativeTime } from '@glean/i18n/utils/date-formatter'
import { useTranslation } from '@glean/i18n'

function MyComponent({ date }) {
  const { i18n } = useTranslation()
  return <time>{formatRelativeTime(date, i18n.language)}</time>
}
```

### Language Switching

Users can change language in Settings → Appearance → Language.
The selection is persisted to localStorage and auto-detected on first visit.

## UI Layout & Design

### Application Layout

The web app uses a **three-column layout**:

```
┌──────────────────────────────────────────────────────────────────┐
│                        Header (optional)                          │
├──────────┬─────────────────┬─────────────────────────────────────┤
│          │                 │                                      │
│ Sidebar  │   Entry List    │          Reading Pane                │
│ (72-256) │    (280-500)    │          (flexible)                  │
│          │                 │                                      │
│ - Feeds  │ - Entry cards   │ - Article title                      │
│ - Folders│ - Filters       │ - Content (prose)                    │
│ - Tags   │ - Skeleton      │ - Actions (like, bookmark, share)   │
│          │                 │                                      │
└──────────┴─────────────────┴─────────────────────────────────────┘
```

- **Sidebar**: Collapsible (72px ↔ 256px), contains navigation and feed list
- **Entry List**: Resizable (280-500px), shows article previews with filters
- **Reading Pane**: Flexible width, displays full article content

### Design Principles

See @docs/design.md for more details.

| Principle         | Description                                                 |
| ----------------- | ----------------------------------------------------------- |
| Warm Dark Theme   | Default theme with amber primary (`hsl(38 92% 50%)`)        |
| Reading-First     | Optimized typography and spacing for long-form content      |
| Subtle Animations | Meaningful feedback without distraction (fade, slide, glow) |
| Glassmorphism     | Modern blur effects for overlays and cards                  |

### Color System

Always use CSS variables, never hard-coded colors:

```tsx
// Correct
className = 'bg-primary text-primary-foreground'
className = 'text-muted-foreground hover:text-foreground'

// Incorrect
className = 'bg-amber-500 text-slate-900'
```

Key semantic colors:

- `--primary`: Amber accent
- `--secondary`: Teal accent
- `--background` / `--foreground`: Main page colors
- `--card` / `--muted`: Surface colors
- `--destructive` / `--success` / `--warning`: Semantic states

### Typography

| Usage           | Font Family | Example Class                     |
| --------------- | ----------- | --------------------------------- |
| Headings/UI     | DM Sans     | `font-display text-2xl font-bold` |
| Article Content | Crimson Pro | `prose font-reading`              |
| Code            | Monospace   | Built-in prose styling            |

### Component Patterns

```tsx
// Glass effect for overlays
<div className="glass">...</div>

// Interactive cards
<div className="card-hover">...</div>

// Primary action buttons with glow
<Button className="btn-glow">...</Button>

// Animations
<div className="animate-fade-in">...</div>
<ul className="stagger-children">{items}</ul>
```

### Interaction Guidelines

- **Buttons**: Primary (glow on hover), Ghost (transparent), Outline (bordered)
- **Cards**: Subtle lift on hover (`translateY(-2px)`)
- **Focus States**: 4px ring in primary color
- **Loading**: Skeleton placeholders matching content layout
- **Transitions**: Fast (150ms) for hover, Standard (200ms) for state changes

Refer to `docs/design.md` for complete color palettes, spacing scales, and detailed component specifications.

## Testing

```bash
cd frontend/apps/web && pnpm test
```

## MCP Tools

When debugging frontend issues, use `chrome-devtools` MCP to help with:

- Taking snapshots and screenshots
- Inspecting network requests and console messages
- Interacting with page elements

## CI Compliance

### Common Fixes

```bash
# Auto-fix ESLint issues
cd frontend && pnpm lint --fix

# Auto-format with Prettier
cd frontend && pnpm format

# Type check
cd frontend && pnpm typecheck

# Build
cd frontend && pnpm build
```

### Common CI Failures and Solutions

| Error                      | Solution                           |
| -------------------------- | ---------------------------------- |
| `ESLint: no-unused-vars`   | Remove variable or prefix with `_` |
| `TypeScript: implicit any` | Add explicit type annotation       |
| `Prettier: formatting`     | Run `pnpm format`                  |

## Development Commands

```bash
# Type check all packages
pnpm typecheck

# Type check specific package
pnpm --filter=@glean/web typecheck

# Build specific package
pnpm --filter=@glean/web build

# Start dev server
pnpm --filter=@glean/web dev

# Run tests
pnpm --filter=@glean/web test
```

## Notes

- This project uses monorepo structure - always check your current working directory
- You don't have to create documentation unless explicitly asked
- Always write code comments in English
- DO NOT modify anything within `frontend/packages/ui/src/components/` unless explicitly asked
