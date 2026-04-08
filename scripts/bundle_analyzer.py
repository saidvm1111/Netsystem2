#!/usr/bin/env python3
"""
Bundle Analyzer - Analyze Next.js / Vite / webpack build output for size issues.

Usage:
    python scripts/bundle_analyzer.py <project-path> [options]

Commands (default: report):
    report      Full bundle size report
    diff        Compare two build directories
    audit       Check for known large packages and duplicates
    treemap     Emit an HTML treemap visualization

Options:
    --build-dir DIR     Build output dir (default: auto-detect .next | dist | build)
    --budget-kb N       Warn when any chunk exceeds this size in KB (default: 250)
    --format FORMAT     Output: text | json | csv (default: text)
    --compare DIR       Second build directory for diff command
    --output FILE       Write report to file instead of stdout
    -v, --verbose       Show individual file breakdown
"""

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ChunkInfo:
    path:     Path
    size_b:   int
    gzip_b:   int = 0          # populated if gzip available
    chunk_id: str = ''

    @property
    def size_kb(self) -> float:
        return self.size_b / 1024

    @property
    def gzip_kb(self) -> float:
        return self.gzip_b / 1024


@dataclass
class BundleReport:
    project:    Path
    build_dir:  Path
    chunks:     List[ChunkInfo] = field(default_factory=list)
    warnings:   List[str]      = field(default_factory=list)

    @property
    def total_kb(self) -> float:
        return sum(c.size_kb for c in self.chunks)

    @property
    def total_gzip_kb(self) -> float:
        return sum(c.gzip_kb for c in self.chunks if c.gzip_kb)


# ---------------------------------------------------------------------------
# Build detection & parsing
# ---------------------------------------------------------------------------

KNOWN_BUILD_DIRS = ['.next', 'dist', 'build', 'out', '.nuxt', '.output']
JS_EXTENSIONS   = {'.js', '.mjs', '.cjs'}
CSS_EXTENSIONS  = {'.css'}

LARGE_PACKAGES = {
    'moment':            'moment@~300 kB — prefer date-fns or dayjs',
    'lodash':            'lodash@~70 kB — import individual functions or use lodash-es',
    'antd':              'antd@~2 MB — use tree-shaking or a lighter UI lib',
    'material-ui':       '@mui@~1 MB — ensure proper tree-shaking with Babel plugin',
    'react-icons/all':   'react-icons all-import — import from specific sub-packages',
    'highlight.js':      'highlight.js@~1 MB — use lighter-weight prism or dynamic import',
    'draft-js':          'draft-js@~600 kB — consider Tiptap or Lexical',
    'react-pdf':         'react-pdf@~500 kB — lazy-load with dynamic import',
    'chart.js':          'chart.js@~200 kB — lazy-load charts',
}


def detect_build_dir(project: Path) -> Optional[Path]:
    for name in KNOWN_BUILD_DIRS:
        candidate = project / name
        if candidate.is_dir():
            return candidate
    return None


def is_js_chunk(path: Path) -> bool:
    return path.suffix in JS_EXTENSIONS and not path.name.startswith('.')


def is_css_chunk(path: Path) -> bool:
    return path.suffix in CSS_EXTENSIONS


def try_gzip_size(path: Path) -> int:
    """Return gzip size in bytes, or 0 if zlib unavailable."""
    try:
        import zlib
        data = path.read_bytes()
        return len(zlib.compress(data, level=6))
    except Exception:
        return 0


def collect_chunks(build_dir: Path, verbose: bool) -> List[ChunkInfo]:
    chunks: List[ChunkInfo] = []
    for root, dirs, files in os.walk(build_dir):
        # Skip source-map-only dirs
        dirs[:] = [d for d in dirs if d not in {'server', 'cache', 'trace'}]
        for fname in files:
            fpath = Path(root) / fname
            if is_js_chunk(fpath) or is_css_chunk(fpath):
                size = fpath.stat().st_size
                gz   = try_gzip_size(fpath)
                chunk_id = str(fpath.relative_to(build_dir))
                chunks.append(ChunkInfo(path=fpath, size_b=size, gzip_b=gz, chunk_id=chunk_id))
    return sorted(chunks, key=lambda c: c.size_b, reverse=True)


def check_next_build_json(project: Path) -> Dict:
    """Parse .next/build-manifest.json for page→chunk mapping."""
    manifest = project / '.next' / 'build-manifest.json'
    if manifest.exists():
        try:
            return json.loads(manifest.read_text())
        except Exception:
            pass
    return {}


def audit_package_json(project: Path) -> List[str]:
    """Warn about known heavy dependencies."""
    pkg = project / 'package.json'
    if not pkg.exists():
        return []
    try:
        data = json.loads(pkg.read_text())
    except Exception:
        return []

    deps = {**data.get('dependencies', {}), **data.get('devDependencies', {})}
    hits = []
    for pattern, msg in LARGE_PACKAGES.items():
        if any(d == pattern or d.startswith(pattern.split('/')[0]) for d in deps):
            hits.append(f'  WARN  {msg}')
    return hits


def detect_duplicates(build_dir: Path) -> List[str]:
    """Heuristic: find modules appearing more than once across chunks (by filename stem)."""
    seen: Dict[str, List[str]] = {}
    for root, _, files in os.walk(build_dir):
        for f in files:
            if Path(f).suffix in JS_EXTENSIONS:
                stem = re.sub(r'[-.][\da-f]{8,}', '', Path(f).stem)
                seen.setdefault(stem, []).append(str(Path(root) / f))

    return [
        f'  DUP   {stem}: {len(paths)} copies'
        for stem, paths in seen.items()
        if len(paths) > 1 and stem not in {'index', 'main', 'app', 'page', 'layout'}
    ]


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def human_size(kb: float) -> str:
    if kb >= 1024:
        return f'{kb/1024:.1f} MB'
    return f'{kb:.1f} kB'


def fmt_bar(kb: float, max_kb: float, width: int = 20) -> str:
    filled = int(width * kb / max_kb) if max_kb else 0
    return '[' + '#' * filled + '.' * (width - filled) + ']'


def print_text_report(report: BundleReport, budget_kb: float, verbose: bool) -> None:
    print(f"\n{'='*60}")
    print(f"  Bundle Analysis: {report.project.name}")
    print(f"  Build dir: {report.build_dir}")
    print(f"{'='*60}")

    js_chunks  = [c for c in report.chunks if is_js_chunk(c.path)]
    css_chunks = [c for c in report.chunks if is_css_chunk(c.path)]
    max_kb = js_chunks[0].size_kb if js_chunks else 1

    print(f"\n  JavaScript ({len(js_chunks)} chunks, "
          f"total {human_size(sum(c.size_kb for c in js_chunks))})")
    for c in js_chunks[:20]:
        bar   = fmt_bar(c.size_kb, max_kb)
        gz    = f'  [{human_size(c.gzip_kb)} gz]' if c.gzip_kb else ''
        flag  = ' *** OVER BUDGET ***' if c.size_kb > budget_kb else ''
        print(f"  {bar} {human_size(c.size_kb):>10}{gz}  {c.chunk_id}{flag}")

    if css_chunks:
        print(f"\n  CSS ({len(css_chunks)} files, "
              f"total {human_size(sum(c.size_kb for c in css_chunks))})")
        for c in css_chunks[:10]:
            print(f"    {human_size(c.size_kb):>10}  {c.chunk_id}")

    print(f"\n  Total raw  : {human_size(report.total_kb)}")
    if report.total_gzip_kb:
        print(f"  Total gzip : {human_size(report.total_gzip_kb)}")

    if report.warnings:
        print(f"\n  Warnings ({len(report.warnings)})")
        for w in report.warnings:
            print(w)

    print(f"{'='*60}\n")


def print_json_report(report: BundleReport, budget_kb: float) -> None:
    data = {
        'project':    str(report.project),
        'build_dir':  str(report.build_dir),
        'total_kb':   round(report.total_kb, 2),
        'total_gzip_kb': round(report.total_gzip_kb, 2),
        'budget_kb':  budget_kb,
        'chunks': [
            {
                'id':      c.chunk_id,
                'size_kb': round(c.size_kb, 2),
                'gzip_kb': round(c.gzip_kb, 2),
                'over_budget': c.size_kb > budget_kb,
            }
            for c in report.chunks
        ],
        'warnings': report.warnings,
    }
    print(json.dumps(data, indent=2))


def print_csv_report(report: BundleReport) -> None:
    import csv, io
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['chunk_id', 'size_kb', 'gzip_kb', 'type'])
    for c in report.chunks:
        ftype = 'js' if is_js_chunk(c.path) else 'css'
        w.writerow([c.chunk_id, round(c.size_kb, 2), round(c.gzip_kb, 2), ftype])
    print(buf.getvalue(), end='')


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_report(args) -> int:
    project   = Path(args.project_path).resolve()
    build_dir = Path(args.build_dir) if args.build_dir else detect_build_dir(project)

    if not build_dir or not build_dir.is_dir():
        print(f"Build directory not found. Run your build first (npm run build).", file=sys.stderr)
        print(f"Searched: {[str(project / d) for d in KNOWN_BUILD_DIRS]}", file=sys.stderr)
        return 1

    chunks   = collect_chunks(build_dir, args.verbose)
    warnings = audit_package_json(project) + detect_duplicates(build_dir)

    report = BundleReport(project=project, build_dir=build_dir,
                          chunks=chunks, warnings=warnings)

    if args.format == 'json':
        print_json_report(report, args.budget_kb)
    elif args.format == 'csv':
        print_csv_report(report)
    else:
        print_text_report(report, args.budget_kb, args.verbose)

    over = [c for c in chunks if c.size_kb > args.budget_kb]
    return 1 if over else 0


def cmd_diff(args) -> int:
    build_a = Path(args.project_path).resolve()
    build_b = Path(args.compare).resolve()

    if not build_a.is_dir() or not build_b.is_dir():
        print('Both directories must exist for diff.', file=sys.stderr)
        return 1

    chunks_a = {c.chunk_id: c for c in collect_chunks(build_a, False)}
    chunks_b = {c.chunk_id: c for c in collect_chunks(build_b, False)}
    all_ids  = sorted(set(chunks_a) | set(chunks_b))

    print(f"\n{'Chunk':<50} {'Before':>10} {'After':>10} {'Delta':>10}")
    print('-' * 85)
    total_delta = 0.0
    for cid in all_ids:
        before = chunks_a[cid].size_kb if cid in chunks_a else 0
        after  = chunks_b[cid].size_kb if cid in chunks_b else 0
        delta  = after - before
        total_delta += delta
        flag   = ' (+)' if delta > 10 else (' (-)' if delta < -10 else '')
        print(f"  {cid:<48} {human_size(before):>10} {human_size(after):>10} "
              f"{('+' if delta>0 else '')}{human_size(abs(delta)):>9}{flag}")

    print('-' * 85)
    print(f"  {'TOTAL DELTA':<48} {'':<10} {'':<10} "
          f"{('+' if total_delta>0 else '')}{human_size(abs(total_delta)):>9}\n")
    return 0


def cmd_audit(args) -> int:
    project  = Path(args.project_path).resolve()
    warnings = audit_package_json(project)
    build_dir = detect_build_dir(project)
    if build_dir:
        warnings += detect_duplicates(build_dir)

    if warnings:
        print(f'\n{len(warnings)} issue(s) found:\n')
        for w in warnings:
            print(w)
        return 1
    print('No known issues found.')
    return 0


def cmd_treemap(args) -> int:
    project   = Path(args.project_path).resolve()
    build_dir = Path(args.build_dir) if args.build_dir else detect_build_dir(project)
    if not build_dir or not build_dir.is_dir():
        print('Build directory not found.', file=sys.stderr)
        return 1

    chunks  = collect_chunks(build_dir, False)
    out_path = Path(args.output) if args.output else Path('bundle-treemap.html')

    # Simple SVG-based treemap
    total = sum(c.size_b for c in chunks) or 1
    items = [
        {'label': c.chunk_id, 'size': c.size_b, 'pct': round(100 * c.size_b / total, 1)}
        for c in chunks[:50]
    ]
    rows = '\n'.join(
        f'<tr><td>{i["label"]}</td>'
        f'<td>{human_size(i["size"]/1024)}</td>'
        f'<td>{i["pct"]}%</td>'
        f'<td><div style="background:#4f46e5;height:14px;width:{min(i["pct"]*4,400):.0f}px"></div></td></tr>'
        for i in items
    )
    html = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>Bundle Treemap — {project.name}</title>
<style>
body{{font-family:monospace;padding:2rem;background:#f8fafc}}
h1{{color:#1e293b}}
table{{border-collapse:collapse;width:100%}}
th,td{{text-align:left;padding:4px 8px;border-bottom:1px solid #e2e8f0}}
th{{background:#f1f5f9;color:#475569}}
</style></head><body>
<h1>Bundle Report: {project.name}</h1>
<p>Total: {human_size(total/1024)} across {len(chunks)} chunks</p>
<table>
<thead><tr><th>Chunk</th><th>Size</th><th>%</th><th>Bar</th></tr></thead>
<tbody>{rows}</tbody>
</table></body></html>"""

    out_path.write_text(html)
    print(f'Treemap written to {out_path}')
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

COMMANDS = {
    'report':  cmd_report,
    'diff':    cmd_diff,
    'audit':   cmd_audit,
    'treemap': cmd_treemap,
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description='Frontend bundle analyzer.')
    p.add_argument('project_path', nargs='?', default='.', help='Project root directory')
    p.add_argument('command', nargs='?', default='report',
                   choices=list(COMMANDS), help='Command to run (default: report)')
    p.add_argument('--build-dir', default=None)
    p.add_argument('--budget-kb', type=float, default=250.0)
    p.add_argument('--format',   choices=['text', 'json', 'csv'], default='text')
    p.add_argument('--compare',  default=None, help='Second build dir for diff')
    p.add_argument('--output',   default=None, help='Output file for treemap')
    p.add_argument('-v', '--verbose', action='store_true')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    return COMMANDS[args.command](args)


if __name__ == '__main__':
    sys.exit(main())
