#!/usr/bin/python

import bs4
import logging
import os
import subprocess as sp
import collections
import plac
import python_essentials
import python_essentials.lib
import python_essentials.lib.os_utils as os_utils

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

melt_default = "melt"
melt_command_tail_default = ["f=mp4", "accodec=acc", "ab=256k", ]

@plac.annotations(
    input_path=("A file to be processed or a directory of which all contained video files will be processed (non-video files are ignored)"), 
    output_dir_path=("An existing directory into which the resulting clips are copied"), 
    melt=("Path to a melt binary"), 
    melt_command_tail=("A string to be appended to the invokation of `melt -consumer avformat:out.avi` (where `out.avi` is contructed programmatically from `output_dir_path` and `input_path`) which allows control of output generation with the full set of melt commands and features"), 
    version=("Print information about the version of the software to stdout and exit", "flag"), 
    debug=("Enable debugging messages", "flag"), 
)
def video_splitter(input_path, output_dir_path, melt=melt_default, melt_command_tail=melt_command_tail_default, version=False, debug=False):
    """Processes file_name if it denotes an existing file or if it is a directory all files in it."""
    if version is True:
        print(video_splitter_version_string)
        return
    if debug is True:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
    if not os.path.exists(input_path):
        raise ValueError("input_path '%s' doesn't exist" % (input_path, ))
    if not os.path.exists(output_dir_path):
        raise ValueError("output_dir_path '%s' doesn't exist" % (output_dir_path, ))
    if not os.path.isdir(output_dir_path):
        raise ValueError("output_dir_path '%s' isn't a directory" % (output_dir_path, ))
    if os.path.isfile(input_path):
        input_files = [input_path]
    elif os.path.isdir(input_path):
        input_files = [os.path.join(input_path, i) for i in os.listdir(input_path)]
    else:
        raise AssertionError("file_name '%s' is neither file nor directory" % (file_name, ))
    # validating installation of aac audio codec (there might be other codecs available, but not figured out yet how to check their availability in melt)
    aac_binary = "aac-enc"
    if os_utils.which(aac_binary) is None:
        raise RuntimeError("The aac codec is not installed on your system (the binary '%s' is missing). Install it and try again" % (aac_binary, ))
    
    for input_file in input_files:
        if not input_file.endswith(".flv") and not input_file.endswith(".mp4"):
            logger.debug("skipping non-video file '%s' based on extension" % (input_file, ))
            continue
        split_filter_name = "motion_est" # in case mlt has not been configured with the `enable-gpl` flag at build time, the `motion_est` filter is not available, but the invokation succeeds nevertheless (the XML result is missing a filter section which is much more difficult to recognize than simply letting the script fail if the filter isn't present (which is tested with the following statement(s) and has been requested to be improved as https://sourceforge.net/p/mlt/bugs/222/)
        melt_filter_test_process_output = sp.check_output([melt, "-query", "\"filter\"", ])
        melt_filters = [i.strip(" -") for i in melt_filter_test_process_output.split("\n")]
        if not split_filter_name in melt_filters:
            raise RuntimeError("The melt binary '%s' can't use the filter '%s' which is used for scene splitting. Correct your melt installation by making the filter available (configure the build with `--enable-gpl` or check with the package maintainer(s) of your system) and ensure that the filter is available with `melt -query \"filter\" | grep %s`. Then run the script agin." % (melt, split_filter_name, split_filter_name, ))
        melt_process_cmds = [melt, input_file, "-attach", "motion_est", "-consumer", "xml", "all=1", ]
        logger.info("finding scene split markers for file '%s' with %s" % (input_file, str(melt_process_cmds)))
        melt_process = sp.Popen(melt_process_cmds, stdout=sp.PIPE, stderr=sp.PIPE) # melt writes a lot of error message about missing frames or timestamps to stderr which don't affect the clip splitting in a significant way
        melt_process_output_tuple = melt_process.communicate()
        melt_process_output = melt_process_output_tuple[0]
        if not melt_process.returncode == 0:
            melt_process_output_stderr = melt_process_output_tuple[1]
            logger.error("melt process failed with output '%s', skipping input file" % (melt_process_output_stderr, ))
            continue
        
        soup = bs4.BeautifulSoup(melt_process_output)
        soup_properties = soup.find_all("property") # <property name="shot_change_list"> is sometimes in playlist and sometimes in produces (querying all property elements is easier than understanding that)
        frames_string = None
        for soup_property in soup_properties:
            if soup_property["name"] == "shot_change_list":
                frames_string = soup_property.string
                break
        if frames_string is None:
            logger.info("no split result for '%s', skipping (mlt source installation might cause trouble, consider running `sudo make uninstall` in source root and install ` melt` in package manager" % (input_file, ))
            continue
        frame_pairs = frames_string.split(";")
        frames = collections.deque()
        for frame_pair in frame_pairs:
            start = frame_pair.split("=")[0]
            frames.append(start)
        logger.info("split file '%s' into %d clips" % (input_file, len(frames)))
        last_start = frames.popleft()
        while len(frames) > 0:
            start = frames.popleft()
            output_file_path = "%s.avi" % (os.path.join(output_dir_path, "%s-%s-%s" % (os.path.basename(input_file), last_start, start)), )
            melt_encode_cmds = [melt, input_file, "in=%s" % (last_start, ), "out=%s" % (start, ), "-consumer", "avformat:%s" % (output_file_path, ), ]+melt_command_tail
            logger.debug("creating clip from scene from frame %s to frame %s as '%s' with %s" % (last_start, start, output_file_path, str(melt_encode_cmds)))
            sp.check_call(melt_encode_cmds, stderr=open(os.devnull))
            last_start = start

if __name__ == "__main__":
    plac.call(video_splitter)

