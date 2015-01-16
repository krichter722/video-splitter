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

import subprocess as sp
from pkg_resources import parse_version

git_default = "git"

def __app_version__(git=git_default, ):
    """Retrieves the version in form of a `StrictVersion` object from git by checking it HEAD is tagged and then returns the tag name or the output of `git describe --tags` otherwise. Uses `git` as git binary. See [PEP 386][1] for an overview over the quite smart attempt to deal with the version mess in this world - gently speaking.
    
    [1]:https://www.python.org/dev/peps/pep-0386/"""
    try:
        ret_value = parse_version(sp.check_output([git, "describe", "--tags", ]).strip())
        return ret_value
    except sp.CalledProcessError:
        ret_value = parse_version(sp.check_output([git, "describe", "--tags", "--long", ]).strip())
        return ret_value

app_name = "video-splitter"
app_version = __app_version__()
app_version_string = str(app_version)
