from setuptools import setup

setup(
  name = 'tcore',
  version = '0.0.1',
  description = 'theCore C++ embedded framework CLI tools',
  author = 'Max Payne',
  author_email = 'forgge@gmail.com',
  url = 'https://github.com/theCore-embedded/tcore_cli',
  download_url = 'https://github.com/theCore-embedded/tcore_cli/archive/0.0.1.tar.gz',
  keywords = ['embedded', 'cpp', 'c++', 'the_core'],
  classifiers = [],
  install_requires = [ 'tabulate', 'requests', 'coloredlogs' ],
)