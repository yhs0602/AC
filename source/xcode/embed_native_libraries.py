"""Bundle arm64 Homebrew dependencies without absolute Homebrew load paths."""
import os
from pathlib import Path
import shutil
import subprocess


def output(*args):
    return subprocess.check_output(args, text=True).strip()


def run(*args):
    subprocess.run(args, check=True)


app = Path(os.environ["TARGET_BUILD_DIR"]) / os.environ["WRAPPER_NAME"]
binary = app / os.environ["EXECUTABLE_PATH"].split(".app/", 1)[-1]
frameworks = app / "Contents/Frameworks"
frameworks.mkdir(parents=True, exist_ok=True)
for library in frameworks.glob("*.dylib"):
    library.unlink()
# Remove framework copies left by builds using the former Intel dependencies.
for name in ("SDL2", "SDL2_image", "Ogg", "Vorbis"):
    old = frameworks / (name + ".framework")
    if old.exists():
        shutil.rmtree(old)

# sdl2-compat loads SDL3 using dlopen("@loader_path/libSDL3.dylib"),
# so it is absent from otool's dependency list.
sdl3 = Path(os.environ["HOMEBREW_PREFIX"]) / "opt/sdl3/lib/libSDL3.dylib"
shutil.copyfile(sdl3.resolve(strict=True), frameworks / "libSDL3.dylib")
(frameworks / "libSDL3.dylib").chmod(0o755)
run("install_name_tool", "-id", "@rpath/libSDL3.dylib", str(frameworks / "libSDL3.dylib"))
pending = [binary, frameworks / "libSDL3.dylib"]
libraries = {"libSDL3.dylib": sdl3.resolve()}
visited = set()
while pending:
    current = pending.pop()
    if current in visited:
        continue
    visited.add(current)
    architectures = output("lipo", "-archs", str(current)).split()
    if "arm64" not in architectures:
        raise RuntimeError(f"Missing arm64 architecture: {current}")
    if architectures != ["arm64"]:
        raise RuntimeError(f"Expected an arm64-only binary: {current}")
    dependencies = output("otool", "-L", str(current)).splitlines()[1:]
    for line in dependencies:
        dependency = line.strip().split(" (", 1)[0]
        if dependency.startswith(("/usr/lib/", "/System/Library/")):
            continue
        if dependency.startswith("@rpath/"):
            original = Path(os.environ["HOMEBREW_PREFIX"]) / "lib" / dependency[7:]
        elif dependency.startswith("@"):
            raise RuntimeError(f"Unsupported dependency path: {dependency}")
        else:
            original = Path(dependency)
        # The first otool entry for a dylib is its own install ID.
        if current != binary and original.name == current.name:
            continue
        name = original.name
        resolved = original.resolve(strict=True)
        if name in libraries and libraries[name] != resolved:
            raise RuntimeError(f"Conflicting dependencies named {name}")
        if name not in libraries:
            libraries[name] = resolved
            destination = frameworks / name
            shutil.copyfile(resolved, destination)
            destination.chmod(0o755)
            run("install_name_tool", "-id", "@rpath/" + name, str(destination))
            pending.append(destination)
        run("install_name_tool", "-change", dependency, "@rpath/" + name, str(current))

for library in frameworks.glob("*.dylib"):
    run("codesign", "--force", "--sign", "-", str(library))
run("codesign", "--force", "--sign", "-", str(app))
print(f"Validated {len(visited)-1} arm64 libraries in {app}")
