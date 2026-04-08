# Next.js Optimization Guide

Performance, caching, and deployment best practices for Next.js 14+ App Router.

---

## 1. Rendering Strategy Selection

| Strategy | When to use |
|----------|------------|
| **Server Component** (default) | Data-fetching, no interactivity, SEO-critical content |
| **Client Component** (`'use client'`) | Event handlers, hooks, browser APIs, real-time state |
| **Static Generation** (`generateStaticParams`) | Marketing pages, blog posts, docs |
| **ISR** (`revalidate`) | Product pages, dashboards that can tolerate slight staleness |
| **Dynamic** (`dynamic = 'force-dynamic'`) | Personalized content, auth-gated pages |

```tsx
// Server Component (no 'use client') — always prefer when possible
async function ProductPage({ params }: { params: { id: string } }) {
  const product = await fetchProduct(params.id);  // runs on server, not bundled
  return <ProductDetail product={product} />;
}

// Opt into ISR — revalidate every 60 seconds
export const revalidate = 60;

// Static params for SSG
export async function generateStaticParams() {
  const products = await fetchAllProducts();
  return products.map(p => ({ id: p.id }));
}
```

---

## 2. Caching

Next.js 14 has four layers of cache. Understanding them prevents stale data bugs.

### Request Memoization

Same `fetch` URL called multiple times in one render is deduped automatically.
This lets you call `fetchUser(id)` in both a layout and a page without extra HTTP requests.

### Data Cache (fetch cache)

```tsx
// Cache indefinitely (default for server-side fetch)
fetch('/api/data', { cache: 'force-cache' });

// Opt out of cache
fetch('/api/data', { cache: 'no-store' });

// Time-based revalidation
fetch('/api/data', { next: { revalidate: 3600 } });

// Tag-based invalidation
fetch('/api/products', { next: { tags: ['products'] } });

// Revalidate tag from a Server Action
import { revalidateTag } from 'next/cache';
revalidateTag('products');
```

### Full Route Cache (static rendering)

Pages rendered at build time are cached on disk. Break out of this with:
- `export const dynamic = 'force-dynamic'`
- `cookies()` / `headers()` calls (auto-opts into dynamic)
- `noStore()` from `next/cache`

### Router Cache (client-side)

Next.js caches visited route segments in memory for the session duration.
Force a refresh with `router.refresh()` or `revalidatePath()` from a Server Action.

---

## 3. Image Optimization

```tsx
import Image from 'next/image';

// Always provide width + height for layout stability (prevents CLS)
<Image
  src="/hero.jpg"
  alt="Hero image"
  width={1200}
  height={600}
  priority              // LCP image — load eagerly
  sizes="(max-width: 768px) 100vw, 50vw"
  placeholder="blur"
  blurDataURL={blurUrl}
/>

// Fill mode for responsive containers
<div className="relative h-64 w-full">
  <Image src={src} alt={alt} fill className="object-cover" sizes="100vw" />
</div>
```

Rules:
- Add `priority` only to above-the-fold images (max 1–2 per page).
- Always provide `sizes` for images that aren't full viewport width.
- Use `placeholder="blur"` with a tiny base64 blurDataURL for perceived performance.
- Serve AVIF/WebP via `formats: ['image/avif', 'image/webp']` in `next.config.ts`.

---

## 4. Font Optimization

```tsx
// next/font loads fonts at build time, hosts on your domain, zero layout shift
import { Inter, JetBrains_Mono } from 'next/font/google';

const inter = Inter({
  subsets:  ['latin'],
  variable: '--font-inter',
  display:  'swap',
});

const mono = JetBrains_Mono({
  subsets:  ['latin'],
  variable: '--font-mono',
  display:  'swap',
});

// Apply CSS variables on <html>
export default function RootLayout({ children }) {
  return (
    <html lang="en" className={`${inter.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
```

---

## 5. Metadata & SEO

```tsx
import type { Metadata } from 'next';

// Static metadata
export const metadata: Metadata = {
  title: {
    template: '%s | Acme',
    default:  'Acme',
  },
  description: 'Acme — the best product',
  openGraph: {
    type:   'website',
    locale: 'en_US',
    url:    'https://acme.com',
    images: [{ url: 'https://acme.com/og.png', width: 1200, height: 630 }],
  },
  twitter: { card: 'summary_large_image' },
  robots:  { index: true, follow: true },
};

// Dynamic metadata
export async function generateMetadata({ params }): Promise<Metadata> {
  const product = await fetchProduct(params.id);
  return {
    title: product.name,
    description: product.description,
    openGraph: { images: [product.imageUrl] },
  };
}
```

---

## 6. Server Actions

```tsx
'use server';

import { revalidatePath } from 'next/cache';
import { redirect }       from 'next/navigation';
import { z }              from 'zod';

const schema = z.object({
  name:  z.string().min(1).max(100),
  email: z.string().email(),
});

export async function createUser(formData: FormData) {
  // Validate
  const result = schema.safeParse({
    name:  formData.get('name'),
    email: formData.get('email'),
  });
  if (!result.success) return { error: result.error.flatten() };

  // Persist
  await db.users.create({ data: result.data });

  // Invalidate affected routes
  revalidatePath('/users');
  redirect('/users');
}
```

Use Server Actions for forms — they work without JavaScript, degrade gracefully, and avoid an API round-trip.

---

## 7. Bundle Size

### Tree-shaking

```tsx
// Bad: imports entire library
import _ from 'lodash';

// Good: import only what you use
import debounce from 'lodash/debounce';
// or use lodash-es for true tree-shaking
import { debounce } from 'lodash-es';
```

### Dynamic Imports

```tsx
import dynamic from 'next/dynamic';

// Client component with no SSR (e.g., chart library)
const Chart = dynamic(() => import('./Chart'), {
  ssr:     false,
  loading: () => <Skeleton className="h-64" />,
});

// Heavy component loaded only when needed
const RichEditor = dynamic(() => import('./RichEditor'));
```

### Analyze Bundles

```bash
ANALYZE=true npm run build
# or
python scripts/bundle_analyzer.py . --budget-kb 200
```

---

## 8. Middleware

```ts
// middleware.ts
import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

export function middleware(request: NextRequest) {
  const response = NextResponse.next();

  // Security headers
  response.headers.set('X-Frame-Options', 'DENY');
  response.headers.set('X-Content-Type-Options', 'nosniff');

  // A/B testing: assign variant cookie
  if (!request.cookies.has('variant')) {
    response.cookies.set('variant', Math.random() < 0.5 ? 'a' : 'b');
  }

  return response;
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
};
```

Middleware runs at the edge — keep it fast and dependency-free.

---

## 9. Core Web Vitals Checklist

| Metric | Target | Key levers |
|--------|--------|-----------|
| **LCP** ≤ 2.5 s | Image `priority`, preload critical assets, fast TTFB via ISR/edge |
| **INP** ≤ 200 ms | Avoid long tasks, defer non-critical JS, use Transitions |
| **CLS** ≤ 0.1 | Explicit `width`/`height` on images, avoid inserting above-fold content |

```tsx
// Avoid layout shift with explicit dimensions
// Bad
<img src="/hero.jpg" alt="Hero" />

// Good
<Image src="/hero.jpg" alt="Hero" width={1200} height={600} />
```

```tsx
// Use React Transition for non-urgent state updates
import { useTransition } from 'react';

const [isPending, startTransition] = useTransition();

const handleSearch = (query: string) => {
  startTransition(() => setSearchResults(search(query)));
};
```

---

## 10. Deployment Checklist

- [ ] `output: 'standalone'` in `next.config.ts` for Docker deployments
- [ ] Environment variables prefixed with `NEXT_PUBLIC_` only for client-exposed values
- [ ] Image domains / `remotePatterns` configured in `next.config.ts`
- [ ] `generateStaticParams` implemented for dynamic routes that can be pre-rendered
- [ ] `revalidate` or cache tags set on all data fetches
- [ ] Lighthouse CI running in pull request checks
- [ ] Content Security Policy header configured
- [ ] `robots.txt` and `sitemap.xml` generated via `app/robots.ts` / `app/sitemap.ts`
