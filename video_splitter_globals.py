#!/usr/bin/python

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
