import ctypes
import pathlib
import subprocess
import hashlib
import json
import platform
import sys
import importlib.util
import sysconfig
import shutil
from datetime import datetime
from typing import Callable, Any, Tuple

# Only used for C methods
class LazyCall:
    def __init__(self, func: Callable[..., Any], args: Tuple[Any, ...]) -> None:
        self.func = func
        self.args = args

    # Calls C function lazily and returns string
    def to_str(self) -> str:
        self.func.restype = ctypes.c_char_p
        res = self.func(*self.__convert_args())
        return res.decode() if res else ""

    # Calls C function lazily and returns int
    def to_int(self) -> int:
        self.func.restype = ctypes.c_int
        return self.func(*self.__convert_args())

    # Calls C function lazily and returns float
    def to_float(self) -> float:
        self.func.restype = ctypes.c_double
        return self.func(*self.__convert_args())

    # Calls C function lazily and returns a list
    def to_list(self, length: int, element_type: type = int) -> list:
        if element_type == int:
            array_type = ctypes.POINTER(ctypes.c_int)
            self.func.restype = array_type
            result = self.func(*self.__convert_args())
            return [result[i] for i in range(length)]
        elif element_type == float:
            array_type = ctypes.POINTER(ctypes.c_double)
            self.func.restype = array_type
            result = self.func(*self.__convert_args())
            return [result[i] for i in range(length)]
        elif element_type == str:
            array_type = ctypes.POINTER(ctypes.c_char_p)
            self.func.restype = array_type
            result = self.func(*self.__convert_args())
            return [result[i].decode() if result[i] else "" for i in range(length)]
        else:
            raise ValueError(f"Unsupported element type: {element_type}")

    # Convert arguments to C types
    def __convert_args(self):
        out = []
        for a in self.args:
            if isinstance(a, str):
                out.append(ctypes.c_char_p(a.encode()))
            elif isinstance(a, int):
                out.append(ctypes.c_int(a))
            elif isinstance(a, float):
                out.append(ctypes.c_double(a))
            else:
                out.append(a)
        return out

# Only used for C methods
class FunctionWrapper:
    def __init__(self, lib: ctypes.CDLL, name: str) -> None:
        self._lib = lib
        self._name = name

    # Prepares lazy function calls
    def __call__(self, *args) -> LazyCall:
        func = getattr(self._lib, self._name)
        return LazyCall(func, args)

# Only used for C libs
class LibWrapper:
    def __init__(self, lib: ctypes.CDLL) -> None:
        self._lib = lib

    # Exposes all C functions within the pylib
    def __getattr__(self, name: str) -> FunctionWrapper:
        return FunctionWrapper(self._lib, name)

# Load C libs or Cpp classes
class Importer:
    def __init__(self) -> None:
        self.build_dir = pathlib.Path(".build")
        self.build_dir.mkdir(exist_ok=True)
        self.ext_suffix = sysconfig.get_config_var("EXT_SUFFIX") or sysconfig.get_config_var("SO")

    # Loads a Cpp class
    def cpp(self, path: str):
        src = pathlib.Path(path).with_suffix(".cpp")
        if not src.exists():
            raise FileNotFoundError(src)
        out = self.build_dir / f"{src.stem}_cpp"

        if self.__needs_rebuild(src, out):
            target = self.__build_cpp(src, out)
        else:
            target = str(out) + ".so"

        spec = importlib.util.spec_from_file_location(src.stem, target)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[src.stem] = mod
        spec.loader.exec_module(mod)
        return mod

    # Loads a C pylib
    def c(self, path: str) -> LibWrapper:
        src = pathlib.Path(path).with_suffix(".c")
        if not src.exists():
            raise FileNotFoundError(src)
        out = self.build_dir / f"{src.stem}_c"
        if self.__needs_rebuild(src, out):
            self.__build_c(src, out)
        lib = ctypes.CDLL(str(out) + ".so")
        return LibWrapper(lib)

    @staticmethod
    def __create_hash(path: pathlib.Path) -> str:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def __info_path(target: pathlib.Path) -> pathlib.Path:
        return target.with_suffix(target.suffix + ".buildinfo")

    @staticmethod
    def __load_info(info_path: pathlib.Path):
        if info_path.exists():
            with open(info_path, "r") as f:
                return json.load(f)
        return None

    def __write_info(self, info_path: pathlib.Path, src: pathlib.Path, out: pathlib.Path) -> None:
        data = {
            "os": platform.system(),
            "build_date": datetime.now().isoformat(),
            "src": str(src),
            "out": str(out),
            "src_hash": self.__create_hash(src),
        }
        with open(info_path, "w") as f:
            json.dump(data, f, indent=2)

    def __needs_rebuild(self, src: pathlib.Path, out: pathlib.Path) -> bool:
        info = self.__load_info(self.__info_path(out))
        final_out = pathlib.Path(str(out) + ".so")
        if not info or not final_out.exists():
            return True
        try:
            return info.get("src_hash") != self.__create_hash(src)
        except FileNotFoundError:
            return True

    def __build_cpp(self, src: pathlib.Path, out: pathlib.Path) -> str:
        includes = (subprocess.check_output(["python3", "-m", "pybind11", "--includes"]).decode().strip().split())

        built_temp = str(out) + self.ext_suffix
        final_path = str(out) + ".so"

        subprocess.run(["c++", "-O3", "-shared", "-fPIC", "-std=c++17", *includes, str(src), "-o", built_temp], check=True)

        shutil.move(built_temp, final_path)
        self.__write_info(self.__info_path(out), src, out)
        return final_path

    def __build_c(self, src: pathlib.Path, out: pathlib.Path) -> None:
        final_path = str(out) + ".so"
        subprocess.run(["gcc", "-O3", "-shared", "-fPIC", "-std=c11", str(src), "-o", final_path], check=True)
        self.__write_info(self.__info_path(out), src, out)
