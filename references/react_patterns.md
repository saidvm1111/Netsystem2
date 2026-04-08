# React Patterns

A practical reference for composable, maintainable React components with TypeScript.

---

## 1. Component Composition

### Compound Components

Expose related components under a shared namespace, letting consumers arrange them freely.

```tsx
// Usage
<Tabs defaultValue="profile">
  <Tabs.List>
    <Tabs.Trigger value="profile">Profile</Tabs.Trigger>
    <Tabs.Trigger value="settings">Settings</Tabs.Trigger>
  </Tabs.List>
  <Tabs.Panel value="profile"><ProfileForm /></Tabs.Panel>
  <Tabs.Panel value="settings"><SettingsForm /></Tabs.Panel>
</Tabs>

// Implementation
const TabsContext = createContext<TabsState | null>(null);

function Tabs({ defaultValue, children }: TabsProps) {
  const [active, setActive] = useState(defaultValue);
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div>{children}</div>
    </TabsContext.Provider>
  );
}

Tabs.List    = TabsList;
Tabs.Trigger = TabsTrigger;
Tabs.Panel   = TabsPanel;
```

### Render Props

Pass rendering control to the consumer — useful for headless UI components.

```tsx
interface DataFetcherProps<T> {
  url: string;
  children: (state: { data: T | null; isLoading: boolean; error: Error | null }) => ReactNode;
}

function DataFetcher<T>({ url, children }: DataFetcherProps<T>) {
  const { data, isLoading, error } = useFetch<T>(url);
  return <>{children({ data, isLoading, error })}</>;
}

// Usage
<DataFetcher<User[]> url="/api/users">
  {({ data, isLoading }) => isLoading ? <Spinner /> : <UserList users={data ?? []} />}
</DataFetcher>
```

### Polymorphic Components (`as` prop)

Let consumers control the rendered element without sacrificing type safety.

```tsx
type AsProp<C extends ElementType> = { as?: C };
type PropsOf<C extends ElementType, P = {}> =
  AsProp<C> & Omit<ComponentPropsWithRef<C>, keyof P> & P;

function Text<C extends ElementType = 'p'>({
  as,
  children,
  className,
  ...rest
}: PropsOf<C, { className?: string }>) {
  const Tag = as ?? 'p';
  return <Tag className={className} {...rest}>{children}</Tag>;
}

// Usage
<Text as="h1" className="text-2xl font-bold">Heading</Text>
<Text as="span">Inline text</Text>
```

---

## 2. State Management Patterns

### useState + Immer (local complex state)

```tsx
import { useImmer } from 'use-immer';

function CartManager() {
  const [cart, updateCart] = useImmer<CartState>({ items: [], coupon: null });

  const addItem = (item: CartItem) => {
    updateCart(draft => {
      const existing = draft.items.find(i => i.id === item.id);
      if (existing) existing.qty += 1;
      else draft.items.push({ ...item, qty: 1 });
    });
  };

  return <CartView cart={cart} onAdd={addItem} />;
}
```

### useReducer for Complex Local State

```tsx
type Action =
  | { type: 'FETCH_START' }
  | { type: 'FETCH_SUCCESS'; payload: User[] }
  | { type: 'FETCH_ERROR'; error: Error };

interface State { users: User[]; isLoading: boolean; error: Error | null }

const initial: State = { users: [], isLoading: false, error: null };

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'FETCH_START':   return { ...state, isLoading: true, error: null };
    case 'FETCH_SUCCESS': return { isLoading: false, error: null, users: action.payload };
    case 'FETCH_ERROR':   return { ...state, isLoading: false, error: action.error };
  }
}
```

### Zustand (global state without boilerplate)

```tsx
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthStore {
  user: User | null;
  token: string | null;
  login:  (user: User, token: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      user:  null,
      token: null,
      login:  (user, token) => set({ user, token }),
      logout: ()             => set({ user: null, token: null }),
    }),
    { name: 'auth-storage' }
  )
);
```

---

## 3. Data Fetching Patterns

### React Query (TanStack Query)

```tsx
// Query with type-safe fetcher
async function fetchUser(id: string): Promise<User> {
  const res = await fetch(`/api/users/${id}`);
  if (!res.ok) throw new Error('Failed to fetch user');
  return res.json();
}

function UserProfile({ userId }: { userId: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['user', userId],
    queryFn:  () => fetchUser(userId),
    staleTime: 60_000,
  });

  if (isLoading) return <Skeleton />;
  if (error)     return <ErrorBanner message={error.message} />;
  return <ProfileCard user={data} />;
}

// Mutation with optimistic update
const updateUser = useMutation({
  mutationFn: (data: Partial<User>) => api.patch(`/users/${userId}`, data),
  onMutate: async (newData) => {
    await queryClient.cancelQueries({ queryKey: ['user', userId] });
    const prev = queryClient.getQueryData<User>(['user', userId]);
    queryClient.setQueryData(['user', userId], old => ({ ...old, ...newData }));
    return { prev };
  },
  onError: (_err, _vars, ctx) => {
    queryClient.setQueryData(['user', userId], ctx?.prev);
  },
  onSettled: () => queryClient.invalidateQueries({ queryKey: ['user', userId] }),
});
```

---

## 4. Performance Patterns

### Memoization

```tsx
// useMemo: expensive derived computation
const sortedUsers = useMemo(
  () => [...users].sort((a, b) => a.name.localeCompare(b.name)),
  [users]
);

// useCallback: stable function reference for child props
const handleDelete = useCallback((id: string) => {
  dispatch({ type: 'DELETE_USER', id });
}, [dispatch]);

// React.memo: skip re-render when props unchanged
const UserRow = React.memo(function UserRow({ user, onDelete }: UserRowProps) {
  return <tr>...</tr>;
}, (prev, next) => prev.user.id === next.user.id && prev.user.updatedAt === next.user.updatedAt);
```

### Code Splitting

```tsx
// Lazy-load heavy components
const RichEditor  = lazy(() => import('./RichEditor'));
const ChartWidget = lazy(() => import('./ChartWidget'));

// Use with Suspense boundary
<Suspense fallback={<Skeleton className="h-64" />}>
  <RichEditor value={content} onChange={setContent} />
</Suspense>
```

### Virtualization for Long Lists

```tsx
import { useVirtualizer } from '@tanstack/react-virtual';

function VirtualList({ items }: { items: Item[] }) {
  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count:         items.length,
    getScrollElement: () => parentRef.current,
    estimateSize:  () => 56,
    overscan:      5,
  });

  return (
    <div ref={parentRef} className="h-96 overflow-auto">
      <div style={{ height: rowVirtualizer.getTotalSize() }} className="relative">
        {rowVirtualizer.getVirtualItems().map(vItem => (
          <div key={vItem.key} style={{ transform: `translateY(${vItem.start}px)` }}
               className="absolute w-full">
            <ListRow item={items[vItem.index]} />
          </div>
        ))}
      </div>
    </div>
  );
}
```

---

## 5. Error Handling

### Error Boundary (class component required)

```tsx
interface ErrorBoundaryState { hasError: boolean; error: Error | null }

class ErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode },
                                       ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Uncaught error:', error, info);
    // report to error tracking service
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}

// Usage
<ErrorBoundary fallback={<ErrorPage />}>
  <FeatureModule />
</ErrorBoundary>
```

---

## 6. Accessibility Patterns

```tsx
// useId for stable IDs
function FormField({ label, ...props }: InputProps & { label: string }) {
  const id = useId();
  return (
    <div>
      <label htmlFor={id}>{label}</label>
      <input id={id} {...props} />
    </div>
  );
}

// Focus trap for modals
import { FocusTrap } from 'focus-trap-react';

function Modal({ isOpen, onClose, children }: ModalProps) {
  if (!isOpen) return null;
  return (
    <FocusTrap focusTrapOptions={{ onDeactivate: onClose }}>
      <div role="dialog" aria-modal="true">
        {children}
      </div>
    </FocusTrap>
  );
}
```

---

## 7. Testing Patterns

```tsx
// Testing component behavior, not implementation
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

test('submits form with valid data', async () => {
  const user   = userEvent.setup();
  const onSave = vi.fn();
  render(<UserForm onSave={onSave} />);

  await user.type(screen.getByLabelText(/name/i), 'Alice');
  await user.type(screen.getByLabelText(/email/i), 'alice@example.com');
  await user.click(screen.getByRole('button', { name: /save/i }));

  await waitFor(() => expect(onSave).toHaveBeenCalledWith({
    name: 'Alice',
    email: 'alice@example.com',
  }));
});
```
