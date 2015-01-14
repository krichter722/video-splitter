#!/usr/bin/python

import bs4
import logging
import os
import subprocess as sp
import collections
import plac

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

melt_default = "melt"

@plac.annotations(
    input_path=("A file to be processed or a directory of which all contained video files will be processed (non-video files are ignored)"), 
    output_dir_path=("An existing directory into which the resulting clips are copied"), 
    melt=("Path to a melt binary"), 
    version=("Print information about the version of the software to stdout and exit", "flag"), 
    debug=("Enable debugging messages", "flag"), 
)
def video_splitter(input_path, output_dir_path, melt=melt_default, version=False, debug=False):
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
    
    for input_file in input_files:
        if not input_file.endswith(".flv") and not input_file.endswith(".mp4"):
            logger.debug("skipping non-video file '%s' based on extension" % (input_file, ))
            continue
        melt_process_cmds = [melt, input_file, "-attach", "motion_est", "-consumer", "xml", "all=1", ]
        logger.info("finding scene split markers for file '%s' with %s" % (input_file, str([melt_process_cmds])))
        melt_process = sp.Popen(melt_process_cmds, stdout=sp.PIPE, stderr=open(os.devnull)) # melt writes a lot of error message about missing frames or timestamps to stderr which don't affect the clip splitting in a significant way
        melt_process_output = melt_process.communicate()[0]
        
        soup = bs4.BeautifulSoup(melt_process_output)
        soup_properties = soup.find_all("property") # <property name="shot_change_list"> is sometimes in playlist and sometimes in produces (querying all property elements is easier than understanding that)
        frames_string = None
        for soup_property in soup_properties:
            if soup_property["name"] == "shot_change_list":
                frames_string = soup_property.string
                break
        if frames_string is None:
            logger.info("no split result for '%s', skipping" % (input_file, ))
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
            logger.debug("creating clip from scene from frame %s to frame %s as '%s'" % (last_start, start, output_file_path))
            sp.check_call([melt, input_file, "in=%s" % (last_start, ), "out=%s" % (start, ), "-consumer", "avformat:%s" % (output_file_path, ), 
                # encoding parameters
                #"-profile", "hdv_720_25p", no sound
                # "r=30", "s=640x360", "f=mp4", "acodec=aac", "ab=128k", "ar=48000", "vcodec=libx264", "b=1000k", "an=1", no sound
                # "acodec=libmp3lame", "vcodec=libx264" not sufficient
            ], stderr=open(os.devnull))
            last_start = start

if __name__ == "__main__":
    plac.call(video_splitter)

