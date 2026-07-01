from lib.Importer import Importer
from pathlib import Path

# Importer is syntactically sugar
imp = Importer()

# Requires gcc
cs_c = imp.c(str(Path(__file__).parent / "cs"))
res = cs_c.measure_context_switch(100000).to_float()
print(res)

# Requires g++/c++
cs_cpp = imp.cpp(str(Path(__file__).parent / "cs"))
res = cs_cpp.measure_context_switch(100000)
print(res)