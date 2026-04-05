# 005: Consolidación de Stack CSS y Docker npm workflow

## Fecha de Completación
5 de Abril de 2026

## Cambios Realizados

### 1. Actualización del Dockerfile (frontend)

**Antes:**
```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json ./
RUN npm install --package-lock=false
```

**Después:**
```dockerfile
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
```

**Razones del cambio:**
- `npm ci` (clean install) respeta exactamente las versiones en `package-lock.json` durante builds
- Mejora reproducibilidad: garantiza builds idénticos en diferentes máquinas/entornos
- `npm install --package-lock=false` es una antipatrón que ignora el lock file
- Ahora el Dockerfile copia `package-lock.json` explícitamente

### 2. Validación del Stack CSS

**Configuración confirmada en `postcss.config.mjs`:**
```javascript
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
    autoprefixer: {},
  },
};

export default config;
```

**Stack CSS completo en `package.json`:**
- `@tailwindcss/postcss: ^4.0.0` — Plugin principal de Tailwind (nuevo formato)
- `autoprefixer: ^10.4.20` — Para compatibilidad de prefijos CSS
- `postcss: ^8.4.31` — Procesador CSS (necesario)
- `tailwindcss: ^4.2.2` — Utilidades de Tailwind

**Validación:**
✅ No hay conflictos: ambas librerías (`@tailwindcss/postcss` y `autoprefixer`) son necesarias en PostCSS  
✅ `postcss.config.mjs` exporta configuración correcta  
✅ `tailwind.config.ts` existe y está disponible

## Impacto

- **Reproducibilidad:** Los builds de Docker ahora son determinísticos
- **Consistencia:** Todos los ambientes (local, CI/CD, producción) usan las mismas versiones
- **Seguridad:** Cambios en dependencias son controlados a través de actualizaciones explícitas de `package-lock.json`

## Próximas Acciones

1. Validar build local: `docker build -f frontend/Dockerfile -t frontend:test .`
2. Confirmar que `npm ci` completa exitosamente sin errores de versión
3. Si hay conflictos en `package-lock.json`, regenerarlo con `npm install && npm ci` en local

## Notas Técnicas

- El cambio es **totalmente compatible** con CI/CD pipelines existentes
- No requiere actualización de versiones en `package.json`
- `npm ci` es el comando recomendado para ambientes Docker/containerizados (https://docs.npmjs.com/cli/v8/commands/npm-ci)
