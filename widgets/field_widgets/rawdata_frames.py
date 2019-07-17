import copy
import os
import tkinter as tk

from tkinter.filedialog import askopenfilename, asksaveasfilename
from traceback import format_exc

from supyr_struct.buffer import get_rawdata
from supyr_struct.defs.audio.wav import wav_def
from supyr_struct.util import sanitize_path

from binilla.widgets.field_widgets import FieldWidget, RawdataFrame

from reclaimer.meta.wrappers.byteswapping import byteswap_pcm16_samples


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
                typ = wav_fmt.fmt.enum_name
                block_align = (2 if typ == "pcm" else 36) * wav_fmt.channels

                if typ not in ('ima_adpcm', 'xbox_adpcm', 'pcm'):
                    raise TypeError(
                        "Wav file audio format must be either ImaADPCM " +
                        "XboxADPCM, or PCM, not %s" % wav_fmt.fmt.enum_name)
                elif sound_data.encoding.data + 1 != wav_fmt.channels:
                    raise TypeError(
                        "Wav file channel count does not match this sound " +
                        "tags channel count. Expected %s, not %s" %
                        (channel_count, wav_fmt.channels))
                elif sample_rate != wav_fmt.sample_rate:
                    raise TypeError(
                        "Wav file sample rate does not match this sound " +
                        "tags sample rate. Expected %skHz, not %skHz" %
                        (sample_rate, wav_fmt.sample_rate))
                elif block_align != wav_fmt.block_align:
                    raise TypeError(
                        "Wav file block size does not match this sound " +
                        "tags block size. Expected %sbytes, not %sbytes" %
                        (block_align, wav_fmt.block_align))

                rawdata = wav_file.data.wav_data.audio_data
                do_pcm_byteswap = (typ == 'pcm')
            else:
                rawdata = get_rawdata(filepath=filepath, writable=False)
                do_pcm_byteswap = False

            undo_node = self.node
            self.parent.set_size(len(rawdata), attr_index=index)
            self.parent.parse(rawdata=rawdata, attr_index=index)

            if do_pcm_byteswap:
                byteswap_pcm16_samples(self.parent)

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

                audio_data = copy.deepcopy(self.parent)
                if typ == "pcm":
                    wav_fmt.fmt.set_to('pcm')
                    wav_fmt.block_align = 2 * wav_fmt.channels
                    byteswap_pcm16_samples(audio_data)
                else:
                    wav_fmt.fmt.set_to('ima_adpcm')
                    wav_fmt.block_align = 36 * wav_fmt.channels

                wav_file.data.wav_data.audio_data = audio_data.data
                wav_file.data.wav_header.filesize = wav_file.data.binsize - 12

                wav_file.serialize(temp=False, backup=False, int_test=False)
            except Exception:
                print(format_exc())
                print("Could not export sound data.")
            return

        try:
            if hasattr(self.node, 'serialize'):
                self.node.serialize(
                    filepath=filepath, clone=self.export_clone,
                    calc_pointers=self.export_calc_pointers)
            else:
                # the node isnt a block, so we need to call its parents
                # serialize method with the attr_index necessary to export.
                self.parent.serialize(
                    filepath=filepath, clone=self.export_clone,
                    calc_pointers=self.export_calc_pointers,
                    attr_index=self.attr_index)
        except Exception:
            print(format_exc())
            print("Could not export sound data.")
