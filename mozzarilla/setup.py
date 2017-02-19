#!/usr/bin/env python
from os.path import dirname, join
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

curr_dir = dirname(__file__)

#               YYYY.MM.DD
release_date = "2017.02.15"
version = (0, 9, 3)

try:
    long_desc = open(join(curr_dir, "readme.md")).read()
except Exception:
    long_desc = ''

setup(
    name='mozzarilla',
    description='',
    long_description=long_desc,
    version='0.9.3',
    url='http://bitbucket.org/moses_of_egypt/mozzarilla',
    author='Devin Bobadilla',
    author_email='MosesBobadilla@gmail.com',
    license='MIT',
    packages=[
        'mozzarilla',
        ],
    package_data={
        '': ['*.txt', '*.md', '*.rst'],
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
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        ],
    zip_safe=False,
    )
