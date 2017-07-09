import tkinter as tk

from binilla.widgets import BinillaWidget
from supyr_struct.defs.constants import *
from supyr_struct.defs.util import *


class SearchAndReplaceWindow(BinillaWidget, tk.Toplevel):

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        kwargs.update(width=450, height=270, bd=0, highlightthickness=0)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Search and Replace(beta)")
        self.minsize(width=450, height=270)
        self.resizable(1, 0)

        # make the tkinter variables
        self.find_var = tk.StringVar(self)
        self.replace_var = tk.StringVar(self)

        # make the frames
        self.comment_frame = tk.Frame(
            self, relief='sunken', bd=self.comment_depth,
            bg=self.comment_bg_color)
        self.find_frame = tk.LabelFrame(self, text="Find this")
        self.replace_frame = tk.LabelFrame(self, text="Replace with this")

        self.search_button = tk.Button(
            self, text='Count occurrances', width=20, command=self.search)
        self.replace_button = tk.Button(
            self, text='Replace occurrances', width=20, command=self.replace)

        self.find_entry = tk.Entry(
            self.find_frame, textvariable=self.find_var)
        self.replace_entry = tk.Entry(
            self.replace_frame, textvariable=self.replace_var)
        self.comment = tk.Label(
            self.comment_frame, anchor='nw', bg=self.comment_bg_color,
            justify='left', font=self.app_root.comment_font,
            text="""Things to note:
  Only strings can be found/replaced. If you type in a number,
  a string consisting of that number will be searched/replaced.

  If the replacement is too long to use, you will be alerted.

  You cannot undo/redo these replacements, so be careful.""")

        self.comment.pack(side='left', fill='both', expand=True)
        self.comment_frame.pack(fill='both', expand=True)

        self.find_frame.pack(fill="x", expand=True, padx=5)
        self.find_entry.pack(fill="x", expand=True, padx=5, pady=2)
        self.search_button.pack(fill="x", anchor='center', padx=5, pady=(0,4))

        self.replace_frame.pack(fill="x", expand=True, padx=5)
        self.replace_entry.pack(fill="x", expand=True, padx=5, pady=2)
        self.replace_button.pack(fill="x", anchor='center', padx=5, pady=(0,4))

        self.apply_style()
        self.transient(app_root)

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        for w in (self.find_frame, self.replace_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        for w in (self.search_button, self.replace_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        for w in (self.find_entry, self.replace_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

    def destroy(self):
        self.app_root.tool_windows.pop("s_and_r_window", None)
        tk.Toplevel.destroy(self)

    def search(self, e=None):
        self.search_and_replace()

    def replace(self, e=None):
        self.search_and_replace(True)

    def search_and_replace(self, replace=False):
        app_root = self.app_root
        try:
            window = app_root.get_tag_window_by_tag(app_root.selected_tag)
        except Exception:
            window = None

        if window is None:
            return

        find_str = self.find_var.get()
        replace_str = self.replace_var.get()

        f_widgets = window.field_widget.f_widgets.values()
        nodes = window.tag.data
        occurances = 0

        while nodes:
            new_nodes = []
            for node in nodes:
                if not isinstance(node, list):
                    continue

                attrs = range(len(node))
                if hasattr(node, 'STEPTREE'):
                    attrs = tuple(attrs) + ('STEPTREE',)
                for i in attrs:
                    val = node[i]
                    if not isinstance(val, str) or find_str != val:
                        continue

                    if not replace:
                        occurances += 1
                        continue

                    desc = node.get_desc(i)
                    f_type = desc['TYPE']

                    field_max = desc.get('MAX', f_type.max)
                    if field_max is None:
                        field_max = desc.get('SIZE')
                    replace_size = f_type.sizecalc(replace_str)
                    if replace_size > field_max:
                        print("String replacement must be less than " +
                               "%s bytes when encoded, not %s." % (
                                   field_max, replace_size))
                        continue

                    occurances += 1
                    node[i] = replace_str
                try:
                    if isinstance(node, list):
                        new_nodes.extend(node)
                    if hasattr(node, 'STEPTREE'):
                        new_nodes.append(node.STEPTREE)
                except Exception:
                    pass

            nodes = new_nodes

        if not replace:
            print('Found %s occurances' % occurances)
            return

        while f_widgets:
            new_f_widgets = []
            for w in f_widgets:
                try: new_f_widgets.extend(w.f_widgets.values())
                except Exception: pass

                if not hasattr(w, 'entry_string'):
                    continue

                try:
                    desc = w.desc
                    f_type = desc['TYPE']

                    # dont want to run this unless the nodes type is a string
                    if not isinstance(f_type.node_cls, str):
                        continue

                    field_max = w.field_max
                    if field_max is None:
                        field_max = desc.get('SIZE')

                    if f_type.sizecalc(replace_str) > field_max:
                        #print("Replacement string too long to fit.")
                        continue
                except AttributeError:
                    continue

                e_str = w.entry_string
                if find_str == e_str.get():
                    e_str.set(replace_str)

            f_widgets = new_f_widgets

        print('Found and replaced %s occurances' % occurances)
        # reload the window to display the newly entered info
        window.reload()
