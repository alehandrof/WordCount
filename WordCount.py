import sublime, sublime_plugin, re
import time
import threading
from math import ceil as ceil
from os.path import basename

Pref = {}
s = {}

def plugin_loaded():
	global s, Pref
	s = sublime.load_settings('WordCount.sublime-settings')
	Pref = Pref()
	Pref.load();
	s.clear_on_change('reload')
	s.add_on_change('reload', lambda:Pref.load())

	if not 'running_word_count_loop' in globals():
		global running_word_count_loop
		running_word_count_loop = True
		t = threading.Thread(target=word_count_loop)
		t.start()

class Pref:
	def load(self):
		Pref.view                   = False
		Pref.modified               = False
		Pref.elapsed_time           = 0.4
		Pref.running                = False
		Pref.wrdRx                  = re.compile(s.get('word_regexp', "^[^\w]?\w+[^\w]*$"), re.U)
		Pref.wrdRx                  = Pref.wrdRx.match
		Pref.splitRx                = s.get('word_split', None)
		if Pref.splitRx:
			Pref.splitRx                = re.compile(Pref.splitRx, re.U)
			Pref.splitRx                = Pref.splitRx.findall
		Pref.enable_live_count      = s.get('enable_live_count', True)
		Pref.enable_readtime        = s.get('enable_readtime', False)
		Pref.enable_line_word_count = s.get('enable_line_word_count', False)
		Pref.enable_line_char_count = s.get('enable_line_char_count', False)
		Pref.enable_count_lines     = s.get('enable_count_lines', False)
		Pref.enable_count_chars     = s.get('enable_count_chars', False)
		Pref.enable_count_pages     = s.get('enable_count_pages', True)
		Pref.char_ignore_whitespace = s.get('char_ignore_whitespace', True)
		Pref.readtime_wpm           = s.get('readtime_wpm', 200)
		Pref.whitelist              = [x.lower() for x in s.get('whitelist_syntaxes', []) or []]
		Pref.blacklist              = [x.lower() for x in s.get('blacklist_syntaxes', []) or []]
		Pref.strip                  = s.get('strip', [])

		for window in sublime.windows():
			for view in window.views():
				view.settings().erase('WordCountShouldRun')
				view.erase_status('WordCount');

class WordCount(sublime_plugin.EventListener):

	def should_run_with_syntax(self, view):
		if view.settings().has('WordCountShouldRun'):
			return view.settings().get('WordCountShouldRun')
		syntax = view.settings().get('syntax')
		syntax = basename(syntax).replace('.tmLanguage', '').lower() if syntax != None else "plain text"
		view.settings().set('WordCountSyntax', syntax)

		if len(Pref.blacklist) > 0:
			for white in Pref.blacklist:
				if white == syntax:
					view.erase_status('WordCount');
					view.settings().set('WordCountShouldRun', False)
					return False
		if len(Pref.whitelist) > 0:
			for white in Pref.whitelist:
				if white == syntax:
					view.settings().set('WordCountShouldRun', True)
					return True
			view.erase_status('WordCount');
			view.settings().set('WordCountShouldRun', False)
			return False
		view.settings().set('WordCountShouldRun', True)
		return True

	def on_activated_async(self, view):
		self.asap(view)

	def on_post_save_async(self, view):
		self.asap(view)

	def on_modified_async(self, view):
		Pref.modified = True

	def on_selection_modified_async(self, view):
		Pref.modified = True

	def on_close(self, view):
		Pref.view = False
		Pref.modified = True

	def asap(self, view):
		Pref.view = view
		Pref.modified = True
		Pref.elapsed_time = 0.4
		sublime.set_timeout(lambda:WordCount().run(True), 0)

	def guess_view(self):
		if sublime.active_window() and sublime.active_window().active_view():
			Pref.view = sublime.active_window().active_view()

	def run(self, asap = False):
		if Pref.modified and (Pref.running == False or asap):
			if Pref.view != False and not Pref.view.settings().get('is_widget'):
				if self.should_run_with_syntax(Pref.view):
					Pref.modified = False
					view = Pref.view
					if view.size() > 10485760:
						pass
					else:
						sel = view.sel()
						if sel:
							if len(sel) == 1 and sel[0].empty():
								if Pref.enable_live_count:
									WordCountThread(view, [view.substr(sublime.Region(0, view.size()))], view.substr(view.line(view.sel()[0].end())), False).start()
								else:
									view.erase_status('WordCount')
							else:
								try:
									WordCountThread(view, [view.substr(sublime.Region(s.begin(), s.end())) for s in sel], view.substr(view.line(view.sel()[0].end())), True).start()
								except:
									pass
			else:
				self.guess_view()

	def display(self, view, on_selection, word_count, char_count, word_count_line, char_count_line):
		m = int(word_count / Pref.readtime_wpm)
		s = int(word_count % Pref.readtime_wpm / (Pref.readtime_wpm / 60))

		status = []

		if word_count:
			status.append(self.makePlural('Word', word_count))

		if Pref.enable_count_chars and char_count > 0:
			status.append(self.makePlural('Char', char_count))

		if Pref.enable_line_word_count and word_count_line > 1:
			status.append( "%d Words in Line" % (word_count_line))

		if Pref.enable_line_char_count and char_count_line > 1:
			status.append("%d Chars in Line" % (char_count_line))

		if Pref.enable_count_lines:
			lines = (view.rowcol(view.size())[0] + 1)
			if lines > 1:
				status.append('%d Lines' % (view.rowcol(view.size())[0] + 1))

		if Pref.enable_count_pages:
			visible = view.visible_region()
			rows = (view.rowcol(visible.end())[0]) - (view.rowcol(visible.begin())[0]) +1
			pages = ceil((view.rowcol(view.size())[0] + 1 ) /  rows)
			if pages > 1:
				status.append('%d Pages' % pages)

		if Pref.enable_readtime and s >= 1:
			status.append("~%dm %ds reading time" % (m, s))

		view.set_status('WordCount', ', '.join(status))

	def makePlural(self, word, count):
		return "%s %s%s" % (count, word, ("s" if count != 1 else ""))

class WordCountThread(threading.Thread):

	def __init__(self, view, content, content_line, on_selection):
		threading.Thread.__init__(self)
		self.view = view
		self.content = content
		self.content_line = content_line
		self.on_selection = on_selection

		self.char_count = 0
		self.word_count_line = 0
		self.chars_in_line = 0

		self.syntax = view.settings().get('WordCountSyntax')

	def run(self):
		# print ('running:'+str(time.time()))
		Pref.running         = True

		if self.syntax and self.syntax in Pref.strip:
			for item in Pref.strip[self.syntax]:
				for k in range(len(self.content)):
					self.content[k] = re.sub(item, '', self.content[k])
				self.content_line = re.sub(item, '', self.content_line)

		self.word_count      = sum([self.count(region) for region in self.content])

		if Pref.enable_count_chars:
			if Pref.char_ignore_whitespace:
				self.char_count  = sum([len(''.join(region.split())) for region in self.content])
			else:
				self.char_count  = sum([len(region) for region in self.content])

		if Pref.enable_line_word_count:
			self.word_count_line = self.count(self.content_line)

		if Pref.enable_line_char_count:
			if Pref.char_ignore_whitespace:
				self.chars_in_line = len(''.join(self.content_line.split()))
			else:
				self.chars_in_line = len(self.content_line.split())

		sublime.set_timeout(lambda:self.on_done(), 0)

	def on_done(self):
		try:
			WordCount().display(self.view, self.on_selection, self.word_count, self.char_count, self.word_count_line, self.chars_in_line)
		except:
			pass
		Pref.running = False

	def count(self, content):

		# begin = time.time()

		#=====1
		# wrdRx = Pref.wrdRx
		# """counts by counting all the start-of-word characters"""
		# # regex to find word characters
		# matchingWrd = False
		# words = 0
		# space_symbols = [' ', '\r', '\n']
		# for ch in content:
		# # 	# test if this char is a word char
		# 	isWrd = ch not in space_symbols
		# 	if isWrd and not matchingWrd:
		# 		words = words + 1
		# 		matchingWrd = True
		# 	if not isWrd:
		# 		matchingWrd = False

		#=====2
		wrdRx = Pref.wrdRx
		splitRx = Pref.splitRx
		if splitRx:
			words = len([x for x in splitRx(content) if False == x.isdigit() and wrdRx(x)])
		else:
			words = len([x for x in content.replace("'", '').split() if False == x.isdigit() and wrdRx(x)])

		# Pref.elapsed_time = end = time.time() - begin;
		# print ('Benchmark: '+str(end))

		return words

def word_count_loop():
	word_count = WordCount().run
	while True:
		# sleep time is adaptive, if takes more than 0.4 to calculate the word count
		# sleep_time becomes elapsed_time*3
		if Pref.running == False:
			sublime.set_timeout(lambda:word_count(), 0)
		time.sleep((Pref.elapsed_time*3 if Pref.elapsed_time > 0.4 else 0.4))