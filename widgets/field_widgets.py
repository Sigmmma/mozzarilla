import os
import tkinter as tk

from array import array
from tkinter.filedialog import askopenfilename, asksaveasfilename
from traceback import format_exc

from supyr_struct.buffer import get_rawdata
from supyr_struct.defs.audio.wav import wav_def
from supyr_struct.defs.util import *

from reclaimer.h2.constants import *
from binilla.widgets.field_widgets import *
from mozzarilla import editor_constants as e_c


class HaloRawdataFrame(RawdataFrame):

    def delete_node(self):
        if None in (self.parent, self.node):
            return

        undo_node = self.node
        self.node = self.parent[self.attr_index] = self.node[0:0]
        self.set_edited()

        self.edit_create(undo_node=undo_node, redo_node=self.node)

        # reload the parent field widget so sizes will be updated
        try:
            self.f_widget_parent.reload()
        except Exception:
            print(format_exc())
            print("Could not reload after deleting data.")

    def edit_apply(self=None, *, edit_state, undo=True):
        attr_index = edit_state.attr_index

        w_parent, parent = FieldWidget.get_widget_and_node(
            nodepath=edit_state.nodepath, tag_window=edit_state.tag_window)

        if undo:
            parent[attr_index] = edit_state.undo_node
        else:
            parent[attr_index] = edit_state.redo_node

        if w_parent is not None:
            try:
                w = w_parent.f_widgets[
                    w_parent.f_widget_ids_map[attr_index]]
                if w.desc is not edit_state.desc:
                    return

                w.node = parent[attr_index]
                w.set_edited()
                w.f_widget_parent.reload()
            except Exception:
                print(format_exc())


class HaloScriptSourceFrame(HaloRawdataFrame):
    @property
    def field_ext(self): return '.hsc'


class SoundSampleFrame(HaloRawdataFrame):

    @property
    def field_ext(self):
        '''The export extension of this FieldWidget.'''
        try:
            if self.parent.parent.compression.enum_name == 'ogg':
                return '.ogg'
        except Exception:
            pass
        return '.wav'

    def import_node(self):
        '''Prompts the user for an exported node file.
        Imports data into the node from the file.'''
        try:
            initialdir = self.tag_window.app_root.last_load_dir
        except AttributeError:
            initialdir = None

        ext = self.field_ext

        filepath = askopenfilename(
            initialdir=initialdir, defaultextension=ext,
            filetypes=[(self.name, "*" + ext), ('All', '*')],
            title="Import sound data from...", parent=self)

        if not filepath:
            return

        ext = os.path.splitext(filepath)[1].lower()

        curr_size = None
        index = self.attr_index

        try:
            curr_size = self.parent.get_size(attr_index=index)

            if ext == '.wav':
                # if the file is wav, we need to give it a header
                wav_file = wav_def.build(filepath=filepath)

                sound_data = self.parent.get_root().data.tagdata
                channel_count = sound_data.encoding.data + 1
                sample_rate = 22050 * (sound_data.sample_rate.data + 1)
                wav_fmt = wav_file.data.format

                if wav_fmt.fmt.enum_name not in ('ima_adpcm', 'xbox_adpcm',
                                                 'pcm'):
                    raise TypeError(
                        "Wav file audio format must be either ImaADPCM " +
                        "XboxADPCM, or PCM, not %s" % wav_fmt.fmt.enum_name)

                if sound_data.encoding.data + 1 != wav_fmt.channels:
                    raise TypeError(
                        "Wav file channel count does not match this sound " +
                        "tags channel count. Expected %s, not %s" %
                        (channel_count, wav_fmt.channels))

                if sample_rate != wav_fmt.sample_rate:
                    raise TypeError(
                        "Wav file sample rate does not match this sound " +
                        "tags sample rate. Expected %skHz, not %skHz" %
                        (sample_rate, wav_fmt.sample_rate))

                if 36 * channel_count != wav_fmt.block_align:
                    raise TypeError(
                        "Wav file block size does not match this sound " +
                        "tags block size. Expected %sbytes, not %sbytes" %
                        (36 * channel_count, wav_fmt.block_align))

                rawdata = wav_file.data.wav_data.audio_data
            else:
                rawdata = get_rawdata(filepath=filepath, writable=False)

            undo_node = self.node
            self.parent.set_size(len(rawdata), attr_index=index)
            self.parent.parse(rawdata=rawdata, attr_index=index)
            self.node = self.parent[index]

            self.set_edited()
            self.edit_create(undo_node=undo_node, redo_node=self.node)

            # reload the parent field widget so sizes will be updated
            try:
                self.f_widget_parent.reload()
            except Exception:
                print(format_exc())
                print("Could not reload after importing sound data.")
        except Exception:
            print(format_exc())
            print("Could not import sound data.")
            try: self.parent.set_size(curr_size, attr_index=index)
            except Exception: pass

    def export_node(self):
        try:
            initialdir = self.tag_window.app_root.last_load_dir
        except AttributeError:
            initialdir = None

        def_ext = self.field_ext

        filepath = asksaveasfilename(
            initialdir=initialdir, title="Export sound data to...",
            parent=self, filetypes=[(self.name, '*' + def_ext),
                                    ('All', '*')])

        if not filepath:
            return

        filepath, ext = os.path.splitext(filepath)
        if not ext: ext = def_ext
        filepath += ext

        if ext == '.wav':
            # if the file is wav, we need to give it a header
            try:
                wav_file = wav_def.build()
                wav_file.filepath = filepath
                sound_data = self.parent.get_root().data.tagdata

                wav_fmt = wav_file.data.format
                wav_fmt.bits_per_sample = 16
                wav_fmt.channels = sound_data.encoding.data + 1
                wav_fmt.sample_rate = 22050 * (sound_data.sample_rate.data + 1)

                wav_fmt.byte_rate = ((wav_fmt.sample_rate *
                                      wav_fmt.bits_per_sample *
                                      wav_fmt.channels) // 8)

                typ = "ima_adpcm"
                if self.parent.parent.compression.enum_name == 'none':
                    typ = "pcm"

                if typ == "pcm":
                    wav_fmt.fmt.set_to('pcm')
                    wav_fmt.block_align = 2 * wav_fmt.channels
                else:
                    wav_fmt.fmt.set_to('ima_adpcm')
                    wav_fmt.block_align = 36 * wav_fmt.channels

                wav_file.data.wav_data.audio_data = self.node
                wav_file.data.wav_header.filesize = wav_file.data.binsize - 12

                wav_file.serialize(temp=False, backup=False, int_test=False)
            except Exception:
                print(format_exc())
                print("Could not export sound data.")
            return

        try:
            if hasattr(self.node, 'serialize'):
                self.node.serialize(filepath=filepath, clone=self.export_clone,
                                    calc_pointers=self.export_calc_pointers)
            else:
                # the node isnt a block, so we need to call its parents
                # serialize method with the attr_index necessary to export.
                self.parent.serialize(filepath=filepath,
                                      clone=self.export_clone,
                                      calc_pointers=self.export_calc_pointers,
                                      attr_index=self.attr_index)
        except Exception:
            print(format_exc())
            print("Could not export sound data.")


class ReflexiveFrame(DynamicArrayFrame):
    export_all_btn = None
    import_all_btn = None

    def __init__(self, *args, **kwargs):
        DynamicArrayFrame.__init__(self, *args, **kwargs)

        btn_kwargs = dict(
            bg=self.button_color, fg=self.text_normal_color,
            disabledforeground=self.text_disabled_color,
            bd=self.button_depth,
            state=tk.DISABLED if self.disabled else tk.NORMAL
            )

        self.import_all_btn = tk.Button(
            self.title, width=8, text='Import all',
            command=self.import_all_nodes, **btn_kwargs)
        self.export_all_btn = tk.Button(
            self.buttons, width=8, text='Export all',
            command=self.export_all_nodes, **btn_kwargs)

        # unpack all the buttons
        for w in (self.export_btn, self.import_btn,
                  self.shift_down_btn, self.shift_up_btn,
                  self.delete_all_btn, self.delete_btn,
                  self.duplicate_btn, self.insert_btn, self.add_btn):
            w.forget()

        # pack all the buttons(and new ones)
        for w in (self.export_all_btn, self.import_all_btn,
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


# replace the DynamicEnumFrame with one that has a specialized option generator
def halo_dynamic_enum_cache_options(self):
    desc = self.desc
    options = {0: "-1: NONE"}

    dyn_name_path = desc.get(DYN_NAME_PATH)
    if self.node is None:
        return
    elif not dyn_name_path:
        print("Missing DYN_NAME_PATH path in dynamic enumerator.")
        print(self.parent.get_root().def_id, self.name)
        print("Tell Moses about this.")
        self.option_cache = options
        return

    try:
        p_out, p_in = dyn_name_path.split(DYN_I)

        # We are ALWAYS going to go to the parent, so we need to slice
        if p_out.startswith('..'): p_out = p_out.split('.', 1)[-1]
        array = self.parent.get_neighbor(p_out)
        for i in range(len(array)):
            name = array[i].get_neighbor(p_in)
            if isinstance(name, list):
                name = repr(name).strip("[").strip("]")
            else:
                name = str(name)

            if p_in.endswith('.filepath'):
                # if it is a dependency filepath
                options[i + 1] = '%s. %s' % (
                    i, name.replace('/', '\\').split('\\')[-1])
            options[i + 1] = '%s. %s' % (i, name)
    except Exception:
        print(format_exc())
        print("Guess something got mistyped. Tell Moses about this.")
        dyn_name_path = False

    try:
        self.sel_menu.max_index = len(options) - 1
    except Exception:
        pass
    self.option_cache = options

DynamicEnumFrame.cache_options = halo_dynamic_enum_cache_options
