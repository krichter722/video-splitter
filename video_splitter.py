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

import bs4
import logging
import os
import subprocess as sp
import collections
import plac
import python_essentials
import python_essentials.lib
import python_essentials.lib.os_utils as os_utils
import video_splitter_globals

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

melt_default = "melt"
melt_command_tail_default = ["f=mp4", "accodec=acc", "ab=256k", ]
recursive_default = False

# melt encode process might fail with error
# `max_analyze_duration 5000000 reached` (not yet researched whether a specific
# return code is given, so that the value can be handled automatically).
# Eventually this means a broken duration, so that increasing the value
# shouldn't help. The default seems to be 5000000.
melt_encode_analyse_duration = 50000000

__input_path_doc__ = "A file to be processed or a directory of which all contained video files will be processed (non-video files are ignored)"
__output_dir_path_doc__ = "An existing directory into which the resulting clips are copied"
__melt_doc__ = "Path to a melt binary"
__melt_command_tail_doc__ = "A string to be appended to the invokation of `melt -consumer avformat:out.avi` (where `out.avi` is contructed programmatically from `output_dir_path` and `input_path`) which allows control of output generation with the full set of melt commands and features"
__recursive_doc__ = "Scan directories recursively for files to process (be careful because you might include files you didn't want to). Has no effect when `input_path` is not a directory."

class AbstractVideoSplitter:
    """A class to maximize code reusage in video_splitter_remove_trailing_frame"""
    def __init__(self, input_path, output_dir_path, melt=melt_default, melt_command_tail=melt_command_tail_default, recursive=recursive_default):
        """
        @args input_path %(__input_path_doc__)s
        @args output_dir_path %(__output_dir_path_doc__)s
        @args melt_doc %(__melt_doc__)s
        @args melt_command_tail %(__melt_command_tail_doc__)s
        @args recursive %(__recursive_doc__)s
        """ % {"__input_path_doc__": __input_path_doc__, "__output_dir_path_doc__": __output_dir_path_doc__, "__melt_doc__": __melt_doc__, "__melt_command_tail_doc__": __melt_command_tail_doc__, "__recursive_doc__": __recursive_doc__}
        if not os.path.exists(input_path):
            raise ValueError("input_path '%s' doesn't exist" % (input_path, ))
        if not os.path.exists(output_dir_path):
            logger.info("creating non-existing output directory '%s'" % (output_dir_path, ))
            os.makedirs(output_dir_path)
        elif len(os.listdir(output_dir_path)) > 0:
            raise ValueError("output_dir_path '%s' isn't empty" % (output_dir_path, ))
        if not os.path.isdir(output_dir_path):
            raise ValueError("output_dir_path '%s' isn't a directory" % (output_dir_path, ))
        self.output_dir_path = output_dir_path
        if os.path.isfile(input_path):
            self.input_files = [input_path.decode("utf-8")] # .decode("utf-8") avoids `UnicodeDecodeError: 'ascii' codec can't decode byte 0xc2 in position 28: ordinal not in range(128)`
        elif os.path.isdir(input_path):
            if recursive is False:
                self.input_files = [os.path.join(input_path, i).decode("utf-8") for i in os.listdir(input_path)]
            else:
                self.input_files = []
                for dirpath, dirnames, filenames in os.walk(input_path):
                    self.input_files += [os.path.join(dirpath, i).decode("utf-8") for i in filenames]
                logger.debug("added %d files under '%s' recursively" % (len(self.input_files), input_path, ))
        else:
            raise AssertionError("file_name '%s' is neither file nor directory" % (file_name, ))
        # validating installation of aac audio codec (there might be other codecs available, but not figured out yet how to check their availability in melt)
        aac_binary = "aac-enc"
        if os_utils.which(aac_binary) is None:
            raise RuntimeError("The aac codec is not installed on your system (the binary '%s' is missing). Install it and try again" % (aac_binary, ))
        if os_utils.which(melt) is None:
            raise RuntimeError("The melt binary '%s' is not available. Install it and try again" % (melt, ))
        analyseplugin_binary = "/usr/bin/analyseplugin"
        applyplugin_binary = "/usr/bin/applyplugin"
        listplugin_binary = "/usr/bin/listplugins"
        if not os.path.exists(analyseplugin_binary) or not os.path.exists(applyplugin_binary) or not os.path.exists(listplugin_binary):
            raise RuntimeError("one or more of the binaries '%s', '%s' and '%s' are missing which indicates that ladspa-sdk is missing. Install it and try again." % (analyseplugin_binary, applyplugin_binary, listplugin_binary, ))
        self.melt = melt
        self.melt_command_tail = melt_command_tail

class VideoSplitter(AbstractVideoSplitter):
    def __init__(self, input_path, output_dir_path, melt=melt_default, melt_command_tail=melt_command_tail_default, recursive=recursive_default):
        AbstractVideoSplitter.__init__(self, input_path, output_dir_path, melt, melt_command_tail, recursive)

    def split(self):
        for input_file in self.input_files:
            video_file_extension = retrieve_file_extension(input_file)
            if not video_file_extension in video_splitter_globals.video_file_extensions:
                logger.debug("skipping non-video file '%s' based on extension" % (input_file, ))
                continue
            split_filter_name = "motion_est" # in case mlt has not been configured with the `enable-gpl` flag at build time, the `motion_est` filter is not available, but the invokation succeeds nevertheless (the XML result is missing a filter section which is much more difficult to recognize than simply letting the script fail if the filter isn't present (which is tested with the following statement(s) and has been requested to be improved as https://sourceforge.net/p/mlt/bugs/222/)
            melt_filter_test_process_output = sp.check_output([self.melt, "-query", "\"filter\"", ])
            melt_filters = [i.strip(" -") for i in melt_filter_test_process_output.split("\n")]
            if not split_filter_name in melt_filters:
                raise RuntimeError("The melt binary '%s' can't use the filter '%s' which is used for scene splitting. Correct your melt installation by making the filter available (configure the build with `--enable-gpl` or check with the package maintainer(s) of your system) and ensure that the filter is available with `melt -query \"filter\" | grep %s`. Then run the script agin." % (melt, split_filter_name, split_filter_name, ))
            melt_process_cmds = [self.melt, input_file, "-attach", "motion_est", "-consumer", "xml", "all=1", ]
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
                start = str(int(frames.popleft())-1) # don't let the last and the first frame overlap
                output_file_path = "%s.avi" % (os.path.join(self.output_dir_path, "%s-%s-%s" % (os.path.basename(input_file), last_start, start)), )
                melt_encode_cmds = [self.melt, input_file, "in=%s" % (last_start, ), "out=%s" % (start, ), "analyzeduration", str(melt_encode_analyse_duration), "-consumer", "avformat:%s" % (output_file_path, ), ]+self.melt_command_tail
                logger.debug("creating clip from scene from frame %s to frame %s as '%s' with %s" % (last_start, start, output_file_path, str(melt_encode_cmds)))
                melt_encode_process = sp.Popen(melt_encode_cmds, stdout=sp.PIPE, stderr=sp.PIPE)
                melt_encode_process_stderr = melt_encode_process.communicate()[1] # rather than Popen.wait use Popen.communicate to suppress output and only display it if an error occured; naively assume that only stderr is interesting; naively assume that the outupt of `melt` won't fill up memory (use a temporary file if that becomes an issue)
                if melt_encode_process.returncode != 0:
                    raise RuntimeError("melt process failed with returncode %d and output:\n%s" % (melt_encode_process.returncode, melt_encode_process_stderr, ))
                last_start = start

def retrieve_file_extension(file_name):
    video_file_extension = file_name.split(".")[-1]
    return video_file_extension

@plac.annotations(
    input_path=(__input_path_doc__),
    output_dir_path=(__output_dir_path_doc__),
    melt=(__melt_doc__),
    melt_command_tail=(__melt_command_tail_doc__),
    recursive=(__recursive_doc__, "flag"),
    version=(video_splitter_globals.__version_doc__, "flag"),
    debug=(video_splitter_globals.__debug_doc__, "flag"),
)
def __main_delegate__(input_path, output_dir_path, melt=melt_default, melt_command_tail=melt_command_tail_default, recursive=recursive_default, version=False, debug=False):
    """
    video_splitter serves to split videos based on automatic scene recognition. It uses `melt`s `motion_est` filter to determine frames in a video file which represent scene changes and creates a new video file from the beginning to the end of the scene ("output") which is stored into a configurable locaction (see `output_dir_path`). It processes `file_name` if it denotes an existing file or if it is a directory all files in it. The generation of the output is produced by `melt` and is fully configurable with the `melt_command_tail` argument."""
    if version is True:
        print(video_splitter_globals.app_version_string)
        return
    if debug is True:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
    videoSplitter = VideoSplitter(input_path, output_dir_path, melt, melt_command_tail, recursive)
    videoSplitter.split()

def main():
    plac.call(__main_delegate__)

if __name__ == "__main__":
    main()

