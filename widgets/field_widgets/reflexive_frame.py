import tkinter as tk
import tkinter.ttk as ttk

from traceback import format_exc

from binilla.constants import DYN_NAME_PATH, DYN_I
from binilla.widgets.field_widgets.array_frame import DynamicArrayFrame


class ReflexiveFrame(DynamicArrayFrame):
    export_all_btn = None
    import_all_btn = None

    def __init__(self, *args, **kwargs):
        DynamicArrayFrame.__init__(self, *args, **kwargs)

        btn_state = tk.DISABLED if self.disabled else tk.NORMAL

        self.import_all_btn = ttk.Button(
            self.title, width=11, text='Import all',
            command=self.import_all_nodes, state=btn_state)
        self.export_all_btn = ttk.Button(
            self.buttons, width=11, text='Export all',
            command=self.export_all_nodes, state=btn_state)

        # unpack all the buttons
        for w in (self.export_btn, self.import_btn,
                  self.shift_down_btn, self.shift_up_btn,
                  self.delete_all_btn, self.delete_btn,
                  self.duplicate_btn, self.insert_btn, self.add_btn):
            w.forget()

        # pack all the buttons(and new ones)
        # due to extra frame padding, this needs one less pixel on x
        self.import_all_btn.pack(side="right", padx=(0, 3), pady=(2, 2))

        for w in (self.export_all_btn,
                  self.shift_down_btn, self.shift_up_btn,
                  self.export_btn, self.import_btn,
                  self.delete_all_btn, self.delete_btn,
                  self.duplicate_btn, self.insert_btn, self.add_btn):
            w.pack(side="right", padx=(0, 4), pady=(2, 2))

    def set_disabled(self, disable=True):
        disable = disable or not self.editable
        if self.node is None and not disable:
            return

        if bool(disable) != self.disabled:
            new_state = tk.DISABLED if disable else tk.NORMAL
            for w in (self.export_all_btn, self.import_all_btn):
                if w:
                    w.config(state=new_state)

        DynamicArrayFrame.set_disabled(self, disable)

    def cache_options(self):
        node, desc = self.node, self.desc
        dyn_name_path = desc.get(DYN_NAME_PATH)
        if node is None:
            dyn_name_path = ""

        options = {}
        if dyn_name_path:
            try:
                if dyn_name_path.endswith('.filepath'):
                    # if it is a dependency filepath
                    for i in range(len(node)):
                        name = str(node[i].get_neighbor(dyn_name_path))\
                               .replace('/', '\\').split('\\')[-1]\
                               .split('\n')[0]
                        if name:
                            options[i] = name
                else:
                    for i in range(len(node)):
                        name = str(node[i].get_neighbor(dyn_name_path))
                        if name:
                            options[i] = name.split('\n')[0]

            except Exception:
                print(format_exc())
                print("Guess something got mistyped. Tell Moses about it.")
                dyn_name_path = False

        if not dyn_name_path:
            # sort the options by value(values are integers)
            options.update({i: n for n, i in
                            self.desc.get('NAME_MAP', {}).items()
                            if i not in options})
            sub_desc = desc['SUB_STRUCT']
            def_struct_name = sub_desc.get('GUI_NAME', sub_desc['NAME'])

            for i in range(len(node)):
                if i in options:
                    continue
                sub_node = node[i]
                if not hasattr(sub_node, 'desc'):
                    continue
                sub_desc = sub_node.desc
                sub_struct_name = sub_desc.get('GUI_NAME', sub_desc['NAME'])
                if sub_struct_name == def_struct_name:
                    continue

                options[i] = sub_struct_name

        for i, v in options.items():
            options[i] = '%s. %s' % (i, v)

        self.option_cache = options

    def set_import_all_disabled(self, disable=True):
        if disable: self.import_all_btn.config(state="disabled")
        else:       self.import_all_btn.config(state="normal")

    def set_export_all_disabled(self, disable=True):
        if disable: self.export_all_btn.config(state="disabled")
        else:       self.export_all_btn.config(state="normal")

    def export_all_nodes(self):
        try:
            w = self.f_widget_parent
        except Exception:
            return
        w.export_node()

    def import_all_nodes(self):
        try:
            w = self.f_widget_parent
        except Exception:
            return
        w.import_node()
