
import setuptools

with open("README.md", "r") as f:
  long_description = f.read()

setuptools.setup(
  name="overboard",
  version="0.4.1",
  author="Joao Henriques",
  description="Pure Python dashboard for monitoring deep learning experiments",
  long_description=long_description,
  long_description_content_type="text/markdown",
  url="https://github.com/jotaf98/overboard",
  packages=setuptools.find_packages(),
  package_data={'overboard': ['style.qss']},
  include_package_data=True,
  classifiers=[
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Operating System :: OS Independent",
  ],
)
