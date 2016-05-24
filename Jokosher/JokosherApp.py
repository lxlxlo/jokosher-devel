#!/usr/bin/python
#
#	THIS FILE IS PART OF THE JOKOSHER PROJECT AND LICENSED UNDER THE GPL. SEE
#	THE 'COPYING' FILE FOR DETAILS
#
#	Jokosher's main class. It creates the majority of the main window GUI
#	and gets everything up and running.
#
#-------------------------------------------------------------------------------

import pygtk
pygtk.require("2.0")
import gtk.glade, gobject
import sys
import os.path
import pygst
pygst.require("0.10")
import gst
from subprocess import Popen, PIPE

import gettext
_ = gettext.gettext

import AddInstrumentDialog, TimeView, Workspace
import PreferencesDialog, ExtensionManagerDialog, RecordingView, NewProjectDialog
import ProjectManager, Globals, WelcomeDialog
import InstrumentConnectionsDialog
import EffectPresets, Extension, ExtensionManager
import Utils, AudioPreview, MixdownProfileDialog, MixdownActions
import PlatformUtils
import ui.StatusBar as StatusBar

#=========================================================================

class MainApp:
	"""
	Jokosher's main class. It creates the majority of the main window GUI and 
	gets everything up and running.
	"""
	
	# Class Constants
	""" Constant value used to indicate Jokosher's recording mode  """
	MODE_RECORDING = 1
	
	""" Constant value used to indicate Jokosher's mixing mode  """
	MODE_COMPACT_MIX = 2

	#_____________________________________________________________________

	def __init__(self, openproject=None, loadExtensions=True, startuptype=None):
		"""
		Creates a new instance of MainApp.
		
		Parameters:
			openproject -- filename of the project to open at startup.
			loadExtensions -- whether the extensions should be loaded.
			startuptype -- determines the startup state of Jokosher:
							0 = Open the project referred by the openproject parameter.
							1 = Do not display the welcome dialog or open a the previous project.
							2 = Display the welcome dialog.
		"""
		# create tooltip messages for buttons
		self.recTipEnabled = _("Stop recording")
		self.recTipDisabled = _("Arm an instrument, then click here to begin recording")
		self.recStopTipEnabled = _("Stop recording")
		self.recStopTipDisabled = _("Stop playback")
		self.mixingViewEnabledTip = _("Hide the audio level mixers")
		self.mixingViewDisabledTip = _("Show the audio level mixers")
		
		gtk.glade.bindtextdomain(Globals.LOCALE_APP, Globals.LOCALE_PATH)
		gtk.glade.textdomain(Globals.LOCALE_APP)

		self.wTree = gtk.glade.XML(Globals.GLADE_PATH, "MainWindow")
		
		#Connect event handlers
		signals = {
			"on_MainWindow_destroy" : self.OnDestroy,
			"on_MainWindow_configure_event" : self.OnResize,
			"on_AddInstrument_clicked" : self.OnShowAddInstrumentDialog,
			"on_About_activate" : self.About,
			"on_Record_toggled" : self.Record, 
			"on_Play_clicked" : self.Play,
			"on_Stop_clicked" : self.Stop,
			"on_CompactMix_toggled" : self.OnCompactMixView,
			"on_export_activate" : self.OnExport,
			"on_preferences_activate" : self.OnPreferences,
			"on_open_activate" : self.OnOpenProject,
			"on_save_activate" : self.OnSaveProject,
			"on_save_as_activate" : self.OnSaveAsProject,
			"on_new_activate" : self.OnNewProject,
			"on_close_activate" : self.OnCloseProject,
			"on_show_as_bars_beats_ticks_toggled" : self.OnShowBarsBeats,
			"on_show_as_hours_minutes_seconds_toggled" : self.OnShowHoursMins,
			"on_undo_activate" : self.OnUndo,
			"on_redo_activate" : self.OnRedo,
			"on_cut_activate" : self.OnCut,
			"on_copy_activate" : self.OnCopy,
			"on_paste_activate" : self.OnPaste,
			"on_delete_activate" : self.OnDelete,
			"on_MouseDown" : self.OnMouseDown,
			"on_instrumentconnections_activate" : self.OnInstrumentConnectionsDialog,
			"on_filemenu_activate" : self.OnFileMenu,
			"on_editmenu_activate" : self.OnEditMenu,
			"on_help_contents_activate" : self.OnHelpContentsMenu,
			"on_forums_activate" : self.OnForumsMenu,
			"on_contributing_activate" : self.OnContributingDialog,
			"on_ExtensionManager_activate" : self.OnExtensionManagerDialog,
			"on_instrumentmenu_activate" : self.OnInstrumentMenu,
			"on_instrMenu_add_audio" : self.OnAddAudio,
			"on_change_instr_type_activate" : self.OnChangeInstrument,
			"on_remove_instr_activate" : self.OnRemoveInstrument,
			"on_report_bug_activate" : self.OnReportBug,
			"on_project_add_audio" : self.OnAddAudioFile,
			"on_system_information_activate" : self.OnSystemInformation,
			"on_properties_activate" : self.OnProjectProperties,
		}
		self.wTree.signal_autoconnect(signals)
		
		# grab some references to bits of the GUI
		self.window = self.wTree.get_widget("MainWindow")
		self.play = self.wTree.get_widget("Play")
		self.stop = self.wTree.get_widget("Stop")
		self.record = self.wTree.get_widget("Record")
		self.save = self.wTree.get_widget("save")
		self.save_as = self.wTree.get_widget("save_as")
		self.close = self.wTree.get_widget("close")
		self.reverse = self.wTree.get_widget("Rewind")
		self.forward = self.wTree.get_widget("Forward")
		self.addInstrumentButton = self.wTree.get_widget("AddInstrument")
		self.compactMixButton = self.wTree.get_widget("CompactMix")
		self.editmenu = self.wTree.get_widget("editmenu")
		self.filemenu = self.wTree.get_widget("filemenu")
		self.undo = self.wTree.get_widget("undo")
		self.redo = self.wTree.get_widget("redo")
		self.cut = self.wTree.get_widget("cut")
		self.copy = self.wTree.get_widget("copy")
		self.paste = self.wTree.get_widget("paste")
		self.delete = self.wTree.get_widget("delete")
		self.instrumentMenu = self.wTree.get_widget("instrumentmenu")
		self.export = self.wTree.get_widget("export")
		self.recentprojects = self.wTree.get_widget("recentprojects")
		self.recentprojectsmenu = self.wTree.get_widget("recentprojects_menu")
		self.menubar = self.wTree.get_widget("menubar")
		self.toolbar = self.wTree.get_widget("MainToolbar")
		self.addAudioMenuItem = self.wTree.get_widget("add_audio_file_instrument_menu")
		self.changeInstrMenuItem = self.wTree.get_widget("change_instrument_type")
		self.removeInstrMenuItem = self.wTree.get_widget("remove_selected_instrument")
		self.addAudioFileButton = self.wTree.get_widget("addAudioFileButton")
		self.addAudioFileMenuItem = self.wTree.get_widget("add_audio_file_project_menu")
		self.addInstrumentFileMenuItem = self.wTree.get_widget("add_instrument1")
		self.recordingInputsFileMenuItem = self.wTree.get_widget("instrument_connections1")
		self.timeFormatFileMenuItem = self.wTree.get_widget("time_format1")
		self.properties_menu_item = self.wTree.get_widget("project_properties")
		
		self.recentprojectitems = []
		self.lastopenedproject = None
		
		self.project = None
		self.headerhbox = None
		self.timeview = None
		self.tvtoolitem = None #wrapper for putting timeview in toolbar
		self.workspace = None
		self.instrNameEntry = None #the gtk.Entry when editing an instrument name
		self.main_vbox = self.wTree.get_widget("main_vbox")
		
		self.statusbar = StatusBar.StatusBar()
		self.main_vbox.pack_end(self.statusbar, False)
		
		# Initialise some useful vars
		self.mode = None
		self.settingButtons = True
		self.compactMixButton.set_active(False)
		self.settingButtons = False
		self.isRecording = False
		self.isPlaying = False
		self.isPaused = False

		# Intialise context sensitive tooltips for workspace buttons
		self.compactMixButton.set_tooltip_text(self.mixingViewDisabledTip)
		
		# set the window size to the last saved value
		x = int(Globals.settings.general["windowwidth"])
		y = int(Globals.settings.general["windowheight"])
		self.window.resize(x, y)
		
		# set sensitivity
		self.SetGUIProjectLoaded()

		# Connect up the forward and reverse handlers. We can't use the autoconnect as we need child items
		innerbtn = self.reverse.get_children()[0]
		innerbtn.connect("pressed", self.OnRewindPressed)
		innerbtn.connect("released", self.OnRewindReleased)
		
		innerbtn = self.forward.get_children()[0]
		innerbtn.connect("pressed", self.OnForwardPressed)
		innerbtn.connect("released", self.OnForwardReleased)
		
		miximg = gtk.Image()
		miximg.set_from_file(os.path.join(Globals.IMAGE_PATH, "icon_mix.png"))	
		self.compactMixButton.set_icon_widget(miximg)
		miximg.show()
		
		#get the audiofile image from Globals
		self.audioFilePixbuf = Globals.getCachedInstrumentPixbuf("audiofile")
		
		audioimg = gtk.Image()
		size = gtk.icon_size_lookup(gtk.ICON_SIZE_MENU)
		pixbuf = self.audioFilePixbuf.scale_simple(size[0], size[1], gtk.gdk.INTERP_BILINEAR)
		audioimg.set_from_pixbuf(pixbuf)
		# set the add audio menu item icon
		self.addAudioMenuItem.set_image(audioimg)
		
		size = gtk.icon_size_lookup(self.toolbar.get_icon_size())
		pixbuf = self.audioFilePixbuf.scale_simple(size[0], size[1], gtk.gdk.INTERP_BILINEAR)
		audioimg = gtk.Image()
		audioimg.set_from_pixbuf(pixbuf)	
		self.addAudioFileButton.set_icon_widget(audioimg)
		audioimg.show()
		
		# populate the Recent Projects menu
		self.OpenRecentProjects()
		self.PopulateRecentProjects()
		
		# set window icon
		icon_theme = gtk.icon_theme_get_default()
		try:
			pixbuf = icon_theme.load_icon("jokosher", 48, 0)
			self.window.set_icon(pixbuf)
		except gobject.GError, exc:
			self.window.set_icon_from_file(os.path.join(Globals.IMAGE_PATH, "jokosher.png"))
		# make icon available to others
		self.window.realize()
		self.icon = self.window.get_icon()
		
		# Make sure we can import for the instruments folder
		sys.path.append("Instruments")
		
		self.window.add_events(gtk.gdk.KEY_PRESS_MASK)
		self.window.connect_after("key-press-event", self.OnKeyPress)
		self.window.connect("button_press_event", self.OnMouseDown)

		self.CheckGstreamerVersions()

		# set up presets registry - this should probably be removed here	
		EffectPresets.EffectPresets()
		Globals.PopulateEncoders()
		Globals.PopulateAudioBackends()
		
		# seems like this is the best place to instantiate RegisterMixdownActionAPI
		# as extensions and the mixdown profile dialog can use it through mainapp
		self.registerMixdownActionAPI = MixdownActions.RegisterMixdownActionAPI()
		
		# register the default MixdownActions
		self.registerMixdownActionAPI.RegisterMixdownActions((MixdownActions.RunAScript, MixdownActions.ExportAsFileType))
		
		if loadExtensions:
			# Load extensions -- this should probably go somewhere more appropriate
			self.extensionManager = ExtensionManager.ExtensionManager(self)

		## Setup is complete so start up the GUI and perhaps load a project
		## any new setup code needs to go above here
		
		# Show the main window
		self.window.show_all()

		# command line options override preferences so check for them first,
		# then preferences, then default to the welcome dialog
		if startuptype == 2: # welcomedialog cmdline switch
			WelcomeDialog.WelcomeDialog(self)
			return
		elif startuptype == 1: # no-project cmdline switch
			return
		elif openproject: # a project name on the cmdline
			self.OpenProjectFromPath(openproject)
		elif Globals.settings.general["startupaction"] == PreferencesDialog.STARTUP_LAST_PROJECT:
			if self.lastopenedproject:
				self.OpenProjectFromPath(self.lastopenedproject[0])
		elif Globals.settings.general["startupaction"] == PreferencesDialog.STARTUP_NOTHING:
			return

		#if everything else bombs out resort to the welcome dialog
		if self.project == None:
			WelcomeDialog.WelcomeDialog(self)

	#_____________________________________________________________________
	
	def OnCompactMixView(self, button=None):
		"""
		Updates the main window after switching to the compact view mixing mode.
		
		Parameters:
			button -- Button object calling this method.
		"""
		if self.workspace:
			self.workspace.ToggleCompactMix()

	#_____________________________________________________________________


	def OnF3Pressed(self):
		"""
		Toggle to compact mix view button when F3 is pressed.
		"""

		self.compactMixButton.set_active(not self.compactMixButton.get_active())

	#_____________________________________________________________________
	
	def OnResize(self, widget, event):
		"""
		Called when the main window gets resized.
		
		Parameters:
			widget -- GTK callback parameter.
			event -- GTK callback parameter.
			
		Returns:
			False -- continue GTK signal propagation.
		"""
		(self.width, self.height) = widget.get_size()
		
		return False
	
	#_____________________________________________________________________
	
	def OnDestroy(self, widget=None, event=None):
		"""
		Called when the main window is destroyed.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			event -- reserved for GTK callbacks, don't use it explicitly.
		
		Returns:
			True -- the current project can't be properly closed.
					This stops signal propagation.
		"""
		# save the current window size
		Globals.settings.general["windowwidth"] = self.width
		Globals.settings.general["windowheight"] = self.height
		Globals.settings.write()
		
		if self.CloseProject() == 0:
			gtk.main_quit()
		else:
			return True #stop signal propogation
		
	#_____________________________________________________________________
	
	def OnShowAddInstrumentDialog(self, widget=None):
		"""
		Creates and shows the "Add Instrument" dialog box.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		AddInstrumentDialog.AddInstrumentDialog(self.project, self)
	
	#_____________________________________________________________________

	def OnChangeInstrument(self, widget=None):
		"""
		Changes the type of the selected Instrument.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.	
		"""
		# Change the type of a select instrument
		for instr in self.project.instruments:
			if (instr.isSelected):
				AddInstrumentDialog.AddInstrumentDialog(self.project, self, instr)
				return
	
	#_____________________________________________________________________
	
	def About(self, widget=None):
		"""
		Creates and shows the "About" dialog box.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		gtk.about_dialog_set_url_hook(self.AboutLinkActivate)
		aboutTree = gtk.glade.XML(Globals.GLADE_PATH, "AboutDialog")
		dlg = aboutTree.get_widget("AboutDialog")
		dlg.set_transient_for(self.window)
		dlg.set_icon(self.icon)
		dlg.run()
		dlg.destroy()
		
	#_____________________________________________________________________

	def AboutLinkActivate(self, widget, link):
		"""
		Opens the Jokosher website in the user's default web browser.

		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		Utils.OpenExternalURL(url=link, message=_("<big>Couldn't launch the jokosher website automatically.</big>\n\nPlease visit %s to access it."), parent=self.window)
		
	#_____________________________________________________________________
	
	def OnReportBug(self, widget):
		"""
		Opens the report bug launchpad website in the user's default web browser.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		Utils.OpenExternalURL(url="https://bugs.launchpad.net/jokosher/+filebug/", message=_("<big>Couldn't launch the launchpad website automatically.</big>\n\nPlease visit %s to access it."), parent=self.window)
		
	#_____________________________________________________________________

	def Record(self, widget=None):
		"""
		Toggles recording. If there's an error, a warning/error message is 
		issued to the user.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		# toggling the record button invokes this function so we use the settingButtons var to 
		# indicate that we're just changing the GUI state and dont need to do anything code-wise
		if self.settingButtons:
			return
		
		if self.isRecording:
			self.project.Stop()
			return
		
		canRecord = False
		for i in self.project.instruments:
			if i.isArmed:
				canRecord = True

		#Check to see if any instruments are trying to use the same input channel
		usedChannels = []
		armed_instrs = [x for x in self.project.instruments if x.isArmed]
		for instrA in armed_instrs:
			for instrB in armed_instrs:
				if instrA is not instrB and instrA.input == instrB.input and instrA.inTrack == instrB.inTrack:
					string = _("The instruments '%(name1)s' and '%(name2)s' both have the same input selected. Please either disarm one, or connect it to a different input through 'Project -> Recording Inputs'")
					message = string % {"name1" : instrA.name, "name2" : instrB.name}
					dlg = gtk.MessageDialog(self.window,
						gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
						gtk.MESSAGE_INFO,
						gtk.BUTTONS_CLOSE,
						message)
					dlg.connect('response', lambda dlg, response: dlg.destroy())
					dlg.run()
					self.settingButtons = True
					widget.set_active(False)
					self.settingButtons = False
					return

		if not canRecord:
			Globals.debug("can not record")
			if self.project.instruments:
				errmsg = "No instruments are armed for recording. You need to arm an instrument before you can begin recording."
			else:
				errmsg = "No instruments have been added. You must add an instrument before recording"
			dlg = gtk.MessageDialog(self.window,
				gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
				gtk.MESSAGE_INFO,
				gtk.BUTTONS_CLOSE,
				_(errmsg))
			dlg.connect('response', lambda dlg, response: dlg.destroy())
			dlg.run()
			self.settingButtons = True
			widget.set_active(False)
			self.settingButtons = False
		else:
			Globals.debug("can record")
			self.project.Record()

	#_____________________________________________________________________
	
	def TogglePlayIcon(self):
		"""
		Changes the play button icon/tooltip from play to pause and viceversa.
		"""
		if not self.isPlaying:
			self.play.set_stock_id(gtk.STOCK_MEDIA_PLAY)
		else:
			self.play.set_stock_id(gtk.STOCK_MEDIA_PAUSE)
		
		# TODO: change the tooltips in 1.0
		#self.contextTooltips.set_tip(play, tooltip)
		
	#_____________________________________________________________________
	
	def Play(self, widget=None):
		"""
		Toggles playback.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""

		if self.settingButtons == True:
			return 

		self.TogglePlayIcon()
		if not self.isPlaying:
			self.project.Play()
		else:
			self.project.Pause()

	#_____________________________________________________________________

	#The stop button is really just an alias for toggling play/record to off
	def Stop(self, widget=None):
		"""
		Stops the current record/playback (whichever is happening) operation.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""

		self.project.Stop()

	#_____________________________________________________________________

	def OnRewindPressed(self, widget=None):
		"""
		Starts moving backward within the project's timeline.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.project.transport.Reverse(True)
		
	#_____________________________________________________________________
		
	def OnRewindReleased(self, widget=None):
		"""
		Stops the current rewind operation.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.project.transport.Reverse(False)
		
	#_____________________________________________________________________
		
	def OnForwardPressed(self, widget=None):
		"""
		Starts moving forward within the project's timeline.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.project.transport.Forward(True)
		
	#_____________________________________________________________________
		
	def OnForwardReleased(self, widget=None):
		"""
		Stops the current forward operation.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.project.transport.Forward(False)
	
	#_____________________________________________________________________
	
	def OnExport(self, widget=None, profile=None):
		"""
		Displays the Mixdown Profiles dialog, which allows the user to
		(simply) export the project as ogg or mp3 (replacing the old
		export dialog), or create a mixdown profile that does a set of
		complicated things.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		MixdownProfileDialog.MixdownProfileDialog(self, self.project, profile)
		
	#_____________________________________________________________________
		
	def OnExport_old(self, widget=None):
		"""
		Creates and shows a save file dialog which allows the user to export
		the project as ogg or mp3.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		buttons = (gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK)
		chooser = gtk.FileChooserDialog(_("Mixdown Project"), self.window, gtk.FILE_CHOOSER_ACTION_SAVE, buttons)
		if os.path.exists(Globals.settings.general["projectfolder"]):
			chooser.set_current_folder(Globals.settings.general["projectfolder"])
		else:
			chooser.set_current_folder(os.path.expanduser("~"))
		chooser.set_do_overwrite_confirmation(True)
		chooser.set_default_response(gtk.RESPONSE_OK)
		chooser.set_current_name(self.project.name)

		saveLabel = gtk.Label(_("Save as file type:"))		
		typeCombo = gtk.combo_box_new_text()
		
		for format in Globals.EXPORT_FORMATS:
			typeCombo.append_text("%s (.%s)" % (format["description"], format["extension"]))
		#Make the first item the default
		typeCombo.set_active(0)
		
		extraHBox = gtk.HBox()
		extraHBox.pack_start(saveLabel, False)
		extraHBox.pack_end(typeCombo, False)
		extraHBox.show_all()
		chooser.set_extra_widget(extraHBox)
		
		response = chooser.run()
		if response == gtk.RESPONSE_OK:
			exportFilename = chooser.get_filename()
			Globals.settings.general["projectfolder"] = os.path.dirname(exportFilename)
			Globals.settings.write()
			#If they haven't already appended the extension for the 
			#chosen file type, add it to the end of the file.
			filetypeDict = Globals.EXPORT_FORMATS[typeCombo.get_active()]
			if not exportFilename.lower().endswith(filetypeDict["extension"]):
				exportFilename += "." + filetypeDict["extension"]
		
			chooser.destroy()
			self.project.Export(exportFilename, filetypeDict["pipeline"])
		else:
			chooser.destroy()
		
	#_____________________________________________________________________
	
	def UpdateExportDialog(self):
		"""
		Updates the progress bar corresponding to the current export operation.
		"""
		progress = self.project.GetExportProgress()
		if progress[0] == -1 or progress[1] == 0:
			self.exportprogress.set_fraction(0.0)
			self.exportprogress.set_text(_("Preparing to mixdown project"))
		elif progress[0] == progress[1] == 100:
			self.exportdlg.destroy()
			return False
		else:
			self.exportprogress.set_fraction(progress[0]/progress[1])
			self.exportprogress.set_text(_("%(progress)d%% of %(total)d seconds completed") % {"progress":(progress[0]/progress[1]*100), "total":progress[1] } )
			
		return True
	
	#_____________________________________________________________________
	
	def OnExportCancel(self, widget=None):
		"""
		Cancels a running export operation and destroys the export progress dialog.
		
		Parameters:
			widget: reserved for GTK callbacks, don't use it explicitly.
		"""
		self.exportdlg.destroy()
		self.project.TerminateExport()
	
	#_____________________________________________________________________
	
	def OnPreferences(self, widget, destroyCallback=None):
		"""
		Creates and shows the "Jokosher Preferences" dialog.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			destroyCallback -- function that'll get called when the preferences 
								dialog gets destroyed.
		"""
		prefsdlg = PreferencesDialog.PreferencesDialog(self.project, self, self.icon)
			
		if destroyCallback:
			prefsdlg.dlg.connect("destroy", destroyCallback)
	
	#_____________________________________________________________________
	
	def OnShowBarsBeats(self, widget):
		"""
		Sets and updates the current timeline view to Bars, Beats and Ticks.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if self.settingButtons:
			return
		if widget.get_active() and self.project and self.project.transport:
			self.project.SetTransportMode(self.project.transport.MODE_BARS_BEATS)
		
	#_____________________________________________________________________
	
	def OnShowHoursMins(self, widget):
		"""
		Sets and updates the current timeline view to Hours, Minutes and Seconds.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if self.settingButtons:
			return
		if widget.get_active() and self.project and self.project.transport:
			self.project.SetTransportMode(self.project.transport.MODE_HOURS_MINS_SECS)
		
	#_____________________________________________________________________

	def OnOpenProject(self, widget, destroyCallback=None):
		"""
		Creates and shows a open file dialog which allows the user to open
		an existing Jokosher project.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			destroyCallback -- function that'll get called when the open file
								dialog gets destroyed.
		"""
		chooser = gtk.FileChooserDialog((_('Choose a Jokosher project file')), None, gtk.FILE_CHOOSER_ACTION_OPEN, (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK))
		if os.path.exists(Globals.settings.general["projectfolder"]):
			chooser.set_current_folder(Globals.settings.general["projectfolder"])
		else:
			chooser.set_current_folder(os.path.expanduser("~"))

		chooser.set_default_response(gtk.RESPONSE_OK)
		chooser.set_transient_for(self.window)
		allfilter = gtk.FileFilter()
		allfilter.set_name(_("All Files"))
		allfilter.add_pattern("*")
		
		jokfilter = gtk.FileFilter()
		jokfilter.set_name(_("Jokosher Project File (*.jokosher)"))
		jokfilter.add_pattern("*.jokosher")
		
		chooser.add_filter(jokfilter)
		chooser.add_filter(allfilter)
		
		if destroyCallback:
			chooser.connect("destroy", destroyCallback)
		
		while True:
			response = chooser.run()
			
			if response == gtk.RESPONSE_OK:
				
				filename = chooser.get_filename()
				Globals.settings.general["projectfolder"] = os.path.dirname(filename)
				Globals.settings.write()
				if self.OpenProjectFromPath(filename,chooser):
					break
				
			elif response == gtk.RESPONSE_CANCEL or response == gtk.RESPONSE_DELETE_EVENT:
				break

		chooser.destroy()
		
	#_____________________________________________________________________
		
	def OnSaveProject(self, widget=None):
		"""
		Saves the current project file.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""	
		if self.project:
			self.project.SelectInstrument(None)
			self.project.ClearEventSelections()
			self.project.SaveProjectFile()
			
	#_____________________________________________________________________
	
	def OnSaveAsProject(self, widget=None):
		"""
		Creates and shows a save as file dialog which allows the user to save
		the current project to an specific file name.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		buttons = (gtk.STOCK_CANCEL,gtk.RESPONSE_CANCEL,gtk.STOCK_SAVE,gtk.RESPONSE_OK)
		chooser = gtk.FileChooserDialog(_("Choose a location to save the project"), self.window,
		                                gtk.FILE_CHOOSER_ACTION_SAVE, buttons)
		chooser.set_do_overwrite_confirmation(False)
		chooser.set_current_name(self.project.name)
		chooser.set_default_response(gtk.RESPONSE_OK)
		if os.path.exists(Globals.settings.general["projectfolder"]):
			chooser.set_current_folder(Globals.settings.general["projectfolder"])
		else:
			chooser.set_current_folder(os.path.expanduser("~"))


		response = chooser.run()
		if response == gtk.RESPONSE_OK:
			# InitProjectLocation expects a URI	
			folder = PlatformUtils.pathname2url(chooser.get_current_folder())
			
			# Save the selected folder as the default folder
			Globals.settings.general["projectfolder"] = folder
			Globals.settings.write()
			
			name = os.path.basename(chooser.get_filename())
			
			old_audio_path = self.project.audio_path
			old_levels_path = self.project.levels_path
	
			try:
				ProjectManager.InitProjectLocation(folder, name, self.project)
			except ProjectManager.CreateProjectError, e:
				chooser.hide()
				if e.errno == 2:
					message = _("A file or folder with this name already exists. Please choose a different project name and try again.")
				elif e.errno == 3:
					message = _("The file or folder location is write-protected.")
				elif e.errno == 5:
					message = _("The URI scheme given is either invalid or not supported")
				
				# show the error dialog with the relavent error message	
				dlg = gtk.MessageDialog(self.window,
					gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
					gtk.MESSAGE_ERROR,
					gtk.BUTTONS_OK,
					_("Unable to create project.\n\n%s") % message)
				dlg.run()
				dlg.destroy()
			else:
				self.project.SelectInstrument()
				self.project.ClearEventSelections()
				self.project.SaveProjectFile(self.project.projectfile)
				
				Globals.CopyAllFiles(old_audio_path, self.project.audio_path, self.project.GetLocalAudioFilenames())
				Globals.CopyAllFiles(old_levels_path, self.project.levels_path, self.project.GetLevelsFilenames())
		
		chooser.destroy()
		
	#_____________________________________________________________________

	def OnNewProject(self, widget, destroyCallback=None):
		"""
		Creates and shows the "New Project" dialog.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			destroyCallback -- function that'll get called when the new project
								dialog gets destroyed.
		"""
		newdlg = NewProjectDialog.NewProjectDialog(self)
		if destroyCallback:
			newdlg.dlg.connect("destroy", destroyCallback)
		
	#_____________________________________________________________________
		
	def OnCloseProject(self, widget):
		"""
		Closes the current project by calling CloseProject(). 
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if self.CloseProject() == 0:
			self.SetGUIProjectLoaded()
	#_____________________________________________________________________
	
	def CloseProject(self):
		"""
		Closes the current project. If there's changes pending, it'll ask the user for confirmation.
		
		Returns:
			the status of the close operation:
			0 = there was no project open or it was closed succesfully.
			1 = cancel the operation and return to the normal program flow.
		"""
		if not self.project:
			return 0
		
		self.Stop()
		if self.project.CheckUnsavedChanges():
			message = _("<span size='large' weight='bold'>Save changes to project \"%s\" before closing?</span>\n\nYour changes will be lost if you don't save them.") % self.project.name
			
			dlg = gtk.MessageDialog(self.window,
				gtk.DIALOG_MODAL |
				gtk.DIALOG_DESTROY_WITH_PARENT,
				gtk.MESSAGE_WARNING,
				gtk.BUTTONS_NONE)
			dlg.set_markup(message)
			
			dlg.add_button(_("Close _Without Saving"), gtk.RESPONSE_NO)
			dlg.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)
			defaultAction = dlg.add_button(gtk.STOCK_SAVE, gtk.RESPONSE_YES)
			#make save the default action when enter is pressed
			dlg.set_default(defaultAction)
			
			dlg.set_transient_for(self.window)
			
			response = dlg.run()
			dlg.destroy()
			if response == gtk.RESPONSE_YES:
				self.OnSaveProject()
			elif response == gtk.RESPONSE_NO:
				pass
			elif response == gtk.RESPONSE_CANCEL or response == gtk.RESPONSE_DELETE_EVENT:
				return 1
		
		self.project.CloseProject()

		self.project = None
		self.mode = None
		return 0
		
	#_____________________________________________________________________
	
	def OnUndo(self, widget):
		"""
		Undoes the last change made to the project and updates the displays.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.project.Undo()
		
	#_____________________________________________________________________
	
	def OnRedo(self, widget):
		"""
		Redoes the last undo operation and updates the displays.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.project.Redo()

	#_____________________________________________________________________
	
	def OnProjectAudioState(self, project):
		"""
		Callback for when the project starts playing or recording, or when it is
		paused or stopped.
		
		Parameters:
			project -- The project instance that send the signal.
		"""
		self.isPlaying = (self.project.audioState == self.project.AUDIO_PLAYING)
		self.isPaused = (self.project.audioState == self.project.AUDIO_PAUSED)
		self.isRecording = (self.project.audioState == self.project.AUDIO_RECORDING)
		self.stop.set_sensitive(True)	#stop should always be clickable
		self.record.set_sensitive(not self.isPlaying)
		
		controls = (self.play, self.reverse, self.forward, self.editmenu, self.instrumentMenu, 
				self.workspace.recordingView.timelinebar.headerhbox, 
				self.addInstrumentButton, self.addAudioFileButton)
		for widget in controls:
			widget.set_sensitive(not self.isRecording)
		
		self.settingButtons = True
		self.record.set_active(self.isRecording)
		self.TogglePlayIcon()
		self.settingButtons = False
		
		# update the tooltips depending on the current recording state
		if self.isRecording:
			self.record.set_tooltip_text(self.recTipEnabled)
			self.stop.set_tooltip_text(self.recStopTipEnabled)
		else:
			self.record.set_tooltip_text(self.recTipDisabled)
			self.stop.set_tooltip_text(self.recStopTipDisabled)
		
		self.workspace.mixView.StartUpdateTimeout()
	
	#_____________________________________________________________________
	
	def OnProjectExportStart(self, project):
		"""
		Callback for when the project starts exporting audio to a file.
		
		Parameters:
			project -- The project instance that send the signal.
		"""
		export = gtk.glade.XML (Globals.GLADE_PATH, "ProgressDialog")
		export.signal_connect("on_cancel_clicked", self.OnExportCancel)
		
		self.exportdlg = export.get_widget("ProgressDialog")
		self.exportdlg.set_icon(self.icon)
		self.exportdlg.set_transient_for(self.window)
		
		label = export.get_widget("progressLabel")
		label.set_text(_("Mixing project to file: %s") % self.project.exportFilename)
		
		self.exportprogress = export.get_widget("progressBar")
		
		gobject.timeout_add(100, self.UpdateExportDialog)
		
	#_____________________________________________________________________
	
	
	def OnProjectExportStop(self, project):
		"""
		Callback for when the project has finished exporting audio to a file.
		
		Parameters:
			project -- The project instance that send the signal.
		"""
		if self.exportdlg:
			self.exportdlg.destroy()
	
	#_____________________________________________________________________
	
	def OnProjectUndo(self, project=None):
		"""
		Callback for when the project's undo or redo stacks change.
		
		Parameters:
			project -- The project instance that send the signal.
		"""
		self.undo.set_sensitive(self.project.CanPerformUndo())
		self.redo.set_sensitive(self.project.CanPerformRedo())
	
		if self.project.CheckUnsavedChanges():
			self.window.set_title(_('*%s - Jokosher') % self.project.name)
		else:
			self.window.set_title(_('%s - Jokosher') % self.project.name)
		
	#_____________________________________________________________________
	
	def OnTransportMode(self, transportManager=None, mode=None):
		"""
		Callback for signal when the transport mode changes.
		
		Parameters:
			transportManager -- the TransportManager instance that send the signal.
			mode -- the mode type that the transport changed to.
		"""
		if self.settingButtons:
			return
		self.settingButtons = True
		modeBars = self.wTree.get_widget("show_as_bars_beats_ticks")
		modeHours = self.wTree.get_widget("show_as_hours_minutes_seconds")
		transport = self.project.transport
		
		modeBars.set_active(transport.mode == transport.MODE_BARS_BEATS)
		modeHours.set_active(transport.mode == transport.MODE_HOURS_MINS_SECS)
		
		self.settingButtons = False
		
	#_____________________________________________________________________

	def InsertRecentProject(self, path, name):
		"""
		Inserts a new project with its corresponding path to the recent project list.
		
		Parameters:
			path -- path to the project file.
			name -- name of the project being added.
		"""
		for item in self.recentprojectitems:
			if path == item[0]:
				self.recentprojectitems.remove(item)
				break
		
		self.recentprojectitems.insert(0, (path, name))
		self.SaveRecentProjects()
		self.PopulateRecentProjects()

	#_____________________________________________________________________
	
	def OnClearRecentProjects(self, widget):
		"""
		Clears the recent projects list. It then updates the user interface to reflect
		the changes.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.recentprojectitems = []
		self.SaveRecentProjects()
		self.PopulateRecentProjects()
		
	#_____________________________________________________________________
	
	def PopulateRecentProjects(self):
		"""
		Populates the Recent Projects menu with items from self.recentprojectitems.
		"""	
		menuitems = self.recentprojectsmenu.get_children()
		for c in menuitems:
			self.recentprojectsmenu.remove(c)
		
		if self.recentprojectitems:
			for item in self.recentprojectitems:
				mitem = gtk.MenuItem(item[1])
				mitem.set_tooltip_text(item[0])
				self.recentprojectsmenu.append(mitem)
				mitem.connect("activate", self.OnRecentProjectsItem, item[0], item[1])
			
			mitem = gtk.SeparatorMenuItem()
			self.recentprojectsmenu.append(mitem)
			
			mitem = gtk.ImageMenuItem(gtk.STOCK_CLEAR)
			mitem.set_tooltip_text(_("Clear the list of recent projects"))
			self.recentprojectsmenu.append(mitem)
			mitem.connect("activate", self.OnClearRecentProjects)
			
			self.recentprojects.set_sensitive(True)
			self.recentprojectsmenu.show_all()
		else:
			#there are no items, so just make it insensitive
			self.recentprojects.set_sensitive(False)
		
	#_____________________________________________________________________
	
	def OpenRecentProjects(self):
		"""
		Populate the self.recentprojectpaths with items from global settings.
		"""
		self.recentprojectitems = []
		if Globals.settings.general.has_key("recentprojects"):
			filestring = Globals.settings.general["recentprojects"]
			filestring = filestring.split(",")
			recentprojectitems = []
			for i in filestring:
				if len(i.split("|")) == 2:
					recentprojectitems.append(i.split("|"))	
					
			for path, name in recentprojectitems:
				#TODO - see ticket 80; should it check if the project is valid?
				if not os.path.exists(path):
					Globals.debug("Error: Couldn't open recent project", path)
				else:
					self.recentprojectitems.append((path, name))
			
			#the first project is our last opened project
			if recentprojectitems and os.path.exists(recentprojectitems[0][0]):
				self.lastopenedproject = recentprojectitems[0]
			
		self.SaveRecentProjects()

	#_____________________________________________________________________
	
	def OnRecentProjectsItem(self, widget, path, name):
		"""
		Opens the project selected from the "Recent Projects" drop-down menu.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			path -- path to the project file.
			name -- name of the project being opened.
		"""
		return self.OpenProjectFromPath(path)

	#_____________________________________________________________________

	def SaveRecentProjects(self):
		"""
		Saves the list of the last 8 recent projects to the Jokosher config file.
		"""
		string = ""

		# Cut list to 8 items
		self.recentprojectitems = self.recentprojectitems[:8]
		
		for path, name in self.recentprojectitems:
			string = string + str(path) + "|" + str(name) + ","
			
		string = string[:-1]
		Globals.settings.general['recentprojects'] = string
		Globals.settings.write()
		
	#______________________________________________________________________
	
	def OnCut(self, widget=None, cut=True):
		"""
		Cuts the portion of selected audio and puts it in the clipboard.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			cut --  determines whether the operation should perform a cut or copy operation:
					True = perform a cut operation.
					False = perform a copy operation.
		"""
		if self.isPlaying or self.isPaused:
			return
		
		if self.instrNameEntry:
			#if an instrument name is currently being edited
			if cut:
				self.instrNameEntry.cut_clipboard()
			else:
				self.instrNameEntry.copy_clipboard()
			return
	
		#Wipe the clipboard clean
		self.project.clipboardList = []
		for instr in self.project.instruments:
			for event in instr.events:
				if event.isSelected:
					#Add to the clipboard
					self.project.clipboardList.append(event)
					if cut:
						#if we are cutting (as opposed to copying)
						event.Delete()
	
	#______________________________________________________________________
	
	def OnCopy(self, widget=None):
		"""
		Copies the portion of selected audio to the clipboard.	
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.OnCut(widget, False)
	
	#______________________________________________________________________
	
	def OnPaste(self, widget=None):
		"""
		Pastes the portion of audio in the clipboard to the selected instrument,
		at the selected position in time.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if self.isPlaying or self.isPaused:
			return
		
		if self.instrNameEntry:
			#if an instrument name is currently being edited
			self.instrNameEntry.paste_clipboard()
			return
	
		for instr in self.project.instruments:
			if instr.isSelected:
				for event in self.project.clipboardList:
					instr.addEventFromEvent(0, event)
				break
	
	#______________________________________________________________________
	
	def OnDelete(self, widget=None):
		"""
		Deletes the currently selected instruments or events.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if self.project.GetIsRecording() or self.isPlaying or self.isPaused:
			return
		
		# list to store instruments to delete, so we don't modify the list while we are iterating
		instrOrEventList = []
		eventList = []
		# Delete any select instruments
		for instr in self.project.instruments:
			if (instr.isSelected):
				#set not selected so when we undo we don't get two selected instruments
				instr.isSelected = False
				instrOrEventList.append(instr)
			else:
				# Delete any selected events
				for ev in instr.events:
					if ev.isSelected:
						instrOrEventList.append(ev)

		if instrOrEventList:
			self.project.DeleteInstrumentsOrEvents(instrOrEventList)
	
	#______________________________________________________________________

	def OnMouseDown(self, widget, mouse):
		"""
		If there's a project open, clears event and instrument selections.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			mouse -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if self.project:
			self.project.ClearEventSelections()
			self.project.SelectInstrument(None)
		
	#______________________________________________________________________
	
	def SetGUIProjectLoaded(self):
		"""
		Refreshes the main window and it's components when a project is opened or closed.
		For example, buttons are enabled/disabled whether there's a project currently open or not. 
		"""
		children = self.main_vbox.get_children()
		if self.workspace in children:
			self.main_vbox.remove(self.workspace)
		
		if self.headerhbox in children:
			self.main_vbox.remove(self.headerhbox)
		if self.tvtoolitem in self.toolbar.get_children():
			self.toolbar.remove(self.tvtoolitem)
		
		ctrls = (self.save, self.save_as, self.close, self.addInstrumentButton, self.addAudioFileButton,
			self.reverse, self.forward, self.play, self.stop, self.record,
			self.instrumentMenu, self.export, self.cut, self.copy, self.paste,
			self.undo, self.redo, self.delete, self.compactMixButton, self.properties_menu_item,
			self.addAudioFileMenuItem, self.addInstrumentFileMenuItem, self.recordingInputsFileMenuItem,
			self.timeFormatFileMenuItem)
		
		if self.project:
			# make various buttons and menu items enabled now we have a project option
			for c in ctrls:
				c.set_sensitive(True)
			
			
			#set undo/redo if there is saved undo history
			self.OnProjectUndo()
				
			# Create our custom widgets
			self.timeview = TimeView.TimeView(self.project)
			self.workspace = Workspace.Workspace(self.project, self)
			
			# Add them to the main window
			self.main_vbox.pack_start(self.workspace, True, True)
			
			self.tvtoolitem = gtk.ToolItem()
			self.tvtoolitem.add(self.timeview)
			self.toolbar.insert(self.tvtoolitem, -1)
			self.tvtoolitem.show_all()
			
			#reset toggle buttons
			self.settingButtons = True
			self.compactMixButton.set_active(False)
			self.settingButtons = False
			
		else:
			#reset toggle buttons when the project is unloaded
			self.settingButtons = True
			self.compactMixButton.set_active(False)
			self.settingButtons = False

			for c in ctrls:
				c.set_sensitive(False)
			
			
			# Set window title with no project name
			self.window.set_title(_('Jokosher'))
			
			# Destroy our custom widgets
			if self.workspace:
				self.workspace.destroy()
				self.workspace = None
			if self.tvtoolitem:
				self.tvtoolitem.destroy()
				self.tvtoolitem = None

	#_____________________________________________________________________
	
	def OnKeyPress(self, widget, event):
		"""
		Handles the hotkeys, calling whichever function they are assigned to.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
			event -- reserved for GTK callbacks, don't use it explicitly.
		"""
		key = gtk.gdk.keyval_name(event.keyval)
		
		if 'GDK_CONTROL_MASK' in event.state.value_names:
			keysdict = {
				"x"	: self.OnCut, # Ctrl-X
				"c"	: self.OnCopy, # Ctrl-C
				"v"	: self.OnPaste, # Ctrl-V
			}
		else:
			keysdict = {
				"F1"			: self.OnHelpContentsMenu, # F1 - Help Contents
				"F3"			: self.OnF3Pressed, # F3 - Compact Mix View
				"Delete"		: self.OnDelete, # delete key - remove selected item
				"BackSpace" 	: self.OnDelete, # backspace key
				"space"		: self.Play,
				"p"			: self.Play,
				"r"			: self.Record
			}	
		
		if key in keysdict:
			keysdict[key]()
			#very important; return True if we successfully handled the key press
			#so that someone else doesn't handle it afterwards as well.
			return True
		else:
			return False
		
	#_____________________________________________________________________
	
	def OnInstrumentConnectionsDialog(self, widget):
		"""
		Creates and shows the "Instrument Connections Dialog".
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		InstrumentConnectionsDialog.InstrumentConnectionsDialog(self.project, self)
		
	#_____________________________________________________________________
	
	def OnFileMenu(self, widget):
		"""
		When the file menu opens, check if there are any events and set the mixdown project menu item's
		sensitivity accordingly and also the 'mixdown as' sensitivity.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.PopulateMixdownAsMenu()
		if self.isRecording:
			self.export.set_sensitive(False)
			self.addInstrumentFileMenuItem.set_sensitive(False)
			self.addAudioFileMenuItem.set_sensitive(False)
			self.recordingInputsFileMenuItem.set_sensitive(False)
			if self.mixdown_as_header:
				self.mixdown_as_header.set_sensitive(False)
			return
		
		eventList = False
		if self.project:
			self.addInstrumentFileMenuItem.set_sensitive(True)
			self.addAudioFileMenuItem.set_sensitive(True)
			self.recordingInputsFileMenuItem.set_sensitive(True)
			for instr in self.project.instruments:
				if instr.events:
					eventList = True
					break
		self.export.set_sensitive(eventList)
		if self.mixdown_as_header:
			self.mixdown_as_header.set_sensitive(eventList)
			
	#_____________________________________________________________________
	
	def OnEditMenu(self, widget):
		"""
		HACK: When the edit menu opens, checks if any events or instruments are selected 
		and sets the cut, copy, paste and delete menu items sensitivity accordingly.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		instrSelected = False
		eventSelected = False
		if self.project:
			for instr in self.project.instruments:
				if instrSelected and eventSelected:
					break
				if instr.isSelected:
					instrSelected = True
				else:
					for ev in instr.events:
						if ev.isSelected:
							eventSelected = True
		
		self.cut.set_sensitive(eventSelected)
		self.copy.set_sensitive(eventSelected)
		self.paste.set_sensitive(instrSelected and bool(self.project.clipboardList))
		self.delete.set_sensitive(instrSelected or eventSelected)
	
	#_____________________________________________________________________
	
	def OnInstrumentMenu(self, widget):
		"""
		HACK: When the instrument menu opens, set sensitivity depending on
		whether there's a selected instrument or not.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		
		instrCount = 0
		if self.project:
			for instr in self.project.instruments:
				if instr.isSelected:
					instrCount += 1
		
		self.addAudioMenuItem.set_sensitive(instrCount == 1)
		self.changeInstrMenuItem.set_sensitive(instrCount == 1)
		self.removeInstrMenuItem.set_sensitive(instrCount > 0)
	
	#_____________________________________________________________________

	def OpenProjectFromPath(self,path, parent=None):
		"""
		Opens the project file referred by the path parameter.
		
		Parameters:
			path -- path to the project to be opened.
			parent -- parent window of the error message dialog.
		
		Returns:
			the status of the loading operation:
			True = the project could be successfully opened and 
			  		set as the current project.
			False = loading the project failed. A dialog will be
					displayed to user detailing the error.
		"""
		try:
			uri = PlatformUtils.pathname2url(path)
			self.SetProject(ProjectManager.LoadProjectFile(uri))
			return True
		except ProjectManager.OpenProjectError, e:
			self.ShowOpenProjectErrorDialog(e,parent)
			return False

	#_____________________________________________________________________
	
	def SetProject(self, project):
		"""
		Tries to establish the Project parameter as the current project.
		If there are errors, an error message is issued to the user.
		
		Parameters:
			project -- the Project object to set as the main project.
		"""
		try:
			ProjectManager.ValidateProject(project)
		except ProjectManager.InvalidProjectError, e:
			message=""
			if e.files:
				message+=_("The project references non-existant files:\n")
				for f in e.files:
					message += f + "\n"
			if e.images:
				message+=_("\nThe project references non-existant images:\n")
				for f in e.images:
					message += f + "\n"

			dlg = gtk.MessageDialog(self.window,
				gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
				gtk.MESSAGE_ERROR,
				gtk.BUTTONS_OK,
				_("%s\n Invalid or corrupt project file, will not open.")%message)
			dlg.run()
			dlg.destroy()
			return

		if self.project:
			if self.CloseProject() != 0:
				return
			
		self.project = project
		
		self.project.connect("audio-state::play", self.OnProjectAudioState)
		self.project.connect("audio-state::pause", self.OnProjectAudioState)
		self.project.connect("audio-state::record", self.OnProjectAudioState)
		self.project.connect("audio-state::stop", self.OnProjectAudioState)
		self.project.connect("audio-state::export-start", self.OnProjectExportStart)
		self.project.connect("audio-state::export-stop", self.OnProjectExportStop)
		self.project.connect("undo", self.OnProjectUndo)
		
		self.project.transport.connect("transport-mode", self.OnTransportMode)
		self.OnTransportMode()
		self.InsertRecentProject(project.projectfile, project.name)
		self.project.PrepareClick()

		# make various buttons and menu items enabled now we have a project
		self.SetGUIProjectLoaded()
		
	#_____________________________________________________________________
	
	def CheckGstreamerVersions(self):
		"""
		Check for CVS versions of Gstreamer and gnonlin. If requirements are not met,
		a warning message is issued to the user.
		"""
		#Check for CVS versions of Gstreamer and gnonlin
		message = ""
		gstVersion = gst.version()
		if ((gstVersion[1] <= 10 and gstVersion[2] < 9) or gstVersion[1] < 10):
			message += _("You must have Gstreamer version 0.10.9 or higher.\n")
		gnl = gst.registry_get_default().find_plugin("gnonlin")
		if gnl:
			ignored, gnlMajor, gnlMinor = gnl.get_version().split(".", 2)
			#Compare gnlMajor and gnlMinor as a float so later versions of gnonlin will work
			gnlMajor = float(gnlMajor)
			gnlMinor = float(gnlMinor)
			if gnlMajor < 10 or gnlMinor < 4.2:
				message += _("You must have Gstreamer plugin gnonlin version 0.10.4.2 or later.\n")
		elif not gnl:
			message += _("Gstreamer plugin gnonlin is not installed.") + \
			_("\nSee http://doc.jokosher.org/Installation for more details.\n")

		if not gst.registry_get_default().find_plugin("level"):
			message += _("You must have the Gstreamer plugin packs gst-plugins-base and gst-plugins-good installed.\n")
		if message:
			dlg = gtk.MessageDialog(self.window,
				gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
				gtk.MESSAGE_WARNING,
				gtk.BUTTONS_CLOSE)
			dlg.set_markup(_("<big>Some functionality will not work correctly or at all.</big>\n\n%s") % message)
			dlg.run()
			dlg.destroy()
	
	#_____________________________________________________________________

	def SetStatusBar(self, message):
		"""
		Appends the message parameter to the status bar text.
		
		Parameters:
			message -- string to append to the status bar text.
		"""
		return self.statusbar.Push(message)
	
	#_____________________________________________________________________

	def ClearStatusBar(self, messageID):
		"""
		Clears the status bar text in the position pointed by messageID.
		
		Parameters:
			messageID -- the message identifier of the text to be cleared.
		"""
		self.statusbar.Remove(messageID)
	
	#_____________________________________________________________________

	def OnHelpContentsMenu(self, widget=None):
		"""
		Calls the appropiate help tool with the user manual in the correct
		locale.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if gtk.pygtk_version[0] == 2 and gtk.pygtk_version[1] < 14:
			helpfile = "http://doc.jokosher.org"
		elif Globals.USE_LOCAL_HELP:
			helpfile = "ghelp:" + Globals.HELP_PATH
		else:
			helpfile = "ghelp:jokosher"
	
		Utils.OpenExternalURL(url=helpfile, message=_("<big>Couldn't launch the Jokosher documentation site.</big>\n\nPlease visit %s to access it."), parent=self.window)

	#_____________________________________________________________________

	def OnForumsMenu(self, widget):
		"""
		Opens the Jokosher forum in the user's default web browser.

		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		Utils.OpenExternalURL(url="http://www.jokosher.org/forums", message=_("<big>Couldn't launch the forums website automatically.</big>\n\nPlease visit %s to access them."), parent=self.window)
		
	#_____________________________________________________________________

	def OnContributingDialog(self, widget):
		"""
		Creates and shows the "Contributing to Jokosher" dialog.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		self.contribTree = gtk.glade.XML(Globals.GLADE_PATH, "ContributingDialog")
		
		# grab references to the ContributingDialog window and vbox
		self.contribdialog = self.contribTree.get_widget("ContributingDialog")
		self.contribvbox = self.contribTree.get_widget("vbox14")
		self.contribdialog.set_icon(self.icon)

		# centre the ContributingDialog window on MainWindow
		self.contribdialog.set_transient_for(self.window)

		# set the contributing image
		self.topimage = self.contribTree.get_widget("topimage")
		self.topimage.set_from_file(os.path.join(Globals.IMAGE_PATH, "jokosher-logo.png"))

		# create the bottom vbox containing the contributing website link
		vbox = gtk.VBox()			
		label = gtk.Label()
		label.set_markup(_("<b>To find out more, visit:</b>"))
		vbox.pack_start(label, False, False)
		
		if gtk.pygtk_version >= (2, 10, 0) and gtk.gtk_version >= (2, 10, 0):
			contriblnkbtn = gtk.LinkButton("http://www.jokosher.org/contribute", label="http://www.jokosher.org/contribute")
			contriblnkbtn.connect("clicked", self.OnContributingLinkButtonClicked)
			vbox.pack_start(contriblnkbtn, False, False)
		else:
			vbox.pack_start(gtk.Label("http://www.jokosher.org/contribute"), False, False)
		
		self.contribvbox.pack_start(vbox, False, False)
		self.contribdialog.show_all()

	#_____________________________________________________________________

	def OnContributingLinkButtonClicked(self, widget):
		"""
		Opens the Jokosher contributing website in the user's default web browser.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		Utils.OpenExternalURL(url="http://www.jokosher.org/contribute", 
			message=_("<big>Couldn't launch the contributing website automatically.</big>\n\nPlease visit %s to access it."), parent=self.window)
	
	#_____________________________________________________________________
	
	def GetDistroVersion(self):
		"""
		Obtain a string with the distribution name and version.
		
		Returns:
			A string with the distribution name and version.
		"""
		versionStr = ""
		try:
			#distro name
			output = Popen(args=["lsb_release", "-i"], stdout=PIPE).stdout.read()
			versionStr += output[output.find("\t")+1:len(output)-1]
			
			#distro version
			output = Popen(args=["lsb_release", "-r"], stdout=PIPE).stdout.read()
			versionStr += " " + output[output.find("\t")+1:len(output)-1]
		except OSError:
			versionStr = None
	
		return versionStr
	
	#_____________________________________________________________________
	
	def OnSystemInformation(self, widget):
		"""
		Displays a small window with the system information.
		
		Parameters:
			widget -- Gtk callback parameter.
		"""
		self.sysInfoTree = gtk.glade.XML(Globals.GLADE_PATH, "SystemInformationDialog")
		
		# grab references to the SystemInformationDialog window and vbox
		self.sysInfoDialog = self.sysInfoTree.get_widget("SystemInformationDialog")
		self.gstVersionStr = self.sysInfoTree.get_widget("labelGStreamerVersion")
		self.gnonlinVersionStr = self.sysInfoTree.get_widget("labelGnonlinVersion")
		self.distroVersionStr = self.sysInfoTree.get_widget("labelDistributionVersion")
		sysInfoCloseButton = self.sysInfoTree.get_widget("closeButton")
	
		#connect the close button
		sysInfoCloseButton.connect("clicked", lambda dialog: self.sysInfoDialog.destroy())
	
		#set the version strings to the appropriate value
		gstVersion = "%s.%s.%s.%s" % gst.version()
		self.gstVersionStr.set_text(gstVersion)
		
		gnlVersion = gst.registry_get_default().find_plugin("gnonlin")
		if gnlVersion:
			ignored, gnlMajor, gnlMinor = gnlVersion.get_version().split(".", 2)		
			message = "%s.%s" % (gnlMajor, gnlMinor)
		elif not gnlVersion:
			message += _("Gnonlin is missing!")
		self.gnonlinVersionStr.set_text(message)
		
		distroVersion = self.GetDistroVersion()
		if distroVersion is not None:
			self.distroVersionStr.set_text(distroVersion)
		else:
			self.distroVersionStr.set_text(_("Unknown"))
	
	#_____________________________________________________________________

	def ShowOpenProjectErrorDialog(self, error, parent=None):
		"""
		Creates and shows a dialog to inform the user about an error that has ocurred.
		
		Parameters:
			error -- string with the error(s) description.
			parent -- parent window of the error message dialog.
		"""
		if not parent:
			parent = self.window

		if error.errno == 1:
			message = _("The URI scheme '%s' is either invalid or not supported.") % error.info
		elif error.errno == 2:
			message = _("Unable to unzip the project file %s") % error.info
		elif error.errno == 3:		
			message = _("The project file was created with version \"%s\" of Jokosher.\n") % error.info + \
					  _("Projects from version \"%s\" are incompatible with this release.\n") % error.info
		elif error.errno == 4:
			message = _("The project:\n%s\n\ndoes not exist.\n") % error.info
		elif error.errno == 5:
			first = _("The project file could not be opened.\n")
			second = _("It is recommended that you report this to the Jokosher developers or get help at http://www.jokosher.org/forums/")
			message = "%s\n%s\n\n%s" % (first, second, error.info)
		else:
			message = _("The project file could not be opened.\n")

			
		dlg = gtk.MessageDialog(parent,
			gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
			gtk.MESSAGE_ERROR,
			gtk.BUTTONS_OK,
			message)
		dlg.set_icon(self.icon)
		dlg.run()
		dlg.destroy()
	
	#_____________________________________________________________________

	def OnExtensionManagerDialog(self, widget):
		"""
		Creates and shows the "Extension Manager" dialog.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		ExtensionManagerDialog.ExtensionManagerDialog(self)
	
	#_____________________________________________________________________

	def OnAddAudio(self, widget):
		"""
		Adds an audio file to the selected Instrument.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		instrID = None
		for instr in self.project.instruments:
			if instr.isSelected:
				instrID = instr.id
				break
		
		if instrID != None:
			for id, instrViewer in self.workspace.recordingView.views:
				if instrID == id:
					instrViewer.eventLane.CreateEventFromFile()
		
	#_____________________________________________________________________

	def OnRemoveInstrument(self, widget):
		"""
		Removes all selected Instruments from the Project.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		# list to store instruments to delete, so we don't modify the list while we are iterating
		instrList = []
		for instr in self.project.instruments:
			if instr.isSelected:
				#set not selected so when we undo we don't get two selected instruments
				instr.isSelected = False
				instrList.append(instr)
		
		if instrList:
			self.project.DeleteInstrumentsOrEvents(instrList)
	
	#_____________________________________________________________________
	
	def ShowImportFileChooser(self):
		"""
		Creates a file chooser dialog and gets the filename to be imported,
		as well as if the file should be copied to the project folder or not.
		
		Returns:
			A 2-tuple containing the a list of file paths to be imported and a boolean
			that will be true if the user requested the file to be copied to the project folder.
			Both entries in the tuple will be None is the dialog was cancelled.
		"""
		buttons = (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL, gtk.STOCK_OPEN, gtk.RESPONSE_OK)

		copyfile = gtk.CheckButton(_("Copy file to project"))
		# Make it copy files to audio dir by default
		copyfile.set_active(True)
		copyfile.show()

		dlg = gtk.FileChooserDialog(_("Add Audio File..."), action=gtk.FILE_CHOOSER_ACTION_OPEN, buttons=buttons)
		dlg.set_default_response(gtk.RESPONSE_OK)
		dlg.set_icon(self.icon)
		if os.path.exists(Globals.settings.general["projectfolder"]):
			dlg.set_current_folder(Globals.settings.general["projectfolder"])
		else:
			dlg.set_current_folder(os.path.expanduser("~"))
		dlg.set_extra_widget(copyfile)
		dlg.set_select_multiple(True)
		
		vbox = gtk.VBox()
		audiopreview = AudioPreview.AudioPreview()
		vbox.pack_start(audiopreview, True, False)
		vbox.show_all()
		
		dlg.set_preview_widget(vbox)
		dlg.set_use_preview_label(False)
		dlg.connect("selection-changed", audiopreview.OnSelection)
		
		response = dlg.run()
		if response == gtk.RESPONSE_OK:
			#stop the preview audio from playing without destorying the dialog
			audiopreview.OnDestroy()
			dlg.hide()
			Globals.settings.general["projectfolder"] = os.path.dirname(dlg.get_filename())
			Globals.settings.write()
			filenames = dlg.get_filenames()
			copyfileBool = copyfile.get_active()
			dlg.destroy()
			
			return (filenames, copyfileBool)
		
		dlg.destroy()
		return (None, None)

	#_____________________________________________________________________

	def OnAddAudioFile(self, widget=None):
		"""
		Called when the "Add Audio File Instrument" in the project menu is clicked.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		
		filenames, copyfile = self.ShowImportFileChooser()
		#check if None in case the user click cancel on the dialog.
		if filenames:
			self.project.AddInstrumentAndEvents(filenames, copyfile)
		
	#_____________________________________________________________________

	def PopulateMixdownAsMenu(self):
		"""
		If there are any saved mixdown profiles, create a Mixdown As submenu in
		the file menu and add links to them.
		"""
		self.mixdown_as_header = None
		savefolder = os.path.join(Globals.JOKOSHER_DATA_HOME, 'mixdownprofiles') # created by Globals
		profiles = os.listdir(savefolder)
		if not profiles: return
		
		# remove any old mixdown profiles
		for item in profiles:
			if not item.endswith(".profile"):
				path = os.path.join(Globals.MIXDOWN_PROFILES_PATH, item)
				os.remove(path)
				break
		profiles = os.listdir(savefolder)
			
		filemenulist = self.filemenu.get_submenu()
		# If there's already a Mixdown As submenu, delete it and recreate it
		for i in filemenulist.get_children():
			if i.get_children():
				if i.get_children()[0].get_label() == _("Mix_down As"):
					filemenulist.remove(i)
					i.destroy()
		
		# Create a Mixdown As submenu header
		self.mixdown_as_header = gtk.MenuItem(label=_("Mix_down As"))
		submenu = gtk.Menu()
		for p in profiles:
			profilenames = p.split(".")[0]
			menuitem = gtk.MenuItem(label=profilenames)
			menuitem.connect("activate", self.OnExport, profilenames)
			submenu.append(menuitem)
		self.mixdown_as_header.set_submenu(submenu)
		# insert it after Mixdown Project
		counter = 0
		insert_position = None
		for i in filemenulist.get_children():
			if i.get_children():
				if i.get_children()[0].get_label() == _("_Mixdown Project..."):
					insert_position = counter
			counter += 1
		if insert_position:
			self.filemenu.get_submenu().insert(self.mixdown_as_header,insert_position + 1)
			
		self.filemenu.show_all()
		
	#_____________________________________________________________________
	
	def OnProjectProperties(self, widget=None):
		"""
		Called when the "Properties..." in the project menu is clicked.
		
		Parameters:
			widget -- reserved for GTK callbacks, don't use it explicitly.
		"""
		if not self.project:
			return
		
		propertiesTree = gtk.glade.XML(Globals.GLADE_PATH, "ProjectPropertiesDialog")
		dlg = propertiesTree.get_widget("ProjectPropertiesDialog")
		nameEntry = propertiesTree.get_widget("nameEntry")
		authorEntry = propertiesTree.get_widget("authorEntry")
		notesTextView = propertiesTree.get_widget("notesTextView")
		
		nameEntry.set_text(self.project.name)
		authorEntry.set_text(self.project.author)
		buffer = gtk.TextBuffer()
		buffer.set_text(self.project.notes)
		notesTextView.set_buffer(buffer)
		
		dlg.connect("response", self.OnProjectPropertiesClose, nameEntry, authorEntry, notesTextView)
		dlg.show_all()
		
	#_____________________________________________________________________
		
	def OnProjectPropertiesClose(self, dialog, response, nameEntry, authorEntry, notesTextView):
		"""
		Called when the "Project Properties" windows is closed.
		
		Parameters:
			dialog -- reserved for GTK callbacks, don't use it explicitly.
		"""
		
		if self.project and response == gtk.RESPONSE_CLOSE:
			name = nameEntry.get_text()
			author = authorEntry.get_text()
			buffer = notesTextView.get_buffer()
			notes = buffer.get_text(*buffer.get_bounds())
			
			self.project.SetName(name)
			self.project.SetAuthor(author)
			self.project.SetNotes(notes)
				
		dialog.destroy()

	#_____________________________________________________________________
#=========================================================================

def main():
	"""
	Main entry point for Jokosher.
	"""	
	MainApp()
	gobject.threads_init()
	gtk.main()

if __name__ == "__main__":
	main()
