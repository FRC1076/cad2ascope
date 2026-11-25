"""Read an Onshape URDF export (zip or folder) into a Robot plus a way to find its mesh files.

EVERY ASSUMPTION ABOUT ONSHAPE'S EXPORT FORMAT LIVES IN THIS FILE (docs/phase0-findings.md, section A).

Confirmed on manual UI exports of the 2025 and 2026 robots (Onshape 1.224, 2026-11-25):

1. The zip is a ROS package: ``<pkg>/urdf/<pkg>.urdf``, ``<pkg>/meshes/*.gltf`` (base64-embedded buffers, meters,
   materials with baseColorFactor), and ``<pkg>/launch/``. There is exactly one ``.urdf``.
2. Mesh ``filename`` values are ``package://<pkg>/meshes/<file>.gltf``, resolved from the ``<pkg>`` folder.
3. Onshape adds joints to a link named ``root`` (which is just the first instance, e.g. a game piece):
   ``fixed_node_to_root_joint`` for the grounded (Fixed) instance, ``hanging_node_to_root_joint[_N]`` for instances
   with no mates. It cuts closed loops itself and names the cut joints and helper links ``*_loop_closure*``.

Still unverified (A6): mate connectors arriving as links with no visuals, attached by a fixed joint, named after
the connector (onshape-to-robot style). ``ascope_origin``, ``cam_<NAME>`` and ``frame_<name>`` are found by link name.
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

GROUNDED_JOINT = "fixed_node_to_root_joint"
HANGING_JOINT = "hanging_node_to_root_joint"
LOOP_CLOSURE = "loop_closure"


@dataclass
class Export:
    """A parsed export. Call close() (or use as a context manager) to delete the unpacked zip."""

    robot: Robot
    urdf_path: Path
    source: Path
    sha256: str
    _tmp: Path | None = None
    _index: dict[str, list[Path]] | None = None

    def _search_root(self) -> Path:
        return (self._tmp or (self.source if self.source.is_dir() else self.urdf_path.parent)).resolve()

    def _by_name(self, name: str) -> list[Path]:
        if self._index is None:
            self._index = {}
            for q in sorted(self._search_root().rglob("*")):
                if q.is_file():
                    self._index.setdefault(q.name, []).append(q)
        return self._index.get(name, [])

    def resolve_mesh(self, filename: str) -> Path:
        """Find the file a URDF mesh ``filename`` points to. Raises CadError if it is missing."""
        base = self.urdf_path.parent
        rel = filename
        if rel.startswith("file://"):
            rel = rel[len("file://") :]
        root = self._search_root()
        tries: list[Path] = []
        if rel.startswith("package://"):
            rel = rel[len("package://") :]
            parts = PurePosixPath(rel).parts
            pkg, rest = parts[0], PurePosixPath(*parts[1:]) if len(parts) > 1 else PurePosixPath(rel)
            # ROS layout: the package folder is an ancestor of the URDF (Onshape: <pkg>/urdf/<pkg>.urdf).
            tries += [anc / rest for anc in [base, *base.parents] if anc.name == pkg]
            tries += [base / rest, base / rel]
        else:
            tries.append(base / rel)
        for p in tries:
            if ".." in PurePosixPath(rel).parts:
                break
            p = p.resolve()
            if p.is_file() and p.is_relative_to(root):
                return p
        matches = self._by_name(PurePosixPath(rel).name)
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


def onshape_notes(robot: Robot, origin_frame: str) -> list[str]:
    """Warnings about what Onshape's exporter did to the assembly's structure (assumption 3 above)."""
    notes = []
    root_kids = robot.child_joints.get(robot.root, [])
    for j in root_kids:
        if j.name != GROUNDED_JOINT:
            continue
        if origin_frame not in robot.links:
            # Without the origin we cannot tell whether the grounded part is on the drivetrain, so just name it.
            notes.append(
                f"Part {j.child!r} is the grounded (Fixed) part in Onshape. Only the drivetrain should be Fixed in the "
                "AdvantageScope export configuration; if this part is not on the drivetrain, unfix it and mate it."
            )
        elif origin_frame not in robot.subtree_links(j.child):
            notes.append(
                f"Part {j.child!r} is grounded (Fixed) in Onshape, so the export bolts it to the robot base and ignores "
                "its mates. Anything mounted on it will not move with a mechanism. In the AdvantageScope export "
                "configuration, only the drivetrain should be Fixed; unfix this part and mate it instead."
            )
    hanging = [j.child for j in root_kids if j.name.startswith(HANGING_JOINT)]
    if hanging:
        shown = ", ".join(repr(h) for h in hanging[:5]) + (" ..." if len(hanging) > 5 else "")
        notes.append(
            f"{len(hanging)} part(s) are not mated to anything ({shown}), so they stay where they were exported, "
            "attached to the robot base. Mate them in Onshape (Fastened is fine) or suppress them."
        )
    cuts = [
        name
        for name in robot.links
        if LOOP_CLOSURE in name and not robot.child_joints.get(name) and name not in (robot.root,)
    ]
    if cuts:
        notes.append(
            f"Onshape cut {len(cuts)} closed loop(s) of mates to export a tree (joints named *_loop_closure). Parts held "
            "together only through a cut will not move together. If a mechanism comes apart when it moves, fasten "
            "all but one joint of its loop in the export configuration (PLAN §4 C4)."
        )
    return notes
