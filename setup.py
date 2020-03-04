#!/usr/bin/env python
#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import mozzarilla

long_desc = ""
try:
    long_desc = open("README.MD").read()
except Exception:
    print("Couldn't read readme.")

setup(
    name='mozzarilla',
    description='A variant of Binilla for editing binary structures for '
                'games built with the Blam engine.',
    long_description=long_desc,
    long_description_content_type='text/markdown',
    version='%s.%s.%s' % mozzarilla.__version__,
    url=mozzarilla.__website__,
    project_urls={
        #"Documentation": <Need a string entry here>,
        "Source": mozzarilla.__website__,
        "Funding": "https://liberapay.com/MEK/",
    },
    author=mozzarilla.__author__,
    author_email='MoeMakesStuff@gmail.com',
    license='GPLv3',
    packages=[
        'mozzarilla',
        'mozzarilla.defs',
        'mozzarilla.widgets',
        'mozzarilla.widgets.field_widgets',
        'mozzarilla.windows',
        'mozzarilla.windows.tools',
        'mozzarilla.windows.tag_converters',
        ],
    package_data={
        'mozzarilla': [
            'styles/*.*', '*.[tT][xX][tT]', '*.MD', '*.pyw', '*.ico', '*.png',
            'msg.dat',
            ]
        },
    platforms=["POSIX", "Windows"],
    keywords=["binilla", "binary", "data structure"],
    install_requires=['reclaimer', 'binilla', 'arbytmap', 'supyr_struct'],
    requires=['reclaimer', 'arbytmap', 'binilla'],
    provides=['mozzarilla'],
    python_requires=">=3.5",
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: End Users/Desktop",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.5",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3 :: Only",
        ],
    zip_safe=False,
    )
