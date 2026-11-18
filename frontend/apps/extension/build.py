"""Package the shared WebExtension for Chrome and Firefox."""

import json
from pathlib import Path
from shutil import copy2, copytree, ignore_patterns, rmtree
from subprocess import run
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

APP = Path(__file__).resolve().parent
ICONS = APP.parent / "web" / "build" / "icon.iconset"
DIST = APP / "dist"


def build(browser: str, manifest: dict[str, object], source: Path) -> None:
    target = DIST / browser
    with TemporaryDirectory(dir=DIST) as directory:
        package = Path(directory) / browser
        copytree(source, package)
        icons = package / "icons"
        icons.mkdir()
        for size in (16, 32, 128):
            copy2(ICONS / f"icon_{size}x{size}.png", icons / f"{size}.png")
        (package / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

        archive = DIST / f"glean-{browser}.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED) as bundle:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    bundle.write(path, path.relative_to(package))
        if target.exists():
            rmtree(target)
        package.rename(target)
        print(archive.relative_to(APP))


if __name__ == "__main__":
    DIST.mkdir(exist_ok=True)
    manifest = json.loads((APP / "src" / "manifest.json").read_text())
    manifest["version"] = json.loads((APP.parents[2] / "package.json").read_text())["version"]
    with TemporaryDirectory() as directory:
        source = Path(directory) / "extension"
        copytree(APP / "src", source, ignore=ignore_patterns("*.ts"))
        run(
            ["pnpm", "exec", "tsc", "-p", str(APP / "tsconfig.json"), "--outDir", str(source)],
            cwd=APP.parents[1],
            check=True,
        )
        build("chrome", manifest | {"minimum_chrome_version": "123"}, source)
        build(
            "firefox",
            manifest
            | {
                "browser_specific_settings": {
                    "gecko": {
                        "id": "glean@leslieleung.github.io",
                        "strict_min_version": "140.0",
                        "data_collection_permissions": {
                            "required": ["authenticationInfo", "browsingActivity", "websiteContent"]
                        },
                    },
                    "gecko_android": {"strict_min_version": "142.0"},
                }
            },
            source,
        )
