#!/usr/bin/env python3

# for APIs GET request
import requests
import json

# to get the current date and time
import datetime

# for invoking the popup notifications
import subprocess

# for the delay
import time

# threading
import _thread

# to handle the incoming signals to this process
import signal

# for keyboard keystrokes detection
from pynput import keyboard

# house keeping to stop CLI warnings
import gi
gi.require_version('Notify', '0.7')
gi.require_version('AppIndicator3', '0.1')
gi.require_version('Gtk', '3.0')

# for the app indicator in ubuntu menu bar
from gi.repository import Gtk as gtk
from gi.repository import AppIndicator3 as appindicator

from gi.repository import Notify as notify

# to allow only one instance of the program
from tendo import singleton

# sleep/resume detection
import dbus      # for dbus communication (obviously)
from gi.repository import GObject as gobject
from dbus.mainloop.glib import DBusGMainLoop # integration into the main loop

##### CONSTANTS #####
KEY_ENTER = 65293
# KEY_SHIFT = 65505
# KEY_CTRL  = 65507
# KEY_CMD   = 65515
# KEY_SPACE = ' '

prayers = ['Fajr', 'Dhuhr', 'Asr', 'Maghrib', 'Isha']

# paths must be absolute to work at startup
# path for notification and app thumbnails
path              = '/home/omarcartera/Desktop/prayforme/src/'

image_path        = path + 'egg.svg'

# path for the notification sound
notification_path = path + 'notification.wav'

# notification messages formats
next_prayer_msg = '{0}, {1} {2}'
adhan_msg       = 'Time to Adhan: {0}'
prayer_time_msg = 'Time for {0} {1} {2}'
#####################


##### GLOBALS #####
ls = []

# image for app indicator icon and notification
indicator = ''
item_mute = ''

muted = False

# to make only one thread alive
thread_id = 0
###################

# app indicator settings
def gtk_main():
	global indicator

	APPINDICATOR_ID = 'myappindicator'

	indicator = appindicator.Indicator.new(APPINDICATOR_ID, image_path, appindicator.IndicatorCategory.SYSTEM_SERVICES)
	indicator.set_status(appindicator.IndicatorStatus.ACTIVE)
	indicator.set_menu(build_menu())

	notify.init(APPINDICATOR_ID)

	gtk.main()


# bulding the menu items
def build_menu():
	global item_mute

	# creating a menu in app indicator
	menu = gtk.Menu()

	# quit tab in the menu
	item_quit = gtk.MenuItem('Quit')
	item_quit.connect('activate', quit)
	menu.append(item_quit)

	# asking for the time remaining for the next prayer
	item_next = gtk.MenuItem('Next Prayer?')
	item_next.connect('activate', what_is_next)
	menu.append(item_next)

	# mute/unmute the notifications until next prayer
	item_mute = gtk.CheckMenuItem('Mute')
	item_mute.set_draw_as_radio(True)
	item_mute.connect('activate', mute)
	menu.append(item_mute)

	menu.show_all()

	return menu


# alternative way to CTRL + C to terminate the process
def quit(source = None, sth = None):
	exit()


# mute/unmute the notifications until next prayer
def mute(source = None):
	global item_mute, muted

	if muted:
		image_path = path + 'egg.svg'
		label = 'Mute'

	else:
		image_path = path + 'mute.png'
		label = 'Unmute'

	# updating the app/notification thumbnail and menu tab label
	indicator.set_icon(image_path)
	item_mute.set_label(label)

	muted = not muted


# pops a notification to tell the remaining time
def what_is_next(source = 0):
	# get the prayers timing sheet
	# also here you need the absolute path
	with open(path + 'prayers.json', 'r') as prayers_file:
		data = json.load(prayers_file)

	times       = data['times']
	actual_date = data['actual_date']
	today       = data['today']

	# to get the current time
	now_in_minutes = get_now_in_minutes()

	# add the current time to the prayers timing list
	times.append(now_in_minutes)

	# sorting will puth the current_time entry just before the next prayer
	times.sort()
		
	# get the remaining time to the next prayer
	delta = get_delta_time(now_in_minutes, times)
	
	# name of next prayer
	next_prayer = get_next_prayer(times, now_in_minutes)
	
	if muted:
		image_path = path + 'mute.png'

	else:
		image_path = path + 'egg.svg'

	# invoke notification
	mode  = 'next_prayer'
	title = next_prayer_msg.format(next_prayer, today, actual_date)
	body  = adhan_msg.format(min_to_time(delta))

	show_notification(mode = mode, title = title, body = body)


# pop notifications of time remaining to the next prayer
def prayer_reminder(my_thread_id):
	global muted
	
	corrected = False

	while True:
		if thread_id != my_thread_id:
			print('thread', my_thread_id, 'is off')
			break

		# get the prayers timing sheet and actual date of the prayer
		with open(path + 'prayers.json', 'r') as prayers_file:
			data = json.load(prayers_file)

		times       = data['times']
		actual_date = data['actual_date']
		today       = data['today']

		# to get the current time
		now_in_minutes = get_now_in_minutes()

		# add the new current_time to the list
		times.append(now_in_minutes)

		# sorting will puth the current_time entry just before the next prayer
		times.sort()

		# get the time difference between now and next prayer
		delta = get_delta_time(now_in_minutes, times)
		
		# name of next prayer
		next_prayer = get_next_prayer(times, now_in_minutes)

		# an initail solution to Isha-Midnight-Fajr problem
		if next_prayer == 'Fajr' and not corrected:
			# get the timing sheet for tomorrow, coz we are now
			# before midnight and the next Fajr is tomorrow
			
			country, city = get_location_data()
			get_prayer_times(0, country, city)

			# to get the current time
			now_in_minutes = get_now_in_minutes()
			corrected = True

			# get the new prayers timing sheet
			with open(path + 'prayers.json', 'r') as prayers_file:
				data = json.load(prayers_file)

				times = data['times']
				actual_date = data['actual_date']
		

		elif next_prayer != 'Fajr' and corrected:
			corrected = False

			
		elif next_prayer == 'Dhuhr' and today == 'Fri':
			next_prayer = 'Jomaa'


		# needs to be placed in a more logical place
		if muted:
			polling_time = int((delta + 1.1) * 60)

			# process state: running --> sleep
			time.sleep(polling_time)
			
			# recover from mute coz the muted prayer has passed
			mute()


		else:
			# we can pray now
			if delta == 0:

				# invoke notification
				mode  = 'prayer_time'
				title = prayer_time_msg.format(next_prayer, today, actual_date)
					
				# wait 25 seconds between every notification
				polling_time = 25
				

			# anything less than 2 hours remaining
			elif delta <= 120:

				# invoke notification
				mode  = 'next_prayer'
				title = next_prayer_msg.format(next_prayer, today, actual_date)
				body  = adhan_msg.format(min_to_time(delta))

				# repeat after (remaining time)/3 elapses
				polling_time = (delta/3.0) * 60


			# anything more than 2 hours remaining
			else:
				# invoke notification
				mode  = 'next_prayer'
				title = next_prayer_msg.format(next_prayer, today, actual_date)
				body  = adhan_msg.format(min_to_time(delta))

				# sleep until it's 2 hours remaining
				polling_time = (delta - 120) * 60

			# invoke notification
			show_notification(mode = mode, title = title, body = body, thread = my_thread_id)

			# process state: running --> sleep
			time.sleep(polling_time)


# get current time
def get_now_in_minutes():
	# to get the current time
	now = datetime.datetime.now()

	# to get the current time as integer minutes counted from 00:00
	now_in_minutes = time_to_min(str(now)[11:16])

	return now_in_minutes


# Delta Time: A term used to describe the time difference between
# two different laps or two different cars. For example, there is
# usually a negative delta between a driver's best practice lap time
# and his best qualifying lap time because he uses a low fuel load and new tyres.
def get_delta_time(now_in_minutes, times):
	# getting delta, times is a circular list
	delta = times[(times.index(now_in_minutes) + 1) % 6] - times[times.index(now_in_minutes)]

	# if now is after isha, before midnight and next prayer is Fajr --> negative delta
	if delta < 0:
		delta = delta + 24 * 60

	return delta


# returns the name of the next prayer based on current
# time index in the timing list
def get_next_prayer(times, now_in_minutes):
	return prayers[times.index(now_in_minutes) % 5]


# get your current location based on your public IP
def get_location_data():
	connected = False

	while not connected:
		try:
			ip_info = (requests.get('http://ipinfo.io/json')).json()

			country = ip_info['country']
			city = ip_info['city']

			connected = True

		except:
			print('*****************')
			print('*Reconnecting...*')
			print('*****************')

			time.sleep(2)

	return country, city


# get prayer times for a complete month
def get_prayer_times(fajr_correction, country, city):
	times = []

	# to get the current date and time
	now = datetime.datetime.now()

	# to get prayer times based on your location
	url = 'http://api.aladhan.com/v1/calendarByCity'

	payload = {'country': country, 'city': city, 'month': now.month,
			   'year': str(now.year), 'method': 3, 'midnightMode': 0 }

	connected = False

	while not connected:
		try:
			response = ((requests.get(url, params=payload)).json())['data']
			connected = True

		except:
			print('*****************')
			print('*Reconnecting...*')
			print('*****************')

			time.sleep(2)
		

	for i in range(5):
		# index of today = today - 1 .. that's how fajr correction works
		times.append(str(response[now.day - fajr_correction]['timings'][prayers[i]][:5]))
		times[i] = time_to_min(str(times[i]))

	# actual date of these timings, for research reasons
	actual_date = response[now.day - fajr_correction]['date']['readable']

	today = (now + datetime.timedelta(days=not(fajr_correction))).strftime("%A")[:3]

	dic = {'times': times, 'actual_date': actual_date, 'today': today}

	# write down the timing sheet and actual date into a json
	with open(path + 'prayers.json', 'w') as prayers_file:
		json.dump(dic, prayers_file)
	

# to play notification sound
def play():
	subprocess.call(['aplay',  notification_path])


# a unified function that shows the popup notification
def show_notification(mode = None, title = None, body = None, thread = -1):
	global muted

	# play notification sound in a temporary thread
	# because aplay command is blocking
	# to be synced with the popup notification
	if muted:
		image_path = path + 'mute.png'

	else:
		image_path = path + 'egg.svg'
		_thread.start_new_thread(play, ())


	if mode == 'next_prayer':
		subprocess.call(['notify-send', '-i', image_path, '-u', 'critical', title + ' - ' + str(thread), body])

	elif mode == 'prayer_time':
		subprocess.call(['notify-send', '-i', image_path, '-u', 'critical', title + ' - ' + str(thread)])

	

# convert hh:mm to integer minutes
def time_to_min(time):
	return int(time[:2]) * 60 + int(time[3:])


# convert integer minutes to hh:mm
def min_to_time(min):
	return str(int((min/60)%24)).zfill(2) + ':' + str(int(min%60)).zfill(2)


# what to do when the buttons combination is pressed
def on_press(key):
	if str(key) in {'Key.ctrl', 'Key.space', 'Key.shift', 'Key.cmd'}:
		ls.append(str(key))

	if sorted(ls) == sorted(['Key.ctrl', 'Key.shift', 'Key.space']):
		what_is_next()

	if sorted(ls) == sorted(['Key.ctrl', 'Key.shift', 'Key.cmd']):
		mute()


# what to do when the buttons combination is released .. ahem
def on_release(key):
	if str(key) in {'Key.ctrl', 'Key.space', 'Key.shift', 'Key.cmd'}:
		ls.remove(str(key))	


# initialize the keyboard monitoring thread
def listener_fn():
	with keyboard.Listener(on_press, on_release) as listener:
		listener.join()


# sleep and resume detection
def resume_detection(sleeping):
	global thread_id

	if not sleeping:
		time.sleep(30)
		thread_id += 1
		print('thread', thread_id, 'is on')
		_thread.start_new_thread(prayer_reminder, (thread_id,))


def onButtonPressed(sth1=None, sth2=None):
	country = lndt_country.get_text()
	city = lndt_city.get_text()

	window.hide()

	# this blocks the main thread
	_thread.start_new_thread(gtk_main, ())
	cont(country, city)

# detecting keypress
def test(sth1, key):
	# 65293 is the key value of enter
	if key.keyval == KEY_ENTER:
		onButtonPressed()

# a gui window to ensure country and city from user
def call_gui():
	global lndt_country, lndt_city, window

	builder = gtk.Builder()
	builder.add_from_file(path + "gui_design.glade")

	handlers = {
	    "onButtonPress": onButtonPressed,
	    "onDestroy"	   : quit
	}

	builder.connect_signals(handlers)

	xml = builder.get_objects()

	window = builder.get_object("window1")
	lndt_country = builder.get_object("lndt_country")
	lndt_city = builder.get_object("lndt_city")

	btn_continue = builder.get_object("btn_continue")

	country, city = get_location_data()

	lndt_country.set_text(country)
	lndt_city.set_text(city)

	# connect the enter keystroke to trigger button press
	lndt_country.connect("key-press-event", test)
	lndt_city.connect("key-press-event", test)

	window.show_all()
	gtk.main()


def cont(country, city):
	# put the prayer times in the json
	get_prayer_times(1, country, city)

	# a thread to monitor the remaining time for the next prayer
	_thread.start_new_thread(prayer_reminder, (thread_id,))
	
	try:
		DBusGMainLoop(set_as_default=True)		# integrate into main loob
		bus = dbus.SystemBus()					# connect to dbus system wide
		bus.add_signal_receiver(				# defince the signal to listen to
			resume_detection,					# name of callback function
			'PrepareForSleep',					# signal name
			'org.freedesktop.login1.Manager',	# interface
			'org.freedesktop.login1'			# bus name
		)

		loop = gobject.MainLoop()				# define mainloop
		loop.run()								# run main loop
	
	except Exception as e:
		print('***', e, '***')


##### MAIN #####
def main():
	global xml
	# to make it responsive to CTRL + C signal
	# put IGN instead of DFL to ignore the CTRL + C
	# put a function name instead of the IGN/DFL
	signal.signal(signal.SIGINT, quit)

	# start the thread to listen for keyboard presses
	_thread.start_new_thread(listener_fn, ())

	call_gui()


if __name__ == '__main__':
	# to limit the program to only one active instance
	try:
		me = singleton.SingleInstance()

	except:
		exit()

	main()



#### FAJR CORRECTION FOR END/BEGINNING OF MANTHS ####
# import datetime

# print(datetime.date.today() + datetime.timedelta(days=1))