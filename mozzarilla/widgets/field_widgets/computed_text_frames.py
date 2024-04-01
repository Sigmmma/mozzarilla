#
# This file is part of Mozzarilla.
#
# For authors and copyright check AUTHORS.TXT
#
# Mozzarilla is free software under the GNU General Public License v3.0.
# See LICENSE for more information.
#

import reclaimer
import tkinter as tk

from reclaimer.strings.strings_decompilation import parse_hmt_message

from binilla.widgets.field_widgets.computed_text_frame import ComputedTextFrame


class HaloScriptTextFrame(ComputedTextFrame):
    syntax  = None
    strings = None

    def get_text(self):
        if self.parent is None:
            return ""

        if None in (self.strings, self.syntax):
            tag_data = self.parent.parent.parent.parent
            self.syntax  = reclaimer.halo_script.hsc.get_hsc_data_block(
                tag_data.script_syntax_data.data)
            self.strings = tag_data.script_string_data.data.decode("latin-1")

        if None in (self.strings, self.syntax):
            return

        # figure out the engine so we can decompile the script data correctly.
        # NOTE: refinery sets the tag window engine when it displays it.
        #       we default to what the tag itself says though.
        tag     = getattr(self.tag_window, "tag", None)
        engine  = (getattr(tag, "engine", None) or
                   getattr(self.tag_window, "engine", None))
        kw      = dict(engine=engine) if engine else dict()

        typ = "global" if "global" in self.f_widget_parent.node.NAME else "script"

        tag_data = self.parent.parent.parent.parent
        script_strings_by_type = ()
        try:
            if self.tag_window.use_scenario_names_for_script_names:
                script_strings_by_type = reclaimer.halo_script.hsc.\
                    get_scenario_script_object_type_strings(tag_data, **kw)
        except Exception:
            pass

        new_text = reclaimer.halo_script.hsc.hsc_bytecode_to_string(
            self.syntax, self.strings, self.f_widget_parent.attr_index,
            tag_data.scripts.STEPTREE, tag_data.globals.STEPTREE, typ,
            hsc_node_strings_by_type=script_strings_by_type,
            )
        return new_text


class HaloHudMessageTextFrame(ComputedTextFrame):
    def get_text(self):
        if self.parent is None:
            return ""

        tag_data = self.parent.parent.parent.parent
        message_index = self.parent.parent.index(self.parent)
        return parse_hmt_message(tag_data, message_index)[0]
