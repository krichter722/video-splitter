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

import plac
import video_splitter
import subprocess as sp
import bs4
import os
import tempfile

class VideoSplitterRemoveTrailingFrame(video_splitter.AbstractVideoSplitter):
    def __init__(self, input_path, output_dir_path, melt=video_splitter.melt_default, melt_command_tail=video_splitter.melt_command_tail_default, recursive=video_splitter.recursive_default, version=False, debug=False):
        video_splitter.AbstractVideoSplitter.__init__(self, input_path, output_dir_path, melt, melt_command_tail, recursive, version, debug)

    def removeTrailingFrame(self, ):
        for input_file in self.input_files:
            melt_process_cmds = [self.melt, input_file, "-attach", "motion_est", "-consumer", "xml", "all=1", ] # scanning the whole file to retrieve an XML summary is probalby not very efficient, but it works for instance
            self.logger.debug("finding clip length of file '%s' with %s" % (input_file, str(melt_process_cmds)))
            melt_process = sp.Popen(melt_process_cmds, stdout=sp.PIPE, stderr=sp.PIPE) # melt writes a lot of error message about missing frames or timestamps to stderr which don't affect the clip splitting in a significant way
            melt_process_output_tuple = melt_process.communicate()
            melt_process_output = melt_process_output_tuple[0]
            if not melt_process.returncode == 0:
                melt_process_output_stderr = melt_process_output_tuple[1]
                self.logger.error("melt process failed with output '%s', skipping input file" % (melt_process_output_stderr, ))
                continue

            soup = bs4.BeautifulSoup(melt_process_output, "lxml")
            soup_producers = soup.find_all("producer")
            if len(soup_producers) != 1:
                raise AssertionError("melt XML output contains more than one or no producer elements, can't proceed, skipping")
            soup_producer = soup_producers[0]
            frame_count = int(soup_producer["out"])
            output_file_path = os.path.join(self.output_dir_path, os.path.basename(input_file))
            new_end = frame_count-1
            melt_encode_cmds = [self.melt, input_file, "in=0", "out=%d" % (new_end, ), "-consumer", "avformat:%s" % (output_file_path, ), ]+self.melt_command_tail
            self.logger.debug("creating clip from scene from frame 0 to frame %d as '%s' with %s" % (new_end, output_file_path, str(melt_encode_cmds)))
            sp.check_call(melt_encode_cmds, stderr=open(os.devnull))

@plac.annotations(
    input_path=(video_splitter.__plac_input_path_doc__),
    output_dir_path=(video_splitter.__plac_output_dir_path_doc__),
    melt=(video_splitter.__plac_melt_doc__),
    melt_command_tail=(video_splitter.__plac_melt_command_tail_doc__),
    recursive=(video_splitter.__plac_recursive_doc__, "flag"),
    version=(video_splitter.__plac_version_doc__, "flag"),
    debug=(video_splitter.__plac_debug_doc__, "flag"),
)
def remove_trailing_frame(input_path, output_dir_path, melt=video_splitter.melt_default, melt_command_tail=video_splitter.melt_command_tail_default, recursive=video_splitter.recursive_default, version=False, debug=False):
    """Removes the trailing frame which has been added by accident in versions of video-splitter below 1.2."""
    videoSplitterRemoveTrailingFrame = VideoSplitterRemoveTrailingFrame(input_path, output_dir_path, melt, melt_command_tail, recursive, version, debug)
    videoSplitterRemoveTrailingFrame.removeTrailingFrame()

if __name__ == "__main__":
    plac.call(remove_trailing_frame)

