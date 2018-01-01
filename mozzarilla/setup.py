#!/usr/bin/env python
from os.path import dirname, join
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

curr_dir = dirname(__file__)

#               YYYY.MM.DD
release_date = "2018.01.01"
version = (1, 1, 8)  # DONT FORGET TO UPDATE THE VERSION IN app_window.py

try:
    try:
        long_desc = open(join(curr_dir, "readme.rst")).read()
    except Exception:
        long_desc = open(join(curr_dir, "readme.md")).read()
except Exception:
    long_desc = 'Could not read long description from readme.'

setup(
    name='mozzarilla',
    description='A variant of Binilla for editing binary structures for \
games built with the Blam engine.',
    long_description=long_desc,
    version='%s.%s.%s' % version,
    url='http://bitbucket.org/moses_of_egypt/mozzarilla',
    author='Devin Bobadilla',
    author_email='MosesBobadilla@gmail.com',
    license='MIT',
    packages=[
        'mozzarilla',
        'mozzarilla.tools',
        ],
    package_data={
        '': ['*.txt', '*.md', '*.rst', '*.pyw'],
        'mozzarilla': [
            'styles/*.*',
            ]
        },
    platforms=["POSIX", "Windows"],
    keywords="binilla, binary, data structure",
    install_requires=['reclaimer', 'binilla'],
    requires=['reclaimer', 'binilla'],
    provides=['mozzarilla'],
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        ],
    zip_safe=False,
    )
