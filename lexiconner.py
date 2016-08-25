#!/usr/bin/python
import csv
import time
import sqlite3
import threading
import random
import gtk
import appindicator
import pynotify
from Queue import Queue
import os

APP_NAME = 'Lexiconner'
HOME_DIR = os.getenv("HOME") 
CONFIG_DIR = os.path.join(HOME_DIR, '.config', APP_NAME)
DATABASE_FILE = os.path.join(CONFIG_DIR, APP_NAME + '.db')


pynotify.init(APP_NAME)
gtk.gdk.threads_init()

class safeDatabase(threading.Thread):
    def __init__(self, db):
        super(safeDatabase, self).__init__()
        self.db=db
        self.reqs=Queue()
        self.start()
    def run(self):
        cnx = sqlite3.connect(self.db) 
        cursor = cnx.cursor()
        while True:
            req, arg, res = self.reqs.get()
            if req == '--close--':
            	break
            cursor.execute(req, arg)
            if res:
                for rec in cursor:
                    res.put(rec)
                res.put('--no more--')
        cnx.commit()			#Don't forget this
        cnx.close()
    def execute(self, req, arg=None, res=None):
        self.reqs.put((req, arg or tuple(), res))
    def select(self, req, arg=None):
        res=Queue()
        self.execute(req, arg, res)
        while True:
            rec=res.get()
            if rec=='--no more--': break
            yield rec
    def close(self):
        self.execute('--close--')  


class NotecardsHandler():
	"""Handles a notecard database.
	"""
	def __init__(self, database_file):
		"""Sets up a sqlite datbase object
		"""
		self.database = safeDatabase(database_file)
		#Check if we have the table
		self.create_table()

	def create_table(self):
		"""Creates a table called notecard_table in the database with the appropriate columns.
		"""
		self.database.execute("""CREATE TABLE IF NOT EXISTS notecard_table 
								(id 	INT 		PRIMARY KEY 	NOT NULL,
								front 	CHAR(50)					NOT NULL,
								back 	TEXT						NOT NULL);""")

	def get_smallest_avialable_id(self):
		"""This function starts at 0 and returns the smallest possible id no.
		"""
		#I am just too lazy to do this more efficiently
		ls = [row[0] for row in  self.database.select("SELECT id FROM notecard_table")]	#Get all ids
		possible_id = 0 					#Start with 0
		while True:
			if possible_id not in ls:
				return possible_id
			possible_id += 1

	def add_notecard(self, _id, front, back):
		"""This function adds a note card to the database and returns the value of the id column.
		"""
		self.database.execute("INSERT INTO notecard_table (id, front, back)\
								VALUES (?,?,?);", [_id, front, back])
		return _id

	def delete_notecard(self, _id):
		"""Deletes a notecard by id.
		"""
		self.database.execute("DELETE FROM notecard_table WHERE id=?", [_id])

	def get_all_notecards(self):
		return [ i for i in self.database.select("SELECT * FROM notecard_table")]

	def get_notecard_by_id(self, _id):
		return self.database.select("SELECT front,back FROM notecard_table WHERE id=?", [_id]).next()

	def edit_notecard(self, _id, front=None, back=None):
		current_front, current_back = self.get_notecard_by_id(_id)

		#This is to make sure the values aren't set to nothing
		front = front or current_front
		back = back or current_back

		self.database.execute("UPDATE notecard_table SET front=?, back=? WHERE id=?", [front, back, _id])

	def lookup(self, front):
		"""This function looks up the front of a notecard and returns the back.
		"""
		return self.database.select("SELECT back FROM notecard_table WHERE front =?", [front]).next() or ""

	def random_notecard(self):
		"""This function returns a tuple (front, back), choosing randomly from database.
		"""
		return self.database.select("SELECT front, back FROM notecard_table ORDER BY RANDOM() LIMIT 1").next()

	def random_question(self):
		"""This function returns a tuple (front, answer_index, choice1, choice2,...)
			where front is the question, answer_index indicates which choice from the remaining is the correct answer.
		"""
		notecards = [i for i in self.database.select("SELECT front, back FROM notecard_table ORDER BY RANDOM() LIMIT 3")]
		front = notecards[0][0]

		choices = [notecard[1] for notecard in notecards[1:]]		# remember a notecard is (front, back), 
																	# This collects all the backs of the notecards

		#And now insert the right choice into the choices, randomly offcourse
		r = random.randint(0,len(choices))		#Choosing a random spot
		choices.insert(r, notecards[0][1])		#Insert the right choice
		return [front, r] + choices

	def count_notecards(self):
		a = self.database.select("SELECT COUNT(*) FROM notecard_table").next()[0]
		print a
		return a

	def close(self):
		"""Just closes the database.
		"""
		self.database.close()


class RepeatedTimer(object):
    def __init__(self, interval, function, *args, **kwargs):
        self._timer     = None
        self.function   = function
        self.interval   = interval
        self.args       = args
        self.kwargs     = kwargs
        self.is_running = False
        self.start()

    def _run(self):
    	"""is called when timer expires. Calls .start() function(which sets the timer again) and 
    		then executes the function. 
    	"""
        self.is_running = False
        self.start()
        self.function(*self.args, **self.kwargs)

    def start(self):
    	"""Used to start the repeated timer.
    	"""
        if not self.is_running:
            self._timer = threading.Timer(self.interval, self._run)
            self._timer.start()
            self.is_running = True

    def stop(self):
    	"""Is called to cancel timer.
    	"""
        self._timer.cancel()
        self.is_running = False



class ChoiceButton(gtk.Button):
	"""Class that inherits from gtk.Button. This class hanldes colors. It takes it's content as a 
	   parameter.
	"""
	def __init__(self, content):
		gtk.Button.__init__(self)
		self.setup_colors()

		#We can't directly use button.set_label because we want to prettify the label
		content_label = gtk.Label()
		content_label.set_line_wrap(True)
		content_label.set_markup('<span color="white" size="20000"> %s </span>' %content)
		content_label.set_alignment(0.5,0.5)
		content_label.set_width_chars(37)
		self.add(content_label)
		self.show_all()


	def setup_colors(self):
		"""Just setting up the colors of the button for different states.
		"""
		normal_color = gtk.gdk.color_parse("#2a7b7d")
		self.modify_bg(gtk.STATE_NORMAL, normal_color)
		active_color = gtk.gdk.color_parse("#29a0a2")
		self.modify_bg(gtk.STATE_ACTIVE ,active_color)
		prelight_color = gtk.gdk.color_parse("#3ba1a2") 
		self.modify_bg(gtk.STATE_PRELIGHT, prelight_color)
		insensitive_color = gtk.gdk.color_parse("#143637")
		self.modify_bg(gtk.STATE_INSENSITIVE, insensitive_color)

class MyWindow(gtk.Window):
	"""Class that creates inherits form gtk.Window and sets background color.
	"""
	def __init__(self):
		gtk.Window.__init__(self)
		color = gtk.gdk.color_parse("#0c1021")
		self.modify_bg(gtk.STATE_NORMAL, color)
		self.connect("destroy", self.quit)
		self.show()

	def quit(self, window):
		self.destroy()

class QuestionWindow(MyWindow):
	def __init__(self, master, front, answer_index, *choices):
		"""
		master:			The master Lexiconner class that launched this window.
		front: 	  		The front of the notecard in question, most probably a single word.
		answer_index:	An integer value indicating which choice is the correct answer.
		choices:		An arbitrary number of choices, among which is the corect answer.
		"""

		MyWindow.__init__(self)
		self.master = master
		self.answer_index = answer_index

		self.vbox = gtk.VBox(homogeneous=True, spacing=0)			#Contains all elements
		self.add(self.vbox)

		self.front_label = gtk.Label() 							#Self explanatory self.front_label.set_alignment(0.5,0.5)					#Center the question
		self.front_label.set_markup(
			'<markup><span color="white" size="100000" face="ubuntu">%s </span></markup>' % front)

		self.front_label.set_line_wrap(True)
		self.vbox.pack_start(self.front_label, True, True, 0)
							# child				,expand, fill, padding)

		self.choice_box = gtk.HBox(homogeneous=True, spacing=10)	#Contains the choices
		self.vbox.pack_start(self.choice_box, True, True, 0)

		#For each choice we have, create a button
		for index, content in enumerate(choices):
			choice_button = ChoiceButton(content)
			choice_button.index = index 				#This is is the index of the answer
			connect_id = choice_button.connect("clicked", self.on_choice_clicked)		#We need the id to disconnect later
			choice_button.id = connect_id
			self.choice_box.pack_start(choice_button, True, True, 5)

		# I looove graphics in python
		# Honestly, even I can't tell if that comment(pun intended) was sarcastic or not.
		self.maximize()
		self.show_all()

	def on_choice_clicked(self, button):
		"""When a choice button is clicked, this function is called and checks if the choice is right.
			If so, it removes all other choices and makes sure when the button is clicked again, it 
			destroys the window. If it's the wrong choice, the button is deactivated.
		"""
		if button.index != self.answer_index:		#  Next time :(
			button.set_sensitive(False)				
		else:
			#Remove all other choices! We have the right one!
			for b in self.choice_box.get_children():
				if b.index != self.answer_index:
					self.choice_box.remove(b) 

			button.disconnect(button.id)

			if self.master:		#If this evaluates to true, that means we are in "perpetual mode"
				button.connect("clicked", self.master.new_question_window, True)		# self.master will handle launching another window if necessary

			#I suffered for hours because I couldn't figure out the callback above wasn't being called because the window was destroyed before getting to it.
			button.connect("clicked", self.quit)

class GUIManager(threading.Thread):
	"""Threading support for gtk
	"""

	def __init__(self):
		threading.Thread.__init__(self)
		self.start()

	def run(self):
		gtk.main()

class Lexiconner():
	"""Manages the app indicator and the timely launch.
	"""
	def __init__(self, database_file):
		self.database_file = database_file
		self.notecards = NotecardsHandler(database_file)
		self.timer = None 		# RepeatedTimer object
		self.edit_window = False 		#Haven't launched it yet
		self.current_interval = 0
		self.build_indicator()
		self.notify()

	def notify(self):
		notification = pynotify.Notification("Lexiconner!", "Lexiconner is ready. Use the icon above on the panel to set a timer or launch a question.")
		notification.show()

	def build_indicator(self):
		self.ind = appindicator.Indicator("example-simple-client", "indicator-messages", appindicator.CATEGORY_APPLICATION_STATUS)
		self.ind.set_status (appindicator.STATUS_ACTIVE)
		self.ind.set_attention_icon ("indicator-messages-new")
		self.ind.set_icon("distributor-logo")
		self.menu = gtk.Menu()
		self.ind.set_menu(self.menu)

		ask_now_menuitem = gtk.MenuItem("Ask now")
		ask_now_menuitem.connect("activate", self.new_question_window, True)		#The callback data means it will launch in "perpetual mode"

		set_timer_menuitem = gtk.MenuItem("Set timer")
		timer_submenu = gtk.Menu()
		set_timer_menuitem.set_submenu(timer_submenu)

		self.current_timer_menu_item = None

		for minute in [5, 10, 15, 30, 45, 60]:
			timer_menuitem = gtk.CheckMenuItem("{0} minutes".format(minute))
			timer_menuitem.connect("toggled", self.on_timer_changed, minute)
			timer_submenu.append(timer_menuitem)

		edit_menu_item = gtk.MenuItem("Edit notecards")
		edit_menu_item.connect("activate", self.on_edit_clicked)

    	# Why would anyone want to quit? Anyways,
		quit_menu_item = gtk.MenuItem("Exit")
		quit_menu_item.connect("activate", self.quit)

		for item in [ask_now_menuitem, set_timer_menuitem, edit_menu_item, quit_menu_item]:
			self.menu.append(item)

		self.menu.show_all()

	def new_question_window(self, widget = None, perpetual=False):
		#Check if we have any notecards
		if self.notecards.count_notecards() ==0:
			a = gtk.MessageDialog(flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, type=gtk.MESSAGE_WARNING, message_format="You have no notecards. Please add some.")
			a.show()
			return

		question = self.notecards.random_question()

		if perpetual: 	#That means pass self as a parameter, because the window will notify you when done.
			QuestionWindow(self, *question)
		else:
			QuestionWindow(False, *question)

	def on_edit_clicked(self, widget):
		if self.edit_window:		#One is already launched
			self.edit_window.present()	#Just switch to that window
		else:
			self.edit_window = EditNotecardsWindow(self)		#Passing self as an argument

	def on_timer_changed(self, menuitem, minutes):
		if not menuitem.get_active():	#Being turned off
			self.timer.stop()
			self.current_timer_menu_item = None
			self.current_interval = 0
			return

		self.current_interval = minutes

		#Delete previous timer and turn off previous CheckMenuitem
		if self.timer:		#If there is a timer already running
			self.timer.stop()
			self.current_timer_menu_item.set_active(False)

		self.timer = RepeatedTimer(minutes*60 , self.new_question_window)
		self.current_timer_menu_item = menuitem

	def quit(self, widget):
		if self.timer:
			self.timer.stop()

		self.notecards.close()
		gtk.main_quit()

class EditNotecardDialog(MyWindow):
	def __init__(self,callback, _id, front_text="", back_text=""):
		"""A simple Dialog with two textboxes and a button to add/edit notecards.
		   It calls the function callback with front, back as arguments.
		   If front and back are not set to None, it will set respective text entry boxes to their respective values.
		"""
		MyWindow.__init__(self)

		self.set_modal = True
		self.set_destroy_with_parent(True)
		self.set_size_request(600,300)
		self.set_position(gtk.WIN_POS_CENTER_ALWAYS)

		self.callback = callback
		self._id = _id

		#This is needed to make the window look less wierd
		padding = gtk.Alignment(xscale=1, yscale=1)
		padding.set_padding(padding_top=20, padding_bottom=20, padding_left=20, padding_right=20)
		self.add(padding)

		#Blah, blah blah blah, blah blah, arrange the text entries and the buttonbox blah, blah blah . . . 
		vbox = gtk.VBox(homogeneous=False, spacing=5)
		padding.add(vbox)

		self.front = gtk.Entry(max=20)	#A simple text entry for the front of the notecard
		vbox.pack_start(self.front, expand=False, padding=5)
		self.front.set_text(front_text)

		self.back_textbuffer = gtk.TextBuffer()
		self.back_textbuffer.set_text(back_text)

		back = gtk.TextView(self.back_textbuffer)		#A more complicated widget, a text view for the back of the notecard
		back.set_wrap_mode(gtk.WRAP_WORD)
		back.set_left_margin(2)
		back.set_right_margin(2)
		vbox.pack_start(back, expand=True, fill=True, padding=5)

		#Now for the button
		done_button = gtk.Button("Done")
		done_button.connect("clicked", self.on_done_clicked)

		buttonbox = gtk.HButtonBox()		#Needed to align the button to the right
		buttonbox.set_layout(gtk.BUTTONBOX_END)
		buttonbox.add(done_button)
		vbox.pack_start(buttonbox, expand=False)

		self.show_all()

	def on_done_clicked(self, widget):
		"""Will check if there are valid values for front and back, and then ca boom.
		"""
		front_text = self.front.get_text()

		#This is why I hate pygtk.
		startiter = self.back_textbuffer.get_start_iter()
		enditer = self.back_textbuffer.get_end_iter()
		back_text = self.back_textbuffer.get_text(startiter, enditer)

		if front_text and back_text:		#And this is why I love python. :)
			self.callback(self._id, front_text, back_text)
			self.destroy()
		else:
			a = gtk.MessageDialog(flags=gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, type=gtk.MESSAGE_WARNING, message_format="Please fill out both boxes.")
			a.show()

class EditNotecardsWindow(MyWindow):
	def __init__(self, master):
		"""Master is of course, the master Lexiconner class, through which we acesss the database and everything.
		"""
		super(EditNotecardsWindow, self).__init__()

		self.master = master
		self.build()
		self.set_size_request( 800, 500)
		self.set_position(gtk.WIN_POS_CENTER_ALWAYS)
		self.show_all()

	def build(self):
		#I need this to make the window less ugly/more beautilful
		padding = gtk.Alignment(xscale=1, yscale=1)
		padding.set_padding(padding_top = 20, padding_bottom=20, padding_right=30, padding_left=30)
		self.add(padding)

		vbox = gtk.VBox(homogeneous=False, spacing=20)
		padding.add(vbox)

		toolbar = gtk.Toolbar()
		toolbar.set_style(gtk.TOOLBAR_ICONS)	#Icons only
		toolbar.set_tooltips(True)
		vbox.pack_start(toolbar, expand=False, padding=5)

		#Add notecard toolitem
		add_icon = gtk.Image()
		add_icon.set_from_stock(stock_id=gtk.STOCK_ADD, size=gtk.ICON_SIZE_DIALOG)
		toolbar.append_item(text="", tooltip_text="Add notecard", tooltip_private_text="", icon=add_icon, callback=self.on_add_clicked)

		#Delete notecard toolitem
		delete_icon = gtk.Image()
		delete_icon.set_from_stock(stock_id=gtk.STOCK_REMOVE, size=gtk.ICON_SIZE_DIALOG)
		toolbar.append_item(text="", tooltip_text="Delete notecard(s)", tooltip_private_text="", icon=delete_icon, callback=self.on_delete_clicked)

		#Scrollable window is needed before the treeview
		scrolled_window = gtk.ScrolledWindow()
		scrolled_window.set_policy(hscrollbar_policy=gtk.POLICY_AUTOMATIC, vscrollbar_policy=gtk.POLICY_AUTOMATIC)	#Automatically decide if we need scrollbars
		vbox.pack_start(scrolled_window, expand=True, fill=True, padding=5)

		#The list store
		self.liststore = gtk.ListStore(int, str, str)	#id, back, front
		self.liststore.set_default_sort_func(None)		#Apparently, it becomes slow otherwise

		self.rows = {}			#We can fetch rows by ids later, if we store them now of course

		count = 0
		for  notecard in self.master.notecards.get_all_notecards():
			 self.liststore.append(notecard)

			 #We need to keep references later for removing, editing, etc 
			 _id = notecard[0]
			 row_reference = gtk.TreeRowReference(self.liststore, count)
			 self.rows[_id] = row_reference
			 count += 1

		#The treeview
		treeview = gtk.TreeView(model=self.liststore)
		treeview.set_enable_search(True)				#Make it searchable
		treeview.set_headers_clickable(True)			#So users can sort by header
		treeview.set_reorderable(True)					#Make sure they can reorder
		scrolled_window.add(treeview)

		treeview.connect("row-activated", self.on_row_clicked)		#When a row is double clicked

		#Tree selection
		self.selection = treeview.get_selection()
		self.selection.set_mode(gtk.SELECTION_MULTIPLE)	#Make multiple items selectable

		#We need the renderers 
		text_renderer = gtk.CellRendererText()
		text_renderer.set_property("wrap-width", 600)		#For some reason, it raises an error here(it doesn't want an integer value) but still works fine
		text_renderer.set_padding(5, 0)

		#Columns
		front_column = gtk.TreeViewColumn("Front", text_renderer, text=1)	#text=1 means fetch from second row(which is front row) of the ListStore
										#  header, CellRenderer,  column reference

		front_column.set_sort_column_id(1)		#Sort with the values of front

		back_column = gtk.TreeViewColumn("Back", text_renderer, text=2)
		back_column.set_sort_column_id(2)

		treeview.append_column(front_column)
		treeview.append_column(back_column)

	def on_add_clicked(self, widget):
		_id = self.master.notecards.get_smallest_avialable_id()
		EditNotecardDialog(self.add_notecard, _id) 

	def on_delete_clicked(self, widget):
		"""Iterates through each row in selection and deletes of database and ListStore
		"""
		store, paths = self.selection.get_selected_rows()

		#This is such a pain. Since the paths change as soon as one item is removed, we have to keep persistent tree refrencess
		references = []
		for path in paths:
			references.append(gtk.TreeRowReference(self.liststore, path))

		for reference in references:
			path = reference.get_path()		#Get the paths
			row = self.liststore[path]		#Fetching the row from the list store 
			_id = row[0]			#Remember the first row is the id

			self.master.notecards.delete_notecard(_id)		#Delete off the database
			del store[path]			#Delete from the tree store
			del self.rows[_id]		#Delete it from self.rows

	def on_row_clicked(self, treeview, path, column):
		"""Activated when a row is double clicked, launches the edit window
		"""
		row = self.liststore[path]
		print row
		[_id, front, back] = row
		EditNotecardDialog(self.edit_notecard, _id, front, back)

	def add_notecard(self, _id, front_text, back_text):
		"""adds notecard to database and to ListStore
		"""
		self.master.notecards.add_notecard(_id, front_text, back_text)

		tree_iter = self.liststore.append([_id, front_text, back_text])

		#We need to store tree reference
		path = self.liststore.get_path(tree_iter)
		row_reference = gtk.TreeRowReference(self.liststore, path)
		self.rows[_id] = row_reference

	def edit_notecard(self, _id, front, back):

		#Update the GUI
		row_reference = self.rows[_id] 		#Get persistent tree row reference,
		path = row_reference.get_path()		#Get path from row reference
		row = self.liststore[path]			#Get row using path

		row[1] = front
		row[2] = back
		pass

		#Update the database first
		self.master.notecards.edit_notecard(_id, front, back)

	def quit(self, widget):
		self.master.edit_window = False
		self.destroy()


class MyDialect(csv.excel):
	def __init__(self):
		csv.Dialect.__init__(self)
		self.delimiter = '|'

def main():

	if not os.path.isdir(CONFIG_DIR):
		os.makedirs(CONFIG_DIR)


	if not os.path.isfile(DATABASE_FILE):
		open(DATABASE_FILE, 'w').close()

	#All is well, let's go!
	a = Lexiconner(database_file=DATABASE_FILE)

	gtk.main()


if __name__ == '__main__':
	main()
