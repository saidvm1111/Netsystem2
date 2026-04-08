# Frontend Best Practices

Engineering standards for modern React / TypeScript frontend development.

---

## 1. Project Structure

```
src/
├── app/               # Next.js App Router routes
│   ├── (marketing)/   # Route group (no URL segment)
│   ├── (dashboard)/
│   └── api/
├── components/        # Shared, reusable UI components
│   ├── ui/            # Primitives (Button, Input, Modal…)
│   └── domain/        # Business-domain components (UserCard, OrderTable…)
├── hooks/             # Custom hooks
├── lib/               # Framework-agnostic utilities
├── stores/            # Zustand or other global state
├── types/             # Shared TypeScript types/interfaces
└── test/              # Global test setup and utilities
```

Rules:
- Co-locate tests and stories with their component (`Button.tsx`, `Button.test.tsx`, `Button.stories.tsx`).
- Use barrel `index.ts` files only for public API of a folder — not for every file.
- Never import from `../../../components` — configure `@/` path alias.

---

## 2. TypeScript Standards

### Prefer `interface` for object shapes, `type` for unions

```ts
// Object shape → interface
interface User {
  id:        string;
  email:     string;
  role:      UserRole;
  createdAt: Date;
}

// Union or computed → type
type UserRole    = 'admin' | 'member' | 'guest';
type UserOrGuest = User | null;
```

### Avoid `any` — use `unknown` and narrow

```ts
// Bad
function parse(data: any) { return data.user.name; }

// Good
function parse(data: unknown): string {
  if (typeof data === 'object' && data !== null &&
      'user' in data && typeof (data as { user: unknown }).user === 'object') {
    // narrow with Zod instead in practice
  }
  throw new Error('Unexpected data shape');
}

// Best: parse at the boundary with Zod
import { z } from 'zod';
const ResponseSchema = z.object({ user: z.object({ name: z.string() }) });
const parsed = ResponseSchema.parse(data);
```

### Discriminated Unions for state machines

```ts
type LoadState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error';   error: Error };

// Exhaustive switch narrows correctly
function render<T>(state: LoadState<T>) {
  switch (state.status) {
    case 'idle':    return <Placeholder />;
    case 'loading': return <Spinner />;
    case 'success': return <DataView data={state.data} />;
    case 'error':   return <ErrorMessage error={state.error} />;
  }
}
```

---

## 3. Component Design

### Single Responsibility

Each component should do one thing. If a component is fetching data, transforming it, and rendering it, split it:

- **Container / Smart**: fetches data, manages state
- **Presentational / Dumb**: receives props, renders UI

```tsx
// Smart — only in Next.js Server Component or page-level client component
async function UsersPage() {
  const users = await fetchUsers();
  return <UserList users={users} />;
}

// Dumb — pure, testable, reusable
function UserList({ users }: { users: User[] }) {
  return <ul>{users.map(u => <UserRow key={u.id} user={u} />)}</ul>;
}
```

### Prop Design

```tsx
// Extend native element props to preserve HTML attributes
interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost';
  isLoading?: boolean;
}

function Button({ variant = 'primary', isLoading, children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      disabled={isLoading || disabled}
      aria-busy={isLoading}
      data-variant={variant}
      {...rest}
    >
      {isLoading ? <Spinner /> : children}
    </button>
  );
}
```

---

## 4. Styling with Tailwind CSS

### Avoid Inline Style; Use `cn()` for Conditional Classes

```tsx
import { cn } from '@/lib/utils';

function Badge({ variant, className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium',
      {
        'bg-green-100 text-green-800': variant === 'success',
        'bg-red-100 text-red-800':    variant === 'error',
        'bg-yellow-100 text-yellow-800': variant === 'warning',
      },
      className  // allow callers to extend
    )}>
      {children}
    </span>
  );
}
```

### CVA (Class Variance Authority) for Component Variants

```tsx
import { cva, type VariantProps } from 'class-variance-authority';

const button = cva(
  'inline-flex items-center justify-center rounded-md font-medium transition-colors',
  {
    variants: {
      variant: {
        primary:   'bg-indigo-600 text-white hover:bg-indigo-700',
        secondary: 'bg-white text-gray-900 border border-gray-300 hover:bg-gray-50',
        ghost:     'hover:bg-gray-100 text-gray-700',
      },
      size: {
        sm: 'h-8 px-3 text-xs',
        md: 'h-10 px-4 text-sm',
        lg: 'h-12 px-6 text-base',
      },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  }
);

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
          VariantProps<typeof button> {}

function Button({ variant, size, className, ...props }: ButtonProps) {
  return <button className={cn(button({ variant, size }), className)} {...props} />;
}
```

---

## 5. Form Handling

### React Hook Form + Zod

```tsx
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';

const schema = z.object({
  email:    z.string().email('Invalid email'),
  password: z.string().min(8, 'At least 8 characters'),
});

type FormValues = z.infer<typeof schema>;

function LoginForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({ resolver: zodResolver(schema) });

  const onSubmit = async (data: FormValues) => {
    await signIn(data);
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register('email')} aria-describedby="email-error" />
      {errors.email && <p id="email-error" role="alert">{errors.email.message}</p>}

      <input type="password" {...register('password')} />
      {errors.password && <p role="alert">{errors.password.message}</p>}

      <button type="submit" disabled={isSubmitting}>
        {isSubmitting ? 'Signing in…' : 'Sign in'}
      </button>
    </form>
  );
}
```

---

## 6. Accessibility Checklist

### Interactive Elements

- [ ] All interactive elements reachable by keyboard (`Tab`, `Enter`, `Space`, arrows for widgets)
- [ ] Focus indicator visible (`outline` not set to `none` without replacement)
- [ ] No `div` or `span` as buttons — use `<button>` or `role="button"` with `tabIndex={0}`

### Images

- [ ] All `<img>` / `<Image>` have descriptive `alt` text
- [ ] Decorative images have `alt=""`
- [ ] Complex images have a linked long description

### Forms

- [ ] Every input has an associated `<label>` (via `htmlFor` or wrapping)
- [ ] Errors announced via `aria-describedby` pointing to the error `id`
- [ ] Required fields marked with `aria-required="true"` or `required`

### Color & Contrast

- [ ] Text contrast ratio ≥ 4.5:1 (normal), ≥ 3:1 (large text) — WCAG AA
- [ ] Information not conveyed by color alone

---

## 7. Testing Strategy

| Level | Tool | What to test |
|-------|------|-------------|
| Unit | Vitest | Pure functions, hooks, utility logic |
| Component | Testing Library | User interactions, rendering, accessibility |
| Integration | Playwright / Cypress | Full user flows, forms, navigation |
| Visual | Storybook + Chromatic | UI regressions |

### Query Priority (Testing Library)

Use queries in this order to keep tests accessible and resilient:
1. `getByRole` — most semantic
2. `getByLabelText` — forms
3. `getByPlaceholderText` — fallback for inputs
4. `getByText` — static text
5. `getByTestId` — last resort

---

## 8. Performance Checklist

- [ ] LCP image has `priority` prop
- [ ] Images have explicit `width`/`height` (no CLS)
- [ ] Heavy dependencies lazy-loaded with `dynamic()` or `lazy()`
- [ ] Long lists virtualized (`@tanstack/react-virtual`)
- [ ] No synchronous `localStorage` reads on first render (hydration mismatch)
- [ ] `useMemo` / `useCallback` used only where profiler shows benefit
- [ ] Third-party scripts loaded with `next/script` strategy `lazyOnload`

---

## 9. Code Review Checklist

- [ ] No business logic in JSX — extracted to hooks or utilities
- [ ] No `any` types
- [ ] Error states handled (not just happy path)
- [ ] Empty states handled
- [ ] Loading states handled
- [ ] Accessible keyboard navigation works
- [ ] `console.log` removed
- [ ] No hardcoded strings that should be i18n keys
- [ ] No secrets or API URLs in client-side code
