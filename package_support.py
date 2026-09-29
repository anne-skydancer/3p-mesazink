"""Shared deterministic configuration and validated package assembly."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid

ROOT = Path(__file__).resolve().parent
MESA_REVISION = "4c18bbc63765c2f468c3fa094242e8654e78d196"
MESA_VERSION = "26.3.0-devel"
PACKAGE_VERSION = "26.3.0-devel-git.4c18bbc637-pkg1"
PATCHES = [ROOT / 'patches' / name for name in (
    'mesa-zink-null-guards.patch', 'mesa-msvc-release.patch', 'mesa-wgl-loader-init.patch')]
MARKER = 'assembly-complete.json'
PROVENANCE = 'package-provenance.json'


def sha256(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def source_hash(path):
    # Git may check text out as CRLF on Windows. Recipe/patch identity must
    # describe the same source on both platforms, not checkout line endings.
    return hashlib.sha256(Path(path).read_text(encoding='utf-8').encode('utf-8')).hexdigest()


def capture(command):
    return subprocess.check_output(command, text=True, stderr=subprocess.STDOUT).strip()


def recipe_identity():
    names = ['build.py', 'build_linux.py', 'package_support.py', 'autobuild.xml']
    hashes = {n: source_hash(ROOT / n) for n in names}
    return hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()


def toolchain_identity():
    identity = {'platform': sys.platform, 'machine': platform.machine(),
                'environment': {k: os.environ.get(k, '') for k in
                    ('CC', 'CXX', 'VSINSTALLDIR', 'VCToolsVersion')}}
    if sys.platform == 'win32':
        vswhere = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
        installations = json.loads(capture([str(vswhere), '-latest', '-products', '*',
            '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-format', 'json']))
        if not installations:
            raise RuntimeError('Visual Studio C++ toolchain is required')
        install = installations[0]
        base = Path(install['installationPath'])
        version = (base / 'VC/Auxiliary/Build/Microsoft.VCToolsVersion.default.txt').read_text().strip()
        compiler = base / 'VC/Tools/MSVC' / version / 'bin/Hostx64/x64/cl.exe'
        identity.update(installation=install['installationPath'], version=version,
                        compiler_sha256=sha256(compiler))
    else:
        compiler = os.environ.get('CC', 'cc')
        identity.update(compiler=shutil.which(compiler), version=capture([compiler, '--version']))
    return identity


def build_directory(source, name, toolchain):
    # Incompatible source/compiler identities get a separate directory. Options
    # are deliberately excluded: compatible builds are explicitly reconfigured.
    identity = {'revision': MESA_REVISION, 'patches': {p.name: source_hash(p) for p in PATCHES},
                'toolchain': toolchain}
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]
    return source / (name + '-' + digest)


def configure(source, build, options, run):
    meson = [sys.executable, '-m', 'mesonbuild.mesonmain']
    run(meson + ['setup'] + (['--reconfigure'] if (build / 'build.ninja').exists() else [])
        + [str(build), str(source)] + options)
    effective = json.loads(capture(meson + ['introspect', '--buildoptions', str(build)]))
    values = {o['name']: o['value'] for o in effective}
    requested = {}
    for option in options:
        if option.startswith('-D'):
            key, value = option[2:].split('=', 1)
        elif option.startswith('--prefix=') or option.startswith('--libdir='):
            key, value = option[2:].split('=', 1)
        else:
            continue
        requested[key] = value
        actual = values.get(key)
        if actual is None and key == 'zlib:default_library' and value == 'static':
            # Meson does not expose subproject builtin default_library in
            # --buildoptions. Check the generated library target instead.
            targets = json.loads(capture(meson + ['introspect', '--targets', str(build)]))
            libraries = [t['type'] for t in targets if t.get('subproject') == 'zlib'
                         and t['type'] in ('static library', 'shared library')]
            if not libraries or any(t != 'static library' for t in libraries):
                raise RuntimeError('Cannot confirm a static zlib subproject')
            actual = values[key] = 'static'
        expected = value.split(',') if isinstance(actual, list) and value else ([] if isinstance(actual, list) else value)
        if isinstance(actual, bool): expected = value.lower() == 'true'
        if actual != expected:
            raise RuntimeError(f'Meson option mismatch: {key}: requested {value!r}, effective {actual!r}')
    return {'requested': requested, 'effective': values}


def begin(out):
    out.mkdir(parents=True, exist_ok=True)
    (out / MARKER).unlink(missing_ok=True)


def validate_windows_payload(stage):
    import ctypes
    import struct
    system = ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(system, len(system)):
        raise RuntimeError('Cannot locate Windows system directory')
    reports = {}
    for dll in (stage / 'bin/release').glob('*.dll'):
        data = dll.read_bytes()
        pe = struct.unpack_from('<I', data, 0x3c)[0]
        if data[:2] != b'MZ' or data[pe:pe+4] != b'PE\0\0' or struct.unpack_from('<H',data,pe+4)[0] != 0x8664:
            raise RuntimeError(f'Not a Windows x86-64 DLL: {dll}')
        count = struct.unpack_from('<H',data,pe+6)[0]
        opt_size = struct.unpack_from('<H',data,pe+20)[0]
        opt = pe + 24
        if struct.unpack_from('<H',data,opt)[0] != 0x20b: raise RuntimeError('Expected PE32+')
        sections = []
        for n in range(count):
            offset = opt + opt_size + 40*n
            size, va, raw_size, raw = struct.unpack_from('<IIII',data,offset+8)
            sections.append((va, max(size,raw_size), raw))
        def file_offset(rva):
            for va,size,raw in sections:
                if va <= rva < va+size: return raw + rva-va
            raise RuntimeError('Import RVA outside image sections')
        imports=[]
        rva = struct.unpack_from('<I',data,opt+120)[0]
        if rva:
            offset=file_offset(rva)
            while any(data[offset:offset+20]):
                name_rva=struct.unpack_from('<I',data,offset+12)[0]
                start=file_offset(name_rva);end=data.index(b'\0',start)
                name=data[start:end].decode('ascii');imports.append(name)
                if not name.lower().startswith(('api-ms-win-', 'ext-ms-win-')) and not any(
                    (folder/name).is_file() for folder in (dll.parent,Path(system.value))):
                    raise RuntimeError(f'Missing runtime import {name} needed by {dll.name}')
                offset+=20
        reports[dll.name]=imports
    return reports


def assemble(out, artifacts, configuration, toolchain, relocate=None):
    """Artifacts are (source, relative payload path); commit marker is written last."""
    begin(out)
    with tempfile.TemporaryDirectory(prefix='mesazink-assembly-', dir=out.parent) as tmp:
        stage = Path(tmp)
        source_hashes = {}
        for src, relative in artifacts:
            src, relative = Path(src), Path(relative)
            if relative.is_absolute() or '..' in relative.parts:
                raise ValueError('Payload path escapes assembly')
            if not src.is_file(): raise RuntimeError(f'Missing build artifact: {src}')
            dest = stage / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
            source_hashes[relative.as_posix()] = sha256(src)
        if relocate: relocate(stage)
        dependencies = validate_windows_payload(stage) if sys.platform == 'win32' and any(
            relative.as_posix().endswith('/opengl32.dll') for _, relative in
            [(src, Path(relative)) for src, relative in artifacts]) else {}
        (stage / 'VERSION.txt').write_text(PACKAGE_VERSION + '\n', encoding='utf-8')
        payload = {p.relative_to(stage).as_posix(): sha256(p) for p in stage.rglob('*') if p.is_file()}
        provenance = {'schema': 1, 'generation': uuid.uuid4().hex,
            'version': PACKAGE_VERSION, 'revision': MESA_REVISION,
            'patches': {p.name: source_hash(p) for p in PATCHES},
            'recipe': recipe_identity(), 'platform': sys.platform,
            'toolchain': toolchain, 'configuration': configuration, 'runtime_imports': dependencies,
            'tools': {'python': sys.version, 'meson': capture([sys.executable, '-m', 'mesonbuild.mesonmain', '--version']),
                      'ninja': capture(['ninja', '--version'])},
            'source_hashes': source_hashes, 'payload': payload}
        (stage / PROVENANCE).write_text(json.dumps(provenance, indent=2, sort_keys=True) + '\n')
        marker = {'generation': provenance['generation'], 'provenance_sha256': sha256(stage / PROVENANCE)}
        # Individual replacements are atomic; the absent marker prevents a
        # partially replaced generation from being accepted as a package.
        for src in stage.rglob('*'):
            if src.is_file():
                dest = out / src.relative_to(stage)
                dest.parent.mkdir(parents=True, exist_ok=True)
                os.replace(src, dest)
        marker_tmp = out / (MARKER + '.tmp')
        marker_tmp.write_text(json.dumps(marker))
        os.replace(marker_tmp, out / MARKER)
    try:
        verify(out)
    except Exception:
        (out / MARKER).unlink(missing_ok=True)
        raise


def verify(out):
    marker = json.loads((out / MARKER).read_text())
    if sha256(out / PROVENANCE) != marker['provenance_sha256']:
        raise RuntimeError('Assembly provenance mismatch')
    provenance = json.loads((out / PROVENANCE).read_text())
    if marker['generation'] != provenance['generation']:
        raise RuntimeError('Mixed assembly generations')
    for relative, digest in provenance['payload'].items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts: raise ValueError('Unsafe payload path')
        if sha256(out / path) != digest: raise RuntimeError(f'Payload mismatch: {relative}')
    return provenance


def verify_archive(archive):
    """Check the exact release payload without extracting untrusted member paths."""
    import tarfile
    import zstandard
    hashes, documents = {}, {}
    with Path(archive).open('rb') as raw, zstandard.ZstdDecompressor().stream_reader(raw) as stream:
        with tarfile.open(fileobj=stream, mode='r|') as tar:
            for member in tar:
                name = member.name
                while name.startswith('./'): name = name[2:]
                path = Path(name)
                if path.is_absolute() or '..' in path.parts or member.issym() or member.islnk():
                    raise ValueError('Unsafe archive member: ' + name)
                if member.isdir(): continue
                if not member.isfile() or name in hashes: raise ValueError('Invalid archive member: ' + name)
                f = tar.extractfile(member)
                if name in (MARKER, PROVENANCE):
                    data = f.read(4 * 1024 * 1024 + 1)
                    if len(data) > 4 * 1024 * 1024: raise ValueError('Oversized provenance')
                    documents[name] = json.loads(data)
                    hashes[name] = hashlib.sha256(data).hexdigest()
                else:
                    hashes[name] = hashlib.file_digest(f, 'sha256').hexdigest()
    marker, provenance = documents[MARKER], documents[PROVENANCE]
    if marker['generation'] != provenance['generation'] or marker['provenance_sha256'] != hashes[PROVENANCE]:
        raise RuntimeError('Archive generation mismatch')
    for name, digest in provenance['payload'].items():
        if hashes.get(name) != digest: raise RuntimeError('Archive payload mismatch: ' + name)
    # Autobuild may include its own metadata; never accept extra runtime files.
    allowed = set(provenance['payload']) | {MARKER, PROVENANCE, 'autobuild-package.xml'}
    if set(hashes) - allowed: raise RuntimeError('Unexpected archive payload: ' + str(set(hashes)-allowed))
    return provenance


def verify_pair(archives):
    packages = [verify_archive(p) for p in archives]
    if len(packages) != 2 or {p['platform'] for p in packages} != {'win32','linux'}:
        raise RuntimeError('Need exactly one successful Windows and Linux package')
    for key in ('version','revision','patches','recipe'):
        if packages[0][key] != packages[1][key]: raise RuntimeError('Platform identity mismatch: ' + key)
    if packages[0]['version'] != PACKAGE_VERSION or packages[0]['recipe'] != recipe_identity():
        raise RuntimeError('Packages were not built with this recipe')
    return packages


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='store_true')
    parser.add_argument('--verify', type=Path)
    parser.add_argument('--archives', nargs='+', type=Path)
    args = parser.parse_args()
    if args.version: print(PACKAGE_VERSION)
    if args.verify: print(json.dumps(verify(args.verify), indent=2))
    if args.archives: verify_pair(args.archives)
