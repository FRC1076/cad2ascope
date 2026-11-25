"""Read an Onshape URDF export (zip or folder) into a Robot plus a way to find its mesh files.

EVERY ASSUMPTION ABOUT ONSHAPE'S EXPORT FORMAT LIVES IN THIS FILE. Phase 0 section A has not run yet, so these are
unverified and are the first thing to update when real exports arrive (docs/phase0-findings.md, A3 and A6):

1. The zip holds exactly one ``.urdf`` file, somewhere in it.
2. Mesh ``filename`` values are paths relative to the URDF's folder, possibly written as ``package://<name>/...``
   (ROS style). If neither resolves, a file with the same name anywhere in the export is used.
3. Mate connectors arrive as links with no visuals, attached by a fixed joint, and the link carries the connector's
   name (onshape-to-robot style). ``ascope_origin``, ``cam_<NAME>`` and ``frame_<name>`` are found by link name.
"""

from __future__ import annotations

import hashlib
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from cad2ascope.errors import CadError
from cad2ascope.urdf import Robot, parse_urdf


@dataclass
class Export:
    """A parsed export. Call close() (or use as a context manager) to delete the unpacked zip."""

    robot: Robot
    urdf_path: Path
    source: Path
    sha256: str
    _tmp: Path | None = None

    def resolve_mesh(self, filename: str) -> Path:
        """Find the file a URDF mesh ``filename`` points to. Raises CadError if it is missing."""
        base = self.urdf_path.parent
        rel = filename
        if rel.startswith("file://"):
            rel = rel[len("file://") :]
        if rel.startswith("package://"):
            rel = rel[len("package://") :]
            # Drop the package name, then try the remainder from the URDF folder.
            parts = PurePosixPath(rel).parts
            candidates = [PurePosixPath(*parts[1:]) if len(parts) > 1 else PurePosixPath(rel), PurePosixPath(rel)]
        else:
            candidates = [PurePosixPath(rel)]
        root = (self._tmp or (self.source if self.source.is_dir() else base)).resolve()
        for cand in candidates:
            if cand.is_absolute() or ".." in cand.parts:
                continue
            p = (base / cand).resolve()
            if p.is_file() and p.is_relative_to(root):
                return p
        name = PurePosixPath(rel).name
        matches = sorted(q for q in root.rglob(name) if q.is_file())
        if len(matches) == 1:
            return matches[0]
        raise CadError(
            f"The export is missing the mesh file {filename!r}. Re-export from Onshape; "
            "if you unzipped and re-zipped it by hand, zip the original download instead."
        )

    def close(self) -> None:
        if self._tmp is not None:
            shutil.rmtree(self._tmp, ignore_errors=True)
            self._tmp = None

    def __enter__(self) -> Export:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_dir():
        for p in sorted(q for q in path.rglob("*") if q.is_file()):
            h.update(str(p.relative_to(path).as_posix()).encode())
            h.update(p.read_bytes())
    else:
        h.update(path.read_bytes())
    return h.hexdigest()


def _safe_extract(zip_path: Path, dest: Path) -> None:
    try:
        with zipfile.ZipFile(zip_path) as z:
            for info in z.infolist():
                target = (dest / info.filename).resolve()
                if not target.is_relative_to(dest.resolve()):
                    raise CadError(
                        f"{zip_path.name} contains an unsafe path ({info.filename!r}). Download the export again from Onshape."
                    )
            z.extractall(dest)
    except zipfile.BadZipFile:
        raise CadError(f"{zip_path.name} is not a readable zip file. Download the export again from Onshape.") from None


def load_export(path: str | Path) -> Export:
    """Open an Onshape URDF export: a .zip, an unzipped folder, or a .urdf file next to its meshes."""
    src = Path(path)
    if not src.exists():
        raise CadError(f"Cannot find {src}. Pass the URDF zip you downloaded from Onshape.")
    tmp: Path | None = None
    if src.is_file() and src.suffix.lower() == ".zip":
        tmp = Path(tempfile.mkdtemp(prefix="cad2ascope-"))
        _safe_extract(src, tmp)
        search = tmp
    elif src.is_dir():
        search = src
    elif src.is_file() and src.suffix.lower() == ".urdf":
        search = None
    else:
        raise CadError(
            f"{src.name} is not a zip, a folder, or a .urdf file. Pass the URDF zip you downloaded from Onshape."
        )

    try:
        if search is None:
            urdf_path = src
        else:
            found = sorted(p for p in search.rglob("*.urdf") if p.is_file() and "__MACOSX" not in p.parts)
            if not found:
                raise CadError(
                    f"{src.name} has no .urdf file in it. In Onshape, export the assembly as URDF (not STEP or glTF)."
                )
            if len(found) > 1:
                names = ", ".join(p.name for p in found[:4])
                raise CadError(f"{src.name} has {len(found)} .urdf files ({names}). Export one assembly at a time.")
            urdf_path = found[0]
        robot = parse_urdf(urdf_path.read_text(encoding="utf-8"), source=urdf_path.name)
        return Export(robot, urdf_path, src, _sha256(src), tmp)
    except BaseException:
        if tmp is not None:
            shutil.rmtree(tmp, ignore_errors=True)
        raise


def frame_links(robot: Robot, prefix: str) -> list[str]:
    """Names of links that are mate-connector frames with this prefix, in tree order (assumption 3 above)."""
    order = [robot.root] + [j.child for j in robot.walk()]
    return [name for name in order if name.startswith(prefix)]
