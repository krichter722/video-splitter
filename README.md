# video-splitter
A command line tool for automated video splitting. You can e.g. specify a file and an output directory and the script will use the `melt` command to search for scene changes and create a video file for the video part between each scene split (and the start and the end, of course). You might as well specify a directory to take input files from and let the script split thousands of file over night.

## Usage 
Invoke `python video_splitter.py -h` for usage information.

## Prerequisties
Run after making sure `pip` is installed (e.g. with `sudo apt-get install python-pip` on Ubuntu 14.10)

    sudo pip install beautifulsoup4
    sudo pip install plac

