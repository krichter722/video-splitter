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

# The video manager consists of a working set list (which allows adding video
# files
# from local storage) and a selection list which contains a selected items of
# the working set list. Items are moved between lists and can be in one list
# only. Items are played when the user double clicks on one of the lists. A
# button allows merging all files in the selection list to one file. Video
# files can be deleted with a menu item in the context menu of both lists.

import os
import time
import wx
import wx.media
import wx.lib.buttons as buttons
import video_splitter_globals
from pkg_resources import resource_string
import cairosvg
import StringIO
import plac
import logging
import video_splitter_globals
import video_splitter
import subprocess as sp
import shutil
import sys
import re
import send2trash
import collections
import python_essentials.lib.os_utils as os_utils
import pkg_resources

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

mp4box_default = "MP4Box"
icon_size_default = 24

# Playback is running
PLAYBACK_STATE_RUNNING = 1
# Playback was running before, but isn't currently
PLAYBACK_STATE_PAUSED = 2
# Playback has been reset to start or was never started
PLAYBACK_STATE_STOPPED = 4

def __generate_video_file_extensions_wildcard__():
    ret_value = "Video files ("
    ret_value += "*.%s" % (video_splitter_globals.video_file_extensions[0],)
    for video_file_extension in video_splitter_globals.video_file_extensions[1:]:
        ret_value += ";*.%s" % (video_file_extension,)
    ret_value += ")|"
    ret_value += "*.%s" % (video_splitter_globals.video_file_extensions[0])
    for video_file_extension in video_splitter_globals.video_file_extensions[1:]:
        ret_value += (";*.%s" % (video_file_extension,))
    return ret_value

video_file_extensions_wildcard = __generate_video_file_extensions_wildcard__()

__mp4box_doc__ = "the `mp4box` binary to use"

app_version = pkg_resources.require("video_splitter")[0].version

# internal implementation notes:
# - undoing a move to trash isn't possible with the `move2trash` and not
# supported in order to KISS (deletions are ignored in the chain of undo
# actions which turns out to be a useful feature)

class VideoManager(wx.Frame):

    def __init__(self, parent, id, title, mp4box, categories=["1", "2", "3", "4", "5","split"], input_directory=None, review_folder=None):
        """
        @args mp4box %(__mp4box_doc__)s
        """ % {"__mp4box_doc__": __mp4box_doc__}
        wx.Frame.__init__(self, parent, id, title, size=(600, 500))
        if os_utils.which(mp4box) is None:
            raise ValueError("mp4box binary '%s' not found or not executable (on Ubuntu make sure the package `gpac` is installed)" % (mp4box,))
        self.mp4box = mp4box
        self.undoStack = collections.deque() # the undo stack to track un- and
                # redoable categorization
        self.redoStack = collections.deque() # the redo stack to track un- and
                # redoable categorization
        # there's no need to manage state of redo components with a flag (they
        # only ought to be enabled if an undoing request has been processed and
        # no new categorization has been performed) because information can be
        # stored in the enabled state of the redo menu item
        mainSplitter = wx.SplitterWindow(self, wx.ID_ANY, style=wx.SP_LIVE_UPDATE)
        mainSplitter.SetMinimumPaneSize(100)
        self.listsPanel = wx.Panel(mainSplitter)
        self.videoPanel = wx.Panel(mainSplitter)

        self.workingSet = set([])
        if input_directory is None:
            logger.debug("using empty initial working set")
            working_set = set([]) # don't add to self.workingSet before
                    # addFilesToWorkingSet has been called below
        else:
            logger.debug("using '%s' as initial input directory" % (input_directory,))
            working_set = set(filter(lambda x: os.path.isfile(x), [os.path.abspath(os.path.join(input_directory, i)) for i in os.listdir(input_directory)])) # filter necessary in order to avoid failure of retrieval of min and max in __split_item__
        standardPaths = wx.StandardPaths.Get()
        self.reviewFolder = review_folder # the folder where video which aren't splitted
            # correctly or need other reviewing are moved to; a default value
            # is too confusing and setting value by the user should be enforced
        self.currentFolder = standardPaths.GetDocumentsDir() # stores the folder of the
            # last selection of input files (initially set to a convenient
            # default value, like $HOME)
        self.currentVolume = 0.5

        self.menuBar = wx.MenuBar()
        self.fileMenu = wx.Menu()
        add_files_menu_item = self.fileMenu.Append(wx.ID_ANY, "&Add files", "Add media file(s)")
        add_from_directory_menu_item = self.fileMenu.Append(wx.ID_ANY, "Add from &directory", "Add all media files of a directory")
        set_review_folder_menu_item = self.fileMenu.Append(wx.ID_ANY, "&Set review folder", "Set review folder")
        self.menuBar.Append(self.fileMenu, '&File')
        self.editMenu = wx.Menu()
        self.editMenuItemUndo = self.editMenu.Append(wx.ID_ANY, item="Undo")
        self.editMenuItemRedo = self.editMenu.Append(wx.ID_ANY, item="Redo")
        self.Bind(wx.EVT_MENU, self.onEditMenuItemUndoClick, self.editMenuItemUndo)
        self.Bind(wx.EVT_MENU, self.onEditMenuItemRedoClick, self.editMenuItemRedo)
        self.menuBar.Append(self.editMenu, "&Edit")
        self.helpMenu = wx.Menu()
        self.helpMenuAboutItem = self.helpMenu.Append(-1, item='&About')
        self.Bind(wx.EVT_MENU, self.onAboutBox, self.helpMenuAboutItem)
        self.menuBar.Append(self.helpMenu, '&Help')
        self.SetMenuBar(self.menuBar)
        self.Bind(wx.EVT_MENU, self.onAddFiles, add_files_menu_item)
        self.Bind(wx.EVT_MENU, self.onAddFromDirectory, add_from_directory_menu_item)
        self.Bind(wx.EVT_MENU, self.onSetReviewFolder, set_review_folder_menu_item)

        # create sizers (no need for a sizer for splitter)
        videoSizer = wx.BoxSizer(wx.VERTICAL)
        controlSizer = wx.BoxSizer(wx.HORIZONTAL)
        sliderSizer = wx.BoxSizer(wx.HORIZONTAL)

        # build the audio bar controls
        playButtonImg = self.getBmpFromSvg(resource_string("video_splitter", os.path.join("resources", "icons", 'play-button.svg')), icon_size_default, icon_size_default)
        self.playButton = buttons.GenBitmapButton(self.videoPanel, bitmap=playButtonImg, name="play")
        self.playButton.SetInitialSize()
        self.playButton.Bind(wx.EVT_BUTTON, self.onPause # handles both play and pause depending on state of the button
             )
        self.playButton.Disable()
        controlSizer.Add(self.playButton, 0, wx.LEFT, 3)
        stopButtonImg = self.getBmpFromSvg(resource_string("video_splitter", os.path.join("resources", "icons", 'stop-button.svg')), icon_size_default, icon_size_default)
        self.stopButton = buttons.GenBitmapButton(self.videoPanel, bitmap=stopButtonImg, name="stop")
        self.stopButton.SetInitialSize()
        self.stopButton.Bind(wx.EVT_BUTTON, self.onStop)
        self.stopButton.Disable()
        controlSizer.Add(self.stopButton, 0, wx.LEFT, 3)

        self.mplayerCtrl = wx.media.MediaCtrl(self.videoPanel, -1)
        self.trackPath = None
        self.playbackState = PLAYBACK_STATE_STOPPED
            # could be checked with self.playbackTime.IsRunning, but then the
            # status depends on using the timer and it's harder to debug issues
            # with it
        self.playbackSlider = wx.Slider(self.videoPanel, size=wx.DefaultSize)
        self.playbackSlider.Bind(wx.EVT_SLIDER, self.onOffsetSet)
        sliderSizer.Add(self.playbackSlider, 1, wx.ALL|wx.EXPAND, 5)

        # create volume control
        self.volumeCtrl = wx.Slider(self.videoPanel, size=(200, -1))
        self.volumeCtrl.SetRange(0, 100) # slider only seems to take integers
            # (multiply and divide with/by 100)
        self.volumeCtrl.SetValue(self.currentVolume*100)
        self.volumeCtrl.Bind(wx.EVT_SLIDER, self.onVolumeSet)
        controlSizer.Add(self.volumeCtrl, 0, wx.ALL|wx.EXPAND, 5)

        # create track counter
        self.trackCounter = wx.StaticText(self.videoPanel, label="00:00")
        sliderSizer.Add(self.trackCounter, 0, wx.ALL|wx.CENTER, 5)

        # set up playback timer

        videoSizer.Add(self.mplayerCtrl, 1, wx.ALL|wx.EXPAND, 5)
        videoSizer.Add(sliderSizer, 0, wx.ALL|wx.EXPAND, 5)
        videoSizer.Add(controlSizer, 0, wx.ALL|wx.CENTER, 5)
        self.videoPanel.SetSizer(videoSizer)

        # setup file lists (a splitter has to be used in order to provide
        # minimal flexibility; the resize control should be left or right of
        # the select and deselect buttons, but it's just a question of decision
        # -> use left)
        listsButtonSizer = wx.BoxSizer(wx.VERTICAL)
        listsPanelSizer = wx.BoxSizer(wx.HORIZONTAL)
        listsSplitterPanelRightSizer = wx.BoxSizer(wx.HORIZONTAL)
        listsSplitter = wx.SplitterWindow(self.listsPanel, style=wx.SP_LIVE_UPDATE) # doesn't expand automatically (although should because it's the only component in listPanel) -> use listsPanelSizer
        listsSplitter.SetMinimumPaneSize(100)
        listsPanelSizer.Add(listsSplitter, 1, wx.ALL|wx.EXPAND, 5)
        self.listsPanel.SetSizer(listsPanelSizer)
        listsSplitterPanelLeft = wx.Panel(parent=listsSplitter)
        listsSplitterPanelRight = wx.Panel(parent=listsSplitter)
        self.workingSetList = wx.ListCtrl(parent=listsSplitterPanelLeft, id=wx.ID_ANY, style=wx.LC_REPORT) # don't make entries editable
        workingSetListSizer = wx.BoxSizer(wx.VERTICAL)
        categoryButtonSizer = wx.WrapSizer(wx.HORIZONTAL)
        selectionListSizer = wx.BoxSizer(wx.VERTICAL)
        self.selectButton = wx.Button(parent=listsSplitterPanelRight, id=wx.ID_ANY, label=">", size=wx.Size(icon_size_default, icon_size_default))
        self.deselectButton = wx.Button(parent=listsSplitterPanelRight, id=wx.ID_ANY, label="<", size=wx.Size(icon_size_default, icon_size_default))
        self.selectionList = wx.ListCtrl(parent=listsSplitterPanelRight, id=wx.ID_ANY, style=wx.LC_REPORT)
        self.workingSetList.InsertColumn(0, heading="File", width=wx.LIST_AUTOSIZE)
        self.selectionList.InsertColumn(0, heading="File", width=wx.LIST_AUTOSIZE)
        self.mergeButton = wx.Button(parent=listsSplitterPanelRight, id=wx.ID_ANY, label="merge selection")
        for category in categories:
            category_button = wx.Button(parent=listsSplitterPanelLeft, id=wx.ID_ANY, label=str(category))
            categoryButtonSizer.Add(category_button, 0, wx.ALL, 5)
            # unable to determine minimal width at this point
            def __createCategoryButtonClickCallback__(category):
                def __onCategoryButtonClick__(event):
                    if self.reviewFolder is None:
                        wx.MessageBox("review folder isn't set", 'Info', wx.OK | wx.ICON_INFORMATION)
                        return
                    selected_index = self.workingSetList.GetNextSelected(-1)
                    if selected_index == -1:
                        logger.debug("no item selected in working set list, so nothing to categorize")
                        return
                    selected_item = self.workingSetList.GetItem(selected_index, col=0)
                    # playback should be stopped before moving file
                    selected_item_playbacked = False # store info for later (much simpler code for the price of one flag)
                    if selected_item.GetText() == self.trackPath:
                        selected_item_playbacked = True
                        self.stopPlayback()
                    category_folder = os.path.join(self.reviewFolder, str(category))
                    if not os.path.exists(category_folder):
                        os.makedirs(category_folder)
                    logger.debug("moving '%s' into category folder '%s'" % (selected_item.GetText(), category_folder))
                    shutil.move(selected_item.GetText(), os.path.join(category_folder, os.path.basename(selected_item.GetText())))
                    self.workingSetList.DeleteItem(selected_index)
                    self.undoStack.append((selected_item.GetText(), category, selected_index))
                    self.editMenuItemRedo.Enable(False)
                    self.redoStack.clear()
                    # automatically start the next item after the categorized in workingSetList in order to proceed faster and select it (but only if the just moved item is currently playbacked because otherwise the playback of another item would be interrupted)
                    if self.workingSetList.GetItemCount() > 0 \
                            and selected_index < self.workingSetList.GetItemCount()-1 \
                            and selected_item_playbacked: # there needs to be one more item after the categorized one (refers to item count after removal of categorized item)
                        selected_item = self.workingSetList.GetItem(selected_index, col=0)
                        self.trackPath = selected_item.GetText()
                        logger.info("starting video '%s'" % (self.trackPath,))
                        self.startVideo(self.trackPath)
                        self.workingSetList.SetItemState(selected_index, # item
                                wx.LIST_STATE_SELECTED, # state
                                wx.LIST_STATE_SELECTED # stateMask
                        )
                return __onCategoryButtonClick__
            category_button.Bind(wx.EVT_BUTTON, __createCategoryButtonClickCallback__(category))
        workingSetListSizer.Add(categoryButtonSizer, 0, wx.ALL|wx.EXPAND, 5)
        workingSetListSizer.Add(self.workingSetList, 1, wx.ALL|wx.EXPAND, 5)
        listsSplitterPanelLeft.SetSizer(workingSetListSizer)
        listsButtonSizer.Add(self.selectButton, 0, wx.ALL, 5)
        listsButtonSizer.Add(self.deselectButton, 0, wx.ALL, 5)
        listsSplitterPanelRightSizer.Add(listsButtonSizer, 0, wx.ALL, 5)
        selectionListSizer.Add(self.selectionList, 1, wx.ALL|wx.EXPAND, 5)
        selectionListSizer.Add(self.mergeButton, 0, wx.ALIGN_BOTTOM|wx.ALL, 5)
        listsSplitterPanelRightSizer.Add(selectionListSizer, 1, wx.EXPAND, 5)
        listsSplitterPanelRight.SetSizer(listsSplitterPanelRightSizer)
        self.workingSetList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, #The item has been activated (ENTER or double click). Processes a wxEVT_LIST_ITEM_ACTIVATED event type.
            self.onWorkingSetListDoubleClick)
        self.workingSetList.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onWorkingSetListSelect)
        self.workingSetList.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.onWorkingSetListDeselect)
        self.selectionList.Bind(wx.EVT_LIST_ITEM_ACTIVATED, #The item has been activated (ENTER or double click). Processes a wxEVT_LIST_ITEM_ACTIVATED event type.
            self.onSelectionListDoubleClick)
        self.selectionList.Bind(wx.EVT_LIST_ITEM_SELECTED, self.onSelectionListSelect)
        self.selectionList.Bind(wx.EVT_LIST_ITEM_DESELECTED, self.onSelectionListDeselect)
        self.selectButton.Bind(wx.EVT_BUTTON, self.onSelectButtonClick)
        self.deselectButton.Bind(wx.EVT_BUTTON, self.onDeselectButtonClick)
        self.mergeButton.Bind(wx.EVT_BUTTON, self.onMergeButtonClick)
        self.workingSetList.Bind(wx.EVT_LIST_ITEM_RIGHT_CLICK, self.onWorkingSetListRightClick)

        listsSplitter.SplitVertically(listsSplitterPanelLeft, listsSplitterPanelRight)
        mainSplitter.SplitVertically(self.listsPanel, self.videoPanel)

        self.Bind(wx.media.EVT_MEDIA_PLAY, self.onMediaStarted)
        self.Bind(wx.media.EVT_MEDIA_FINISHED, self.onMediaFinished)

        # working set list popup menu
        self.workingSetListPopupMenu = wx.Menu()
        self.workingSetListPopupMenuItemClear = self.workingSetListPopupMenu.Append(wx.ID_ANY, "Clear working set")
        self.workingSetListPopupMenuItemDelete = self.workingSetListPopupMenu.Append(wx.ID_ANY, "Move to trash")
        self.Bind(wx.EVT_MENU, self.onWorkingSetListPopupMenuItemClearClick, self.workingSetListPopupMenuItemClear) # MenuItem doesn't have a Bind function
        self.Bind(wx.EVT_MENU, self.onWorkingSetListPopupMenuItemDeleteClick, self.workingSetListPopupMenuItemDelete)

        # set up components
        self.statusBar = self.CreateStatusBar(style=wx.STB_DEFAULT_STYLE)
        self.statusBar.SetFieldsCount(1)
        self.statusBar.SetStatusStyles([wx.SB_NORMAL]) # @TODO: wx.SB_SUNKEN only available after 2.9.5<ref>http://wxpython.org/Phoenix/docs/html/StatusBar.html</ref> -> assert 3.0.x at run and compile time somewhere
        self.addFilesToWorkingSet(working_set) # run after self.workingSetList has been initialized
        self.workingSet = working_set
        self.updateReviewFolderStatusText()

        self.Show(True)

    def onWorkingSetListDeselect(self, event):
        if self.workingSetList.GetSelectedItemCount() == 0 and self.selectionList.GetSelectedItemCount() == 0:
            self.playButton.Disable()
            self.stopButton.Disable()

    def onSelectionListDeselect(self, event):
        if self.workingSetList.GetSelectedItemCount() == 0 and self.selectionList.GetSelectedItemCount() == 0:
            self.playButton.Disable()
            self.stopButton.Disable()

    def onWorkingSetListSelect(self, event):
        """Removes all selection on selectionList in order to allow videos to be played based on selection (doesn't make sense if items are selected on two lists)"""
        for i in range(0, self.selectionList.GetItemCount()):
            self.selectionList.Select(i, on=0)
        self.playButton.Enable()

    def onSelectionListSelect(self, event):
        """Removes all selection on workingSetList in order to allow videos to be played based on selection (doesn't make sense if items are selected on two lists)"""
        for i in range(0, self.workingSetList.GetItemCount()):
            self.workingSetList.Select(i, on=0)
        self.playButton.Enable()

    def onSelectButtonClick(self, event):
        # need to collect all selected indices first because the ListCtrl.GetNextSelected doesn't modify the multi-selection state after ListCtrl.DeleteItem
        selected_indices = []
        next_selected = self.workingSetList.GetNextSelected(-1)
        while next_selected != -1:
            selected_indices.append(next_selected)
            next_selected = self.workingSetList.GetNextSelected(next_selected)
        # need to remove backwards
        for selected_index in sorted(selected_indices, reverse=True):
            next_selected_item = self.workingSetList.GetItem(selected_index, col=0)
            self.workingSetList.DeleteItem(selected_index)
            selected_item = next_selected_item.GetText()
            logger.debug("selecting item '%s'" % (selected_item,))
            self.selectionList.Append([selected_item])
        self.workingSetList.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self.selectionList.SetColumnWidth(0, wx.LIST_AUTOSIZE)

    def onDeselectButtonClick(self, event):
        """
        Moves selected items from the selection list back to the working set
        list. Prepends items (rather than append them) in order to avoid
        scrolling when dealing with a large working set
        """
        # need to collect all selected indices first because the ListCtrl.GetNextSelected doesn't modify the multi-selection state after ListCtrl.DeleteItem
        selected_indices = []
        next_selected = self.selectionList.GetNextSelected(-1)
        while next_selected != -1:
            selected_indices.append(next_selected)
            next_selected = self.selectionList.GetNextSelected(next_selected)
        # need to remove backwards
        for selected_index in sorted(selected_indices, reverse=True):
            next_selected_item = self.selectionList.GetItem(selected_index, col=0)
            self.selectionList.DeleteItem(selected_index)
            selected_item = next_selected_item.GetText()
            logger.debug("deselecting item '%s'" % (selected_item,))
            self.workingSetList.InsertItem(0, selected_item)
        self.workingSetList.SetColumnWidth(0, wx.LIST_AUTOSIZE)
        self.selectionList.SetColumnWidth(0, wx.LIST_AUTOSIZE)

    def onSelectionListDoubleClick(self, event):
        selected_item = event.GetItem()
        self.trackPath = selected_item.GetText()
        self.startVideo(self.trackPath)

    def onWorkingSetListDoubleClick(self, event):
        selected_item = event.GetItem()
        self.trackPath = selected_item.GetText()
        self.startVideo(self.trackPath)

    def onWorkingSetListRightClick(self, event):
        self.workingSetList.PopupMenu(self.workingSetListPopupMenu, event.GetPoint())

    def onWorkingSetListPopupMenuItemClearClick(self, event):
        self.workingSetList.DeleteAllItems() # ListCtrl.ClearAll removes columns as well

    def onWorkingSetListPopupMenuItemDeleteClick(self, event):
        selected_indices = []
        next_selected = self.workingSetList.GetNextSelected(-1)
        while next_selected != -1:
            selected_indices.append(next_selected)
            next_selected = self.workingSetList.GetNextSelected(next_selected)
        for selected_index in selected_indices:
            next_selected_item = self.workingSetList.GetItem(selected_index, col=0)
            if next_selected_item.GetText() == self.trackPath:
                self.stopPlayback()
            logger.debug("moving '%s' to trash" % (next_selected_item.GetText(),))
            send2trash.send2trash(next_selected_item.GetText())
            self.workingSetList.DeleteItem(selected_index)

    def updateReviewFolderStatusText(self):
        new_text = "review folder: "
        if self.reviewFolder is None:
            new_text += "(not yet selected)"
        else:
            new_text += os.path.abspath(self.reviewFolder)
            # since there's no way to determine whether
            # wx.StatusBar.PopStatusText succeeds simply always push status
            # texts over the preceeding
        self.statusBar.PushStatusText(new_text, # string
            0 # field
        )

    def getBmpFromSvg(self,svgxml, width, height):
        """
        Credit goes to https://cyberxml.wordpress.com/2015/02/17/wxpython-wx-bitmap-icons-from-svg-xml/. Asked https://cyberxml.wordpress.com/2015/02/17/wxpython-wx-bitmap-icons-from-svg-xml/comment-page-1/#comment-11 to a version avoiding deprecated wx.BitmapFromImage.
        """
        svgpng = cairosvg.svg2png(svgxml)
        svgimg = wx.ImageFromStream(StringIO.StringIO(svgpng),wx.BITMAP_TYPE_PNG)
        svgimg = svgimg.Scale(width, height, wx.IMAGE_QUALITY_HIGH)
        svgbmp = wx.BitmapFromImage(svgimg)
        return svgbmp

    def onAddFiles(self, event):
        """
        Add media file(s) to the working list
        """
        dlg = wx.FileDialog(
            self, message="Choose a file",
            defaultDir=self.currentFolder,
            defaultFile="",
            wildcard=video_file_extensions_wildcard,
            style=wx.FD_MULTIPLE
            )
        if dlg.ShowModal() == wx.ID_OK:
            paths = dlg.GetPaths()
            # set doesn't support adding a collection because of hashable type issue, but checking if value is already present improves logging feedback
            self.addFilesToWorkingSet(paths)
            self.currentFolder = os.path.dirname(paths[0])

    def onAddFromDirectory(self, event):
        """
        Add all media files from a directory to the working list
        """
        dlg = wx.DirDialog(
            self, message="Choose a directory",
            defaultPath=self.currentFolder,
            style=wx.DD_DEFAULT_STYLE
            )
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            files = [os.path.abspath(os.path.join(path, i)) for i in os.listdir(path)]
            self.addFilesToWorkingSet(files)
            self.currentFolder = dlg.GetPath()

    def addFilesToWorkingSet(self, files):
        # filter first because it needs to be done and otherwise __split_item__
        # fails for files without name matching bla-n-n.ext (e.g. review
        # folders)
        if len(files) == 0:
            return
        def __filter_file__(file0):
            file_extension = video_splitter.retrieve_file_extension(file0)
            if not file_extension in video_splitter_globals.video_file_extensions:
                logger.debug("skipping non-video file '%s' based on extension" % (file0,))
                return False
            if file0 in self.workingSet:
                logger.debug("skipping already added file '%s'" % (file0,))
                return False
            return True
        files = [i for i in files if __filter_file__(i)]
        for new_file_path in sorted(files, key=lambda x: __split_item__(x)[3]+"%050d" % (__split_item__(x)[1],)): # sorting with item_min of __split_item__ isn't sufficient because we need to include the item_head as well; then sort by joining head and item_min with 50 leading zeros (assuming that item_min's length won't exceed 50 digits)
            self.workingSet.add(new_file_path)
            self.workingSetList.InsertItem(self.workingSetList.GetItemCount(), new_file_path)
            logger.debug("added file '%s' to working set" % (new_file_path,))
        self.workingSetList.SetColumnWidth(0, wx.LIST_AUTOSIZE)


    def onSetReviewFolder(self, event):
        wildcard = "Media Files (*.*)|*.*"
        defaultPath = self.reviewFolder
        if defaultPath is None:
            standardPaths = wx.StandardPaths.Get()
            defaultPath = standardPaths.GetDocumentsDir()
        dlg = wx.DirDialog(
            self, message="Choose the review directory",
            defaultPath=defaultPath,
            style=wx.DD_DEFAULT_STYLE
            )
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.reviewFolder = path
            logger.debug("review folder set to '%s'" % (self.reviewFolder,))
            self.updateReviewFolderStatusText()

    def onMediaStarted(self, event):
        logger.debug("playback started of '%s'" % (self.trackPath,))

    def onMediaFinished(self, event):
        logger.debug("playback finished of '%s'" % (self.trackPath,))
        self.playbackState = PLAYBACK_STATE_STOPPED
        self.playbackSlider.SetValue(0)
        self.trackCounter.SetLabel("00:00")

    def onPause(self, event):
        """Starts and unpauses video after the play button has been pressed.
        Plays the selected item in working set list or selection list (only one
        list can have a selected item). Does nothing is no item is selected."""
        if self.playbackState == PLAYBACK_STATE_RUNNING:
            logger.info("pausing...")
            self.mplayerCtrl.Pause()
        #    self.playbackTimer.Stop()
            self.playbackState = PLAYBACK_STATE_PAUSED
        else:
            if self.playbackState == PLAYBACK_STATE_PAUSED:
                logger.info("unpausing...")
                self.mplayerCtrl.Play()
            else:
                # start new playback (see function comment for explanation)
                selection_list_selected_index = self.selectionList.GetNextSelected(-1)
                selected_item = None
                if selection_list_selected_index != -1:
                    selected_item = self.selectionList.GetItem(selection_list_selected_index, col=0)
                else:
                    working_set_list_selected_index = self.workingSetList.GetNextSelected(-1)
                    if working_set_list_selected_index != -1:
                        selected_item = self.workingSetList.GetItem(working_set_list_selected_index, col=0)
                if selected_item != None:
                    self.trackPath = selected_item.GetText()
                    logger.info("starting video '%s'" % (self.trackPath,))
                    self.startVideo(self.trackPath)
            self.playbackState = PLAYBACK_STATE_RUNNING

    def startVideo(self, trackPath):
        if not self.playbackState == PLAYBACK_STATE_PAUSED:
            # first start
            self.mplayerCtrl.Load(trackPath)
        self.mplayerCtrl.Play()
        t_len = self.mplayerCtrl.Length()
        self.playbackSlider.SetRange(0, t_len)
        self.playbackState = PLAYBACK_STATE_RUNNING

    def onVolumeSet(self, event):
        """
        Sets the volume of the music player
        """
        self.currentVolume = self.volumeCtrl.GetValue()/float(100)
        logger.debug("setting volume %f" % (self.currentVolume,))
        self.mplayerCtrl.SetVolume(self.currentVolume)

    def onStop(self, event):
        """"""
        self.stopPlayback()

    def stopPlayback(self):
        logger.debug("stopping playback")
        self.mplayerCtrl.Stop()
        self.playbackState = PLAYBACK_STATE_STOPPED

    def onUpdatePlayback(self, event):
        """
        Updates playback slider and track counter
        """
        try:
            offset = self.mplayerCtrl.Tell() # offset in millisecond
        except:
            return
        logger.debug("offset is %s milliseconds" % (offset,))
        self.playbackSlider.SetValue(offset)
        secsPlayed = time.strftime('%M:%S', time.gmtime(offset/1000))
        self.trackCounter.SetLabel(secsPlayed)

    def onOffsetSet(self, event):
        """
        Updates offset of video playback after clicking on playbackSlider
        """
        offset = self.playbackSlider.GetValue()
        self.mplayerCtrl.Seek(offset)

    def onMergeButtonClick(self, event):
        """
        Copies first file in the selection list to be the first piece of the
        merged file and appends all items in the selection list to the file
        """
        if self.selectionList.GetItemCount() == 0:
            logger.debug("nothing to merge because selection list is empty")
            return
        if self.selectionList.GetItemCount() == 1:
            logger.debug("nothing to merge because selection list contains only one item")
            return
        # prepare merging
        selection_list_item_count = self.selectionList.GetItemCount()
        item_list = []
        for row in range(selection_list_item_count):
            selectionItem = self.selectionList.GetItem(itemIdx=row, col=0)
            next_item = str(selectionItem.GetText())
            logger.debug("adding '%s' to merge list" % (next_item,))
            item_list.append(next_item)
        # automatically determine output file name based on video_splitter file
        # naming
        min_offset = sys.maxint
        max_offset = -1
        for item in item_list:
            item_tuple = __split_item__(item)
            if item_tuple is None:
                continue
            item_ext, item_min, item_max, item_head = item_tuple
            if item_min < min_offset:
                min_offset = item_min
            if item_max > max_offset:
                max_offset = item_max
        output_file_path = "%s-%d-%d.%s" % (item_head, min_offset, max_offset,item_ext,)
        # merging
        merge_cmd_list = []
        for item in item_list:
            merge_cmd_list.append("-cat")
            merge_cmd_list.append(item)
        logger.debug("merging selection using mp4box binary  '%s' to output file '%s'" % (self.mp4box,output_file_path,))
        mp4box_cmds = [self.mp4box]+merge_cmd_list+["-new", output_file_path]
        try:
            sp.check_call(mp4box_cmds)
        except sp.CalledProcessError as ex:
            wx.MessageBox("mp4box command '%s' failed to run" % (str.join(" ", mp4box_cmds),), 'Info', wx.OK | wx.ICON_INFORMATION)
        # delete merged videos
        for item in item_list:
            logger.debug("removing merged file '%s'" % (item,))
            os.remove(item)
        logger.debug("cleared selection list")
        self.selectionList.DeleteAllItems() # ListCtrl.ClearAll removes columns as well
        self.selectionList.InsertItem(0, output_file_path)

    def onAboutBox(self, event):
        wx.AboutBox(video_splitter_globals.app_about_box_info)

    def onEditMenuItemUndoClick(self, event):
        """
        Handles an undo request and moves files from category folder back to the
        original location stored in self.undoStack. Appends the information used
        for undoing the change to self.redoStack in order to allow the action to
        be redoable.
        """
        file_path, category, old_index = self.undoStack.pop() # append adds to the right side
        category_folder = os.path.join(self.reviewFolder, str(category))
        logger.debug("undoing move of '%s' into category folder '%s'" % (file_path, category_folder))
        shutil.move(os.path.join(category_folder, os.path.basename(file_path)), file_path)
        self.workingSetList.InsertItem(old_index, file_path)
        self.redoStack.append((file_path, category, old_index))
        self.editMenuItemRedo.Enable(True)

    def onEditMenuItemRedoClick(self, event):
        """
        Handles a redo request and moves files from their original location to the category folder they have been added before (before they where moved back to their original location in an undo request) with the information stored in self.redoStack (where information has been added during processing the undo request). Appends the information used
        for redoing the change to self.undoStack in order to allow the action to
        be undoable again.
        """
        file_path, category, old_index = self.redoStack.pop() # append adds to the right side
        category_folder = os.path.join(self.reviewFolder, str(category))
        logger.debug("redoing move of '%s' into category folder '%s'" % (file_path, category_folder))
        shutil.move(file_path, os.path.join(category_folder, os.path.basename(file_path)))
        self.workingSetList.DeleteItem(old_index)
        self.undoStack.append((file_path, category, old_index))

def __split_item__(item):
    item_ext_split = str.rsplit(str(item), # work with complete path (instead of
            # just the filename) in order to avoid unnecessary joining
            # later
        ".", # sep
        1 # maxsplit
    )
    minus_split_input = item_ext_split[0]
    item_ext = item_ext_split[1]
    minus_split = re.split("-", minus_split_input)
    if minus_split == None:
        return None
    try:
        item_min = int(minus_split[-2])
        item_max = int(minus_split[-1])
        item_head = str.join("-", minus_split[0:-2])
        return (item_ext, item_min, item_max, item_head)
    except ValueError:
        raise ValueError("encountered item '%s' which doesn't match the required input format of a filename ending in '-[begin frame]-[end frame].[extension]'" % (item,))

def __generate_window_title__(title):
    if title is None:
        ret_value = "%s %s" % (video_splitter_globals.app_name, app_version)
    else:
        ret_value = "%s - %s %s" % (title, video_splitter_globals.app_name, app_version)
    return ret_value

@plac.annotations(mp4box=(__mp4box_doc__, "option"),
    version=(video_splitter_globals.__version_doc__, "flag"),
    debug=(video_splitter_globals.__debug_doc__, "flag"),
    input_directory=("a directory to read video files from", "positional"),
    review_folder=("the review folder", "option"),
)
def __main_delegate__(mp4box=mp4box_default, version=False, debug=False, input_directory=None, review_folder=None):
    """necessary function to make `plac.call` possible in `main`"""
    if version is True:
        print(app_version)
        return
    if debug is True:
        logger.setLevel(logging.DEBUG)
        ch.setLevel(logging.DEBUG)
    app = wx.App(False)
    frame = VideoManager(None, wx.ID_ANY, __generate_window_title__(None), mp4box=mp4box, input_directory=input_directory, review_folder=review_folder)
    frame.Show(True)
    app.MainLoop()

def main():
    """`entry_point` for `setuptools`"""
    plac.call(__main_delegate__)

if "__main__" == __name__:
    main()
