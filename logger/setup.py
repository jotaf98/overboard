
import setuptools

with open("../README.md", "r", encoding="utf-8") as f:
  long_description = f.read()

setuptools.setup(
  name="overboard_logger",
  version="0.7.1",
  author="Joao Henriques",
  description="Stand-alone logger class for OverBoard -- Pure Python dashboard for monitoring deep learning experiments",
  long_description=long_description,
  long_description_content_type="text/markdown",
  url="https://github.com/jotaf98/overboard",
  packages=['overboard_logger'],
  classifiers=[
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Operating System :: OS Independent",
  ],
)
