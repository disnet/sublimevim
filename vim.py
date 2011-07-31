import sublime
import sublime_plugin
import string
import re

class WithEdit:
	def __init__(self, view):
		self.view = view

	def __enter__(self):
		self.edit = self.view.begin_edit()
		return self.edit
	
	def __exit__(self, *args, **kwargs):
		self.view.end_edit(self.edit)

class Wrapper(object):
	static = {
		'obj': None
	}

	public = []

	def __init__(self):
		self.static = self.static.copy()

	def __getattribute__(self, key):
		if key in ('public', 'static'):
			return object.__getattribute__(self, key)

		if key in self.static:
			return self.static[key]
		elif key in self.public:
			return object.__getattribute__(self, key)
		else:
			return getattr(self.view, key)

	def __setattr__(self, key, value):
		if key == 'static':
			object.__setattr__(self, key, value)
		elif key in self.static:
			self.static[key] = value
		else:
			setattr(self.view, key, value)

class InsertView(Wrapper):
	static = {
		'mode': 'insert',
		'obj': None,
		'view': None,
	}

	public = [
		'escape',
		'key_escape',
		'key_slash',
		'key_colon',
		'key_char',
		'key_arrow',
		'natural_insert',
		'set_mode'
	]

	def __init__(self, view):
		Wrapper.__init__(self)

		self.obj = self.view = view
		self.set_mode()
	
	def natural_insert(self, string, edit=None):
		view = self.view

		lines = string.split('\n')

		if not edit:
			edit = view.begin_edit()
			self.natural_insert(string, edit)
			view.end_edit(edit)
			return

		sel = view.sel()
		if len(lines) == len(sel):
			inserts = lines
		else:
			inserts = [string]*len(sel)

		for cur in sel:
			ins = inserts.pop(0)
			if cur.empty():
				view.insert(edit, cur.a, ins)
			else:
				sel.subtract(cur)
				sel.add(sublime.Region(cur.a, cur.a))
				view.replace(edit, cur, ins)
	
	def escape(self):
		window = self.window()
		if len(self.sel()) > 1:
			self.run_command('single_selection')
		else:
			window.run_command('clear_fields')
			window.run_command('hide_panel')
			window.run_command('hide_overlay')
			window.run_command('hide_auto_complete')

	def key_escape(self, edit): self.escape()
	def key_slash(self, edit): self.key_char(edit, '/')
	def key_colon(self, edit): self.key_char(edit, ':')
	def key_char(self, edit, char): self.natural_insert(char, edit)
	
	def key_arrow(self, direction):
		if   direction == 'left':  self.run_command('move', {"by": "characters", "forward": False})
		elif direction == 'down':  self.run_command('move', {"by": "lines", "forward": True})
		elif direction == 'up':    self.run_command('move', {"by": "lines", "forward": False})
		elif direction == 'right': self.run_command('move', {"by": "characters", "forward": True})

	def set_mode(self, mode=None): return

class View(InsertView): # this is where the logic happens
	static = {
		'mode': 'command',
		'obj': None,
		'view': None,
		'cmd': '',
		'yank': [],
		'marks': {},
		'last_find': ''
	}

	public = [
		'command',
		'delete_char',
		'delete_line',
		'edit',
		'escape',
		'increment_num',
		'substr',
		'save',
		'find_replace',
		'key_escape',
		'key_slash',
		'key_colon',
		'key_char',
		'key_arrow',
		'natural_insert',
		'set_mode'
	]

	def set_mode(self, mode=None):
		if mode and mode != self.mode:
			self.cmd = ''
			self.mode = mode
		
		self.obj.set_status('vim', '%s mode' % self.mode.upper())
	
	def edit(self):
		return WithEdit(self)
	
	def find_replace(self, edit, string, forward=True):
		self.last_find = string
		self.run_command('single_selection')
		sel = self.sel()
		pos = sel[0].b

		found = None
		finds = self.find_all(string)
		if not forward:
			finds = reversed(finds)

		for find in finds:
			if not forward and find.a < pos:
				found = find
			elif forward and find.a > pos:
				found = find
			else:
				continue
			break
		
		if len(finds) > 0 and not found:
			if forward:
				found = finds[0]
			else:
				found = finds[-1]

		if found:
			sel.subtract(sel[0])
			# region must be reversed for backwards find to work
			found = sublime.Region(found.b, found.a)
			self.show_at_center(found)
			sel.add(found)
	
	def increment_num(self, edit, p, by=1):
		if self.substr(p).isdigit(): digit = True
		elif self.substr(p-1).isdigit():
			p -= 1
			digit = True
		else:
			digit = False

		if digit:
			line = self.line(p)
			leftmost, rightmost = p, p+1
			for i in xrange(p-1, line.a-1, -1):
				c = self.substr(i)
				if c == '-':
					leftmost = i
					break
				elif not c.isdigit(): break
				leftmost = i
			
			for i in xrange(p+1, line.b+1):
				if not self.substr(i).isdigit(): break
				rightmost = i
			
			num = self.substr(leftmost, rightmost)
			num = int(num) + by
			self.replace(edit, sublime.Region(leftmost, rightmost), str(num))
	
	def substr(self, arg, end=None):
		try:
			p = int(arg)
			if end != None:
				end = int(end)
			else:
				end = p+1

			return self.view.substr(sublime.Region(p, end))
		except TypeError:
			return self.view.substr(arg)

	def save(self):
		self.run_command('save')
	
	def delete_line(self, edit, num=1):
		pass

	def delete_char(self, edit, num=1):
		for cur in self.sel():
			if cur.empty():
				next = sublime.Region(cur.a, cur.a+1)
				if self.line(cur) == self.line(next):
					self.erase(edit, next)
	
	def key_colon(self, edit, string):
		view = self.view
		window = view.window()
		sel = view.sel()
		line = None

		start = string[0]
		remains = string[1:]
		if start in ('+', '-') and remains.isdigit():
			view.run_command('single_selection')
			line = view.rowcol(sel[0].a)[0]
			shift = int(remains)

			if start == '+': line += shift
			else: line -= shift
		
		elif string == '$':
			line = view.visible_region().b

		elif string.isdigit():
			line = max(int(string) - 1, 0)

		elif string == 'w':
			self.save()

		elif string == 'wq':
			view.run_command('save')
			window.run_command('close')
		
		elif string == 'q!':
			if view.is_dirty():
				view.run_command('revert')
			
			window.run_command('close')

		elif string == 'q':
			if not view.is_dirty():
				window.run_command('close')
		
		elif string == 'x':
			if view.is_dirty():
				view.run_command('save')
			
			window.run_command('close')
		
		elif string == 'n':
			window.run_command('next_view')
		
		elif string == 'N':
			window.run_command('prev_view')

		if line != None:
			point = view.text_point(line, 0)
			
			sel.clear()
			line = view.line(point)

			cur = sublime.Region(line.a, line.a)
			sel.add(cur)

			view.show(sel)
	
	def key_slash(self, edit, string):
		self.find_replace(edit, string)
	
	def key_escape(self, edit):
		if self.mode != 'command' and len(self.sel()) == 1:
			self.set_mode('command')
		else:
			self.escape()
		return True

	def key_char(self, edit, char):
		if self.mode == 'command':
			self.command(edit, char)
		
		elif self.mode == 'insert':
			self.natural_insert(char, edit)
		
		elif self.mode == 'replace':
			self.delete_char(edit)
			self.natural_insert(char, edit)
			self.set_mode('command')
	
	def key_arrow(self, direction):
		InsertView.key_arrow(self, direction)

	def command(self, edit, char):
		print 'command', self.cmd, char
		mode = self.mode
		view = self.view
		sel = view.sel()

		if not self.cmd:
			if char == 'a':
					mode = 'insert'
					for cur in sel:
						sel.subtract(cur)
						if cur.empty():
							next = sublime.Region(cur.b+1, cur.b+1)
						
						if not cur.empty() or not view.line(next).contains(cur):
							next = sublime.Region(cur.b, cur.b)

						sel.add(next)
			if char == 'A':
				mode = 'insert'
				for cur in sel:
					sel.subtract(cur)
					next = view.line(cur.b).b
					sel.add(sublime.Region(next, next))

			elif char == 'i':
				mode = 'insert'

			elif char == 'r':
				mode = 'replace'

			elif char in ('O', 'o'):
				for cur in sel:
					line = view.line(cur.a)
					if char == 'o':
						p = view.line(line.b+1).a
					else:
						p = line.a
						line = view.line(p-1)

					next = sublime.Region(p, p)
					end = view.visible_region().b

					sel.subtract(cur)
					if line.b < end:
						self.insert(edit, line.b, '\n')
						sel.add(next)
					else:
						self.insert(edit, end, '\n')
						sel.add(sublime.Region(end+1, end+1))

					mode = 'insert'

				view.run_command('reindent')
				for cur in sel:
					line = view.line(cur.a)
					if char == 'o':
						old = view.line(line.a-1)
					else:
						old = view.line(line.b+1)
					
					text = view.substr(old)
					if not re.match('\s', text):
						view.replace(edit, line, '')
			
			elif char == 'v':
				mode = 'visual'

			elif char == 'V':
				mode = 'visual line'
				
			elif char == 'u':
				pass
				# view.run_command('undo')
			
			elif char == 'x':
				for cur in sel:
					if cur.empty():
						if cur.a == view.line(cur).b:
							prev = sublime.Region(cur.a-1, cur.a-1)
							if view.line(prev).contains(cur):
								sel.subtract(cur)
								sel.add(prev)

				self.delete_char(edit)

			elif char == 'p':
				if self.yank:
					for cur in sel:
						sel.subtract(cur)
						p = view.full_line(cur.b).b
						sel.add(sublime.Region(p, p))
					self.natural_insert('\n'.join(self.yank))

					for cur in sel:
						sel.subtract(cur)
						p = view.line(view.line(cur.b).a-1).a
						sel.add(sublime.Region(p, p))
			
			elif char == 'P':
				if self.yank:
					old = [cur for cur in sel]
					self.natural_insert('\n'.join(self.yank))

					sel.clear()
					for cur in old:
						sel.add(cur)

			elif char == 'w':
				view.run_command('move', {'by': 'subwords', 'forward': True})
			elif char == 'b':
				view.run_command('move', {'by': 'subwords', 'forward': False})

			elif char == 'e':
				view.run_command('move', {'by': 'subword_ends', 'forward':True})

			elif char == 'h': self.key_arrow('left')
			elif char == 'j': self.key_arrow('down')
			elif char == 'k': self.key_arrow('up')
			elif char == 'l': self.key_arrow('right')
			elif char == 'n': self.find_replace(edit, self.last_find)
			elif char == 'N': self.find_replace(edit, self.last_find, forward=False)

			elif char in ('c', 'd', 'y', 'f'):
				self.cmd = char
			elif char == 'D':
				self.yank = []
				for cur in sel:
					eol = view.line(cur.a).b
					cur_to_eol = view.substr(sublime.Region(cur.a, eol))
					self.yank.append(cur_to_eol)
					view.erase(edit, sublime.Region(cur.a, eol))

			elif char == 'Y':
				self.yank = []
				for cur in sel:
					self.yank.append(view.substr(view.full_line(cur.b)))

			elif char == '$':
				for cur in sel:
					sel.subtract(cur)
					p = view.line(cur.b).b
					sel.add(sublime.Region(p, p))
			elif char == '0':
				for cur in sel:
					sel.subtract(cur)
					p = view.line(cur.b).a
					sel.add(sublime.Region(p, p))
			elif char in string.digits:
				print 'number handling later!'

		else:
			if self.cmd == char:
				if char == 'd':
					self.yank = []
					for cur in sel:
						self.yank.append(view.substr(view.full_line(cur.b)))

					points = set()
					for cur in sel:
						points.add(cur.b)
					
					for point in points:
						line = view.full_line(point)
						view.replace(edit, line, '')

				elif char == 'y':
					self.yank = []
					for cur in sel:
						self.yank.append(view.substr(view.full_line(cur.b)))
										

				self.cmd = ''
			else:
				if self.cmd == 'f':
					for cur in sel:
						eol = view.line(cur.a).b
						cur_to_eol = view.substr(sublime.Region(cur.a+1, eol))
						index = cur_to_eol.find(char) + 1
						if(index > 0):
							sel.subtract(cur)
							sel.add(sublime.Region(cur.a+index, cur.b+index))


				if self.cmd in ('c', 'd', 'y'):
					# hack to grab the partial word area for all cursors for b, e
					if char in ('b', 'e'):
						for cur in sel:
							sel.subtract(cur)
							sel.add(sublime.Region(cur.b, cur.b))
						
						saved = [cur for cur in sel]

						if char == 'b':
							view.run_command('move', {'by': 'subwords', 'forward':False, 'extend':True})
						elif char == 'e':
							view.run_command('move', {'by': 'subword_ends', 'forward':True, 'extend':True})

						self.yank = []
						for cur in sel:
							self.yank.append(view.substr(cur))
						
						sel.clear()
						for cur in saved:
							sel.add(cur)

						cmd = self.cmd
						if cmd in ('c', 'd'):
							if char == 'b':
								view.run_command('delete_word', {'forward': False})
							elif char == 'e':
								view.run_command('delete_word', {'forward': True})

							if cmd == 'c':
								mode = 'insert'

				self.cmd = ''
		
		self.set_mode(mode)

if not 'views' in globals():
	views = {}
else:
	for vid in list(views):
		static = views[vid].static
		view = views[vid] = View(views[vid].view)
		view.static.update(static)
		view.set_mode()

class VimBase(sublime_plugin.TextCommand):
	def get_view(self):
		view = self.view
		vid = view.id()
		if not vid in views:
			view = views[vid] = InsertView(view)
		else:
			view = views[vid]
		
		return view
	
	def run(self, edit): pass

class VimHook(VimBase):
	def run(self, edit):
		view = self.get_view()

		if 'hook' in dir(self):
			return self.hook(view, edit)
		else:
			return False

class VimInsertHook(VimHook):
	def run(self, edit):
		if not VimHook.run(self, edit):
			self.get_view().natural_insert(self.char, edit)

class VimEscape(VimHook):
	def hook(self, view, edit):
		view.key_escape(edit)

class VimColon(VimInsertHook):
	char = ':'

	def on_done(self, content):
		content = content.replace(':', '', 1)
		if not content: return

		view = self.get_view()
		with view.edit() as edit:
			view.key_colon(edit, content)

	def on_change(self, content):
		if not content.startswith(':'):
			self.view.window().run_command('hide_panel')
		
	def on_cancel(self):
		print 'cancel'

	def hook(self, view, edit):
		if view.mode == 'command':
			view.window().show_input_panel('Line', ':', self.on_done, self.on_change, self.on_cancel)
			return True

class VimSlash(VimInsertHook):
	char = '/'

	def on_done(self, content):
		content = content.replace('/', '', 1)
		view = self.get_view()
		with view.edit() as edit:
			view.key_slash(edit, content)

	def on_change(self, content):
		if not content.startswith('/'):
			self.view.window().run_command('hide_panel')
		
	def on_cancel(self):
		print 'cancel'

	def hook(self, view, edit):
		if view.mode == 'command':
			view.window().show_input_panel('Search', '/', self.on_done, self.on_change, self.on_cancel)
			return True

class VimChar(VimInsertHook):
	def hook(self, view, edit):
		view.key_char(edit, self.char)
		return True

class VimArrow(VimHook):
	def hook(self, view, edit):
		view.key_arrow(self.direction)

class VimCtrlA(VimHook):
	def hook(self, view, edit):
		print 'command: ctrl+a'
		sel = view.sel()
	 	if view.mode == 'command':
			for cur in view.sel():
				p = cur.b
				view.increment_num(edit, p)
		else:
			sel.clear()
			sel.add(view.visible_region())

class VimCtrlX(VimHook):
	def hook(self, view, edit):
		print 'command: ctrl+x'
		if view.mode == 'command':
			for cur in view.sel():
				p = cur.b
				view.increment_num(edit, p, -1)
		else:
			pass
			# dd the line

# tracks open views
class Vim(sublime_plugin.EventListener):
	def add(self, view):
		vid = view.id()
		views[vid] = View(view)

	def on_load(self, view):
		self.add(view)
	
	def on_new(self, view):
		self.add(view)
	
	def on_close(self, view):
		vid = view.id()
		if vid in views:
			del views[vid]

# automatic letter classes
def add_hook(name, cls, **kwargs):
	globals()[name] = type(name, (cls,), kwargs)

for char in string.letters:
	name = 'Vim' + char.upper()
	if char == char.upper():
		name += '_upper'
	
	add_hook(name, VimChar, char=char)

for num in string.digits:
	name = 'Vim_' + num
	add_hook(name, VimChar, char=num)

for sym in ["(", ")", "="]:
	name = "Vim_" + sym
	add_hook(name, VimChar, char=sym)

for d in ('up', 'down', 'left', 'right'):
	name = 'Vim' + d.capitalize()

	add_hook(name, VimArrow, direction=d)

add_hook('Vim_dollar', VimChar, char='$')