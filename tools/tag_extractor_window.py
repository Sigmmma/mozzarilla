import tkinter as tk
import mmap

from os import makedirs
from os.path import dirname, exists, join
from time import time
from tkinter.filedialog import askopenfilename, askdirectory
from traceback import format_exc

from .shared_widgets import HierarchyFrame
from .hashcacher_window import INVALID_PATH_CHARS
from binilla.widgets import BinillaWidget
from reclaimer.os_v4_hek.handler import OsV4HaloHandler,\
     tag_class_be_int_to_fcc_os,     tag_class_fcc_to_ext_os,\
     tag_class_be_int_to_fcc_stubbs, tag_class_fcc_to_ext_stubbs
from reclaimer.meta.halo1_map import get_map_version, get_map_header,\
     get_tag_index, get_index_magic, get_map_magic, decompress_map
from reclaimer.os_hek.defs.gelc import gelc_def
from supyr_struct.buffer import BytearrayBuffer
from supyr_struct.defs.constants import *
from supyr_struct.field_types import FieldType

from reclaimer.os_v4_hek.defs.antr import antr_def
from reclaimer.os_v4_hek.defs.bipd import bipd_def
from reclaimer.os_v4_hek.defs.cdmg import cdmg_def
from reclaimer.os_v4_hek.defs.coll import coll_def
from reclaimer.os_v4_hek.defs.jpt_ import jpt__def
from reclaimer.os_v4_hek.defs.mode import mode_def
from reclaimer.os_v4_hek.defs.soso import soso_def
from reclaimer.os_v4_hek.defs.unit import unit_def
from reclaimer.os_v4_hek.defs.vehi import vehi_def

from reclaimer.stubbs.defs.antr import antr_def as stubbs_antr_def
from reclaimer.stubbs.defs.cdmg import cdmg_def as stubbs_cdmg_def
from reclaimer.stubbs.defs.coll import coll_def as stubbs_coll_def
from reclaimer.stubbs.defs.jpt_ import jpt__def as stubbs_jpt__def
from reclaimer.stubbs.defs.mode import mode_def as stubbs_mode_def
from reclaimer.stubbs.defs.soso import soso_def as stubbs_soso_def
from reclaimer.stubbs.defs.imef import imef_def as imef_def

no_op = lambda *a, **kw: None

this_dir = dirname(__file__)

resource_names = rn = {}
rn['bitm'] = []
rn['font'] = rn['hmt '] = rn['str#'] = rn['ustr'] = []

# load the shared resource tag paths
for typ, name in (('bitm','bitmaps'),('font','loc')):
    try:
        paths = resource_names[typ]
        with open(this_dir + '\\resources\\%s.txt' % name) as f:
            for line in f:
                paths.append(line[:-1])
    except Exception:
        print(format_exc())


tag_cls_int_to_fcc = dict(tag_class_be_int_to_fcc_os)
tag_cls_int_to_ext = {}

tag_cls_int_to_fcc.update(tag_class_be_int_to_fcc_stubbs)

for key in tag_class_be_int_to_fcc_os:
    tag_cls_int_to_ext[key] = tag_class_fcc_to_ext_os[
        tag_class_be_int_to_fcc_os[key]]

for key in tag_class_be_int_to_fcc_stubbs:
    tag_cls_int_to_ext[key] = tag_class_fcc_to_ext_stubbs[
        tag_class_be_int_to_fcc_stubbs[key]]


def is_protected(tagpath):
    return not INVALID_PATH_CHARS.isdisjoint(set(tagpath))


class TagExtractorWindow(BinillaWidget, tk.Toplevel):
    app_root = None
    map_path = None
    out_dir  = None
    handler  = None

    _map_loaded = False
    _running = False
    _display_mode = "hierarchy"

    engine = None
    map_data = None  # the complete uncompressed map
    map_magic = None
    map_is_compressed = False
    stop_processing = False

    # these are the different pieces of the map as parsed blocks
    map_header = None
    tag_index = None

    scnr_meta = None

    # a cache of all the different headers for
    # each type of tag to speed up writing tags
    tag_headers = {}

    def __init__(self, app_root, *args, **kwargs):
        self.app_root = app_root
        kwargs.update(width=600, height=450, bd=0, highlightthickness=0)
        tk.Toplevel.__init__(self, app_root, *args, **kwargs)

        self.title("Tag Extractor")
        self.minsize(width=600, height=450)

        # make the tkinter variables
        self.map_path = tk.StringVar(self)
        self.out_dir = tk.StringVar(self)
        self.use_resource_names = tk.IntVar(self)
        self.use_hashcaches = tk.IntVar(self)
        self.use_heuristics = tk.IntVar(self)
        try:
            self.out_dir.set(self.app_root.tags_dir)
        except Exception:
            pass
        self.use_resource_names.set(1)

        self.map_path.set("Click browse to load a map for extraction")

        # make the window pane
        self.panes = tk.PanedWindow(self, sashwidth=4)

        # make the frames
        self.map_frame = tk.LabelFrame(self, text="Map to extract from")
        self.map_select_frame = tk.Frame(self.map_frame)
        self.map_action_frame = tk.Frame(self.map_frame)
        self.deprotect_frame = tk.LabelFrame(self, text="Deprotection settings")
        self.out_dir_frame = tk.LabelFrame(self, text="Location to extract to")

        self.explorer_frame = tk.LabelFrame(self.panes, text="Map contents")
        self.add_del_frame = tk.Frame(self.explorer_frame)
        self.queue_frame = tk.LabelFrame(self.panes, text="Extraction queue")

        self.hierarchy_frame = ExplorerHierarchyFrame(
            self.explorer_frame, app_root=self.app_root, select_mode='extended')

        # bind the queue_add to activating the hierarchy frame in some way
        self.hierarchy_frame.tags_tree.bind('<Double-Button-1>', self.queue_add)
        self.hierarchy_frame.tags_tree.bind('<Return>', self.queue_add)

        self.panes.add(self.explorer_frame)
        self.panes.add(self.queue_frame)

        # make the entries
        self.map_path_entry = tk.Entry(
            self.map_select_frame, textvariable=self.map_path, state='disabled')
        self.map_path_browse_button = tk.Button(
            self.map_select_frame, text="Browse",
            command=self.map_path_browse, width=6)

        self.out_dir_entry = tk.Entry(
            self.out_dir_frame, textvariable=self.out_dir, state='disabled')
        self.out_dir_browse_button = tk.Button(
            self.out_dir_frame, text="Browse",
            command=self.out_dir_browse, width=6)

        self.map_info_text = tk.Text(
            self.map_frame, font=self.app_root.fixed_font,
            state='disabled', height=8)

        # make the buttons
        self.begin_button = tk.Button(
            self.map_action_frame, text="Begin extraction",
            command=self.begin_extraction)
        self.cancel_button = tk.Button(
            self.map_action_frame, text="Cancel extraction",
            command=self.cancel_extraction)

        self.use_resource_names_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use resource names",
            variable=self.use_resource_names)
        self.use_hashcaches_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use hashcaches",
            variable=self.use_hashcaches)
        self.use_heuristics_checkbutton = tk.Checkbutton(
            self.deprotect_frame, text="Use heuristics",
            variable=self.use_heuristics)
        self.deprotect_button = tk.Button(
            self.deprotect_frame, text="Deprotect names",
            command=self.deprotect_names)

        self.add_button = tk.Button(self.add_del_frame, text="Add",
                                    width=4, command=self.queue_add)
        self.del_button = tk.Button(self.add_del_frame, text="Del",
                                    width=4, command=self.queue_del)

        self.add_all_button = tk.Button(
            self.add_del_frame, text="Add\nAll", width=4,
            command=self.queue_add_all)
        self.del_all_button = tk.Button(
            self.add_del_frame, text="Del\nAll", width=4,
            command=self.queue_del_all)

        # pack everything
        self.map_path_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.map_path_browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.cancel_button.pack(side='right', padx=4, pady=4)
        self.begin_button.pack(side='right', padx=4, pady=4)

        self.use_resource_names_checkbutton.pack(side='left', padx=4, pady=4)
        self.use_hashcaches_checkbutton.pack(side='left', padx=4, pady=4)
        self.use_heuristics_checkbutton.pack(side='left', padx=4, pady=4)
        self.deprotect_button.pack(side='right', padx=4, pady=4)

        self.map_select_frame.pack(fill='x', expand=True, padx=1)
        self.map_info_text.pack(fill='x', expand=True, padx=1)
        self.map_action_frame.pack(fill='x', expand=True, padx=1)

        self.out_dir_entry.pack(
            padx=(4, 0), pady=2, side='left', expand=True, fill='x')
        self.out_dir_browse_button.pack(padx=(0, 4), pady=2, side='left')

        self.add_button.pack(side='top', padx=2, pady=4)
        self.del_button.pack(side='top', padx=2, pady=(0, 20))
        self.add_all_button.pack(side='top', padx=2, pady=(20, 0))
        self.del_all_button.pack(side='top', padx=2, pady=4)

        self.explorer_frame.pack(fill='both', padx=1, expand=True)
        self.add_del_frame.pack(side='right', fill='y', anchor='center')
        self.hierarchy_frame.pack(side='right', fill='both', expand=True)
        self.queue_frame.pack(fill='y', padx=1, expand=True)

        self.map_frame.pack(fill='x', padx=1)
        self.out_dir_frame.pack(fill='x', padx=1)
        self.deprotect_frame.pack(fill='x', padx=1)
        self.panes.pack(fill='both', expand=True)

        self.panes.paneconfig(self.explorer_frame, sticky='nsew')
        self.panes.paneconfig(self.queue_frame, sticky='nsew')

        self.apply_style()
        self.transient(app_root)

        # make a new handler for handling all these tags to
        # ensure it doesn't muck with mozzarilla's handlers
        id_ext_map = {}
        defs = {}
        try:
            os_v4_handler = app_root.handlers[2]
            if not isinstance(os_v4_handler, type):
                id_ext_map = os_v4_handler.id_ext_map
                defs = os_v4_handler.defs
        except Exception:
            pass

        self.handler = handler = OsV4HaloHandler(
            id_ext_map=id_ext_map, defs=defs, reload_defs=not defs)
        self.handler.add_def(gelc_def)
        self.handler.add_def(imef_def)
        
        # create a bunch of tag headers for each type of tag
        for def_id in sorted(handler.defs):
            if len(def_id) != 4:
                continue
            h_desc = handler.defs[def_id].descriptor[0]
            
            h_block = [None]
            h_desc['TYPE'].parser(h_desc, parent=h_block, attr_index=0)
            b_buffer = h_block[0].serialize(buffer=BytearrayBuffer(),
                                            calc_pointers=False)

            self.tag_headers[def_id] = bytes(b_buffer)
            del b_buffer[:]

    @property
    def running(self):
        return self._running

    def destroy(self):
        self.app_root.tool_windows.pop("tag_extractor_window", None)
        self.unload_maps()
        FieldType.force_normal()
        tk.Toplevel.destroy(self)

    def queue_add(self, e=None):
        if not self._map_loaded:
            return

        tags_tree = self.hierarchy_frame.tags_tree

        iids = tags_tree.selection()
        if not iids:
            return

        # make a popup window asking how to extract this tag/directory

    def queue_del(self, e=None):
        if not self._map_loaded:
            return

        tags_tree = self.queue_frame.queue_tree

        iids = queue_tree.selection()
        if not iids:
            return

    def queue_add_all(self, e=None):
        if not self._map_loaded:
            return

        tags_tree = self.hierarchy_frame.tags_tree

        # make a popup window asking how to extract this tag/directory

    def queue_del_all(self, e=None):
        if not self._map_loaded:
            return

        tags_tree = self.queue_frame.queue_tree

    def unload_maps(self):
        try: self.map_data.close()
        except Exception: pass
        try: self.bitmap_data.close()
        except Exception: pass
        try: self.sound_data.close()
        except Exception: pass
        try: self.loc_data.close()
        except Exception: pass
        self.tag_index = self.map_header = self.scnr_meta = None
        self.bitmap_data = self.sound_data = self.loc_data = None
        self.map_data = self.map_magic = self.index_magic = None
        self._map_loaded = self._running = False
        self.stop_processing = True

    def set_defs(self):
        '''Switch definitions based on which game the map is for'''
        defs = self.handler.defs
        if "stubbs" in self.engine:
            defs["antr"] = stubbs_antr_def
            defs["bipd"] = None
            defs["cdmg"] = stubbs_cdmg_def
            defs["coll"] = stubbs_coll_def
            defs["jpt!"] = stubbs_jpt__def
            defs["mode"] = stubbs_mode_def
            defs["soso"] = stubbs_soso_def
            defs["unit"] = None
            defs["vehi"] = None
            defs["imef"] = imef_def
        else:
            defs["antr"] = antr_def
            defs["bipd"] = bipd_def
            defs["cdmg"] = cdmg_def
            defs["coll"] = coll_def
            defs["jpt!"] = jpt__def
            defs["mode"] = mode_def
            defs["soso"] = soso_def
            defs["unit"] = unit_def
            defs["vehi"] = vehi_def
            defs.pop("imef", None)

    def load_map(self, map_path=None):
        try:
            if map_path is None:
                map_path = self.map_path.get()
            if not exists(map_path):
                return
            elif self.running:
                return

            self._running = True
            self.map_path.set(map_path)

            with open(map_path, 'rb+') as f:
                comp_map_data = mmap.mmap(f.fileno(), 0)

            self.map_header = get_map_header(comp_map_data)
            self.engine = get_map_version(self.map_header)
            self.map_data = decompress_map(comp_map_data, self.map_header)
            self.map_is_compressed = len(comp_map_data) < len(self.map_data)

            self.index_magic = get_index_magic(self.map_header)
            self.map_magic = get_map_magic(self.map_header)
            self.tag_index = get_tag_index(self.map_data, self.map_header)
            self.set_defs()
            self._map_loaded = True

            try:
                base_tag_magic = self.tag_index.base_tag_magic
                self.scnr_meta = self.get_meta(base_tag_magic)
                tag_index = self.tag_index.tag_index
                for b in self.scnr_meta.structure_bsps.STEPTREE:
                    # copy the(non-magic) bsp pointers into the appropriate
                    # tag_index_ref in the tag_index and it them magical
                    bsp = b.structure_bsp
                    tag_id = (bsp.id - base_tag_magic) & 0xFFFF
                    tag_index[tag_id].meta_offset = (self.map_magic +
                                                     b.bsp_meta_pointer)
            except Exception:
                print(format_exc())
                self.display_map_info(
                    "Could not read scenario tag. Cannot extract anything.")
                self.unload_maps()
                return

            self.display_map_info()
            self.hierarchy_frame.map_magic = self.map_magic
            self.reload_map_explorer()

            maps_dir = dirname(map_path)

            bitmap_data = sound_data = loc_data = self.map_data
            bitmap_path = sound_path = loc_path = None
            if self.engine in ("pc", "pcdemo"):
                bitmap_path = join(maps_dir, "bitmaps.map")
                sound_path = join(maps_dir, "sounds.map")
            elif self.engine == "ce":
                bitmap_path = join(maps_dir, "bitmaps.map")
                sound_path = join(maps_dir, "sounds.map")
                loc_path = join(maps_dir, "loc.map")

            while bitmap_data is self.map_data and bitmap_path:
                try:
                    with open(bitmap_path, 'rb+') as f:
                        bitmap_data = mmap.mmap(f.fileno(), 0)
                        maps_dir = dirname(bitmap_path)
                except Exception:
                    bitmap_path = askopenfilename(
                        initialdir=maps_dir,
                        title="Select the bitmaps.map", parent=self,
                        filetypes=(("bitmaps.map", "*.map"), ("All", "*")))

            while sound_data is self.map_data and sound_path:
                try:
                    with open(sound_path, 'rb+') as f:
                        sound_data = mmap.mmap(f.fileno(), 0)
                        maps_dir = dirname(sound_path)
                except Exception:
                    sound_path = askopenfilename(
                        initialdir=maps_dir,
                        title="Select the sounds.map", parent=self,
                        filetypes=(("sounds.map", "*.map"), ("All", "*")))

            while loc_data is self.map_data and loc_path:
                try:
                    with open(loc_path, 'rb+') as f:
                        loc_data = mmap.mmap(f.fileno(), 0)
                        maps_dir = dirname(loc_path)
                except Exception:
                    loc_path = askopenfilename(
                        initialdir=maps_dir,
                        title="Select the loc.map", parent=self,
                        filetypes=(("loc.map", "*.map"), ("All", "*")))

            self.bitmap_data = self.sound_data = self.loc_data = self.map_data

            try:
                if comp_map_data is not self.map_data:
                    comp_map_data.close()
            except Exception:
                pass
        except Exception:
            try: comp_map_data.close()
            except Exception: pass
            self.display_map_info(
                "Could not load map.\nCheck console window for error.")
            self.reload_map_explorer()
            raise

        self._running = False

    def display_map_info(self, string=None):
        if string is None:
            if not self._map_loaded:
                return
            try:
                header = self.map_header
                index = self.tag_index
                comp_size = "uncompressed"
                if self.map_is_compressed:
                    comp_size = len(self.map_data)

                string = ((
                    "Engine == %s   Map type == %s   Decompressed size == %s\n" +
                    "Map name   == '%s'\n" +
                    "Build date == '%s'\n" +
                    "Index magic  == %s   Map magic == %s\n" +
                    "Index offset == %s   Tag count == %s\n" +
                    "Index header offset  == %s   Metadata length == %s\n" +
                    "Vertex object count  == %s   Model data offset == %s\n" +
                    "Indices object count == %s   Indices offset == %s"
                    ) %
                (self.engine, header.map_type.enum_name, comp_size,
                 header.map_name,
                 header.build_date,
                 self.index_magic, self.map_magic,
                 index.tag_index_offset, index.tag_count,
                 header.tag_index_header_offset, header.tag_index_meta_len,
                 index.vertex_object_count, index.model_raw_data_offset,
                 index.indices_object_count, index.indices_offset,
                 ))
            except Exception:
                string = ""
                print(format_exc())
        try:
            self.map_info_text.config(state='normal')
            self.map_info_text.delete('1.0', 'end')
            self.map_info_text.insert('end', string)
        finally:
            self.map_info_text.config(state='disabled')

    def is_indexed(self, tag_index_ref):
        if self.engine in ("pc", "pcdemo"):
            return tag_index_ref.class_1.enum_name in ("bitmap", "sound")
        return bool(tag_index_ref.indexed)

    def deprotect_names(self, e=None):
        if not self._map_loaded:
            return
        elif self.running:
            return

        print("Deprotecting tag names...")
        self.update()
        start = time()
        self.stop_processing = False
        self._running = True

        tag_index = self.tag_index.tag_index
        print("    Running basic deprotection...")
        i = 0
        for b in tag_index:
            if self.stop_processing:
                print("Deprotection stopped by user.")
                self._running = False
                return
            if is_protected(b.tag.tag_path):
                b.tag.tag_path = "protected_%s" % i
                i += 1

        if self.use_resource_names.get():
            print("    Detecting resource tags...")
            i = 0
            for b in tag_index:
                if self.stop_processing:
                    print("Deprotection stopped by user.")
                    self._running = False
                    return
                if not self.is_indexed(b):
                    continue
                try:
                    cls_fcc = tag_cls_int_to_fcc[b.class_1.data]
                    b.tag.tag_path = resource_names[cls_fcc][b.meta_offset]
                except (IndexError, KeyError):
                    try:
                        curr_path = b.tag.tag_path
                        if is_protected(curr_path):
                            b.tag.tag_path = "indexed_protected_%s" % i
                            i += 1
                    except Exception:
                        print(format_exc())

        self._running = False
        print("Completed. Took %s seconds." % (time()-start))
        self.reload_map_explorer()

    def begin_extraction(self, e=None):
        if not self._map_loaded:
            return
        elif self.running:
            return

        self._running = True
        out_dir = self.out_dir.get()
        handler = self.handler

        tag_index = self.tag_index
        base_tag_magic = tag_index.base_tag_magic
        tag_index = tag_index.tag_index
        start = time()
        self.stop_processing = False

        for i in range(len(tag_index)):
            try:
                tag_path = "could not get tag path"
                if self.stop_processing:
                    print("Extraction stopped by user.")
                    self._running = False
                    return
                tag_index_ref = tag_index[i]
                if self.is_indexed(tag_index_ref):
                    continue

                tag_cls = tag_cls_int_to_fcc[tag_index_ref.class_1.data]
                tag_ext = tag_cls_int_to_ext.get(
                    tag_index_ref.class_1.data, "INVALID")
                tag_path = "%s.%s" % (tag_index_ref.tag.tag_path, tag_ext)
                if is_protected(tag_path):
                    print(("Protected tags detected.\n    %s\n    " +
                           "You must run at least basic deprotection " +
                           "before extracting tags.") % tag_path)
                    self._running = False
                    return
                abs_tag_path = join(out_dir, tag_path)

                meta = self.get_meta(i + base_tag_magic)
                if not meta:
                    continue

                meta = self.meta_to_tag_data(meta, tag_cls, tag_index_ref)
                if not meta:
                    continue

                print(tag_path)
                self.update()

                if not exists(dirname(abs_tag_path)):
                    makedirs(dirname(abs_tag_path))

                FieldType.force_big()
                with open(abs_tag_path, "wb") as f:
                    f.write(self.tag_headers[tag_cls])
                    f.write(meta.serialize(calc_pointers=False))
            except Exception:
                print(format_exc())
                print("Error ocurred while extracting '%s'" % tag_path)
                
            FieldType.force_normal()

        self._running = False
        print("Extraction complete. Took %s seconds." % (time()-start))

    def get_meta(self, tag_id):
        '''
        Takes a tag reference id as the sole argument.
        Returns that tags meta data as a parsed block.
        '''
        tag_index = self.tag_index
        map_data = self.map_data
        magic = self.map_magic

        if tag_id > 0xFFFF:
            tag_id = (tag_id - tag_index.base_tag_magic) & 0xFFFF

        if tag_id == 0 and self.scnr_meta is not None:
            return self.scnr_meta

        tag_index_ref = tag_index.tag_index[tag_id]

        tag_cls = tag_cls_int_to_fcc.get(tag_index_ref.class_1.data)
        if tag_cls is None:
            return
        elif tag_index_ref.meta_offset == 0 or tag_index_ref.indexed:
            return
        elif tag_cls == "sbsp":
            return

        FieldType.force_little()

        # read the meta data from the map
        if self.handler.defs.get(tag_cls) is None:
            return

        h_desc = self.handler.defs[tag_cls].descriptor[1]
        
        h_block = [None]
        h_desc['TYPE'].parser(
            h_desc, parent=h_block, attr_index=0, magic=magic,
            tag_index=tag_index, rawdata=map_data,
            offset=tag_index_ref.meta_offset - magic)

        FieldType.force_normal()
        return h_block[0]

    def meta_to_tag_data(self, meta, tag_cls, tag_index_ref):
        tag_index = self.tag_index
        magic = self.map_magic
        base_tag_magic = tag_index.base_tag_magic
        engine = self.engine

        map_data = self.map_data
        bitmap_data = self.bitmap_data
        sound_data = self.sound_data
        loc_data = self.loc_data
        tag_index = tag_index.tag_index

        # need to treat all a8r8g8b8 values in each tag as a UInt32
        # so it can be byteswapped when going from meta to tag
        if tag_cls == "antr":
            # byteswap animation data
            anims = meta.animations.STEPTREE

            for anim in anims:
                frame_info   = anim.frame_info.STEPTREE
                default_data = anim.default_data.STEPTREE
                frame_data   = anim.frame_data.STEPTREE

                frame_count = anim.frame_count
                node_count  = anim.node_count
                uncomp_size = anim.frame_size * frame_count
                trans_flags = anim.trans_flags0 + (anim.trans_flags1<<32)
                rot_flags   = anim.rot_flags0   + (anim.rot_flags1<<32)
                scale_flags = anim.scale_flags0 + (anim.scale_flags1<<32)

                default_data_size = 0
                for n in range(node_count):
                    if not rot_flags & (1<<n):
                        default_data_size += 8
                    if not trans_flags & (1<<n):
                        default_data_size += 12
                    if not scale_flags & (1<<n):
                        default_data_size += 4

                new_frame_info   = bytearray(len(frame_info))
                new_default_data = bytearray(default_data_size)
                new_frame_data   = bytearray(uncomp_size)

                # byteswap the frame info
                for i in range(0, len(frame_info), 4):
                    new_frame_info[i] = frame_info[i+3]
                    new_frame_info[i+1] = frame_info[i+2]
                    new_frame_info[i+2] = frame_info[i+1]
                    new_frame_info[i+3] = frame_info[i]

                if anim.flags.compressed_data:
                    anim.offset_to_compressed_data = uncomp_size
                    new_frame_data += frame_data
                else:
                    i = 0
                    swap = new_default_data
                    raw = default_data
                    # byteswap the default_data
                    for n in range(node_count):
                        if not rot_flags & (1<<n):
                            for j in range(0, 8, 2):
                                swap[i] = raw[i+1]; swap[i+1] = raw[i]
                                i += 2

                        if not trans_flags & (1<<n):
                            for j in range(0, 12, 4):
                                swap[i] = raw[i+3];   swap[i+1] = raw[i+2]
                                swap[i+2] = raw[i+1]; swap[i+3] = raw[i]
                                i += 4

                        if not scale_flags & (1<<n):
                            swap[i] = raw[i+3]; swap[i+1] = raw[i+2]
                            swap[i+2] = raw[i+1]; swap[i+3] = raw[i]
                            i += 4

                    i = 0
                    swap = new_frame_data
                    raw = frame_data
                    # byteswap the frame_data
                    for f in range(frame_count):
                        for n in range(node_count):
                            if rot_flags & (1<<n):
                                for j in range(0, 8, 2):
                                    swap[i] = raw[i+1]; swap[i+1] = raw[i]
                                    i += 2

                            if trans_flags & (1<<n):
                                for j in range(0, 12, 4):
                                    swap[i] = raw[i+3];   swap[i+1] = raw[i+2]
                                    swap[i+2] = raw[i+1]; swap[i+3] = raw[i]
                                    i += 4

                            if scale_flags & (1<<n):
                                swap[i] = raw[i+3]; swap[i+1] = raw[i+2]
                                swap[i+2] = raw[i+1]; swap[i+3] = raw[i]
                                i += 4

                anim.frame_info.STEPTREE   = new_frame_info
                anim.default_data.STEPTREE = new_default_data
                anim.frame_data.STEPTREE   = new_frame_data

        elif tag_cls == "bitm":
            # grab bitmap data correctly from map and set the
            # size of the compressed plate data to nothing

            new_pixels = BytearrayBuffer()
            meta.compressed_color_plate_data.STEPTREE = BytearrayBuffer()
            if bitmap_data is None:
                return

            if engine == "ce" and not tag_index_ref.indexed:
                bitmap_data = map_data

            # uncheck the prefer_low_detail flag, get the pixel data
            # from the map, and set up the pixels_offset correctly. 
            for bitmap in meta.bitmaps.STEPTREE:
                bitmap.flags.xbox_bitmap = False
                new_pixels_offset = len(new_pixels)

                # grab the bitmap data from this map(no magic used)
                bitmap_data.seek(bitmap.pixels_offset)
                new_pixels += bitmap_data.read(bitmap.pixels_meta_size)

                bitmap.pixels_offset = new_pixels_offset

            meta.processed_pixel_data.STEPTREE = new_pixels
        elif tag_cls in ("mode", "mod2"):
            # grab vertices and indices correctly from the map
            return None
        elif tag_cls == "scnr":
            # need to remove the references to the child scenarios
            del meta.child_scenarios.STEPTREE[:]
        elif tag_cls == "hudg":
            # need to remove the references to the carnage report bitmap
            # and checkpoint bitmap if they aren't valid bitmaps
            for b in (meta.carnage_report_bitmap,
                      meta.misc_hud_crap.checkpoint):
                if b.id == 0xFFFFFFFF:
                    continue
                tag_id = (b.id - base_tag_magic) & 0xFFFF
                try:
                    index_cls = tag_index[tag_id].class_1.data
                except Exception:
                    index_cls = None
                # if the tag classes are wrong, the reference is invalid
                if b.tag_class.data != index_cls:
                    b.id = 0xFFFFFFFF
                    b.filepath = ""
        elif tag_cls == "scnr":
            # set the bsp pointers and stuff to 0
            for b in meta.structure_bsps.STEPTREE:
                b.bsp_meta_pointer = b.bsp_meta_size = b.unknown = 0
        elif tag_cls == "snd!":
            # might need to get samples and permutations from the resource map
            if engine == "ce" and not tag_index_ref.indexed:
                sound_data = map_data
            pass

        return meta

    def cancel_extraction(self, e=None):
        if not self._map_loaded:
            return
        self.stop_processing = True

    def reload_map_explorer(self):
        if not self._map_loaded:
            return

        self.hierarchy_frame.reload(self.tag_index)

    def apply_style(self):
        self.config(bg=self.default_bg_color)
        # pane style
        self.panes.config(bd=self.frame_depth, bg=self.frame_bg_color)
        self.map_info_text.config(fg=self.text_disabled_color,
                                  bg=self.entry_disabled_color)

        # frame styles
        for w in (self.map_select_frame, self.map_action_frame,
                  self.hierarchy_frame, self.add_del_frame):
            w.config(bg=self.default_bg_color)

        # label frame styles
        for w in (self.map_frame, self.out_dir_frame, self.deprotect_frame,
                  self.explorer_frame, self.queue_frame):
            w.config(fg=self.text_normal_color, bg=self.default_bg_color)

        # button styles
        for w in (self.use_resource_names_checkbutton,
                  self.use_hashcaches_checkbutton,
                  self.use_heuristics_checkbutton,
                  self.add_button, self.del_button,
                  self.add_all_button, self.del_all_button,
                  self.deprotect_button, self.begin_button, self.cancel_button,
                  self.map_path_browse_button, self.out_dir_browse_button):
            w.config(bg=self.button_color, activebackground=self.button_color,
                     fg=self.text_normal_color, bd=self.button_depth,
                     disabledforeground=self.text_disabled_color)

        # entry styles
        for w in (self.map_path_entry, self.out_dir_entry):
            w.config(bd=self.entry_depth,
                bg=self.entry_normal_color, fg=self.text_normal_color,
                disabledbackground=self.entry_disabled_color,
                disabledforeground=self.text_disabled_color,
                selectbackground=self.entry_highlighted_color,
                selectforeground=self.text_highlighted_color)

        self.hierarchy_frame.apply_style()

    def map_path_browse(self):
        if self.running:
            return
        fp = askopenfilename(
            initialdir=self.app_root.last_load_dir,
            title="Select map to load", parent=self,
            filetypes=(("Halo mapfile", "*.map"),
                       ("Halo mapfile(extra sauce)", "*.yelo"),
                       ("All", "*")))

        if not fp:
            return

        fp = sanitize_path(fp)
        self.app_root.last_load_dir = dirname(fp)
        self.map_path.set(fp)
        self.unload_maps()
        self.load_map()

    def out_dir_browse(self):
        if self.running:
            return
        dirpath = askdirectory(initialdir=self.out_dir.get(), parent=self,
                               title="Select the extraction directory")

        if not dirpath:
            return

        dirpath = sanitize_path(dirpath)
        if not dirpath.endswith(PATHDIV):
            dirpath += PATHDIV

        self.out_dir.set(dirpath)


class ExplorerHierarchyFrame(HierarchyFrame):
    map_magic = None
    tag_index = None

    def __init__(self, *args, **kwargs):
        HierarchyFrame.__init__(self, *args, **kwargs)

    def reload(self, tag_index=None):
        self.tag_index = tag_index
        tags_tree = self.tags_tree
        if not tags_tree['columns']:
            # dont want to do this more than once
            tags_tree['columns'] = ('class1', 'class2', 'class3',
                                    'magic', 'pointer', )
            tags_tree.heading("#0", text='')
            tags_tree.heading("class1", text='class 1')
            tags_tree.heading("class2", text='class 2')
            tags_tree.heading("class3", text='class 3')
            tags_tree.heading("magic", text='magic')
            tags_tree.heading("pointer", text='pointer')

            tags_tree.column("#0", minwidth=100, width=100)
            tags_tree.column("class1", minwidth=5, width=50, stretch=False)
            tags_tree.column("class2", minwidth=5, width=50, stretch=False)
            tags_tree.column("class3", minwidth=5, width=50, stretch=False)
            tags_tree.column("magic", minwidth=5, width=80, stretch=False)
            tags_tree.column("pointer", minwidth=5, width=80, stretch=False)

        if tag_index:
            # remove any currently existing children
            for child in tags_tree.get_children():
                tags_tree.delete(child)

            # generate the hierarchy
            self.generate_subitems()

    def generate_subitems(self, dir_name='', hierarchy=None):
        tags_tree = self.tags_tree

        if hierarchy is None:
            hierarchy = self.get_hierarchy_map()

        dirs, files = hierarchy
        if dir_name:        
            prefix = dir_name + "\\"

        for subdir_name in sorted(dirs):
            abs_dir_name = dir_name + subdir_name

            # add the directory to the treeview
            self.tags_tree.insert(
                dir_name, 'end', iid=abs_dir_name, text=subdir_name)

            # generate the subitems for this directory
            self.generate_subitems(abs_dir_name, dirs[subdir_name])

        map_magic = self.map_magic
        base_magic = self.tag_index.base_tag_magic

        for filename in sorted(files):
            # add the file to the treeview
            b = files[filename]
            if b.indexed:
                pointer = "not in map"
            else:
                pointer = b.meta_offset-map_magic

            self.tags_tree.insert(
                dir_name, 'end', iid=(b.id-base_magic)&0xFFFF, text=filename,
                values=(tag_cls_int_to_fcc.get(b.class_1.data, ''),
                        tag_cls_int_to_fcc.get(b.class_2.data, ''),
                        tag_cls_int_to_fcc.get(b.class_3.data, ''),
                        b.meta_offset, pointer, b))

    def get_hierarchy_map(self):
        # the keys are the names of the directories and files.
        # the values for the files are that tags index block, whereas
        # the values for the directories are a hierarchy of that folder.

        # the keys will always be lowercased to make things less complicated
        dirs = {}
        files = {}

        # loop over each tag in the index and add it to the hierarchy map
        for b in self.tag_index.tag_index:
            tagpath = b.tag.tag_path.replace("/", "\\").lower()
            if is_protected(tagpath):
                tagpath = "protected"
            
            # make sure the tagpath has only valid path characters in it
            self._add_to_hierarchy_map(dirs, files, tagpath.split("\\"), b)

        return dirs, files

    def _add_to_hierarchy_map(self, dirs, files, tagpath, tagblock):
        this_name = tagpath[0]
        if len(tagpath) == 1:
            i = 1
            try:
                ext = "." + tag_cls_int_to_ext[tagblock.class_1.data]
            except Exception:
                ext = ".INVALID"

            this_unique_name = this_name + ext
            # in case certain tags end up having the same name
            while this_unique_name in files:
                this_unique_name = "%s_%s%s" % (this_name, i, ext)
                i += 1

            files[this_unique_name] = tagblock
        else:
            # get the dirs dict for this folder, making one if necessary
            dirs[this_name] = sub_dirs, sub_files = dirs.get(this_name, ({},{}))

            self._add_to_hierarchy_map(sub_dirs, sub_files,
                                       tagpath[1:], tagblock)

    open_selected = close_selected = activate_item = no_op

    set_root_dir = add_root_dir = insert_root_dir = del_root_dir = no_op

    destroy_subitems = no_op

    get_item_tags_dir = highlight_tags_dir = no_op
