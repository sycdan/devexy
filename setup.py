from pathlib import Path

from setuptools import find_packages, setup

from devexy.constants import APP_NAME, APP_VERSION

setup(
  name=APP_NAME,
  version=APP_VERSION,
  packages=find_packages(),
  install_requires=Path("requirements.txt").read_text().splitlines(),
  entry_points={
    "console_scripts": [
      "dev=devexy.main:app",
    ],
  },
  classifiers=[
    "Programming Language :: Python :: 3",
    "Operating System :: OS Independent",
  ],
  python_requires=">=3.7",
)
