import os
import sys
from pathlib import Path

from setuptools import setup, Extension
from Cython.Build import cythonize


WRAPPER_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = WRAPPER_DIR.parent

INCLUDE_DIR = Path(
    os.environ.get(
        "BREEZE_INCLUDE_DIR",
        PROJECT_ROOT / "breeze_native" / "include",
    )
).resolve()

LIB_DIR = Path(
    os.environ.get(
        "BREEZE_LIB_DIR",
        PROJECT_ROOT / "breeze_native" / "lib",
    )
).resolve()


extension = Extension(
    name="breeze",
    sources=[str(WRAPPER_DIR / "breeze.pyx")],
    language="c++",
    include_dirs=[str(INCLUDE_DIR)],
    library_dirs=[str(LIB_DIR)],
    libraries=["breeze"],
    runtime_library_dirs=(
        []
        if sys.platform == "win32"
        else [str(LIB_DIR)]
    ),
)

setup(
    name="breeze-cython",
    version="0.1.0",
    ext_modules=cythonize(
        [extension],
        compiler_directives={"language_level": "3"},
    ),
    py_modules=["breeze_voice"],
)
