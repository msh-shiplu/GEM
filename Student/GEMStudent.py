# GEMStudent
# Author: Vinhthuy Phan, 2018
#
import sublime, sublime_plugin
import urllib.parse
import urllib.request
import os
import json
import time
import random
import datetime
import webbrowser

gemsFILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "info")
gemsFOLDER = ''
# gemsUID = 0
gemsTIMEOUT = 7
gemsAttempts = {}
gemsAnswerTag = 'ANSWER:'

# ------------------------------------------------------------------------------
def gemsRequest(path, data, authenticated=True, method='POST'):
	# global gemsUID
	global gemsFOLDER
	try:
		with open(gemsFILE, 'r') as f:
			info = json.loads(f.read())
	except:
		info = dict()

	if 'Server' not in info:
		sublime.message_dialog("Please set server address.")
		return None

	if 'Folder' not in info:
		sublime.message_dialog("Please set a local folder to store working files.")
		return None

	# data['server'] = info['Server']
	if authenticated:
		if 'Uid' not in info:
			sublime.message_dialog("Please register.")
			return None
		data['name'] = info['Name']
		data['password'] = info['Password']
		data['uid'] = info['Uid']
		gemsFOLDER = info['Folder']
		# gemsUID = info['Uid']

	url = urllib.parse.urljoin(info['Server'], path)
	load = urllib.parse.urlencode(data).encode('utf-8')
	req = urllib.request.Request(url, load, method=method)
	try:
		with urllib.request.urlopen(req, None, gemsTIMEOUT) as response:
			return response.read().decode(encoding="utf-8")
	except urllib.error.HTTPError as err:
		sublime.message_dialog("{0}".format(err))
	except urllib.error.URLError as err:
		sublime.message_dialog("{0}\nCannot connect to server.".format(err))
	print('Error making request')
	return None

# ------------------------------------------------------------------
class gemsGetReport(sublime_plugin.WindowCommand):
	def run(self):
		response = gemsRequest('student_gets_report', {})
		if response != None:
			json_obj = json.loads(response)
			report = {}
			total_points = 0
			for i in json_obj:
				Date, Points = i['Date'], i['Points']
				if Date not in report:
					report[Date] = []
				report[Date].append(Points)
				total_points += Points
			
			with open(gemsFILE, 'r') as f:
				info = json.loads(f.read())
			report_file = os.path.join(info['Folder'], 'report.txt')
			with open(report_file, 'w', encoding='utf-8') as f:
				f.write('Total points: {}\n'.format(total_points))
				for d,v in reversed(sorted(report.items())):
					date = datetime.datetime.fromtimestamp(d).strftime('%Y-%m-%d')
					for p in v:
						f.write('{}\t{}\n'.format(date,p))
			new_view = sublime.active_window().open_file(report_file)

# ------------------------------------------------------------------
class gemsShowMessages(sublime_plugin.WindowCommand):
	def run(self):
		try:
			with open(gemsFILE, 'r') as f:
				info = json.loads(f.read())
		except:
			info = dict()

		if 'Server' not in info:
			sublime.message_dialog("Please set server address.")
			return None

		if 'Uid' not in info:
			sublime.message_dialog("Please register.")
			return None

		u = urllib.parse.urlencode({'stid' : info['Uid']})
		webbrowser.open(info['Server'] + '/show_student_messages?' + u)

# ------------------------------------------------------------------
def gems_get_pid_attempts(fname):
	basename = os.path.basename(fname)
	if not basename.startswith('gemp'):
		return 0, 0
	name = basename.rsplit('.', 1)[0]
	items = name.rsplit('_', 2)
	if len(items)!=3 or  not items[1].isdecimal() or not items[2].isdecimal():
		return 0, 0
	return int(items[1]), int(items[2])

# ------------------------------------------------------------------
def gems_share(self, edit, priority):
	global gemsAttempts

	fname = self.view.file_name()
	if fname is None:
		sublime.message_dialog('Cannot share unsaved content.')
		return
	ext = fname.rsplit('.',1)[-1]
	pid, attempts = gems_get_pid_attempts(fname)

	# Lower priority if it's not a problem.
	if pid == 0:
		priority = 1

	if pid > 0 or sublime.ok_cancel_dialog('This file is not a graded problem. Do you want to send it?'):
		expired = False
		if pid in gemsAttempts:
			if gemsAttempts[pid] == 0:
				expired = True
			else:
				gemsAttempts[pid] -= 1
		if expired:
			sublime.message_dialog('This problem has expired and is not submitted.')
			return
		content = self.view.substr(sublime.Region(0, self.view.size())).lstrip()
		items = content.rsplit(gemsAnswerTag, 1)
		if len(items)==2:
			answer = items[1].strip()
		else:
			answer = ''
		data = dict(content=content, answer=answer, pid=pid, ext=ext, priority=priority)
		response = gemsRequest('student_shares', data)
		if response == 'OK':
			if pid in gemsAttempts and gemsAttempts[pid]<=3:
				sublime.message_dialog('There are {} attempts left.'.format(gemsAttempts[pid]))
			else:
				sublime.message_dialog('Content submitted.')
		else:
			sublime.message_dialog(response)

# ------------------------------------------------------------------
class gemsCheckin(sublime_plugin.WindowCommand):
	def run(self):
		response = gemsRequest('student_checks_in', {})
		sublime.message_dialog(response)

# ------------------------------------------------------------------
class gemsNeedHelp(sublime_plugin.TextCommand):
	def run(self, edit):
		gems_share(self, edit, priority=2)

# ------------------------------------------------------------------
class gemsGotIt(sublime_plugin.TextCommand):
	def run(self, edit):
		gems_share(self, edit, priority=1)

# ------------------------------------------------------------------
def gems_rand_chars(n):
	letters = 'abcdefghijklmkopqrstuvwxyzABCDEFGHIJKLMLOPQRSTUVWXYZ'
	return ''.join(random.choice(letters) for i in range(n))

# ------------------------------------------------------------------
class gemsGetBoardContent(sublime_plugin.WindowCommand):
	def run(self):
		global gemsAttempts

		response = gemsRequest('student_gets', {})
		if response is None:
			return
		json_obj = json.loads(response)
		if json_obj == []:
			sublime.message_dialog("Whiteboard is empty.")
			return
		for board in json_obj:
			content = board['Content']
			attempts = board['Attempts']
			ext = board['Ext']
			pid = board['Pid']
			today = datetime.datetime.today()
			if pid > 0:
				if attempts > 0:
					gemsAttempts[pid] = attempts
				prefix = 'gemp{}_{}'.format(today.strftime('%m%d'), pid)
			else:
				rpid = gems_rand_chars(2)
				prefix = 'gem{}_{}'.format(today.strftime('%m%d'), rpid)
			tmp = [os.path.basename(f) for f in os.listdir(gemsFOLDER)]
			count = len([f for f in tmp if f.startswith(prefix)])
			fname = os.path.join(gemsFOLDER, '{}_{}.{}'.format(prefix,count+1,ext))
			with open(fname, 'w', encoding='utf-8') as f:
				f.write(content)
			sublime.active_window().open_file(fname)

# ------------------------------------------------------------------
class gemsRegister(sublime_plugin.WindowCommand):
	def run(self):
		try:
			with open(gemsFILE, 'r') as f:
				info = json.loads(f.read())
		except:
			info = dict()

		if 'Server' not in info:
			sublime.message_dialog("Please set server address.")
			return None

		if 'Folder' not in info:
			sublime.message_dialog("Please set a local folder to store working files.")
			return None

		mesg = 'Enter a new name'
		if 'Name' in info:
			mesg = '{} is already registered. Enter a new name or Esc:'.format(info['Name'])

		if 'Name' not in info:
			info['Name'] = ''

		sublime.active_window().show_input_panel(
			mesg,
			info['Name'],
			self.process,
			None,
			None,
		)

	def process(self, name):
		name = name.strip()
		response = gemsRequest('student_registers', {'name':name}, authenticated=False)
		if response == 'exist':
			sublime.message_dialog('{} exists. Choose a different name.'.format(name))
		else:
			uid, password = response.split(',')
			try:
				with open(gemsFILE, 'r') as f:
					info = json.loads(f.read())
			except:
				info = dict()
			info['Uid'] = int(uid)
			info['Password'] = password
			info['Name'] = name
			with open(gemsFILE, 'w') as f:
				f.write(json.dumps(info, indent=4))
			sublime.message_dialog('{} registered'.format(name))

# ------------------------------------------------------------------
class gemsSetLocalFolder(sublime_plugin.WindowCommand):
	def run(self):
		try:
			with open(gemsFILE, 'r') as f:
				info = json.loads(f.read())
		except:
			info = dict()
		if 'Folder' not in info:
			info['Folder'] = os.path.join(os.path.expanduser('~'), 'GEM')
		sublime.active_window().show_input_panel("This folder will be used to store working files.",
			info['Folder'],
			self.set,
			None,
			None)

	def set(self, folder):
		folder = folder.strip()
		if len(folder) > 0:
			try:
				with open(gemsFILE, 'r') as f:
					info = json.loads(f.read())
			except:
				info = dict()
			info['Folder'] = folder
			if not os.path.exists(folder):
				try:
					os.mkdir(folder)
					with open(gemsFILE, 'w') as f:
						f.write(json.dumps(info, indent=4))
				except:
					sublime.message_dialog('Could not create {}.'.format(folder))
			else:
				with open(gemsFILE, 'w') as f:
					f.write(json.dumps(info, indent=4))
				sublime.message_dialog('Folder exists. Will use it to store working files.')
		else:
			sublime.message_dialog("Folder name cannot be empty.")

# ------------------------------------------------------------------
class gemsSetServerAddress(sublime_plugin.WindowCommand):
	def run(self):
		try:
			with open(gemsFILE, 'r') as f:
				info = json.loads(f.read())
		except:
			info = dict()
		if 'Server' not in info:
			info['Server'] = 'http://x.x.x.x:8080'
		sublime.active_window().show_input_panel("Set server address.  Press Enter:",
			info['Server'],
			self.set,
			None,
			None)

	def set(self, addr):
		addr = addr.strip()
		if len(addr) > 0:
			try:
				with open(gemsFILE, 'r') as f:
					info = json.loads(f.read())
			except:
				info = dict()
			if not addr.startswith('http://'):
				addr = 'http://' + addr
			info['Server'] = addr
			with open(gemsFILE, 'w') as f:
				f.write(json.dumps(info, indent=4))
		else:
			sublime.message_dialog("Server address cannot be empty.")

# ------------------------------------------------------------------------------
