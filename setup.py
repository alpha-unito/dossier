import os
from os import path

from setuptools import setup

from dossier.version import VERSION

this_directory = path.abspath(path.dirname(__file__))
with open(path.join(this_directory, "README.md"), encoding="utf-8") as f:
    long_description = f.read()
with open(os.path.join(this_directory, "requirements.txt")) as f:
    install_requires = f.read().splitlines()

data_files = []
for (d, dirs, filenames) in os.walk(os.path.join(this_directory, 'share', 'jupyterhub')):
    rel_d = os.path.relpath(d, this_directory)
    data_files.append((rel_d, [os.path.join(rel_d, f) for f in filenames]))

setup(
    name="dossier",
    version=VERSION,
    packages=[
        "dossier",
        "dossier.auth",
        "dossier.handlers",
        "dossier.spawners"
    ],
    data_files=data_files,
    entry_points={
        'console_scripts': [
            'dossier = dossier.app:main'
        ]
    },
    url="https://github.com/alpha-unito/dossier",
    download_url="".join(["https://github.com/alpha-unito/dossier/releases"]),
    author="Iacopo Colonnelli",
    author_email="iacopo.colonnelli@unito.it",
    description="Dossier platform",
    long_description=long_description,
    long_description_content_type="text/markdown",
    install_requires=install_requires,
    python_requires=">=3.8",
    zip_safe=False,
    classifiers=[
        "Development Status :: 3 - Alpha",
        "License :: OSI Approved :: GNU Lesser General Public License v3 (LGPLv3)",
        "Intended Audience :: Science/Research",
        "Intended Audience :: Education",
        "Intended Audience :: System Administrators",
        "Operating System :: POSIX",
        "Operating System :: MacOS",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering",
        "Topic :: System :: Distributed Computing",
    ]
)
