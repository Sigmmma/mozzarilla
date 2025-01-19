#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import tkinter as tk
import tkinter.ttk as ttk
import weakref

from traceback import format_exc

from array import array

from binilla.widgets.scroll_menu import ScrollMenu
from binilla.widgets.field_widgets import ContainerFrame
from reclaimer.sounds import constants as const, playback,\
    sound_decompilation as sound_decomp
from supyr_struct.tag import Tag as SupyrTag


class SoundPlayerMixin():
    sound_player = None
    permutation_index = -1
    pitch_range_index = -1
    big_endian_pcm    = True

    def __init__(self):
        self.sound_player = playback.SoundTagPlayer()

    def update_player(self):
        # if parent isn't able to be traversed, use the node
        sound_data = self.parent or self.node
        if hasattr(sound_data, "get_root"):
            sound_data = sound_data.get_root()

        # handle cases where the root is a tag, the root is the data of
        # a tag, or the root is just the body of a tag(no blam_header).
        if isinstance(sound_data, SupyrTag):
            sound_data = sound_data.data
            if hasattr(sound_data, "tagdata"):
                sound_data = sound_data.tagdata

        if not hasattr(sound_data, "pitch_ranges"):
            sound_data             = None
            self.permutation_index = -1
            self.pitch_range_index = -1

        self.sound_player.sound_data        = sound_data
        self.sound_player.permutation_index = self.permutation_index
        self.sound_player.pitch_range_index = self.pitch_range_index
        self.sound_player.big_endian_pcm    = self.big_endian_pcm
    
    def playback_action(self, action):
        self.update_player() # ensure it's always up-to-date
        if action == "stop":
            self.sound_player.stop_sound()
        elif action == "stop_all":
            self.sound_player.stop_all_sounds()
        elif not const.PLAYBACK_AVAILABLE:
            print("Audio playback unavailable.")
        elif action == "play":
            self.sound_player.play_sound()


class SoundPlayerFrame(ContainerFrame, SoundPlayerMixin):
    sound_frame  = None

    def __init__(self, *args, **kwargs):
        SoundPlayerMixin.__init__(self)
        self.sound_player.separate_wave_queues = False
        ContainerFrame.__init__(self, *args, **kwargs)

    @property
    def big_endian_pcm(self):
        # metadata pcm audio is little endian. we can detect 
        # this based on whether or not the engine property 
        # exists that Refinery's MetaWindow should have.
        return not hasattr(getattr(self, "tag_window", None), "engine")
    
    def destroy(self):
        try:
            self.playback_action("stop_all")
        except Exception:
            pass

        super().destroy()

    def update_player(self):
        super().update_player()
        try:
            pr = self.sound_player.get_pitch_range()
            self.actual_perm_count = pr.actual_permutation_count
        except (ValueError, AttributeError):
            self.actual_perm_count = 0

    @property
    def pitch_range_index(self):
        return self._pitch_range_index.get()
    @pitch_range_index.setter
    def pitch_range_index(self, new_val):
        self._pitch_range_index.set(new_val)

    @property
    def permutation_index(self):
        return self._permutation_index.get()
    @permutation_index.setter
    def permutation_index(self, new_val):
        self._permutation_index.set(new_val)

    def update_pitch_range_options(self, e=None):
        self.update_player()
        self.pitch_ranges_menu.set_options(
            self.generate_pitch_range_options()
            )

    def update_permutation_options(self, e=None):
        self.update_player()
        self.permutations_menu.set_options(
            self.generate_permutation_options()
            )

    def populate(self):
        self.create_sound_frame()
        super().populate()

    def create_sound_frame(self):
        self._pitch_range_index = tk.IntVar(self, 0)
        self._permutation_index = tk.IntVar(self, 0)

        if self.sound_frame is not None:
            return

        self.sound_frame = tk.Frame(
            self, relief='raised', bd=self.frame_depth
            )
        self.sound_row0_frame = tk.Frame(
            self.sound_frame, relief='flat', bg=self.frame_bg_color
            )
        self.sound_row1_frame = tk.Frame(
            self.sound_frame, relief='flat', bg=self.frame_bg_color
            )
        self.sound_row2_frame = tk.Frame(
            self.sound_frame, relief='flat', bg=self.frame_bg_color
            )
        self.sound_playback_label = tk.Label(
            self.sound_row0_frame, text="Sound playback",
            width=self.title_size, anchor='w', justify='left', 
            disabledforeground=self.text_disabled_color,
            font=self.get_font("frame_title"),
            )
        self.sound_playback_label.font_type = "frame_title"

        self.pitch_range_menu_label = tk.Label(
            self.sound_row1_frame, text="pitch range",
            width=self.title_size, anchor='w', justify='left', 
            disabledforeground=self.text_disabled_color
            )
        self.permutation_menu_label = tk.Label(
            self.sound_row2_frame, text="permutation",
            width=self.title_size, anchor='w', justify='left', 
            disabledforeground=self.text_disabled_color
            )
        self.pitch_ranges_menu = ScrollMenu(
            self.sound_row1_frame, f_widget_parent=self,
            variable=self._pitch_range_index, options_volatile=True,
            menu_width=35, option_getter=self.generate_pitch_range_options,
            callback=self.update_permutation_options
            )
        self.permutations_menu = ScrollMenu(
            self.sound_row2_frame, f_widget_parent=self,
            variable=self._permutation_index, options_volatile=True,
            menu_width=35, option_getter=self.generate_permutation_options,
            )

        self.play_sound_btn = ttk.Button(
            self.sound_row0_frame, width=8, text='Play',
            command=(lambda e=None: self.playback_action("play"))
            )
        self.stop_sound_btn = ttk.Button(
            self.sound_row0_frame, width=8, text='Stop',
            command=(lambda e=None: self.playback_action("stop"))
            )
        self.stop_all_sounds_btn = ttk.Button(
            self.sound_row0_frame, width=8, text='Stop all',
            command=(lambda e=None: self.playback_action("stop_all"))
            )

        self.update_pitch_range_options()
        self.update_permutation_options()

    def apply_style(self, seen=None):
        super().apply_style(seen)
        self.sound_frame.config(bd=self.frame_depth)
        for w in (
                self.sound_frame,
                self.sound_row0_frame, self.sound_playback_label,
                self.sound_row1_frame, self.pitch_range_menu_label,
                self.sound_row2_frame, self.permutation_menu_label,
                ):
            w.config(bg=self.frame_bg_color)

    def pose_fields(self):
        # pack these first so they appear at the top
        self.sound_frame.pack(fill="x", expand=True, padx=0, pady=(0, 5))
        for w in (
                self.sound_row0_frame, self.sound_row1_frame, 
                self.sound_row2_frame
                ):
            w.pack(fill="x", expand=True, padx=0, pady=2)

        for w in (self.pitch_range_menu_label, self.pitch_ranges_menu,
                  self.permutation_menu_label, self.permutations_menu):
            w.pack(side='left', padx=0, pady=2)

        self.sound_playback_label.pack(side="left", padx=(30, 0), pady=0)
        for w in (
                self.play_sound_btn, self.stop_sound_btn, 
                # this isn't really needed since we're managing all sounds
                # being played in the same play_objects dict for queueing.
                # self.stop_all_sounds_btn,
                ):
            w.pack(side="left", padx=(4, 0), pady=2)

        super().pose_fields()

    def generate_pitch_range_options(self, opt_index=None):
        prs = self.sound_player.pitch_ranges
        if opt_index is None:
            self.pitch_ranges_menu.max_index = len(prs) - 1
            if not prs:
                self.pitch_range_index = -1

            return {
                i: "%s: %s" % (i, pr.name) 
                for i, pr in prs.items()
                }
        elif opt_index in range(len(prs)):
            return "%s: %s" % (opt_index, prs[opt_index].name)

    def generate_permutation_options(self, opt_index=None):
        perms = self.sound_player.permutations
        if opt_index is None:
            self.permutations_menu.max_index = min(
                self.actual_perm_count, len(perms)
                ) - 1
            if not perms:
                self.permutation_index = -1

            return {
                i: "%s. %s" % (i, perm.name) 
                for i, perm in perms.items()
                if i < self.actual_perm_count
                }
        elif opt_index in range(len(perms)):
            return "%s. %s" % (opt_index, perms[opt_index].name)