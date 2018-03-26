# Code4Brownies - Instructor module
# Author: Vinhthuy Phan, 2015-2017
#

import sublime, sublime_plugin
import urllib.parse
import urllib.request
import os
import json
import socket
import webbrowser
import random

gemtFILE = os.path.join(os.path.dirname(os.path.realpath(__file__)), "info")
gemtFOLDER = ''
gemtOrTag = '<GEM_OR>'
gemtSeqTag = '<GEM_NEXT>'
gemtAnswerTag = 'ANSWER:'
gemsHighestPriority = 2
gemtTIMEOUT = 7
gemtStudentSubmissions = {}

# ------------------------------------------------------------------
def gemtRequest(path, data, authenticated=True, localhost=False, method='POST'):
	global gemtFOLDER
	try:
		with open(gemtFILE, 'r') as f:
			info = json.loads(f.read())
	except:
		info = dict()

	if 'Folder' not in info:
		sublime.message_dialog("Please set a local folder for keeping working files.")
		return None

	if 'Server' not in info or localhost:
		info['Server'] = 'http://localhost:8080'

	if authenticated:
		if 'Name' not in info or 'Password' not in info:
			sublime.message_dialog("Please ask to setup a new teacher account and register.")
			return None
		data['name'] = info['Name']
		data['password'] = info['Password']
		data['uid'] = info['Uid']
		data['role'] = 'teacher'
		gemtFOLDER = info['Folder']

	url = urllib.parse.urljoin(info['Server'], path)
	load = urllib.parse.urlencode(data).encode('utf-8')
	req = urllib.request.Request(url, load, method=method)
	try:
		with urllib.request.urlopen(req, None, gemtTIMEOUT) as response:
			return response.read().decode(encoding="utf-8")
	except urllib.error.HTTPError as err:
		sublime.message_dialog("{0}".format(err))
	except urllib.error.URLError as err:
		sublime.message_dialog("{0}\nCannot connect to server.".format(err))
	print('Something is wrong')
	return None


# ------------------------------------------------------------------
class gemtTest(sublime_plugin.WindowCommand):
	def run(self):
		response = gemtRequest('test', {})
		sublime.message_dialog(response)

# ------------------------------------------------------------------
class gemtAddBulletin(sublime_plugin.TextCommand):
	def run(self, edit):
		this_file_name = self.view.file_name()
		if this_file_name is None:
			sublime.message_dialog('Error: file is empty.')
			return
		beg, end = self.view.sel()[0].begin(), self.view.sel()[0].end()
		content = '\n' + self.view.substr(sublime.Region(beg,end)) + '\n'
		if len(content) <= 20:
			sublime.message_dialog('Select more text to show on the bulletin board.')
			return
		response = gemtRequest('teacher_adds_bulletin_page', {'content':content})
		if response:
			sublime.message_dialog(response)

# ------------------------------------------------------------------
def gemt_grade(self, edit, decision):
	fname = self.view.file_name()
	basename = os.path.basename(fname)
	if not basename.startswith('gemt') or basename.count('_')!=2:
		sublime.message_dialog('This is not a student submission.')
		return
	prefix, ext = basename.rsplit('.', 1)
	prefix = prefix[4:]
	stid, pid, sid = prefix.split('_')
	try:
		stid = int(stid)
		sid = int(sid)
	except:
		sublime.message_dialog('This is not a student submission.')
		return
	try:
		pid = int(pid)
	except:
		sublime.message_dialog('This is not a graded problem.')
		return
	changed = False
	if decision=='dismiss':
		content = ''
	else:
		content = self.view.substr(sublime.Region(0, self.view.size())).strip()
		if pid in gemtStudentSubmissions and content.strip()!=gemtStudentSubmissions[pid].strip():
			changed = True
	data = dict(
		stid = stid,
		pid = pid,
		content = content,
		ext = ext,
		decision = decision,
		changed = changed,
	)
	response = gemtRequest('teacher_grades', data)
	if response:
		sublime.message_dialog(response)

# ------------------------------------------------------------------
class gemtGradeCorrect(sublime_plugin.TextCommand):
	def run(self, edit):
		gemt_grade(self, edit, "correct")

class gemtGradeIncorrect(sublime_plugin.TextCommand):
	def run(self, edit):
		gemt_grade(self, edit, "incorrect")

class gemtDismiss(sublime_plugin.TextCommand):
	def run(self, edit):
		gemt_grade(self, edit, "dismiss")

# ------------------------------------------------------------------
def gemt_rand_chars(n):
	letters = 'abcdefghijklmkopqrstuvwxyzABCDEFGHIJKLMLOPQRSTUVWXYZ'
	return ''.join(random.choice(letters) for i in range(n))

# ------------------------------------------------------------------
def gemt_gets(self, index, priority):
	global gemtStudentSubmissions
	response = gemtRequest('teacher_gets', {'index':index, 'priority':priority})
	if response is not None:
		sub = json.loads(response)
		if sub['Content'] != '':
			ext = sub['Ext'] or 'txt'
			pid, sid, uid = sub['Pid'], sub['Sid'], sub['Uid']
			if pid == 0:
				pid = gemt_rand_chars(4)
			fname = 'gemt{}_{}_{}.{}'.format(uid,pid,sid,ext)
			fname = os.path.join(gemtFOLDER, fname)
			with open(fname, 'w', encoding='utf-8') as fp:
				fp.write(sub['Content'])
			gemtStudentSubmissions[pid] = sub['Content']
			sublime.active_window().open_file(fname)
		else:
			sublime.message_dialog('No submission with index {} or priority {}.'.format(index,priority))

# ------------------------------------------------------------------
# Priorities: 1 (I got it), 2 (I need help), 
# ------------------------------------------------------------------
class gemtGetPrioritized(sublime_plugin.WindowCommand):
	def run(self):
		gemt_gets(self, -1, 0)

class gemtGetFromNeedHelp(sublime_plugin.WindowCommand):
	def run(self):
		gemt_gets(self, -1, 2)

class gemtGetFromOk(sublime_plugin.WindowCommand):
	def run(self):
		gemt_gets(self, -1, 1)

# ------------------------------------------------------------------
class gemtShare(sublime_plugin.TextCommand):
	def run(self, edit):
		fname = self.view.file_name()
		if fname is None:
			sublime.message_dialog('Cannot share unsaved content.')
			return
		ext = fname.rsplit('.',1)[-1]
		content = self.view.substr(sublime.Region(0, self.view.size())).lstrip()
		if content == '':
			sublime.message_dialog("File is empty.")
			return
		data = {
			'content': 			content,
			'ext': 				ext,
		}
		response = gemtRequest('teacher_shares', data)
		if response is not None:
			sublime.status_message(response)

# ------------------------------------------------------------------
# used by gemt_multicast and gemtUnicast to start a new problem
# ------------------------------------------------------------------
def gemt_broadcast(content, answers, merits, efforts, attempts, exts, tag, mode):
	data = {
		'content': 			content,
		'answers':			answers,
		'exts': 			exts,
		'merits':			merits,
		'efforts':			efforts,
		'attempts':			attempts,
		'divider_tag':	 	tag,
		'mode':				mode
	}
	# print(data)
	response = gemtRequest('teacher_broadcasts', data)
	if response is not None:
		sublime.status_message(response)

# ------------------------------------------------------------------
def gemt_get_problem_info(fname):
	merit, effort, attempts = 0, 0, -1
	ext = fname.rsplit('.', 1)[-1]
	with open(fname, 'r', encoding='utf-8') as fp:
		content = fp.read()
	items = content.split('\n',1)
	if len(items)==1:
		sublime.message_dialog('Improper problem definition')
		raise Exception('Improper problem definition')
	first_line, body = items[0], items[1]
	if first_line.startswith('#'):
		first_line = first_line.strip('# ')
	elif first_line.startswith('/'):
		first_line = first_line.strip('/ ')
	try:
		items = first_line.split(' ')
		merit, effort = int(items[0]), int(items[1])
		if len(items) > 2:
			attempts = int(items[2])
	except:
		sublime.message_dialog('Improper problem definition')
		raise Exception('Improper problem definition')
	if merit < effort:
		sublime.message_dialog('Merit points ({}) should be higher than effort points {}.'.format(merit, effort))
		raise Exception('Merit points lower than effort points.')

	items = body.split(gemtAnswerTag)
	if len(items) > 2:
		sublime.message_dialog('This problem has {} answers. There should be at most 1.'.format(len(items)-1))
		raise Exception('Too many answers')

	body = items[0]
	answer = ''
	if len(items) == 2:
		body += '\n{} '.format(gemtAnswerTag)
		answer = items[1].strip()

	return body, answer, str(merit), str(effort), str(attempts), ext


# ------------------------------------------------------------------
def gemt_multicast(self, edit, tag, mode, mesg):
	fnames = [ v.file_name() for v in sublime.active_window().views() ]
	fnames = [ fname for fname in fnames if fname is not None ]
	if len(fnames)>0 and sublime.ok_cancel_dialog(mesg):
		content, answers, merits, efforts, attempts, exts = [],[],[],[],[],[]
		for fname in fnames:
			# ext = fname.rsplit('.',1)[-1]
			# with open(fname, 'r', encoding='utf-8') as fp:
			# 	contents.append(fp.read())
			c, an, m, e, at, ex = gemt_get_problem_info(fname)
			content.append(c)
			answers.append(an)
			merits.append(m)
			efforts.append(e)
			attempts.append(at)
			exts.append(ex)

		content = '\n{}\n'.format(tag).join(content)
		answers = '\n'.join(answers)
		merits = '\n'.join(merits)
		efforts = '\n'.join(efforts)
		attempts = '\n'.join(attempts)
		exts = '\n'.join(exts)
		gemt_broadcast(content, answers, merits, efforts, attempts, exts, tag, mode)

# ------------------------------------------------------------------
class gemtUnicast(sublime_plugin.TextCommand):
	def run(self, edit):
		fname = self.view.file_name()
		if fname is None:
			sublime.message_dialog('Cannot broadcast unsaved content.')
			return
		# ext = fname.rsplit('.',1)[-1]
		# content = self.view.substr(sublime.Region(0, self.view.size())).lstrip()
		# if content == '':
		# 	sublime.message_dialog("File is empty.")
		# 	return
		content, answers, merits, efforts, attempts, exts = gemt_get_problem_info(fname)
		gemt_broadcast(content, answers, merits, efforts, attempts, exts, tag='', mode='unicast')

# ------------------------------------------------------------------
class gemtMulticastOr(sublime_plugin.TextCommand):
	def run(self, edit):
		gemt_multicast(
			self,
			edit,
			gemtOrTag,
			'multicast_or',
			'Broadcast *randomly* all non-empty tabs in this window?',
		)

# ------------------------------------------------------------------
class gemtMulticastSeq(sublime_plugin.TextCommand):
	def run(self, edit):
		gemt_multicast(
			self,
			edit,
			gemtSeqTag,
			'multicast_seq',
			'Broadcast *sequentially* all non-empty tabs in this window?',
		)

# ------------------------------------------------------------------
class gemtDeactivateProblems(sublime_plugin.WindowCommand):
	def run(self):
		if sublime.ok_cancel_dialog('Do you want to close active problems?  No more submissions are possible until a new problem is started.'):
			response = gemtRequest('teacher_deactivates_problems', {})
			sublime.message_dialog(response)

# ------------------------------------------------------------------
class gemtClearSubmissions(sublime_plugin.WindowCommand):
	def run(self):
		if sublime.ok_cancel_dialog('Do you want to clear all submissions and white boards?'):
			response = gemtRequest('teacher_clears', {})
			sublime.message_dialog(response)

# ------------------------------------------------------------------
class gemtViewBulletinBoard(sublime_plugin.WindowCommand):
	def run(self):
		response = gemtRequest('teacher_gets_passcode', {})
		if response.startswith('Unauthorized'):
			sublime.message_dialog('Unauthorized')
		else:
			p = urllib.parse.urlencode({'pc' : response})
			with open(gemtFILE, 'r') as f:
				info = json.loads(f.read())
			webbrowser.open(info['Server'] + '/view_bulletin_board?' + p)

# ------------------------------------------------------------------
class gemtSetupNewTeacher(sublime_plugin.WindowCommand):
	def run(self):
		if sublime.ok_cancel_dialog("This can only be done if SublimeText and the server are running on localhost."):
			sublime.active_window().show_input_panel('Enter username:',
				'',
				self.process,
				None,
				None)

	def process(self, name):
		name = name.strip()
		response = gemtRequest('teacher_adds_ta', {'name':name}, authenticated=False, localhost=True)
		sublime.message_dialog(response)


# ------------------------------------------------------------------
class gemtSetServerAddress(sublime_plugin.WindowCommand):
	def run(self):
		try:
			with open(gemtFILE, 'r') as f:
				info = json.loads(f.read())
		except:
			info = dict()
		if 'Server' not in info:
			info['Server'] = 'http://localhost:8080'
		sublime.active_window().show_input_panel("Set server address.  Press Enter:",
			info['Server'],
			self.set,
			None,
			None)

	def set(self, addr):
		addr = addr.strip()
		if len(addr) > 0:
			try:
				with open(gemtFILE, 'r') as f:
					info = json.loads(f.read())
			except:
				info = dict()
			if not addr.startswith('http://'):
				addr = 'http://' + addr
			info['Server'] = addr
			with open(gemtFILE, 'w') as f:
				f.write(json.dumps(info, indent=4))
		else:
			sublime.message_dialog("Server address cannot be empty.")

# ------------------------------------------------------------------
class gemtSetLocalFolder(sublime_plugin.WindowCommand):
	def run(self):
		try:
			with open(gemtFILE, 'r') as f:
				info = json.loads(f.read())
		except:
			info = dict()
		if 'Folder' not in info:
			info['Folder'] = os.path.join(os.path.expanduser('~'), 'GEMT')
		sublime.active_window().show_input_panel("This folder will be used to store working files.",
			info['Folder'],
			self.set,
			None,
			None)

	def set(self, folder):
		folder = folder.strip()
		if len(folder) > 0:
			try:
				with open(gemtFILE, 'r') as f:
					info = json.loads(f.read())
			except:
				info = dict()
			info['Folder'] = folder
			print(info)
			if not os.path.exists(folder):
				try:
					os.mkdir(folder)
					with open(gemtFILE, 'w') as f:
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
