#!/usr/bin/env python3
"""
Component Generator - Scaffold React/Next.js components with TypeScript.

Usage:
    python scripts/component_generator.py <name> [options]

Options:
    --dir DIR           Output directory (default: src/components)
    --type TYPE         Component type: fc | page | layout | hook | context (default: fc)
    --style STYLE       Styling: tailwind | css-module | styled (default: tailwind)
    --story             Generate a Storybook story file
    --test              Generate a Vitest/Jest test file
    --no-index          Skip generating an index.ts barrel export
    --dry-run           Print files without writing
    -v, --verbose       Verbose output

Examples:
    python scripts/component_generator.py Button
    python scripts/component_generator.py UserCard --type fc --story --test
    python scripts/component_generator.py Dashboard --type page --dir src/app/dashboard
    python scripts/component_generator.py useAuth --type hook --dir src/hooks
"""

import argparse
import re
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def to_pascal(name: str) -> str:
    return re.sub(r'[-_\s]+(.)', lambda m: m.group(1).upper(),
                  name[0].upper() + name[1:])


def to_camel(name: str) -> str:
    pascal = to_pascal(name)
    return pascal[0].lower() + pascal[1:]


def to_kebab(name: str) -> str:
    s = re.sub(r'([A-Z])', r'-\1', name).lower().lstrip('-')
    return re.sub(r'[-_\s]+', '-', s)


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------

FC_COMPONENT = '''\
import React from 'react';
{imports}

interface {pascal}Props {{
  className?: string;
  children?: React.ReactNode;
}}

export function {pascal}({{ className, children }}: {pascal}Props) {{
  return (
    <div className={{className}}>
      {{children}}
    </div>
  );
}}

export default {pascal};
'''

FC_TAILWIND_IMPORTS = ''
FC_CSS_MODULE_IMPORTS = "import styles from './{kebab}.module.css';\n"
FC_STYLED_IMPORTS = "import styled from 'styled-components';\n"

PAGE_COMPONENT = '''\
import type {{ Metadata }} from 'next';
{imports}

export const metadata: Metadata = {{
  title: '{pascal}',
  description: '{pascal} page',
}};

interface PageProps {{
  params: Promise<{{ [key: string]: string }}>;
  searchParams: Promise<{{ [key: string]: string | string[] | undefined }}>;
}}

export default async function {pascal}Page({{ params, searchParams }}: PageProps) {{
  return (
    <main>
      <h1>{pascal}</h1>
    </main>
  );
}}
'''

LAYOUT_COMPONENT = '''\
import type {{ Metadata }} from 'next';

export const metadata: Metadata = {{
  title: {{
    template: '%s | My App',
    default: '{pascal}',
  }},
}};

export default function {pascal}Layout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <section>
      {{children}}
    </section>
  );
}}
'''

HOOK_TEMPLATE = '''\
import {{ useState, useEffect, useCallback }} from 'react';

interface Use{pascal}Options {{
  // add options here
}}

interface Use{pascal}Return {{
  data: null;
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
}}

export function use{pascal}(options: Use{pascal}Options = {{}}): Use{pascal}Return {{
  const [data, setData] = useState<null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const refetch = useCallback(() => {{
    setIsLoading(true);
    setError(null);
    // TODO: implement fetch logic
    setIsLoading(false);
  }}, []);

  useEffect(() => {{
    refetch();
  }}, [refetch]);

  return {{ data, isLoading, error, refetch }};
}}
'''

CONTEXT_TEMPLATE = '''\
import React, {{ createContext, useContext, useState, useMemo }} from 'react';

interface {pascal}State {{
  // define state shape
}}

interface {pascal}ContextValue extends {pascal}State {{
  // define actions
}}

const {pascal}Context = createContext<{pascal}ContextValue | null>(null);

interface {pascal}ProviderProps {{
  children: React.ReactNode;
  initialState?: Partial<{pascal}State>;
}}

export function {pascal}Provider({{ children, initialState }}: {pascal}ProviderProps) {{
  const value = useMemo<{pascal}ContextValue>(() => ({{
    // spread state and actions
  }}), []);

  return (
    <{pascal}Context.Provider value={{value}}>
      {{children}}
    </{pascal}Context.Provider>
  );
}}

export function use{pascal}(): {pascal}ContextValue {{
  const ctx = useContext({pascal}Context);
  if (!ctx) throw new Error('use{pascal} must be used within {pascal}Provider');
  return ctx;
}}
'''

STORY_TEMPLATE = '''\
import type {{ Meta, StoryObj }} from '@storybook/react';
import {{ {pascal} }} from './{pascal}';

const meta = {{
  title: 'Components/{pascal}',
  component: {pascal},
  parameters: {{
    layout: 'centered',
  }},
  tags: ['autodocs'],
  argTypes: {{
    className: {{ control: 'text' }},
  }},
}} satisfies Meta<typeof {pascal}>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = {{
  args: {{
    children: '{pascal} content',
  }},
}};

export const WithClassName: Story = {{
  args: {{
    className: 'p-4 border rounded',
    children: 'Styled content',
  }},
}};
'''

TEST_TEMPLATE = '''\
import {{ render, screen }} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {{ describe, it, expect, vi }} from 'vitest';
import {{ {pascal} }} from './{pascal}';

describe('{pascal}', () => {{
  it('renders without crashing', () => {{
    render(<{pascal} />);
  }});

  it('renders children', () => {{
    render(<{pascal}>hello</{pascal}>);
    expect(screen.getByText('hello')).toBeInTheDocument();
  }});

  it('applies className', () => {{
    const {{ container }} = render(<{pascal} className="custom" />);
    expect(container.firstChild).toHaveClass('custom');
  }});
}});
'''

HOOK_TEST_TEMPLATE = '''\
import {{ renderHook, act }} from '@testing-library/react';
import {{ describe, it, expect, vi, beforeEach }} from 'vitest';
import {{ use{pascal} }} from './{pascal}';

describe('use{pascal}', () => {{
  it('initializes with default state', () => {{
    const {{ result }} = renderHook(() => use{pascal}());
    expect(result.current.data).toBeNull();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.error).toBeNull();
  }});

  it('exposes refetch', () => {{
    const {{ result }} = renderHook(() => use{pascal}());
    expect(typeof result.current.refetch).toBe('function');
  }});
}});
'''

CSS_MODULE_TEMPLATE = '''\
.root {{
  /* {pascal} styles */
}}
'''

INDEX_TEMPLATE = "export {{ {pascal}, default }} from './{pascal}';\n"
HOOK_INDEX_TEMPLATE = "export {{ use{pascal} }} from './{pascal}';\n"
CONTEXT_INDEX_TEMPLATE = "export {{ {pascal}Provider, use{pascal} }} from './{pascal}';\n"


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

TEMPLATES: dict = {
    'fc': {
        'file':    '{pascal}.tsx',
        'content': FC_COMPONENT,
        'index':   INDEX_TEMPLATE,
    },
    'page': {
        'file':    'page.tsx',
        'content': PAGE_COMPONENT,
        'index':   None,
    },
    'layout': {
        'file':    'layout.tsx',
        'content': LAYOUT_COMPONENT,
        'index':   None,
    },
    'hook': {
        'file':    '{pascal}.ts',
        'content': HOOK_TEMPLATE,
        'index':   HOOK_INDEX_TEMPLATE,
    },
    'context': {
        'file':    '{pascal}.tsx',
        'content': CONTEXT_TEMPLATE,
        'index':   CONTEXT_INDEX_TEMPLATE,
    },
}

STYLE_IMPORTS = {
    'tailwind':    FC_TAILWIND_IMPORTS,
    'css-module':  FC_CSS_MODULE_IMPORTS,
    'styled':      FC_STYLED_IMPORTS,
}


def write(path: Path, content: str, dry_run: bool, verbose: bool) -> None:
    if dry_run:
        print(f"  [dry-run] {path}")
        if verbose:
            print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    if verbose:
        print(f"  created  {path}")
    else:
        print(f"  {path}")


def generate(name: str, out_dir: Path, comp_type: str, style: str,
             story: bool, test: bool, no_index: bool,
             dry_run: bool, verbose: bool) -> int:
    pascal = to_pascal(name)
    camel  = to_camel(name)
    kebab  = to_kebab(name)

    tmpl = TEMPLATES.get(comp_type)
    if not tmpl:
        print(f"Unknown type: {comp_type}", file=sys.stderr)
        return 1

    ctx = dict(pascal=pascal, camel=camel, kebab=kebab,
               imports=STYLE_IMPORTS.get(style, ''))

    # Main component file
    filename = tmpl['file'].format(**ctx)
    content  = tmpl['content'].format(**ctx)
    comp_dir = out_dir / pascal if comp_type == 'fc' else out_dir
    write(comp_dir / filename, content, dry_run, verbose)

    # CSS module
    if style == 'css-module' and comp_type == 'fc':
        write(comp_dir / f'{kebab}.module.css', CSS_MODULE_TEMPLATE.format(**ctx),
              dry_run, verbose)

    # Storybook story
    if story and comp_type == 'fc':
        write(comp_dir / f'{pascal}.stories.tsx', STORY_TEMPLATE.format(**ctx),
              dry_run, verbose)

    # Test file
    if test:
        test_tmpl = HOOK_TEST_TEMPLATE if comp_type == 'hook' else TEST_TEMPLATE
        ext = '.ts' if comp_type == 'hook' else '.tsx'
        write(comp_dir / f'{pascal}.test{ext}', test_tmpl.format(**ctx),
              dry_run, verbose)

    # Index barrel export
    if not no_index and tmpl['index']:
        write(comp_dir / 'index.ts', tmpl['index'].format(**ctx), dry_run, verbose)

    print(f"\nGenerated {comp_type} '{pascal}' in {comp_dir}")
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Scaffold React/Next.js components.')
    p.add_argument('name', help='Component name (PascalCase or kebab-case)')
    p.add_argument('--dir',     default='src/components', help='Output base directory')
    p.add_argument('--type',    default='fc',
                   choices=['fc', 'page', 'layout', 'hook', 'context'])
    p.add_argument('--style',   default='tailwind',
                   choices=['tailwind', 'css-module', 'styled'])
    p.add_argument('--story',   action='store_true')
    p.add_argument('--test',    action='store_true')
    p.add_argument('--no-index', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('-v', '--verbose', action='store_true')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return generate(
        name=args.name,
        out_dir=Path(args.dir),
        comp_type=args.type,
        style=args.style,
        story=args.story,
        test=args.test,
        no_index=args.no_index,
        dry_run=args.dry_run,
        verbose=args.verbose,
    )


if __name__ == '__main__':
    sys.exit(main())
