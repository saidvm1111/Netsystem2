#!/usr/bin/env python3
"""
Frontend Scaffolder - Generate Next.js / React project boilerplate.

Usage:
    python scripts/frontend_scaffolder.py <project-name> [options]

Options:
    --template TMPL     Template: nextjs-app | nextjs-pages | react-vite (default: nextjs-app)
    --ui UI             UI library: tailwind | shadcn | chakra | none (default: tailwind)
    --auth              Include NextAuth.js scaffold
    --api               Include API routes scaffold (Next.js only)
    --testing           Include Vitest + Testing Library config
    --storybook         Include Storybook config
    --docker            Include Dockerfile
    --dry-run           Print files without writing
    -v, --verbose       Verbose output

Examples:
    python scripts/frontend_scaffolder.py my-app
    python scripts/frontend_scaffolder.py my-app --template nextjs-app --auth --api --testing
    python scripts/frontend_scaffolder.py my-app --template react-vite --ui tailwind
"""

import argparse
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def write(path: Path, content: str, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print(f'  [dry-run] {path}')
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if verbose:
        print(f'  created  {path}')


# ---------------------------------------------------------------------------
# Next.js App Router template
# ---------------------------------------------------------------------------

NEXTJS_APP_FILES: dict = {
    'package.json': '''\
{{
  "name": "{name}",
  "version": "0.1.0",
  "private": true,
  "scripts": {{
    "dev":   "next dev",
    "build": "next build",
    "start": "next start",
    "lint":  "next lint",
    "test":  "vitest run",
    "test:watch": "vitest"
  }},
  "dependencies": {{
    "next":    "^14.2.0",
    "react":   "^18.3.0",
    "react-dom": "^18.3.0"
  }},
  "devDependencies": {{
    "@types/node":   "^20",
    "@types/react":  "^18",
    "@types/react-dom": "^18",
    "typescript":    "^5",
    "eslint":        "^8",
    "eslint-config-next": "^14"
  }}
}}
''',

    'tsconfig.json': '''\
{{
  "compilerOptions": {{
    "target":     "ES2017",
    "lib":        ["dom", "dom.iterable", "esnext"],
    "allowJs":    true,
    "skipLibCheck": true,
    "strict":     true,
    "noEmit":     true,
    "esModuleInterop": true,
    "module":     "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx":        "preserve",
    "incremental": true,
    "plugins":    [{{"name": "next"}}],
    "paths": {{
      "@/*": ["./src/*"]
    }}
  }},
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}}
''',

    'next.config.ts': '''\
import type {{ NextConfig }} from 'next';

const config: NextConfig = {{
  // Strict mode for highlighting potential issues in development
  reactStrictMode: true,

  // Image optimization
  images: {{
    formats: ['image/avif', 'image/webp'],
    remotePatterns: [],
  }},

  // Headers for security
  async headers() {{
    return [
      {{
        source: '/(.*)',
        headers: [
          {{ key: 'X-Content-Type-Options', value: 'nosniff' }},
          {{ key: 'X-Frame-Options',        value: 'DENY' }},
          {{ key: 'Referrer-Policy',        value: 'strict-origin-when-cross-origin' }},
        ],
      }},
    ];
  }},
}};

export default config;
''',

    'src/app/layout.tsx': '''\
import type {{ Metadata }} from 'next';
import {{ Inter }} from 'next/font/google';
{tailwind_import}

const inter = Inter({{ subsets: ['latin'] }});

export const metadata: Metadata = {{
  title: {{
    template: '%s | {title}',
    default:  '{title}',
  }},
  description: '{title} application',
}};

export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <html lang="en">
      <body className={{inter.className}}>{{children}}</body>
    </html>
  );
}}
''',

    'src/app/page.tsx': '''\
export default function HomePage() {{
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-24">
      <h1 className="text-4xl font-bold">{title}</h1>
      <p className="mt-4 text-lg text-gray-500">Get started by editing src/app/page.tsx</p>
    </main>
  );
}}
''',

    'src/app/globals.css': '''\
@tailwind base;
@tailwind components;
@tailwind utilities;
''',

    'src/lib/utils.ts': '''\
import {{ type ClassValue, clsx }} from 'clsx';
import {{ twMerge }} from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {{
  return twMerge(clsx(inputs));
}}
''',

    '.eslintrc.json': '''\
{{
  "extends": ["next/core-web-vitals", "next/typescript"]
}}
''',

    '.gitignore': '''\
# dependencies
node_modules/
.pnp
.pnp.js

# build output
.next/
out/
build/
dist/

# env files
.env
.env.local
.env.production

# misc
.DS_Store
*.pem
npm-debug.log*
yarn-debug.log*
yarn-error.log*

# testing
coverage/
''',

    '.env.example': '''\
NEXT_PUBLIC_APP_URL=http://localhost:3000
''',
}

TAILWIND_CONFIG = '''\
import type {{ Config }} from 'tailwindcss';

const config: Config = {{
  content: [
    './src/pages/**/*.{{js,ts,jsx,tsx,mdx}}',
    './src/components/**/*.{{js,ts,jsx,tsx,mdx}}',
    './src/app/**/*.{{js,ts,jsx,tsx,mdx}}',
  ],
  theme: {{
    extend: {{
      fontFamily: {{
        sans: ['var(--font-inter)'],
      }},
    }},
  }},
  plugins: [],
}};

export default config;
'''

POSTCSS_CONFIG = '''\
export default {{
  plugins: {{
    tailwindcss: {{}},
    autoprefixer: {{}},
  }},
}};
'''

NEXTAUTH_FILES = {
    'src/app/api/auth/[...nextauth]/route.ts': '''\
import NextAuth from 'next-auth';
import GitHub from 'next-auth/providers/github';
import Google from 'next-auth/providers/google';

export const {{ handlers, auth, signIn, signOut }} = NextAuth({{
  providers: [
    GitHub({{
      clientId:     process.env.GITHUB_ID!,
      clientSecret: process.env.GITHUB_SECRET!,
    }}),
    Google({{
      clientId:     process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }}),
  ],
  callbacks: {{
    session: ({{ session, token }}) => ({{
      ...session,
      user: {{ ...session.user, id: token.sub }},
    }}),
  }},
}});

export const {{ GET, POST }} = handlers;
''',

    'src/middleware.ts': '''\
export {{ auth as middleware }} from '@/app/api/auth/[...nextauth]/route';

export const config = {{
  matcher: ['/((?!api|_next/static|_next/image|favicon.ico).*)'],
}};
''',
}

API_FILES = {
    'src/app/api/health/route.ts': '''\
import {{ NextResponse }} from 'next/server';

export async function GET() {{
  return NextResponse.json({{ status: 'ok', timestamp: new Date().toISOString() }});
}}
''',

    'src/lib/api.ts': '''\
const API_URL = process.env.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000';

type FetchOptions = RequestInit & {{ params?: Record<string, string> }};

export async function apiFetch<T>(
  path: string,
  options: FetchOptions = {{}}
): Promise<T> {{
  const {{ params, ...init }} = options;
  const url = new URL(path, API_URL);
  if (params) Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));

  const res = await fetch(url, {{
    headers: {{ 'Content-Type': 'application/json', ...init.headers }},
    ...init,
  }});

  if (!res.ok) {{
    const body = await res.text().catch(() => '');
    throw new Error(`API ${{res.status}} — ${{path}}: ${{body}}`);
  }}

  return res.json() as Promise<T>;
}}
''',
}

VITEST_CONFIG = '''\
import {{ defineConfig }} from 'vitest/config';
import react from '@vitejs/plugin-react';
import {{ resolve }} from 'path';

export default defineConfig({{
  plugins: [react()],
  test: {{
    environment: 'jsdom',
    setupFiles:  ['./src/test/setup.ts'],
    globals:     true,
    coverage: {{
      provider: 'v8',
      reporter: ['text', 'html'],
    }},
  }},
  resolve: {{
    alias: {{ '@': resolve(__dirname, './src') }},
  }},
}});
'''

VITEST_SETUP = '''\
import '@testing-library/jest-dom';
'''

STORYBOOK_MAIN = '''\
import type {{ StorybookConfig }} from '@storybook/nextjs';

const config: StorybookConfig = {{
  stories: ['../src/**/*.stories.{{ts,tsx}}'],
  addons: [
    '@storybook/addon-essentials',
    '@storybook/addon-interactions',
    '@storybook/addon-a11y',
  ],
  framework: {{
    name: '@storybook/nextjs',
    options: {{}},
  }},
}};

export default config;
'''

STORYBOOK_PREVIEW = '''\
import type {{ Preview }} from '@storybook/react';
import '../src/app/globals.css';

const preview: Preview = {{
  parameters: {{
    controls: {{ matchers: {{ color: /(background|color)$/i, date: /Date$/i }} }},
    nextjs: {{ appDirectory: true }},
  }},
}};

export default preview;
'''

DOCKERFILE = '''\
FROM node:20-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup -S appgroup && adduser -S appuser -G appgroup

COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

USER appuser
EXPOSE 3000
ENV PORT 3000
CMD ["node", "server.js"]
'''

VITE_REACT_FILES = {
    'package.json': '''\
{{
  "name": "{name}",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {{
    "dev":   "vite",
    "build": "tsc && vite build",
    "preview": "vite preview",
    "test":  "vitest run",
    "lint":  "eslint . --ext ts,tsx --report-unused-disable-directives --max-warnings 0"
  }},
  "dependencies": {{
    "react":     "^18.3.0",
    "react-dom": "^18.3.0"
  }},
  "devDependencies": {{
    "@types/react":        "^18",
    "@types/react-dom":    "^18",
    "@vitejs/plugin-react": "^4.3.0",
    "typescript":          "^5",
    "vite":                "^5.4.0",
    "vitest":              "^1.6.0",
    "@testing-library/react": "^15",
    "@testing-library/jest-dom": "^6"
  }}
}}
''',

    'vite.config.ts': '''\
import {{ defineConfig }} from 'vite';
import react from '@vitejs/plugin-react';
import {{ resolve }} from 'path';

export default defineConfig({{
  plugins: [react()],
  resolve: {{
    alias: {{ '@': resolve(__dirname, './src') }},
  }},
  build: {{
    rollupOptions: {{
      output: {{
        manualChunks: {{
          vendor: ['react', 'react-dom'],
        }},
      }},
    }},
  }},
}});
''',

    'src/main.tsx': '''\
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
''',

    'src/App.tsx': '''\
export default function App() {{
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-8">
      <h1 className="text-4xl font-bold">{title}</h1>
      <p className="mt-4 text-gray-500">Get started by editing src/App.tsx</p>
    </main>
  );
}}
''',

    'src/index.css': '''\
@tailwind base;
@tailwind components;
@tailwind utilities;
''',

    'index.html': '''\
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>{title}</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
''',
}


# ---------------------------------------------------------------------------
# Scaffolding logic
# ---------------------------------------------------------------------------

def scaffold(name: str, template: str, ui: str, auth: bool, api: bool,
             testing: bool, storybook: bool, docker: bool,
             dry_run: bool, verbose: bool) -> int:
    base  = Path(name)
    title = name.replace('-', ' ').replace('_', ' ').title()
    tailwind_import = "import './globals.css';" if ui == 'tailwind' else ''

    ctx = dict(name=name, title=title, tailwind_import=tailwind_import)

    print(f"Scaffolding '{name}' ({template}) → {base.resolve()}")
    if dry_run:
        print('(dry-run — no files written)\n')

    if template in ('nextjs-app', 'nextjs-pages'):
        for rel, tmpl in NEXTJS_APP_FILES.items():
            write(base / rel, tmpl.format(**ctx), dry_run, verbose)

        if ui == 'tailwind':
            write(base / 'tailwind.config.ts', TAILWIND_CONFIG.format(**ctx), dry_run, verbose)
            write(base / 'postcss.config.mjs', POSTCSS_CONFIG, dry_run, verbose)

        if auth:
            for rel, content in NEXTAUTH_FILES.items():
                write(base / rel, content, dry_run, verbose)

        if api:
            for rel, content in API_FILES.items():
                write(base / rel, content, dry_run, verbose)

    elif template == 'react-vite':
        for rel, tmpl in VITE_REACT_FILES.items():
            write(base / rel, tmpl.format(**ctx), dry_run, verbose)
        write(base / 'tsconfig.json', NEXTJS_APP_FILES['tsconfig.json'].format(**ctx),
              dry_run, verbose)
        if ui == 'tailwind':
            write(base / 'tailwind.config.ts', TAILWIND_CONFIG.format(**ctx), dry_run, verbose)
            write(base / 'postcss.config.mjs', POSTCSS_CONFIG, dry_run, verbose)

    if testing:
        write(base / 'vitest.config.ts',  VITEST_CONFIG,  dry_run, verbose)
        write(base / 'src/test/setup.ts', VITEST_SETUP,   dry_run, verbose)

    if storybook:
        write(base / '.storybook/main.ts',    STORYBOOK_MAIN,    dry_run, verbose)
        write(base / '.storybook/preview.ts', STORYBOOK_PREVIEW, dry_run, verbose)

    if docker:
        write(base / 'Dockerfile', DOCKERFILE, dry_run, verbose)

    write(base / '.gitignore',    NEXTJS_APP_FILES['.gitignore'],    dry_run, verbose)
    write(base / '.env.example',  NEXTJS_APP_FILES['.env.example'],  dry_run, verbose)

    print(f'\nDone! Next steps:')
    print(f'  cd {name}')
    print(f'  npm install')
    print(f'  cp .env.example .env')
    print(f'  npm run dev')
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Scaffold a Next.js or React project.')
    p.add_argument('name', help='Project name / directory')
    p.add_argument('--template', default='nextjs-app',
                   choices=['nextjs-app', 'nextjs-pages', 'react-vite'])
    p.add_argument('--ui',  default='tailwind',
                   choices=['tailwind', 'shadcn', 'chakra', 'none'])
    p.add_argument('--auth',      action='store_true')
    p.add_argument('--api',       action='store_true')
    p.add_argument('--testing',   action='store_true')
    p.add_argument('--storybook', action='store_true')
    p.add_argument('--docker',    action='store_true')
    p.add_argument('--dry-run',   action='store_true')
    p.add_argument('-v', '--verbose', action='store_true')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return scaffold(
        name=args.name,
        template=args.template,
        ui=args.ui,
        auth=args.auth,
        api=args.api,
        testing=args.testing,
        storybook=args.storybook,
        docker=args.docker,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())
