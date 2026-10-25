"""Build Vite and publish its output to Vercel's native static CDN directory."""
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def publish_static(dist: Path, public: Path):
    """Validate before replacing generated public; retain dist for FastAPI routes."""
    if not (dist / 'index.html').is_file():
        raise ValueError('Vite build must contain index.html')
    reserved = {'api', 'docs', 'redoc', 'openapi.json'}
    private_suffixes = {'.py', '.pyc', '.db', '.sqlite', '.sqlite3', '.sql', '.dump', '.pem', '.key'}
    for path in dist.rglob('*'):
        relative = path.relative_to(dist)
        if (path.is_symlink() or relative.parts[0] in reserved
                or any(part.startswith('.') for part in relative.parts)
                or path.suffix.lower() in private_suffixes):
            raise ValueError(f'Unsafe or reserved static output: {relative}')
    if public.exists():
        shutil.rmtree(public)
    shutil.copytree(dist, public)


def main():
    subprocess.run(['npm', 'ci', '--prefix', 'frontend', '--include=dev', '--no-audit', '--no-fund'], cwd=ROOT, check=True)
    subprocess.run(['npm', 'run', 'build', '--prefix', 'frontend'], cwd=ROOT, check=True)
    publish_static(ROOT / 'frontend/dist', ROOT / 'public')
    # CLI 65's native Python builder excludes public/ from its function bundle
    # but does not collect it into CDN output. Emit that standard Build Output
    # directory explicitly while leaving native function generation to Vercel.
    publish_static(ROOT / 'public', ROOT / '.vercel/output/static')
    print('Vite output copied to public/ and .vercel/output/static; frontend/dist retained for SPA fallback.')


if __name__ == '__main__':
    main()
