
import setuptools

with open("README.md", "r", encoding="utf-8") as f:
  long_description = f.read()

setuptools.setup(
  name="overboard",
  version="1.0.0",
  author="Joao Henriques",
  description="Pure Python dashboard for monitoring deep learning experiments",
  long_description=long_description,
  long_description_content_type="text/markdown",
  url="https://github.com/jotaf98/overboard",
  packages=['overboard'],
  package_data={'overboard': ['style.qss']},
  include_package_data=True,
  python_requires='>=3.6',
  install_requires=[
    'pyqt5>=5.12',
    'pyqtgraph>=0.11,<0.12',
    'pyopengl>=3.1',
    'fs>=2.4',
    'overboard_logger>=0.7.1'
  ],
  classifiers=[
    "Programming Language :: Python :: 3",
    "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    "Operating System :: OS Independent",
  ],
)
