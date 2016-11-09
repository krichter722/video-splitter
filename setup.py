#!/usr/bin/python
# -*- coding: utf-8 -*-

#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
#    Dieses Programm ist Freie Software: Sie können es unter den Bedingungen
#    der GNU General Public License, wie von der Free Software Foundation,
#    Version 3 der Lizenz oder (nach Ihrer Wahl) jeder neueren
#    veröffentlichten Version, weiterverbreiten und/oder modifizieren.
#
#    Dieses Programm wird in der Hoffnung, dass es nützlich sein wird, aber
#    OHNE JEDE GEWÄHRLEISTUNG, bereitgestellt; sogar ohne die implizite
#    Gewährleistung der MARKTFÄHIGKEIT oder EIGNUNG FÜR EINEN BESTIMMTEN ZWECK.
#    Siehe die GNU General Public License für weitere Details.
#
#    Sie sollten eine Kopie der GNU General Public License zusammen mit diesem
#    Programm erhalten haben. Wenn nicht, siehe <http://www.gnu.org/licenses/>.

from setuptools import setup, find_packages
from pkg_resources import parse_version
import os
import subprocess as sp
import video_splitter.video_splitter_globals as video_splitter_globals

setup(
    name = video_splitter_globals.app_name,
    version_command=('git describe --tags', "pep440-git-local"),
    packages = find_packages(),
    setup_requires = ["setuptools-version-command"],
    dependency_links = [
        "git+https://github.com/wxWidgets/Phoenix.git#egg=Phoenix"
    ],
    install_requires = ["plac>=0.9.1", "beautifulsoup4", "python-essentials",
        # "Phoenix",
        "MplayerCtrl", "cairosvg<2", # 2.x only supports python3<ref>http://cairosvg.org/</ref>
            "Send2Trash"],
    include_package_data = True,
    package_data = {
        'video_manager:main': ['resources/icons/*.svg'],
        'video_splitter:main': ['resources/icons/*.svg'],
    },
    entry_points={
        'console_scripts': [
            '%s = video_splitter.video_manager:main' % ("video-manager", ),
            '%s = video_splitter.video_splitter:main' % (video_splitter_globals.app_name, ),
        ],
    },

    # metadata for upload to PyPI
    author = "Karl-Philipp Richter",
    author_email = "krichter722@aol.de",
    url='https://github.com/krichter722/video-splitter',
    description = "An application to split video file at scenes using melt's motion_est filter",
    license = "GPLv3",
    keywords = "video-edition, automation, video-scene-split",
)

