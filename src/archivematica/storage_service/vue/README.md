# Archivematica Storage Service Vue Components

Vue.js components for Archivematica Storage Service, migrating legacy frontend
code to modern Vue 3 + TypeScript.

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

### Development environment

- **Backend service**: Run Storage Service locally on `http://127.0.0.1:62081`
  while developing Vue components.
- **Local playground**: Available at `http://localhost:3000` via `npm run dev`.
- **Proxying**: Vite proxies `/api`, `/locations`, `/administration`, `/media`,
  and `/static` to the local backend target.

## Project layout

- `dev/` contains a local development shell app.
- `lib/` contains frontend library entrypoints built for Django staticfiles.
- `lib/location-directory-picker/` contains the Storage Service location
  directory picker app.

## Integration

The build currently emits a `location-directory-picker` entrypoint for Django
staticfiles:

- `dist/location-directory-picker.js`

When adding new Vue apps, register additional library entries in
`vite.config.ts`.
