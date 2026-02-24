from pathlib import Path

from OCP.STEPControl import STEPControl_Reader
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib  # <-- class-based API
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer


STEP_PATH = Path(r"C:\Users\T\Desktop\L1.step")  # <-- írd át

print("Using STEP:", STEP_PATH)
print("Exists:", STEP_PATH.exists())

reader = STEPControl_Reader()
status = reader.ReadFile(str(STEP_PATH))
print("ReadFile status:", status)

if status != 1:
    raise SystemExit("STEP read failed")

reader.TransferRoots()
shape = reader.OneShape()

box = Bnd_Box()
BRepBndLib.AddOptimal_s(shape, box)

xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
dx, dy, dz = (xmax - xmin), (ymax - ymin), (zmax - zmin)
print("BBox:", dx, dy, dz)

def count_topo(shape, topabs_kind) -> int:
    exp = TopExp_Explorer(shape, topabs_kind)
    n = 0
    while exp.More():
        n += 1
        exp.Next()
    return n

faces = count_topo(shape, TopAbs_FACE)
edges = count_topo(shape, TopAbs_EDGE)
solids = count_topo(shape, TopAbs_SOLID)

print("Solids:", solids)
print("Faces:", faces)
print("Edges:", edges)