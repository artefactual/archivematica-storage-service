# Archivematica Storage Service Frontend Components

Vue.js components for Archivematica Storage Service, migrating from legacy
JavaScript to modern Vue 3 + TypeScript.

## Development

### Setup

```bash
npm install
```

### Development server

```bash
npm run dev
# Starts on http://localhost:3000 (or custom port with --port)
```

### Testing

```bash
npm run test              # Run unit tests
npm run test:interactive  # Run unit tests in watch mode
npm run lint              # Run ESLint with auto-fix
npm run type-check        # Run TypeScript checks
npm run check             # Run all checks (lint + type-check + test + build)
```

### Build

```bash
npm run build             # Production build
npm run build:watch       # Production build (watch mode)
npm run preview           # Preview production build locally
```

## Internationalization (i18n)

Vue i18n is configured in `lib/shared/i18n` and loads JSON translation bundles
at runtime. The frontend package does not include gettext conversion scripts; the
JSON files under `lib/shared/i18n/locales` are the runtime source of truth.

### Translation files structure

The locale JSON files are located in `lib/shared/i18n/locales`:

```text
lib/shared/i18n/locales/
├── en.json
├── es.json
└── ...
```

`en.json` is the source language file and must contain all translation keys used
in the Vue components. Other language files should mirror the structure of
`en.json`.

### Development environment

- **Local playground**: Available at `http://localhost:3000` via `npm run dev`.
- **Proxying**: Vite proxies `/api`, `/locations`, `/administration`, `/media`,
  and `/static` to the local Storage Service backend target.
- **Playground usage**:
  Enter a Space UUID and root path to load the directory picker tree.
  Use row-level `Select` actions to commit a directory selection.

### Adding a new language

1. Add a new JSON file in `lib/shared/i18n/locales` (BCP 47 filename, e.g.
   `pt-br.json`).
2. Add the locale code to `AVAILABLE_LOCALES` in `lib/shared/i18n/index.ts`.
3. Ensure the backend sets `window.StorageServiceConfig.currentLanguage` to the
   POSIX/CLDR form (e.g. `pt_BR`) when needed.

### Language selection at runtime

- The initial locale comes from `window.StorageServiceConfig.currentLanguage`
  when present, and falls back to English.
- The runtime expects POSIX/CLDR style values like `pt_BR` and converts them to
  BCP 47 (`pt-br`) internally.

## Project layout

- `dev/` contains a local development shell app.
- `lib/` contains frontend library entrypoints built for Django staticfiles.
- `lib/location-directory-picker/` contains the Storage Service location
  directory picker app.
- `lib/shared/` contains shared components, encoding helpers, HTTP utilities,
  and i18n runtime setup.

## Integration

The build currently emits a `location-directory-picker` entrypoint for Django
staticfiles:

- `dist/location-directory-picker.js`

When adding new Vue apps, register additional library entries in
`vite.config.ts`.
